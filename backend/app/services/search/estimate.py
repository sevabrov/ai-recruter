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

    return SearchEstimate(
        queries=queries,
        search_calls=len(queries),
        max_pages=pages,
        credits=billable * settings.scrapegraph_credits_per_page if reads_pages else 0,
        target_leads=criteria.target_leads or settings.target_leads,
        pages_per_lead=settings.pages_per_lead,
        max_cost_eur=round(cost, 2),
    )
