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
from app.services.scraping.base import ProfileExtractor, cost_of
from app.services.search.deduplicator import deduplicate
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
            profiles = await self._extract(search, urls)
            leads = await self._score(search, profiles)
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
    async def _extract(self, search: Search, urls: list[DiscoveredUrl]) -> list[ExtractedProfile]:
        """
        Candidate URLs are read concurrently under EXTRACTION_CONCURRENCY (spec §35)
        — never one at a time, never unlimited.

        What "read" means is the extractor's business (`services/adapters.py`), and
        since Phase 5 it can cost money: the chain reports how many pages it fetched
        and how many the cache saved, and those are copied into the search's usage
        rather than inferred from the number of URLs (§53–54).
        """
        await self._enter(search.id, SearchStage.EXTRACTING)
        semaphore = asyncio.Semaphore(self.settings.extraction_concurrency)
        profiles: list[ExtractedProfile] = []
        processed = 0

        async def extract_one(url: DiscoveredUrl) -> None:
            nonlocal processed
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
                    profile = None

            processed += 1
            self._usage.pages_analyzed += 1
            self._bill_extraction()
            if profile and profile.is_person:
                profiles.append(profile)
            self._progress.profiles_processed = processed
            await self._save(search.id, SearchStage.EXTRACTING, processed / max(1, len(urls)))

        await asyncio.gather(*(extract_one(url) for url in urls))
        self._bill_extraction()
        spent = cost_of(self.extractor)
        log.info(
            "extraction_completed",
            extra={
                "profiles": len(profiles),
                "pages": processed,
                "pages_read": self._usage.pages_read,
                "pages_cached": self._usage.pages_cached,
                # Reported by the reader itself. Phase 6 puts tokens on the usage
                # screen, when the LLM stage starts spending them too (spec §54).
                "tokens_in": spent.tokens_in,
                "tokens_out": spent.tokens_out,
                "read_by": {profile.extractor for profile in profiles},
            },
        )
        return profiles

    def _bill_extraction(self) -> None:
        """Copy what the extractor chain has spent so far into this run's usage."""
        spent = cost_of(self.extractor)
        self._usage.pages_read = spent.pages_read
        self._usage.pages_cached = spent.pages_cached
        self._usage.scrape_credits = spent.credits

    # --------------------------------------------------------------- stage 5
    async def _score(self, search: Search, profiles: list[ExtractedProfile]) -> list[Lead]:
        """
        Signals are detected per profile, then scored by code (spec §37): the
        must-have criteria act as a hard gate, so `qualified` means "matches what
        the user said they require", not "was looked at".
        """
        await self._enter(search.id, SearchStage.SCORING)
        semaphore = asyncio.Semaphore(self.settings.llm_concurrency)
        weights = search.criteria.signal_weights
        required = set(search.criteria.must_have)
        leads: list[Lead] = []
        rejected = 0

        async def score_one(index: int, profile: ExtractedProfile) -> None:
            nonlocal rejected
            async with semaphore:
                await self._tick()
                signals = await self.detector.detect(profile, search.criteria)
            self._usage.llm_calls += 1

            detected = {signal.type for signal in signals if signal.detected}
            if not required.issubset(detected):
                rejected += 1
                return

            score, breakdown = self.scoring.score(signals, weights)
            leads.append(_build_lead(search, profile, signals, score, breakdown, index))

            self._progress.qualified = len(leads)
            self._progress.high_quality = sum(
                1 for lead in leads if lead.score >= HIGH_QUALITY_THRESHOLD
            )
            await self._save(search.id, SearchStage.SCORING, (index + 1) / max(1, len(profiles)))

        await asyncio.gather(*(score_one(index, profile) for index, profile in enumerate(profiles)))
        log.info(
            "scoring_completed",
            extra={"qualified": len(leads), "rejected_missing_must_have": rejected},
        )
        return leads

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

        Pages are billed by what was *read*, not by what was looked at: a page the
        cache answered was paid for by an earlier search, and charging for it again
        would make the cache invisible in the only place it matters.
        """
        settings = self.settings
        cost = (
            self._usage.search_api_calls * settings.cost_per_search_call_eur
            + self._usage.pages_read * settings.cost_per_page_eur
            + self._usage.llm_calls * settings.cost_per_llm_call_eur
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
