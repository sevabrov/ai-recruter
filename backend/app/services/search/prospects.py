"""
Deciding which candidates are worth a credit, before spending one.

A live search finds a hundred candidate URLs and the budget pays for twenty-five
of them (`MAX_PAGES_PER_SEARCH`). Which twenty-five is then the most consequential
decision in the pipeline, and until now it was made by `asyncio.gather` — that is,
by whichever coroutine happened to start first.

So candidates are ranked first, for free, using what the search provider already
gave us: the title, the description, the index's page age and language. The
snippet extractor turns that into a profile with observations, the scoring service
turns those into the score the product already trusts, and the result is the
*promise* of a page — the score its search result alone supports.

Two additions to that score, both deliberate:

* **must-have signals already visible** count extra. A page whose description
  already mentions what the user requires is likelier to survive the gate than one
  that has to prove everything from scratch.
* **a small per-platform prior**, because promise here means "worth paying to
  read", and the two halves of that are what the page might say and whether it
  will open at all. Milestone 5's own finding is that a personal site opens and an
  Instagram profile shows a login wall to a server; the prior is a nudge on the
  scale of a tie-break, never a filter, and every platform stays eligible.

What this file does *not* do is drop anything. Ranking changes the order in which
candidates are read, and — when the search has a lead target — where the tail is
cut. Nothing is excluded on the strength of a snippet.
"""

from dataclasses import dataclass

from app.core.logging import get_logger
from app.models.common import Platform
from app.models.profile import ExtractedProfile
from app.models.search import SearchCriteria
from app.models.source import DiscoveredUrl
from app.services.scoring.scoring_service import ScoringService
from app.services.scraping.base import ProfileExtractor

log = get_logger(__name__)

#: How readable a platform tends to be, in score points. Measured behaviour, not a
#: judgement about the platforms: `GET /sources` reports what actually happens in
#: this workspace, and these are the same ranks it keeps showing.
#:
#: Kept small on purpose: a score runs to 100, so no prior here can outweigh a
#: signal someone actually published. Evidence decides; this only breaks ties.
PLATFORM_PRIOR: dict[Platform, int] = {
    Platform.WEBSITE: 8,
    Platform.BLOG: 8,
    Platform.LINKEDIN: 5,
    Platform.FACEBOOK: 3,
    Platform.THREADS: 3,
    Platform.INSTAGRAM: 0,
}

#: Per must-have signal the search result already shows.
MUST_HAVE_BONUS = 5


@dataclass
class Prospect:
    """A candidate URL, ordered."""

    url: DiscoveredUrl
    #: What the search result alone supports. None when it does not read like a
    #: person at all — which is not a verdict: the page itself may say otherwise,
    #: so the URL keeps its place in the queue.
    profile: ExtractedProfile | None
    promise: int


async def rank(
    urls: list[DiscoveredUrl],
    criteria: SearchCriteria,
    *,
    snippets: ProfileExtractor,
    scoring: ScoringService,
) -> list[Prospect]:
    """
    Candidates, best first. Free: nothing here opens a URL.

    Ties keep discovery order, so a search is reproducible — the same results in
    the same order produce the same reading queue.
    """
    prospects: list[Prospect] = []
    for url in urls:
        profile = await snippets.extract(url)
        prospects.append(
            Prospect(
                url=url,
                profile=profile,
                promise=_promise(url, profile, criteria, scoring),
            )
        )

    ranked = sorted(prospects, key=lambda prospect: prospect.promise, reverse=True)
    log.info(
        "candidates_ranked",
        extra={
            "candidates": len(ranked),
            "best": ranked[0].promise if ranked else 0,
            "worst": ranked[-1].promise if ranked else 0,
            "with_a_name": sum(1 for prospect in ranked if prospect.profile is not None),
        },
    )
    return ranked


def _promise(
    url: DiscoveredUrl,
    profile: ExtractedProfile | None,
    criteria: SearchCriteria,
    scoring: ScoringService,
) -> int:
    prior = PLATFORM_PRIOR.get(url.platform, 0)
    if profile is None:
        return prior

    score, _ = scoring.score(profile.observations, criteria.signal_weights)
    required = set(criteria.must_have)
    visible = sum(
        1
        for observation in profile.observations
        if observation.detected and observation.type in required
    )
    return prior + score + MUST_HAVE_BONUS * visible
