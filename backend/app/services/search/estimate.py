"""
What this search will cost, before it is started (spec §54).

The client's request was plain: choosing how many leads to look for, and seeing
the price of that choice, belongs in the wizard — not in a dashboard afterwards.

The number shown is a **ceiling, not a forecast**. A forecast of a live web
search is a guess dressed up as arithmetic: nobody can say how many of forty
candidate pages will open, or how many of the people behind them will turn out to
live in the right country. A ceiling can be promised, because it is enforced —
the same function produces the figure the wizard shows and the `PageBudget` the
run is given, so the search physically cannot exceed what was quoted.

    cost ≤ queries × price(search call) + pages × price(page)

where `pages` is the page budget: `targetLeads × PAGES_PER_LEAD`, capped by
`MAX_PAGES_PER_SEARCH`. Asking for ten leads therefore buys thirty paid reads,
and asking for two buys six. Candidates past the budget are not thrown away —
they become leads from their search snippet, for free, at lower confidence.

Judging is priced only when a detector that really calls an LLM is configured;
the keyword stand-in costs nothing, and quoting it would put money on the screen
that nobody will spend.
"""

from dataclasses import dataclass, field

from app.core.config import Settings
from app.models.common import SignalType, SourceKind
from app.models.search import SearchCriteria
from app.services.search.query_generator import QueryGenerator, QueryPlan


@dataclass
class SearchEstimate:
    """The ceiling, and every number it is made of."""

    queries: list[QueryPlan] = field(default_factory=list)
    #: One query is one billed call to the search provider.
    search_calls: int = 0
    #: The most pages this search may pay to read.
    max_pages: int = 0
    #: …in the reader plan's own units.
    credits: int = 0
    target_leads: int = 0
    pages_per_lead: int = 0
    max_cost_eur: float = 0.0
    #: What is likely to go wrong with *these* criteria, in words the client can act
    #: on. Written here rather than discovered afterwards: a search that returns
    #: nothing has already been paid for.
    warnings: list[str] = field(default_factory=list)

    @property
    def unlimited_pages(self) -> bool:
        """No page budget at all — the fixture demo, and a deliberate `0` setting."""
        return self.max_pages <= 0


def page_budget_for(criteria: SearchCriteria, settings: Settings) -> int:
    """
    How many paid page reads this search may make. 0 means unlimited.

    The lead target is the client's control; the server-wide ceiling is the one
    they cannot exceed by typing a bigger number into the wizard.
    """
    ceiling = max(0, settings.max_pages_per_search)
    target = criteria.target_leads or settings.target_leads
    if target <= 0:
        return ceiling
    wanted = target * max(1, settings.pages_per_lead)
    return min(ceiling, wanted) if ceiling else wanted


def estimate(
    criteria: SearchCriteria,
    settings: Settings,
    *,
    generator: QueryGenerator,
    reads_pages: bool = True,
    paid_detector: bool = False,
) -> SearchEstimate:
    """
    `reads_pages` and `paid_detector` are what is actually plugged in right now.
    A workspace with no page-reader key spends nothing on pages, and quoting for
    one would be quoting for a stage that is not running (see `services/adapters`).
    """
    queries = generator.generate(criteria, limit=settings.max_queries_per_search)
    pages = page_budget_for(criteria, settings) if reads_pages else 0
    # An unlimited budget still has to be priced, and the only honest number for
    # it is the server ceiling — which is what `MAX_PAGES_PER_SEARCH=0` removes.
    billable = pages if pages else (settings.max_pages_per_search if reads_pages else 0)

    cost = len(queries) * settings.cost_per_search_call_eur + billable * settings.cost_per_page_eur
    if paid_detector:
        # One judgement per candidate that gets as far as being judged. Pages read
        # is the closest bound the wizard can put on that before anything runs.
        cost += max(billable, 1) * settings.cost_per_llm_call_eur

    per_page = settings.scrapegraph_credits_per_page + (
        settings.scrapegraph_stealth_credits if settings.scrapegraph_stealth else 0
    )
    return SearchEstimate(
        queries=queries,
        search_calls=len(queries),
        max_pages=pages,
        credits=billable * per_page if reads_pages else 0,
        target_leads=criteria.target_leads or settings.target_leads,
        pages_per_lead=settings.pages_per_lead,
        max_cost_eur=round(cost, 2),
        warnings=warnings_for(criteria),
    )


def warnings_for(criteria: SearchCriteria) -> list[str]:
    """
    What these criteria are likely to do to the result, said before the search runs.

    Every line here is a lesson from a measured run, not a guess. The client's
    complaint was not that the filters were wrong — it was that a reasonable-looking
    set of criteria returned nothing and the screen blamed the filters afterwards.
    """
    notes: list[str] = []
    social_only = bool(criteria.sources) and not (
        {SourceKind.PUBLIC_WEB, SourceKind.COMPANY_WEBSITES, SourceKind.BLOGS}
        & set(criteria.sources)
    )

    if criteria.location.country and criteria.require_confirmed_location and social_only:
        notes.append(
            f"Only social sources are selected, and “confirmed {criteria.location.country} "
            "only” is on. Social profiles rarely state a location and their pages often "
            "will not open, so most candidates will be dropped as unconfirmed."
        )
    if criteria.languages and criteria.require_confirmed_language and social_only:
        notes.append(
            "“Confirmed languages only” over social sources is strict: a two-line "
            "profile description often shows no language at all."
        )
    if len(criteria.must_have) > 1:
        notes.append(
            f"{len(criteria.must_have)} must-have signals means all of them at once, "
            "each proven by a quote from the profile. Two are already hard to find "
            "together on a profile that could not be opened."
        )
    if SignalType.ACTIVITY in criteria.must_have:
        notes.append(
            "“Recent activity” as a must-have gates hard and is worth no points: it "
            "needs a date the page states, which a search result usually omits."
        )
    if not criteria.keywords:
        notes.append(
            "No keywords of your own: the queries fall back to the niche's generic "
            "name, which is what the niche's famous brand accounts are called. Add "
            "the brand people actually distribute (jerelia, farmasi) and the "
            "queries start describing a person."
        )
    if SourceKind.THREADS_PUBLIC in criteria.sources:
        notes.append(
            "Threads has returned zero results for every query in every measured "
            "run. Each one still costs a search call — unselect it unless you know "
            "it works for your market."
        )
    if criteria.location.city and criteria.require_confirmed_location:
        notes.append(
            f"A city narrows the queries sharply. If {criteria.location.city} returns "
            "little, the country alone usually returns much more."
        )
    return notes
