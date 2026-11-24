"""
The search pipeline (spec §44).

    criteria → queries → provider → normalize → dedup URLs → candidate discovery
            → extraction → signal detection → scoring → lead dedup → storage

Every arrow is real code here, and most of them are real services now: with
`BRAVE_SEARCH_API_KEY` set, `→ provider` is the live web (Phase 4), and with
`SCRAPEGRAPH_API_KEY` set, `→ extraction` opens the pages it found and reads them
(Phase 5). Judging what was read is Phase 6. Which adapter is behind each stage is
`services/adapters.py`'s business, not this file's. Storage is PostgreSQL.

Two properties matter more than the stub data:

* progress is written by the worker as it happens, so `GET /searches/:id` reports
  measured counters instead of a client-side animation (spec §43);
* concurrency is bounded per stage by configuration, never unlimited (§35, §52).
"""

import asyncio
import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import zip_longest
from typing import Protocol
from urllib.parse import unquote, urlparse

from app.core.config import Settings
from app.core.logging import bind, get_logger
from app.core.retry import retry_async
from app.db.repository import Repository
from app.models.common import (
    HIGH_QUALITY_THRESHOLD,
    SearchStage,
    SearchStatus,
    SignalType,
)
from app.models.lead import Lead, LeadSignal, ScoreComponent
from app.models.profile import ExtractedProfile
from app.models.rejection import (
    ANY_REQUIREMENT,
    MissingSignal,
    RejectedCandidate,
    RejectionReason,
)
from app.models.search import GeneratedQuery, Search, SearchProgress, SearchUsage
from app.models.source import DiscoveredUrl, LeadSourceKind, ProviderResult, UrlKind
from app.services.extraction import personhood
from app.services.extraction.posts import with_posts
from app.services.extraction.signal_detector import (
    Judgement,
    SignalDetector,
    assess_many,
    placed_by_judge,
)
from app.services.scoring.scoring_service import ScoringService
from app.services.scraping.base import (
    ProfileExtractor,
    bills_for,
    budget_of,
    cost_of,
    fetch_from,
)
from app.services.scraping.snippet_extractor import SnippetProfileExtractor
from app.services.search.deduplicator import deduplicate
from app.services.search.eligibility import Refusal, admit, country_param, place_param
from app.services.search.estimate import judging_budget_for, page_budget_for
from app.services.search.markets import country_code, iso_code
from app.services.search.prospects import Prospect, rank
from app.services.search.providers.base import SearchMarket, SearchProvider
from app.services.search.query_generator import QueryGenerator, is_network_marketing
from app.services.search.url_tools import (
    SOCIAL_PLATFORMS,
    allowed_platforms,
    attach_posts,
    author_profile,
    candidates,
    canonicalize,
    discover,
    needs_opening,
    promote_posts,
)

log = get_logger(__name__)

#: Extractors that never open a page. A profile one of these produced was judged
#: on the search result alone, which is what `RejectedCandidate.read` records.
SNIPPET_ONLY = {"snippet"}

#: How far a free read may run ahead of the best paid candidate still waiting for a
#: budget slot, in multiples of EXTRACTION_CONCURRENCY. Wide enough that the
#: browser is not idle while ScrapeGraphAI takes a minute over a LinkedIn page;
#: narrow enough that "best first" — and the judging budget — still mean something.
LOOKAHEAD_WIDTHS = 2

#: How long a read profile waits for others to share a judging call with. A batch
#: shares the instructions and requirements, which is most of a call's tokens; a
#: lead left waiting behind a slow page is a lead the target check cannot see.
JUDGE_AFTER_SECONDS = 2.0

#: How many authorless posts one run may open to learn who published them. Each is
#: a free browser read of about a second; the cap keeps a hashtag-heavy run from
#: spending minutes on posts before it reads a single profile.
MAX_POSTS_OPENED = 40

#: How often reading writes the progress record. Reads now finish one at a time,
#: and a database write per page would be most of the work for the cached ones.
SAVE_EVERY_SECONDS = 1.0

#: Why an address is not somebody's profile, per classification. Written out
#: rather than counted, because the client reads this list to check whether a
#: refusal was right — and "irrelevant" on its own is not checkable.
WHY_NOT_A_PROFILE: dict[UrlKind, str] = {
    UrlKind.COMPANY: "A company or school page, not a person.",
    UrlKind.ARTICLE: "A post or an article, not somebody's profile.",
    UrlKind.PRODUCT: "A shop page.",
    UrlKind.IRRELEVANT: "Nothing here relates to the search.",
    UrlKind.UNKNOWN: (
        "Not the shape of a profile address on this platform — a login form, a "
        "photo, a directory page or a numeric page id."
    ),
}

#: Where each stage ends on the 0–1 progress bar. Mirrors the Phase 1 timeline so
#: the meter feels the same before and after the backend took over.
STAGE_BOUNDS: dict[SearchStage, tuple[float, float]] = {
    SearchStage.GENERATING_QUERIES: (0.00, 0.12),
    SearchStage.WEB_SEARCH: (0.12, 0.34),
    SearchStage.DISCOVERING_PROFILES: (0.34, 0.50),
    SearchStage.EXTRACTING: (0.50, 0.78),
    SearchStage.SCORING: (0.78, 0.92),
    SearchStage.DEDUPLICATING: (0.92, 1.00),
}

STAGE_STATUS: dict[SearchStage, SearchStatus] = {
    SearchStage.GENERATING_QUERIES: SearchStatus.SEARCHING,
    SearchStage.WEB_SEARCH: SearchStatus.SEARCHING,
    SearchStage.DISCOVERING_PROFILES: SearchStatus.SEARCHING,
    SearchStage.EXTRACTING: SearchStatus.EXTRACTING,
    SearchStage.SCORING: SearchStatus.SCORING,
    SearchStage.DEDUPLICATING: SearchStatus.SCORING,
}


class SearchCancelled(Exception):
    """Raised internally when a cancel request is noticed at a checkpoint."""


class PostReader(Protocol):
    """Fills in a post's author — and its date and caption — by opening it."""

    async def read_post(self, url: DiscoveredUrl) -> DiscoveredUrl | None: ...


@dataclass
class Harvest:
    """
    What reading the candidates produced, carried between the two stages that now
    share the work.

    Reading and judging used to be strictly sequential: read all the pages, then
    judge all the profiles. A lead target makes that impossible — the only thing
    that can tell a search to stop paying is a judged lead — so judging moved into
    the reading loop, and this is the state the two stages pass between them.
    """

    profiles: list[ExtractedProfile] = field(default_factory=list)
    leads: list[Lead] = field(default_factory=list)
    #: Canonical URLs already judged, so nothing is judged (or billed) twice.
    judged_urls: set[str] = field(default_factory=set)
    #: How many candidates each requirement turned away. A search that admits two
    #: of forty owes the client this breakdown (spec §43).
    refusals: Counter[Refusal] = field(default_factory=Counter)
    #: What each candidate's search result alone supported, by canonical URL. Kept
    #: so a refusal recorded at judging can still say how promising the run had
    #: rated it — the highest-rated refusals are the ones worth re-reading.
    promise: dict[str, int] = field(default_factory=dict)
    #: True when the lead target was reached and the remaining candidates were left
    #: unread. Reported, never hidden: a thin result must be explained by the limit.
    stopped_early: bool = False


class SearchPipeline:
    def __init__(
        self,
        *,
        repository: Repository,
        settings: Settings,
        query_generator: QueryGenerator,
        provider: SearchProvider,
        extractor: ProfileExtractor,
        detector: SignalDetector,
        scoring: ScoringService,
        post_reader: PostReader | None = None,
    ) -> None:
        self.repo = repository
        self.settings = settings
        self.query_generator = query_generator
        self.provider = provider
        self.extractor = extractor
        self.detector = detector
        self.scoring = scoring
        #: Opens a post that names its author nowhere else (`url_tools.needs_opening`).
        #: Our own browser, so free; absent when the browser is switched off.
        self.post_reader = post_reader
        # Ranking reads no pages: it judges candidates by the search result the
        # provider already returned, which is exactly what this extractor does.
        self._snippets = SnippetProfileExtractor()
        self._progress = SearchProgress()
        self._usage = SearchUsage()
        #: Every candidate this run turned away, by rejection id. A dict rather
        #: than a list because one address is one verdict: whichever stage refuses
        #: it first is the one that owns the explanation.
        self._rejected: dict[str, RejectedCandidate] = {}
        #: How many leads this run was asked for; set per search by `_aim`.
        self._target = 0
        #: LLM_CONCURRENCY for the whole run (§52). Judging now overlaps reading, so
        #: several `_judge` calls can be in flight at once and must share the limit.
        self._llm_slots = asyncio.Semaphore(max(1, settings.llm_concurrency))
        #: Addresses and candidates earlier waves already dealt with. A later wave's
        #: queries find many of the same people again; they are not read twice.
        self._seen_urls: set[str] = set()
        self._seen_candidates: set[str] = set()
        #: Posts opened so far this run, against MAX_POSTS_OPENED.
        self._posts_opened = 0

    async def run(self, search_id: str) -> None:
        search = await self.repo.get_search(search_id)
        if search is None:
            log.error("pipeline_search_missing")
            return

        bind(search_id=search_id, user_id=search.user_id)
        log.info("search_started", extra={"criteria_country": search.criteria.location.country})

        self._progress = SearchProgress()
        self._usage = SearchUsage()
        self._rejected = {}
        self._seen_urls = set()
        self._seen_candidates = set()
        self._posts_opened = 0
        self._aim(search)

        try:
            planned = await self._generate_queries(search)
            harvest = Harvest()
            sent: list[GeneratedQuery] = []
            while True:
                wave = self._next_wave(planned, sent)
                sent.extend(wave)
                results = await self._run_queries(search, wave, sent)
                urls = await self._discover(search, results)
                harvest = await self._extract(search, urls, harvest)
                if not self._wants_another_wave(planned, sent, harvest):
                    break
            leads = await self._score(search, harvest)
            leads = await self._deduplicate(search, leads)
            await self._complete(search, leads)
        except SearchCancelled:
            log.info("search_cancelled")
        except asyncio.CancelledError:
            await self._mark_cancelled(search_id)
            raise
        except Exception as error:
            log.exception("search_failed")
            await self._patch(
                search_id,
                status=SearchStatus.FAILED,
                error=str(error),
                completed_at=datetime.now(UTC),
            )

    def _aim(self, search: Search) -> None:
        """
        Point this run's limits at what *this* search was asked for.

        The extractor chain is built per job with the server's default ceiling;
        the number of leads the client asked for is only known here. Both live in
        one place (`services/search/estimate.py`) so that the price quoted in the
        wizard and the budget the run is actually given cannot drift apart.
        """
        self._target = search.criteria.target_leads or self.settings.target_leads
        # The judging budget follows the leads asked for — the same figure the
        # wizard quoted (see `estimate.judging_budget_for`).
        if hasattr(self.detector, "limit"):
            self.detector.limit = judging_budget_for(search.criteria, self.settings)
        # Fetch the pages through the country being searched: a social platform
        # then serves the page a local visitor sees, which is also the version
        # that names the city the geographic filter needs (spec §33).
        fetch_from(self.extractor, iso_code(search.criteria.location.country))
        budget = budget_of(self.extractor)
        if budget is not None:
            budget.limit = page_budget_for(search.criteria, self.settings)
            log.info(
                "search_budget_set",
                extra={"pages": budget.limit or "unlimited", "target_leads": self._target},
            )

    # ------------------------------------------------------------- stage 1–2
    async def _generate_queries(self, search: Search) -> list[GeneratedQuery]:
        """
        Every query this search may send, best first. How many of them actually go
        out is decided wave by wave (`_next_wave`), so only those are saved on the
        search: a query listed with zero results would read as one that found
        nothing, when it was never asked.
        """
        await self._enter(search.id, SearchStage.GENERATING_QUERIES)
        generated = self.query_generator.generate(
            search.criteria, limit=self.settings.max_queries_per_search
        )
        queries = [
            GeneratedQuery(
                id=f"q_{index + 1}",
                query=plan.query,
                provider=self.provider.name,
                language=plan.language,
                country=plan.country,
            )
            for index, plan in enumerate(generated)
        ]
        await self._tick()
        await self._save(search.id, SearchStage.GENERATING_QUERIES, 1.0)
        log.info("queries_generated", extra={"count": len(queries)})
        return queries

    def _next_wave(
        self, planned: list[GeneratedQuery], sent: list[GeneratedQuery]
    ) -> list[GeneratedQuery]:
        """
        The next queries to send. Without a lead target there is nothing to stop
        for, so everything planned goes out at once; with one, a wave at a time —
        the next page of every query that came back full, alternated with the
        planned queries not yet sent, up to MAX_QUERIES_PER_SEARCH in all.
        """
        asked = {entry.id for entry in sent}
        remaining = [entry for entry in planned if entry.id not in asked]
        if self._target <= 0:
            return remaining
        room = min(
            max(1, self.settings.queries_per_wave),
            self.settings.max_queries_per_search - len(sent),
        )
        mixed = [
            entry
            for pair in zip_longest(self._follow_ups(sent), remaining)
            for entry in pair
            if entry is not None
        ]
        return mixed[: max(0, room)]

    def _follow_ups(self, sent: list[GeneratedQuery]) -> list[GeneratedQuery]:
        """
        The next page of each query whose last page came back (nearly) full.

        Brave answers twenty results a question, and a well-aimed question has more
        than twenty answers: `Avon konsultantka Polska` returned a full page every
        time it was asked. Its second page is twenty people nobody else's query
        reaches — a better bet than a new question that may return nothing (21 of
        a run's 48 returned nothing at all).
        """
        full = max(1, self.settings.brave_results_per_query * 3 // 4)
        asked = {(entry.query, entry.page) for entry in sent}
        follow: list[GeneratedQuery] = []
        for entry in sent:
            page = entry.page + 1
            if (
                entry.result_count < full
                or page >= self.settings.max_result_pages
                or (entry.query, page) in asked
            ):
                continue
            base = entry.id.split("_p", 1)[0]
            update = {"id": f"{base}_p{page + 1}", "page": page, "result_count": 0}
            follow.append(entry.model_copy(update=update))
        return follow

    def _wants_another_wave(
        self, planned: list[GeneratedQuery], sent: list[GeneratedQuery], harvest: Harvest
    ) -> bool:
        """
        Whether to go back to the provider: the search is still short of the leads it
        was asked for, under its query ceiling, and has something left to ask —
        a planned query, or the next page of one that came back full.

        Everything found so far has been read and judged by now (with a target,
        judging runs inside reading), so the lead count is final for these waves.
        """
        if self._target <= 0 or harvest.stopped_early:
            return False
        if len(sent) >= self.settings.max_queries_per_search:
            return False
        if not self._next_wave(planned, sent):
            return False
        leads = len(deduplicate(harvest.leads)[0])
        if leads >= self._target:
            return False
        log.info(
            "search_wave_needed",
            extra={
                "leads": leads,
                "target": self._target,
                "sent": len(sent),
                "planned": len(planned),
            },
        )
        return True

    async def _run_queries(
        self, search: Search, queries: list[GeneratedQuery], sent: list[GeneratedQuery]
    ) -> list[ProviderResult]:
        """
        Queries fan out concurrently (spec §30) under SEARCH_CONCURRENCY (§52),
        each aimed at the country the user asked for and at the index of the
        language it is written in: a Ukrainian query put to the global English
        index returns English pages *about* Ukraine, which is what the first live
        run came back with.

        One query failing is not the search failing: real providers rate-limit and
        time out, and eleven good queries are worth more than an error page. Only a
        search where *nothing* came back reports the provider's error.

        `queries` is this wave; `sent` is every query the run has sent, this wave
        included — the counters and the stored list are the run's, not the wave's.
        """
        self._progress.queries = len(sent)
        await self._enter(search.id, SearchStage.WEB_SEARCH)
        await self._save(search.id, SearchStage.WEB_SEARCH, 0.0, queries=sent)
        market = SearchMarket.from_criteria(search.criteria)
        semaphore = asyncio.Semaphore(self.settings.search_concurrency)
        collected: list[ProviderResult] = []
        done = 0
        known = len(self._seen_urls)

        async def run_one(entry: GeneratedQuery) -> None:
            nonlocal done
            aimed = market.model_copy(
                update={
                    "language": entry.language or market.language,
                    # A search over several countries aims each query at its own.
                    "country": country_code(entry.country) if entry.country else market.country,
                    "page": entry.page,
                }
            )
            async with semaphore:
                await self._tick()
                results = await retry_async(
                    lambda: self.provider.search(entry.query, market=aimed),
                    attempts=self.settings.max_retries,
                    label=f"search:{self.provider.name}",
                )
            entry.result_count = len(results)
            collected.extend(results)
            done += 1
            # One query is one billed call: the provider is capped at a single
            # request per query, so this stays exact (spec §54).
            self._usage.search_api_calls += 1
            self._progress.queries_completed += 1
            self._progress.urls_discovered = known + len(collected)
            await self._save(search.id, SearchStage.WEB_SEARCH, done / max(1, len(queries)))

        outcomes = await asyncio.gather(
            *(run_one(entry) for entry in queries), return_exceptions=True
        )
        failures = [outcome for outcome in outcomes if isinstance(outcome, BaseException)]
        for failure in failures:
            if isinstance(failure, SearchCancelled | asyncio.CancelledError):
                raise failure
        if failures and not collected:
            raise failures[0]
        if failures:
            log.warning(
                "web_search_partial",
                extra={"failed_queries": len(failures), "of": len(queries)},
            )

        await self._save(search.id, SearchStage.WEB_SEARCH, 1.0, queries=sent)
        log.info(
            "web_search_completed",
            extra={"raw_results": len(collected), "queries": len(queries), "sent": len(sent)},
        )
        return collected

    # --------------------------------------------------------------- stage 3
    async def _discover(self, search: Search, results: list[ProviderResult]) -> list[DiscoveredUrl]:
        """
        Normalize, classify, and keep only what the client asked to look at.

        The source list is enforced here as well as in the queries, because a
        `site:` operator is a request and not a guarantee: a search told to look at
        Instagram, LinkedIn and Facebook returned a legal journal's article about
        network marketing, and it became the run's only lead.

        Both refusals are also written down one by one, not just counted. They are
        the free ones — nothing here is read or paid for — and they are therefore
        the ones a client has no other way of checking: an address dropped here
        never appears anywhere else in the product.
        """
        await self._enter(search.id, SearchStage.DISCOVERING_PROFILES)
        # A hashtag search returns posts, and a post names its author: the profile
        # behind it is the candidate, not the post (`url_tools.promote_posts`).
        normalized = promote_posts(discover(results))
        # A later wave finds many of the same addresses again: only new ones count.
        normalized = [url for url in normalized if url.canonical_url not in self._seen_urls]
        self._seen_urls.update(url.canonical_url for url in normalized)
        normalized = await self._open_posts(search, normalized)
        sources = search.criteria.sources
        profile_urls = [
            url
            for url in candidates(normalized, sources)
            if url.canonical_url not in self._seen_candidates
        ]
        kept = {url.canonical_url for url in profile_urls}
        self._seen_candidates.update(kept)
        readable = candidates(normalized)
        # Not kept *this* wave can also mean an author an earlier wave already read
        # (a new post of theirs promoted them again) — that is no off-source refusal.
        off_source = [url for url in readable if url.canonical_url not in self._seen_candidates]
        self._refuse_addresses(search, normalized, readable, off_source, kept)

        self._progress.urls_discovered = len(self._seen_urls)
        self._progress.profiles_discovered += len(profile_urls)
        self._progress.rejected_off_source += len(off_source)
        await self._tick()
        await self._save(search.id, SearchStage.DISCOVERING_PROFILES, 1.0)
        log.info(
            "profiles_identified",
            extra={
                "unique_urls": len(normalized),
                "candidates": len(profile_urls),
                "rejected": len(normalized) - len(profile_urls),
                "off_source": len(off_source),
                "platforms": sorted({url.platform.value for url in profile_urls}),
            },
        )
        return profile_urls

    async def _open_posts(self, search: Search, urls: list[DiscoveredUrl]) -> list[DiscoveredUrl]:
        """
        Learn who published the posts that name nobody: `instagram.com/p/Cxyz`,
        `facebook.com/reel/…`, `facebook.com/watch/?v=…`.

        Seven of 34 refused addresses in one run were posts like that — "Czy
        marketing sieciowy to piramida finansowa?" — and every one was thrown away
        unread, while the post page names its author (and its date) in its first
        line (Facebook sends the visitor on to `{account}/videos/…`). Our browser
        opens it for nothing; the author then becomes a candidate like any other
        post's author, with the post attached as evidence.
        """
        if self.post_reader is None:
            return urls
        allowed = allowed_platforms(search.criteria.sources)
        todo = [
            url
            for url in urls
            if needs_opening(url) and (allowed is None or url.platform in allowed)
        ][: max(0, MAX_POSTS_OPENED - self._posts_opened)]
        if not todo:
            return urls
        self._posts_opened += len(todo)

        slots = asyncio.Semaphore(max(1, self.settings.extraction_concurrency))
        reader = self.post_reader

        async def open_one(url: DiscoveredUrl) -> DiscoveredUrl | None:
            async with slots:
                try:
                    return await reader.read_post(url)
                except Exception:
                    log.warning("post_open_failed", extra={"url": url.canonical_url})
                    return None

        opened = await asyncio.gather(*(open_one(url) for url in todo))
        resolved = [post for post in opened if post is not None and post.author_url]
        log.info("posts_opened", extra={"opened": len(todo), "authors": len(resolved)})
        return attach_posts(urls, resolved)

    def _refuse_addresses(
        self,
        search: Search,
        normalized: list[DiscoveredUrl],
        readable: list[DiscoveredUrl],
        off_source: list[DiscoveredUrl],
        kept: set[str],
    ) -> None:
        """Write down each address discovery threw away, with the reason in words."""
        profile_shaped = {url.canonical_url for url in readable}
        for url in normalized:
            if url.canonical_url in profile_shaped:
                continue
            author = author_profile(url)
            followed = canonicalize(author) if author and canonicalize(author) in kept else None
            detail, code, params = _why_not_a_profile(url, kept)
            self._refuse(
                search,
                url,
                RejectionReason.NOT_A_PROFILE,
                detail,
                author_url=followed,
                code=code,
                params=params,
            )
        for url in off_source:
            self._refuse(
                search,
                url,
                RejectionReason.OFF_SOURCE,
                f"Found on {url.platform.value}, which is not among this search's "
                "sources — so it was never opened and nothing was paid for it.",
                code="off_source",
                params={"platform": url.platform.value},
            )

    # --------------------------------------------------------------- stage 4
    async def _extract(
        self, search: Search, urls: list[DiscoveredUrl], harvest: Harvest | None = None
    ) -> Harvest:
        """
        Read the candidates — best first, as a stream, and only as far as the
        search's limits allow.

        * **order is a decision.** Candidates are ranked by what their search result
          alone already supports (`services/search/prospects.py`), so the page
          budget is spent on the most promising pages instead of on whichever
          coroutine started first.
        * **paid and free reads do not wait for each other.** This used to run in
          waves of EXTRACTION_CONCURRENCY, each finished before the next began — so
          one LinkedIn page taking a minute at ScrapeGraphAI held up nine Instagram
          profiles our own browser reads in two seconds. A measured run spent 4½ of
          its 6 minutes like that. Now every read starts as soon as it has a slot:
          paid reads take budget slots strictly in rank order, free ones run beside
          them, but never more than `LOOKAHEAD_WIDTHS` × EXTRACTION_CONCURRENCY
          places ahead of the best candidate still waiting — so "best first" stays
          true to within that window, and the weakest tail is what a target drops.
        * **the search result can already say "not a person".** A paid candidate
          whose name is the searched-for brand ("Farmasi Bucuresti") is refused
          before anything is spent on it (`personhood.before_reading`).
        * **judging runs alongside reading.** With `TARGET_LEADS` set, profiles are
          judged in batches as they arrive, and the search stops dispatching as soon
          as the user has the leads they asked for. Reads already in flight finish —
          a paid one is billed either way — and are judged with the rest.
        * **the budget lives lower down.** How many pages may be *read* is enforced
          by the reader itself (`services/scraping/budget.py`); the pages it refuses
          still become leads from their snippet. That is why every candidate still
          goes through the chain: a cache hit costs nothing and is worth having
          (spec §53).

        Each kind of read is bounded by EXTRACTION_CONCURRENCY (§35).

        A later wave passes in the `harvest` the earlier ones built, so the target
        is checked against every lead the run has, not this wave's alone.
        """
        await self._enter(search.id, SearchStage.EXTRACTING)
        ranked = await rank(urls, search.criteria, snippets=self._snippets, scoring=self.scoring)
        target = self._target
        harvest = harvest if harvest is not None else Harvest()
        #: Pages earlier waves processed; the progress counter is the run's.
        before = self._progress.profiles_processed
        width = max(1, self.settings.extraction_concurrency)
        window = width * LOOKAHEAD_WIDTHS
        batch = max(1, self.settings.judge_batch_size)
        budget = budget_of(self.extractor)
        clock = asyncio.get_running_loop()

        #: Dispatched, or refused before reading — either way, not waiting any more.
        decided = [False] * len(ranked)
        #: The best-ranked candidate still waiting; the window is measured from here.
        head = 0
        reads: dict[asyncio.Task[tuple[ExtractedProfile | None, bool]], tuple[Prospect, bool]] = {}
        judging: set[asyncio.Task[None]] = set()
        #: Read and admitted to judging, but not yet sent: profiles go in batches.
        waiting: list[ExtractedProfile] = []
        waiting_since = 0.0
        running = {True: 0, False: 0}  # paid / free reads in flight
        processed = 0
        saved_at = clock.time()
        stopping = False

        async def extract_one(url: DiscoveredUrl) -> tuple[ExtractedProfile | None, bool]:
            """The profile, and whether the reader failed outright getting it."""
            await self._tick()
            try:
                profile = await retry_async(
                    lambda: self.extractor.extract(url),
                    attempts=self.settings.max_retries,
                    label=f"extract:{self.extractor.name}",
                )
            except Exception:
                log.warning("extraction_failed", extra={"url": url.canonical_url})
                return None, True
            # The posts the search found by this person are evidence about them —
            # added here, after the cache, because they belong to this search.
            return (with_posts(profile, url) if profile is not None else None), False

        def paid_slot_open() -> bool:
            if running[True] >= width:
                return False
            if budget is None or budget.unlimited or budget.exhausted:
                # Past the budget a "paid" read is a cache lookup or a skip: free.
                return True
            # Every read in flight may still claim a slot, so one more is sent only
            # if all of them fit: the last credit then goes to the better-ranked page,
            # not to whichever coroutine reached the reader first.
            return running[True] < (budget.remaining or 0)

        def dispatch() -> None:
            nonlocal head, processed
            progressed = True
            while progressed:
                progressed = False
                paid_blocked = False
                for index in range(head, min(len(ranked), head + window)):
                    if decided[index]:
                        continue
                    if paid_blocked and running[False] >= width:
                        break
                    prospect = ranked[index]
                    paid = bills_for(self.extractor, prospect.url)
                    if paid and self._prescreened(search, prospect, harvest):
                        decided[index] = progressed = True
                        processed += 1
                        continue
                    if paid and (paid_blocked or not paid_slot_open()):
                        # Later paid candidates must not jump this one.
                        paid_blocked = True
                        continue
                    if not paid and running[False] >= width:
                        continue
                    decided[index] = progressed = True
                    running[paid] += 1
                    reads[asyncio.create_task(extract_one(prospect.url))] = (prospect, paid)
                while head < len(ranked) and decided[head]:
                    head += 1

        def judge_waiting() -> None:
            nonlocal waiting
            # Judged now rather than in the scoring stage, because "we have enough
            # leads" is the only thing that can stop the spending.
            profiles, waiting = waiting, []
            judging.add(asyncio.create_task(self._judge(search, profiles, harvest)))

        try:
            dispatch()
            while reads or judging:
                timeout = None
                if waiting:
                    timeout = max(0.0, waiting_since + JUDGE_AFTER_SECONDS - clock.time())
                done, _ = await asyncio.wait(
                    {*reads, *judging}, timeout=timeout, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    if task in judging:
                        judging.discard(task)
                        task.result()  # a judge that failed fails the search, as before
                        continue
                    prospect, paid = reads.pop(task)
                    running[paid] -= 1
                    # A page nobody could find a person on is the first refusal, and
                    # it happens here rather than at judging: there is nothing to judge.
                    fresh = self._sift(search, [prospect], [task.result()], harvest)
                    harvest.profiles.extend(fresh)
                    processed += 1
                    self._usage.pages_analyzed += 1
                    if target > 0 and fresh:
                        if not waiting:
                            waiting_since = clock.time()
                        waiting.extend(fresh)

                # A full batch, or one that has waited long enough for company, or the
                # last reads are in: a slow paid page must not hold judged leads back.
                if waiting and (
                    len(waiting) >= batch
                    or not reads
                    or clock.time() - waiting_since >= JUDGE_AFTER_SECONDS
                ):
                    judge_waiting()

                # Counted as the client will see them: the same person reached at two
                # addresses is one lead. Counting before merging stopped a search at
                # eleven candidates that became nine leads.
                if not stopping and target > 0 and len(deduplicate(harvest.leads)[0]) >= target:
                    stopping = harvest.stopped_early = True
                    log.info(
                        "lead_target_reached",
                        extra={"target": target, "leads": len(harvest.leads), "pages": processed},
                    )
                if not stopping:
                    dispatch()

                self._progress.profiles_processed = before + processed
                self._bill_extraction()
                self._tally(harvest)
                if clock.time() - saved_at >= SAVE_EVERY_SECONDS:
                    await self._save(
                        search.id, SearchStage.EXTRACTING, processed / max(1, len(ranked))
                    )
                    saved_at = clock.time()
        finally:
            # Only reached with work left on a failure or a cancel: nothing may outlive
            # the stage that started it.
            leftovers = [*reads, *judging]
            for task in leftovers:
                task.cancel()
            await asyncio.gather(*leftovers, return_exceptions=True)

        self._progress.profiles_processed = before + processed
        self._bill_extraction()
        self._tally(harvest)
        await self._save(search.id, SearchStage.EXTRACTING, 1.0)

        # Whatever the stop left behind is not a judgement about anybody: those
        # candidates were never opened. Recorded all the same, because "we had
        # enough" is the one refusal the client may want to undo by asking for more.
        for index, prospect in enumerate(ranked):
            if decided[index]:
                continue
            self._refuse(
                search,
                prospect.url,
                RejectionReason.NOT_EXAMINED,
                f"The search already had the {target} leads it was asked for and "
                "stopped here. This candidate was never opened or paid for.",
                promise=prospect.promise,
                code="not_examined",
                params={"target": str(target)},
            )

        spent = cost_of(self.extractor)
        log.info(
            "extraction_completed",
            extra={
                "profiles": len(harvest.profiles),
                "pages": processed,
                "candidates": len(ranked),
                "stopped_early": harvest.stopped_early,
                "pages_read": self._usage.pages_read,
                "pages_cached": self._usage.pages_cached,
                "pages_skipped": self._usage.pages_skipped,
                # What the provider billed, which is not the same as what we could
                # use: a page that answered too late still spent its credits.
                "paid_attempts": spent.paid_attempts,
                "credits": spent.credits,
                # Reported by the reader itself. Phase 6 puts tokens on the usage
                # screen, when the LLM stage starts spending them too (spec §54).
                "tokens_in": spent.tokens_in,
                "tokens_out": spent.tokens_out,
                "read_by": {profile.extractor for profile in harvest.profiles},
            },
        )
        return harvest

    def _sift(
        self,
        search: Search,
        wave: list[Prospect],
        found: list[tuple[ExtractedProfile | None, bool]],
        harvest: Harvest,
    ) -> list[ExtractedProfile]:
        """
        Split what was read into profiles worth judging and refusals worth explaining.

        Two different things used to be counted as one here, and the difference is
        the whole reason the refused list exists. *We opened the page and there was
        no person on it* is a verdict about the candidate. *We never got the page*
        is a verdict about the reader — and behind it there may well be a lead.
        """
        fresh: list[ExtractedProfile] = []
        for prospect, (profile, failed) in zip(wave, found, strict=True):
            harvest.promise[prospect.url.canonical_url] = prospect.promise
            if profile is not None and profile.is_person:
                fresh.append(profile)
                continue

            if failed:
                harvest.refusals[Refusal.UNREADABLE] += 1
                self._refuse(
                    search,
                    prospect.url,
                    RejectionReason.UNREADABLE,
                    "The reader failed on this address, so nothing about this "
                    "person was ever seen.",
                    promise=prospect.promise,
                    code="unreadable",
                )
                continue

            # `None` here is the reader settling the question — a shop it opened
            # and read. A profile without a name is whatever the chain fell back to.
            # Unless the chain says it never got the page: then `None` is the
            # search result naming nobody, and "was read" would be untrue.
            unread = getattr(self.extractor, "unread", ())
            read = (profile is None and prospect.url.canonical_url not in unread) or (
                profile is not None and profile.extractor not in SNIPPET_ONLY
            )
            harvest.refusals[Refusal.NOT_A_PERSON] += 1
            if profile is None and prospect.url.canonical_url in getattr(
                self.extractor, "gone", ()
            ):
                # Not a brand: an account that is gone, which the index still lists.
                self._refuse(
                    search,
                    prospect.url,
                    RejectionReason.NOT_A_PERSON,
                    "The profile no longer exists or is not public — the search engine "
                    "still remembers an old copy of it.",
                    promise=prospect.promise,
                    read=True,
                    code="profile_gone",
                )
                continue
            self._refuse(
                search,
                prospect.url,
                RejectionReason.NOT_A_PERSON,
                "The page was read and named no person: a brand account, a community or a shop."
                if read
                else "The page would not open, and the search result on its own named nobody.",
                promise=prospect.promise,
                read=read,
                code="page_no_person" if read else "unopened_no_person",
            )
        return fresh

    def _prescreened(self, search: Search, prospect: Prospect, harvest: Harvest) -> bool:
        """
        Refuse a paid candidate, unread, when its search result already names no
        person — and say so, because the client can only check a refusal that tells
        them nothing was opened.

        Only paid reads are screened: a page our own browser opens costs nothing, and
        reading it is better evidence than any title.
        """
        named = prospect.profile.name if prospect.profile else None
        verdict = personhood.before_reading(
            named or _title_name(prospect.url.title),
            search.criteria.brands,
            sellers=is_network_marketing(search.criteria),
        )
        if verdict.is_person:
            return False
        harvest.promise[prospect.url.canonical_url] = prospect.promise
        harvest.refusals[Refusal.NOT_A_PERSON] += 1
        self._refuse(
            search,
            prospect.url,
            RejectionReason.NOT_A_PERSON,
            f"{verdict.detail} Decided from the search result alone, so the page was "
            "never opened or paid for.",
            promise=prospect.promise,
            code=verdict.code,
            params={**verdict.params, "unopened": "1"},
        )
        log.info(
            "candidate_prescreened",
            extra={"url": prospect.url.canonical_url, "detail": verdict.detail},
        )
        return True

    def _bill_extraction(self) -> None:
        """Copy what the extractor chain has spent so far into this run's usage."""
        spent = cost_of(self.extractor)
        self._usage.pages_read = spent.pages_read
        self._usage.pages_cached = spent.pages_cached
        self._usage.pages_skipped = spent.pages_skipped
        self._usage.scrape_credits = spent.credits

    # --------------------------------------------------------------- stage 5
    async def _score(self, search: Search, harvest: Harvest) -> list[Lead]:
        """
        Judge whatever the harvest has not judged yet.

        With a lead target set, reading did this as the profiles landed and this
        stage has nothing left to do — that is the point of the target: judging is
        what tells the search it can stop. Without one, every profile is judged
        here, exactly as before.
        """
        await self._enter(search.id, SearchStage.SCORING)
        pending = [
            profile
            for profile in harvest.profiles
            if profile.canonical_url not in harvest.judged_urls
        ]
        await self._judge(search, pending, harvest, stage=SearchStage.SCORING)
        await self._save(search.id, SearchStage.SCORING, 1.0)
        log.info(
            "scoring_completed",
            extra={
                "qualified": len(harvest.leads),
                "judged": len(harvest.judged_urls),
                "refused": {str(reason): count for reason, count in harvest.refusals.items()},
                "judged_during_extraction": len(harvest.judged_urls) - len(pending),
            },
        )
        return harvest.leads

    async def _judge(
        self,
        search: Search,
        profiles: list[ExtractedProfile],
        harvest: Harvest,
        *,
        stage: SearchStage | None = None,
    ) -> None:
        """
        Signals are detected per profile, then scored by code (spec §37). Four
        things can refuse a candidate, and `qualified` means it passed all of them:

        * it is not a person (`services/extraction/personhood.py`);
        * it is not in the country the client asked for;
        * it does not publish in a language the client asked for;
        * it does not visibly meet one of the search's required requirements.

        The first three are `services/search/eligibility.py` and are checked before
        the detector runs, which also means a filtered-out candidate is never paid
        for once Phase 6 makes judging an LLM call.

        Bounded by LLM_CONCURRENCY (§52) across the whole run, and every profile is
        judged at most once — `harvest.judged_urls` is what keeps a profile judged
        while reading from being paid for a second time at scoring.

        `stage=None` means "count, do not move the bar": while reading, the meter is
        already advancing with the pages read, and a second writer would make it go
        backwards. The reading loop saves the progress itself.
        """
        if not profiles:
            return

        semaphore = self._llm_slots
        requirements = search.criteria.effective_requirements()
        required = [requirement for requirement in requirements if requirement.required]
        done = 0

        # The cheap gates first, for every profile: a candidate refused for the
        # country is never sent to the (paid) judge.
        admitted: list[ExtractedProfile] = []
        for profile in profiles:
            harvest.judged_urls.add(profile.canonical_url)
            eligible = admit(profile, search.criteria)
            if eligible.admitted:
                admitted.append(profile)
                continue
            harvest.refusals[eligible.refusal] += 1
            self._refuse_profile(
                search,
                profile,
                RejectionReason(str(eligible.refusal)),
                eligible.detail,
                harvest.promise.get(profile.canonical_url),
                code=eligible.code,
                params=eligible.params,
            )
            log.info(
                "candidate_refused",
                extra={
                    "url": profile.canonical_url,
                    "reason": str(eligible.refusal),
                    "detail": eligible.detail,
                },
            )

        def finish(profile: ExtractedProfile, judgement: Judgement) -> None:
            signals = judgement.signals
            # Read by the judge as a company, shop or school: the cheap personhood
            # heuristics let it through, the page's own words did not.
            if judgement.is_person is False:
                harvest.refusals[Refusal.NOT_A_PERSON] += 1
                self._refuse_profile(
                    search,
                    profile,
                    RejectionReason.NOT_A_PERSON,
                    judgement.reason or "This page belongs to an organisation, not a person.",
                    harvest.promise.get(profile.canonical_url),
                    code="judge_not_person",
                    params={"kind": judgement.not_person_kind or "other"},
                )
                return

            # Where the judge read the person is, when code could not tell.
            profile, signals = placed_by_judge(profile, search.criteria, judgement)
            if judgement.country and search.criteria.in_excluded_place(profile.location.country):
                harvest.refusals[Refusal.WRONG_COUNTRY] += 1
                self._refuse_profile(
                    search,
                    profile,
                    RejectionReason.WRONG_COUNTRY,
                    f"“{judgement.country_evidence}” places this profile in "
                    f"{profile.location.country}, which this search excludes.",
                    harvest.promise.get(profile.canonical_url),
                    code="judge_excluded_country",
                    params={
                        "evidence": judgement.country_evidence,
                        "found": country_param(profile.location.country),
                    },
                )
                return
            if (
                judgement.country
                and search.criteria.allowed_countries()
                and search.criteria.in_allowed_place(profile.location.country) is False
            ):
                harvest.refusals[Refusal.WRONG_COUNTRY] += 1
                self._refuse_profile(
                    search,
                    profile,
                    RejectionReason.WRONG_COUNTRY,
                    f"“{judgement.country_evidence}” places this profile in "
                    f"{profile.location.country}, not {search.criteria.place_label()}.",
                    harvest.promise.get(profile.canonical_url),
                    code="judge_wrong_country",
                    params={
                        "evidence": judgement.country_evidence,
                        "found": country_param(profile.location.country),
                        "place": place_param(search.criteria),
                    },
                )
                return

            detected = {str(signal.type) for signal in signals if signal.detected}
            missing = [
                MissingSignal(id=requirement.id, label=requirement.label)
                for requirement in required
                if requirement.id not in detected
            ]
            # A search's own requirements, none of them marked required: a lead must
            # still meet at least one of them besides the place. Without this, a
            # candidate who matched nothing at all took a place in the list.
            judged = [
                requirement
                for requirement in requirements
                if requirement.id != SignalType.LOCATION and requirement.weight > 0
            ]
            if (
                not missing
                and not required
                and search.criteria.requirements is not None
                and judged
                and not any(requirement.id in detected for requirement in judged)
            ):
                missing = [MissingSignal(id=ANY_REQUIREMENT)]
            if missing:
                harvest.refusals[Refusal.MISSING_SIGNALS] += 1
                named = ", ".join(
                    "any of the search's requirements"
                    if entry.id == ANY_REQUIREMENT
                    else entry.label or entry.id
                    for entry in missing
                )
                self._refuse_profile(
                    search,
                    profile,
                    RejectionReason.MISSING_SIGNALS,
                    f"Nothing on this profile showed: {named}.",
                    harvest.promise.get(profile.canonical_url),
                    missing=missing,
                    code="missing_signals",
                )
                return

            score, breakdown = self.scoring.score(signals, requirements)
            harvest.leads.append(
                _build_lead(search, profile, signals, score, breakdown, len(harvest.leads))
            )
            self._progress.qualified = len(harvest.leads)
            self._progress.high_quality = sum(
                1 for lead in harvest.leads if lead.score >= HIGH_QUALITY_THRESHOLD
            )

        # Several candidates per call: the instructions and the requirements are
        # sent once for the batch instead of once per person, which is most of a
        # judging call's tokens.
        size = max(1, self.settings.judge_batch_size)
        batches = [admitted[index : index + size] for index in range(0, len(admitted), size)]

        async def judge_batch(batch: list[ExtractedProfile]) -> None:
            nonlocal done
            async with semaphore:
                await self._tick()
                judgements = await assess_many(self.detector, batch, search.criteria)
            # A judge with a budget counts the candidates it was paid for; the free
            # ones count every judgement, as before.
            paid_calls = getattr(self.detector, "paid_calls", None)
            self._usage.llm_calls = (
                paid_calls if paid_calls is not None else self._usage.llm_calls + len(batch)
            )
            for profile, judgement in zip(batch, judgements, strict=True):
                finish(profile, judgement)
            done += len(batch)
            if stage is not None:
                await self._save(search.id, stage, done / max(1, len(admitted)))

        await asyncio.gather(*(judge_batch(batch) for batch in batches))
        self._tally(harvest)

    def _refuse(
        self,
        search: Search,
        url: DiscoveredUrl,
        reason: RejectionReason,
        detail: str,
        *,
        promise: int | None = None,
        read: bool = False,
        author_url: str | None = None,
        code: str = "",
        params: dict[str, str] | None = None,
    ) -> None:
        """Record a refused address — one the run never got a profile out of."""
        self._record(
            RejectedCandidate(
                author_url=author_url,
                detail_code=code,
                detail_params=params or {},
                id=_rejection_id(search.id, url.canonical_url),
                user_id=search.user_id,
                search_id=search.id,
                url=url.url,
                canonical_url=url.canonical_url,
                platform=url.platform,
                reason=reason,
                detail=detail,
                read=read,
                name=_handle_in(url),
                title=url.title,
                snippet=url.snippet,
                query=url.query,
                promise=promise,
            )
        )

    def _refuse_profile(
        self,
        search: Search,
        profile: ExtractedProfile,
        reason: RejectionReason,
        detail: str,
        promise: int | None = None,
        *,
        missing: list[MissingSignal] | None = None,
        code: str = "",
        params: dict[str, str] | None = None,
    ) -> None:
        """Record a refused person — one the run did read something about."""
        source = next(
            (source for source in profile.sources if source.kind is not LeadSourceKind.POST),
            profile.sources[0] if profile.sources else None,
        )
        self._record(
            RejectedCandidate(
                id=_rejection_id(search.id, profile.canonical_url),
                user_id=search.user_id,
                search_id=search.id,
                url=profile.url,
                canonical_url=profile.canonical_url,
                platform=profile.platform,
                reason=reason,
                detail=detail,
                read=profile.extractor not in SNIPPET_ONLY,
                name=profile.name or "",
                title=source.title if source else (profile.headline or ""),
                snippet=source.snippet if source else (profile.summary or ""),
                promise=promise,
                missing=missing or [],
                detail_code=code,
                detail_params=params or {},
                found_via=[
                    source.url for source in profile.sources if source.kind is LeadSourceKind.POST
                ],
            )
        )

    def _record(self, rejected: RejectedCandidate) -> None:
        """First verdict wins: one address is refused once, by the stage that got to it."""
        self._rejected.setdefault(rejected.id, rejected)

    def _tally(self, harvest: Harvest) -> None:
        """Put the refusals on the progress record, where the client can read them."""
        self._progress.rejected_unreadable = harvest.refusals[Refusal.UNREADABLE]
        self._progress.rejected_not_a_person = harvest.refusals[Refusal.NOT_A_PERSON]
        self._progress.rejected_country = harvest.refusals[Refusal.WRONG_COUNTRY]
        self._progress.rejected_language = harvest.refusals[Refusal.WRONG_LANGUAGE]
        self._progress.rejected_signals = harvest.refusals[Refusal.MISSING_SIGNALS]

    # --------------------------------------------------------------- stage 6
    async def _deduplicate(self, search: Search, leads: list[Lead]) -> list[Lead]:
        await self._enter(search.id, SearchStage.DEDUPLICATING)
        merged, duplicates = deduplicate(leads)
        self._progress.qualified = len(merged)
        self._progress.high_quality = sum(
            1 for lead in merged if lead.score >= HIGH_QUALITY_THRESHOLD
        )
        await self._tick()
        await self._save(search.id, SearchStage.DEDUPLICATING, 1.0)
        log.info("deduplicated", extra={"leads": len(merged), "duplicates_merged": duplicates})
        return merged

    async def _complete(self, search: Search, leads: list[Lead]) -> None:
        await self.repo.add_leads(leads)
        # The result is both lists. Storing only the leads left the client with a
        # count of refusals and no way to check a single one of them.
        refused, merged = _settle_posts(list(self._rejected.values()), leads)
        await self.repo.add_rejections(refused)
        self._progress.posts_merged = merged
        high_quality = sum(1 for lead in leads if lead.score >= HIGH_QUALITY_THRESHOLD)
        self._progress.stage = SearchStage.DONE
        self._progress.percent = 100
        self._progress.qualified = len(leads)
        self._progress.high_quality = high_quality

        await self._patch(
            search.id,
            status=SearchStatus.COMPLETED,
            completed_at=datetime.now(UTC),
            lead_count=len(leads),
            high_quality_count=high_quality,
            progress=self._progress.model_copy(),
            usage=self._costed(),
        )
        log.info(
            "search_completed",
            extra={
                "leads": len(leads),
                "high_quality": high_quality,
                "refused": len(self._rejected),
                # Where a lost lead would be hiding, if there is one: refusals
                # decided without anybody ever opening the page.
                "refused_unseen": sum(1 for entry in self._rejected.values() if not entry.read),
            },
        )

    # ----------------------------------------------------------------- plumbing
    async def _enter(self, search_id: str, stage: SearchStage) -> None:
        self._progress.stage = stage
        await self._save(search_id, stage, 0.0)

    async def _save(
        self,
        search_id: str,
        stage: SearchStage,
        fraction: float,
        *,
        queries: list[GeneratedQuery] | None = None,
    ) -> None:
        self._progress.stage = stage
        # A second wave goes back to searching; the bar waits, it never goes back.
        self._progress.percent = max(self._progress.percent, _percent(stage, fraction))
        updates: dict[str, object] = {
            "status": STAGE_STATUS[stage],
            "progress": self._progress.model_copy(),
            "usage": self._costed(),
        }
        if queries is not None:
            updates["queries"] = [entry.model_copy() for entry in queries]
        if await self._patch(search_id, **updates) is None:
            raise SearchCancelled

    async def _patch(self, search_id: str, **updates: object) -> Search | None:
        """
        A single locked read-modify-write in the store, so a cancel that landed
        between two stages is never overwritten by stale progress. Returns None
        when the search is gone or already finished — the caller then stops.
        """
        return await self.repo.patch_search(search_id, updates)

    async def _mark_cancelled(self, search_id: str) -> None:
        current = await self.repo.get_search(search_id)
        if current and current.is_running:
            await self.repo.patch_search(
                search_id,
                {"status": SearchStatus.CANCELLED, "completed_at": datetime.now(UTC)},
            )

    def _costed(self) -> SearchUsage:
        """
        Usage is money (spec §54); unit costs are configuration.

        Two rules keep the figure honest rather than tidy:

        * pages are billed by what the *provider served*, not by what we could use.
          A page the cache answered was paid for by an earlier search and a page the
          budget refused was never fetched — both are free — but a page that
          answered too late for us spent its credits all the same.
        * a stage that calls nothing costs nothing. The keyword detector is free, so
          judging is only priced once a detector that really calls an LLM is plugged
          in; billing it earlier would put money on the screen nobody spent.
        """
        settings = self.settings
        spent = cost_of(self.extractor)
        judging = settings.cost_per_llm_call_eur if getattr(self.detector, "paid", False) else 0.0
        cost = (
            self._usage.search_api_calls * settings.cost_per_search_call_eur
            + spent.paid_attempts * settings.cost_per_page_eur
            + self._usage.llm_calls * judging
        )
        return self._usage.model_copy(update={"estimated_cost_eur": round(cost, 2)})

    async def _tick(self) -> None:
        """Fixture adapters answer instantly; keep the run watchable (spec §13)."""
        delay = self.settings.pipeline_step_delay_ms
        if delay > 0:
            await asyncio.sleep(delay / 1000)


def _why_not_a_profile(url: DiscoveredUrl, kept: set[str]) -> tuple[str, str, dict[str, str]]:
    """
    Why this address is not a person, said so the client can check it.

    A post gets its own sentence, and it matters: `instagram.com/anna/reel/C3Z…`
    appears in the refused list *and* its author appears in the leads. Without the
    sentence the first reads as a person thrown away.

    The sentence comes with its code and facts (`RejectedCandidate.detail_code`),
    so the interface can say it in the client's language.
    """
    profile = author_profile(url)
    if profile is not None and canonicalize(profile) in kept:
        author = canonicalize(profile)
        return (
            "A post rather than a profile — the account that published it "
            f"({author}) was looked at instead.",
            "post_author_followed",
            {"author": author},
        )
    detail = WHY_NOT_A_PROFILE.get(url.kind, "Not a person's page.")
    code = f"not_profile_{url.kind.value}" if url.kind in WHY_NOT_A_PROFILE else "not_profile"
    return detail, code, {}


#: Refusals that are a verdict about the author: their page (or, for the country
#: and language gates, what was known about them) was judged.
JUDGED_REASONS = frozenset(
    {
        RejectionReason.MISSING_SIGNALS,
        RejectionReason.WRONG_COUNTRY,
        RejectionReason.WRONG_LANGUAGE,
    }
)


def _settle_posts(
    rejected: list[RejectedCandidate], leads: list[Lead]
) -> tuple[list[RejectedCandidate], int]:
    """
    Decide where each refused post belongs, now that its author has been judged.

    A post is never the candidate — its author is. So:

    * the author became a lead → the post is one of the lead's sources and is not
      listed as a refusal at all;
    * the author was judged and refused → the post moves onto the author's row
      (`found_via`), under the reason the author was refused for;
    * the author could not be checked — the page would not open, the run stopped
      first, or no author could be named → the post stays where it was, saying
      what is known about its author.

    Returns the refusals to store and how many posts were folded into an author.
    """
    lead_by_url = {url: lead for lead in leads for url in lead.merged_urls}
    refused_by_url = {entry.canonical_url: entry for entry in rejected}
    folded: dict[str, list[str]] = {}
    kept: list[RejectedCandidate] = []
    merged = 0

    for entry in rejected:
        author_url = entry.author_url
        if not author_url:
            kept.append(entry)
            continue
        if author_url in lead_by_url:
            merged += 1
            continue
        author = refused_by_url.get(author_url)
        if author is not None and _was_judged(author):
            folded.setdefault(author_url, []).append(entry.url)
            merged += 1
            continue
        entry = entry.model_copy(
            update={
                "author_outcome": author.reason.value if author else None,
                "author_name": author.name if author else "",
                "detail": "A post rather than a profile. The account that published it "
                f"({author_url}) could not be checked, so the post stays here.",
                "detail_code": "post_author_unchecked",
                "detail_params": {"author": author_url},
            }
        )
        kept.append(entry)

    settled = [
        entry.model_copy(
            update={"found_via": _unique([*entry.found_via, *folded[entry.canonical_url]])}
        )
        if folded.get(entry.canonical_url)
        else entry
        for entry in kept
    ]
    return settled, merged


def _was_judged(entry: RejectedCandidate) -> bool:
    """Whether this refusal is a verdict about the person rather than about the reader."""
    if entry.reason in JUDGED_REASONS:
        return True
    return entry.reason is RejectionReason.NOT_A_PERSON and entry.read


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _title_name(title: str) -> str:
    """The name a search result is titled with: what comes before "- Headline", "|", "(@"."""
    return re.split(r"\s*\(@|\s+[-–—|·•:]\s+|\s*[|•]\s*", title or "", maxsplit=1)[0].strip()


def _rejection_id(search_id: str, canonical_url: str) -> str:
    """One address is one row per search, so re-running replaces rather than doubles."""
    return f"{search_id}__rej_{_digest(canonical_url)}"


def _handle_in(url: DiscoveredUrl) -> str:
    """What to call an address nobody managed to read a name out of."""
    parsed = urlparse(url.canonical_url)
    segments = [segment for segment in parsed.path.split("/") if segment]
    if url.platform in SOCIAL_PLATFORMS and segments:
        return unquote(segments[0]).lstrip("@")
    return parsed.netloc


def _percent(stage: SearchStage, fraction: float) -> int:
    start, end = STAGE_BOUNDS[stage]
    clamped = min(1.0, max(0.0, fraction))
    return round(100 * (start + (end - start) * clamped))


def _build_lead(
    search: Search,
    profile: ExtractedProfile,
    signals: list[LeadSignal],
    score: int,
    breakdown: list[ScoreComponent],
    index: int,
) -> Lead:
    return Lead(
        # The name alone is not unique on the open web — two real people called
        # María García would otherwise be one row, so the URL settles it.
        id=(
            f"{search.id}__{_slug(profile.name or profile.canonical_url)}"
            f"_{_digest(profile.canonical_url)}"
        ),
        user_id=search.user_id,
        search_id=search.id,
        search_name=search.name,
        name=profile.name or "Unknown",
        headline=profile.headline or "",
        company=profile.company,
        location=profile.location,
        languages=list(profile.languages),
        score=score,
        score_breakdown=breakdown,
        platforms=[entry.model_copy() for entry in profile.platforms],
        summary=profile.summary or "",
        signals=signals,
        sources=[source.model_copy() for source in profile.sources],
        contacts=profile.contacts.model_copy(),
        # Stagger by a millisecond so "newest first" is stable.
        created_at=datetime.now(UTC) - timedelta(milliseconds=index),
        merged_urls=[profile.canonical_url],
    )


def _slug(value: str) -> str:
    cleaned = "".join(char if char.isalnum() else "_" for char in value.lower())
    return "_".join(part for part in cleaned.split("_") if part)[:64]


def _digest(value: str) -> str:
    return hashlib.sha1(value.encode()).hexdigest()[:8]
