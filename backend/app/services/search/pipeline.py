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
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import unquote, urlparse

from app.core.config import Settings
from app.core.logging import bind, get_logger
from app.core.retry import retry_async
from app.db.repository import Repository
from app.models.common import HIGH_QUALITY_THRESHOLD, SearchStage, SearchStatus, SignalType
from app.models.lead import Lead, LeadSignal, ScoreComponent
from app.models.profile import ExtractedProfile
from app.models.rejection import RejectedCandidate, RejectionReason
from app.models.search import GeneratedQuery, Search, SearchProgress, SearchUsage
from app.models.source import DiscoveredUrl, ProviderResult, UrlKind
from app.services.extraction.signal_detector import (
    Judgement,
    SignalDetector,
    assess_many,
    placed_by_judge,
)
from app.services.scoring.scoring_service import ScoringService
from app.services.scraping.base import ProfileExtractor, budget_of, cost_of, fetch_from
from app.services.scraping.snippet_extractor import SnippetProfileExtractor
from app.services.search.deduplicator import deduplicate
from app.services.search.eligibility import Refusal, admit
from app.services.search.estimate import judging_budget_for, page_budget_for
from app.services.search.markets import country_code, iso_code
from app.services.search.prospects import Prospect, rank
from app.services.search.providers.base import SearchMarket, SearchProvider
from app.services.search.query_generator import QueryGenerator
from app.services.search.url_tools import (
    SOCIAL_PLATFORMS,
    author_profile,
    candidates,
    canonicalize,
    discover,
    promote_posts,
)

log = get_logger(__name__)

#: Extractors that never open a page. A profile one of these produced was judged
#: on the search result alone, which is what `RejectedCandidate.read` records.
SNIPPET_ONLY = {"snippet"}

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
    ) -> None:
        self.repo = repository
        self.settings = settings
        self.query_generator = query_generator
        self.provider = provider
        self.extractor = extractor
        self.detector = detector
        self.scoring = scoring
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
        self._aim(search)

        try:
            queries = await self._generate_queries(search)
            results = await self._run_queries(search, queries)
            urls = await self._discover(search, results)
            harvest = await self._extract(search, urls)
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
        self._progress.queries = len(queries)
        await self._tick()
        await self._save(search.id, SearchStage.GENERATING_QUERIES, 1.0, queries=queries)
        log.info("queries_generated", extra={"count": len(queries)})
        return queries

    async def _run_queries(
        self, search: Search, queries: list[GeneratedQuery]
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
        """
        await self._enter(search.id, SearchStage.WEB_SEARCH)
        market = SearchMarket.from_criteria(search.criteria)
        semaphore = asyncio.Semaphore(self.settings.search_concurrency)
        collected: list[ProviderResult] = []
        done = 0

        async def run_one(entry: GeneratedQuery) -> None:
            nonlocal done
            aimed = market.model_copy(
                update={
                    "language": entry.language or market.language,
                    # A search over several countries aims each query at its own.
                    "country": country_code(entry.country) if entry.country else market.country,
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
            self._progress.queries_completed = done
            self._progress.urls_discovered = len(collected)
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

        await self._save(search.id, SearchStage.WEB_SEARCH, 1.0, queries=queries)
        log.info("web_search_completed", extra={"raw_results": len(collected)})
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
        sources = search.criteria.sources
        profile_urls = candidates(normalized, sources)
        kept = {url.canonical_url for url in profile_urls}
        readable = candidates(normalized)
        off_source = [url for url in readable if url.canonical_url not in kept]
        self._refuse_addresses(search, normalized, readable, off_source, kept)

        self._progress.urls_discovered = len(normalized)
        self._progress.profiles_discovered = len(profile_urls)
        self._progress.rejected_off_source = len(off_source)
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
            self._refuse(search, url, RejectionReason.NOT_A_PROFILE, _why_not_a_profile(url, kept))
        for url in off_source:
            self._refuse(
                search,
                url,
                RejectionReason.OFF_SOURCE,
                f"Found on {url.platform.value}, which is not among this search's "
                "sources — so it was never opened and nothing was paid for it.",
            )

    # --------------------------------------------------------------- stage 4
    async def _extract(self, search: Search, urls: list[DiscoveredUrl]) -> Harvest:
        """
        Read the candidates — best first, in waves, and only as far as the search's
        limits allow.

        Three things changed here once reading became a paid operation:

        * **order is a decision.** Candidates are ranked by what their search result
          alone already supports (`services/search/prospects.py`), so the page
          budget is spent on the most promising pages instead of on whichever
          coroutine started first.
        * **a wave is a checkpoint.** With `TARGET_LEADS` set, each wave is judged as
          soon as it lands, and the search stops as soon as the user has the leads
          they asked for — the pages behind that point are never paid for.
        * **the budget lives lower down.** How many pages may be *read* is enforced
          by the reader itself (`services/scraping/budget.py`); the pages it refuses
          still become leads from their snippet. That is why every candidate still
          goes through the chain: a cache hit costs nothing and is worth having
          (spec §53).

        Concurrency inside a wave stays bounded by EXTRACTION_CONCURRENCY (§35).
        """
        await self._enter(search.id, SearchStage.EXTRACTING)
        ranked = await rank(urls, search.criteria, snippets=self._snippets, scoring=self.scoring)
        target = self._target
        harvest = Harvest()
        semaphore = asyncio.Semaphore(self.settings.extraction_concurrency)
        processed = 0

        async def extract_one(url: DiscoveredUrl) -> tuple[ExtractedProfile | None, bool]:
            """The profile, and whether the reader failed outright getting it."""
            async with semaphore:
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
                return profile, False

        while processed < len(ranked):
            wave = ranked[processed : processed + self._wave_size()]
            found = await asyncio.gather(*(extract_one(prospect.url) for prospect in wave))
            # A page nobody could find a person on is the first refusal, and it
            # happens here rather than at judging: there is nothing to judge.
            fresh = self._sift(search, wave, found, harvest)
            harvest.profiles.extend(fresh)

            processed += len(wave)
            self._usage.pages_analyzed += len(wave)
            self._bill_extraction()
            self._progress.profiles_processed = processed

            if target > 0:
                # Judged now rather than in the scoring stage, because "we have
                # enough leads" is the only thing that can stop the spending.
                await self._judge(search, fresh, harvest)
            self._tally(harvest)
            await self._save(search.id, SearchStage.EXTRACTING, processed / max(1, len(ranked)))

            # Counted as the client will see them: the same person reached at two
            # addresses is one lead. Counting before merging stopped a search at
            # eleven candidates that became nine leads.
            if target > 0 and len(deduplicate(harvest.leads)[0]) >= target:
                harvest.stopped_early = True
                log.info(
                    "lead_target_reached",
                    extra={"target": target, "leads": len(harvest.leads), "pages": processed},
                )
                break

        # Whatever the break left behind is not a judgement about anybody: those
        # candidates were never opened. Recorded all the same, because "we had
        # enough" is the one refusal the client may want to undo by asking for more.
        for prospect in ranked[processed:]:
            self._refuse(
                search,
                prospect.url,
                RejectionReason.NOT_EXAMINED,
                f"The search already had the {target} leads it was asked for and "
                "stopped here. This candidate was never opened or paid for.",
                promise=prospect.promise,
            )

        self._bill_extraction()
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
        Split a wave into profiles worth judging and refusals worth explaining.

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
            self._refuse(
                search,
                prospect.url,
                RejectionReason.NOT_A_PERSON,
                "The page was read and named no person: a brand account, a community or a shop."
                if read
                else "The page would not open, and the search result on its own named nobody.",
                promise=prospect.promise,
                read=read,
            )
        return fresh

    def _wave_size(self) -> int:
        """
        How many candidates to dispatch together.

        EXTRACTION_CONCURRENCY, except when the budget has fewer paid reads left
        than that: with one page left to pay for and ten coroutines in flight, the
        last credit would go to whichever of them reached the reader first, and
        ranking the candidates would have bought nothing. Once the budget is spent
        nothing costs money any more, so the rest runs at full width.
        """
        width = max(1, self.settings.extraction_concurrency)
        budget = budget_of(self.extractor)
        if budget is None or budget.unlimited or budget.exhausted:
            return width
        return max(1, min(width, budget.remaining or width))

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

        With a lead target set, the waves above did this as they landed and this
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

        Bounded by LLM_CONCURRENCY (§52), and every profile is judged at most once —
        `harvest.judged_urls` is what keeps a wave-judged profile from being paid
        for a second time when the LLM detector arrives in Phase 6.

        `stage=None` means "count, do not move the bar": inside a wave the meter is
        already advancing with the pages read, and a second writer would make it go
        backwards. The wave loop saves once the wave is judged.
        """
        if not profiles:
            return

        semaphore = asyncio.Semaphore(self.settings.llm_concurrency)
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
                )
                return

            # Where the judge read the person is, when code could not tell.
            profile, signals = placed_by_judge(profile, search.criteria, judgement)
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
                )
                return

            detected = {str(signal.type) for signal in signals if signal.detected}
            missing = [
                requirement.label or requirement.id
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
                missing = ["any of the search's requirements"]
            if missing:
                harvest.refusals[Refusal.MISSING_SIGNALS] += 1
                self._refuse_profile(
                    search,
                    profile,
                    RejectionReason.MISSING_SIGNALS,
                    f"Nothing on this profile showed: {', '.join(missing)}.",
                    harvest.promise.get(profile.canonical_url),
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
    ) -> None:
        """Record a refused address — one the run never got a profile out of."""
        self._record(
            RejectedCandidate(
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
    ) -> None:
        """Record a refused person — one the run did read something about."""
        source = profile.sources[0] if profile.sources else None
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
        await self.repo.add_rejections(list(self._rejected.values()))
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
        self._progress.percent = _percent(stage, fraction)
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


def _why_not_a_profile(url: DiscoveredUrl, kept: set[str]) -> str:
    """
    Why this address is not a person, said so the client can check it.

    A post gets its own sentence, and it matters: `instagram.com/anna/reel/C3Z…`
    appears in the refused list *and* its author appears in the leads. Without the
    sentence the first reads as a person thrown away.
    """
    profile = author_profile(url)
    if profile is not None and canonicalize(profile) in kept:
        return (
            "A post rather than a profile — the account that published it "
            f"({canonicalize(profile)}) was looked at instead."
        )
    return WHY_NOT_A_PROFILE.get(url.kind, "Not a person's page.")


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
