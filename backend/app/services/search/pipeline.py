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
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.core.logging import bind, get_logger
from app.core.retry import retry_async
from app.db.repository import Repository
from app.models.common import HIGH_QUALITY_THRESHOLD, SearchStage, SearchStatus
from app.models.lead import Lead, LeadSignal, ScoreComponent
from app.models.profile import ExtractedProfile
from app.models.search import GeneratedQuery, Search, SearchProgress, SearchUsage
from app.models.source import DiscoveredUrl, ProviderResult
from app.services.extraction.signal_detector import SignalDetector
from app.services.scoring.scoring_service import ScoringService
from app.services.scraping.base import ProfileExtractor, budget_of, cost_of
from app.services.scraping.snippet_extractor import SnippetProfileExtractor
from app.services.search.deduplicator import deduplicate
from app.services.search.prospects import rank
from app.services.search.providers.base import SearchMarket, SearchProvider
from app.services.search.query_generator import QueryGenerator
from app.services.search.url_tools import candidates, discover

log = get_logger(__name__)

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
    rejected: int = 0
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

    async def run(self, search_id: str) -> None:
        search = await self.repo.get_search(search_id)
        if search is None:
            log.error("pipeline_search_missing")
            return

        bind(search_id=search_id, user_id=search.user_id)
        log.info("search_started", extra={"criteria_country": search.criteria.location.country})

        self._progress = SearchProgress()
        self._usage = SearchUsage()

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

    # ------------------------------------------------------------- stage 1–2
    async def _generate_queries(self, search: Search) -> list[GeneratedQuery]:
        await self._enter(search.id, SearchStage.GENERATING_QUERIES)
        generated = self.query_generator.generate(search.criteria)
        queries = [
            GeneratedQuery(id=f"q_{index + 1}", query=query, provider=self.provider.name)
            for index, query in enumerate(generated)
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
        Queries fan out concurrently (spec §30) under SEARCH_CONCURRENCY (§52), and
        each one is aimed at the country the user asked for.

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
            async with semaphore:
                await self._tick()
                results = await retry_async(
                    lambda: self.provider.search(entry.query, market=market),
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
        await self._enter(search.id, SearchStage.DISCOVERING_PROFILES)
        normalized = discover(results)
        profile_urls = candidates(normalized)

        self._progress.urls_discovered = len(normalized)
        self._progress.profiles_discovered = len(profile_urls)
        await self._tick()
        await self._save(search.id, SearchStage.DISCOVERING_PROFILES, 1.0)
        log.info(
            "profiles_identified",
            extra={
                "unique_urls": len(normalized),
                "candidates": len(profile_urls),
                "rejected": len(normalized) - len(profile_urls),
            },
        )
        return profile_urls

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
        target = self.settings.target_leads
        harvest = Harvest()
        semaphore = asyncio.Semaphore(self.settings.extraction_concurrency)
        processed = 0

        async def extract_one(url: DiscoveredUrl) -> ExtractedProfile | None:
            async with semaphore:
                await self._tick()
                try:
                    return await retry_async(
                        lambda: self.extractor.extract(url),
                        attempts=self.settings.max_retries,
                        label=f"extract:{self.extractor.name}",
                    )
                except Exception:
                    log.warning("extraction_failed", extra={"url": url.canonical_url})
                    return None

        while processed < len(ranked):
            wave = ranked[processed : processed + self._wave_size()]
            found = await asyncio.gather(*(extract_one(prospect.url) for prospect in wave))
            fresh = [profile for profile in found if profile and profile.is_person]
            harvest.profiles.extend(fresh)

            processed += len(wave)
            self._usage.pages_analyzed += len(wave)
            self._bill_extraction()
            self._progress.profiles_processed = processed

            if target > 0:
                # Judged now rather than in the scoring stage, because "we have
                # enough leads" is the only thing that can stop the spending.
                await self._judge(search, fresh, harvest)
            await self._save(search.id, SearchStage.EXTRACTING, processed / max(1, len(ranked)))

            if target > 0 and len(harvest.leads) >= target:
                harvest.stopped_early = True
                log.info(
                    "lead_target_reached",
                    extra={"target": target, "leads": len(harvest.leads), "pages": processed},
                )
                break

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
                "rejected_missing_must_have": harvest.rejected,
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
        Signals are detected per profile, then scored by code (spec §37): the
        must-have criteria act as a hard gate, so `qualified` means "matches what
        the user said they require", not "was looked at".

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
        weights = search.criteria.signal_weights
        required = set(search.criteria.must_have)
        done = 0

        async def judge_one(profile: ExtractedProfile) -> None:
            nonlocal done
            async with semaphore:
                await self._tick()
                signals = await self.detector.detect(profile, search.criteria)
            self._usage.llm_calls += 1
            harvest.judged_urls.add(profile.canonical_url)
            done += 1

            detected = {signal.type for signal in signals if signal.detected}
            if not required.issubset(detected):
                harvest.rejected += 1
                return

            score, breakdown = self.scoring.score(signals, weights)
            harvest.leads.append(
                _build_lead(search, profile, signals, score, breakdown, len(harvest.leads))
            )
            self._progress.qualified = len(harvest.leads)
            self._progress.high_quality = sum(
                1 for lead in harvest.leads if lead.score >= HIGH_QUALITY_THRESHOLD
            )
            if stage is not None:
                await self._save(search.id, stage, done / len(profiles))

        await asyncio.gather(*(judge_one(profile) for profile in profiles))

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
        log.info("search_completed", extra={"leads": len(leads), "high_quality": high_quality})

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
