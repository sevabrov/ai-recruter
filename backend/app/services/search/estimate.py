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
from app.services.search.markets import language_code
from app.services.search.query_generator import QueryGenerator, QueryPlan


@dataclass(frozen=True)
class EstimateWarning:
    """
    One thing likely to go wrong, as a code and the values it mentions.

    A code rather than a sentence: the sentence belongs to the interface language.
    The first version sent English prose, which then sat in the middle of a
    Ukrainian screen — the client could read neither the warning nor why it was
    in English. The wording lives in the frontend's catalogue under
    `wizard.review.warning.<code>`.
    """

    code: str
    params: dict[str, str] = field(default_factory=dict)


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
    #: What a search like this usually costs: the same calls and pages, and the
    #: judging measured per lead rather than its ceiling. Never above the ceiling.
    expected_cost_eur: float = 0.0
    #: Whether any chosen platform is read by the paid reader at all.
    reads_pages: bool = False
    #: Whether some of the chosen platforms are read by our own browser, for free.
    browser_pages: bool = False
    #: The most candidates a model may judge (0 when judging is free).
    max_judgements: int = 0
    #: What is likely to go wrong with *these* criteria, in words the client can act
    #: on. Written here rather than discovered afterwards: a search that returns
    #: nothing has already been paid for.
    warnings: list[EstimateWarning] = field(default_factory=list)

    @property
    def unlimited_pages(self) -> bool:
        """No page budget at all — the fixture demo, and a deliberate `0` setting."""
        return self.max_pages <= 0


def judging_budget_for(criteria: SearchCriteria, settings: Settings) -> int:
    """
    How many candidates the model may judge in this search: so many per lead asked
    for, under the server's ceiling. The run is given exactly this, so the quote holds.
    """
    ceiling = max(0, settings.max_judgements_per_search)
    target = criteria.target_leads or settings.target_leads
    if target <= 0:
        return ceiling
    return min(ceiling, target * max(1, settings.judgements_per_lead))


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
    free_sources: frozenset[SourceKind] = frozenset(),
) -> SearchEstimate:
    """
    `reads_pages` and `paid_detector` are what is actually plugged in right now.
    A workspace with no page-reader key spends nothing on pages, and quoting for
    one would be quoting for a stage that is not running (see `services/adapters`).
    """
    queries = generator.generate(criteria, limit=settings.max_queries_per_search)
    # Platforms our own browser reads cost nothing per page (Instagram, Facebook):
    # pages are paid for only when a chosen source goes to the paid reader. A search
    # on Instagram alone was quoted 25 paid pages and paid for none.
    sources = set(criteria.sources) or {SourceKind.PUBLIC_WEB}
    browser_pages = bool(sources & free_sources)
    reads_pages = reads_pages and bool(sources - free_sources)
    pages = page_budget_for(criteria, settings) if reads_pages else 0
    # An unlimited budget still has to be priced, and the only honest number for
    # it is the server ceiling — which is what `MAX_PAGES_PER_SEARCH=0` removes.
    billable = pages if pages else (settings.max_pages_per_search if reads_pages else 0)

    cost = len(queries) * settings.cost_per_search_call_eur + billable * settings.cost_per_page_eur
    # One paid judgement per candidate, up to the search's judging budget — the
    # rest are judged by their words for free, so the budget is the ceiling.
    judgements = judging_budget_for(criteria, settings) if paid_detector else 0
    fixed = cost
    cost += judgements * settings.cost_per_llm_call_eur
    target = criteria.target_leads or settings.target_leads
    usual = (
        min(judgements, target * max(1, settings.expected_judgements_per_lead))
        if target > 0
        else judgements
    )
    expected = fixed + usual * settings.cost_per_llm_call_eur

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
        expected_cost_eur=round(min(expected, cost), 2),
        reads_pages=reads_pages,
        browser_pages=browser_pages,
        max_judgements=judgements,
        warnings=warnings_for(criteria),
    )


def warnings_for(criteria: SearchCriteria) -> list[EstimateWarning]:
    """
    What these criteria are likely to do to the result, said before the search runs.

    Every line here is a lesson from a measured run, not a guess. The client's
    complaint was not that the filters were wrong — it was that a reasonable-looking
    set of criteria returned nothing and the screen blamed the filters afterwards.
    """
    notes: list[EstimateWarning] = []
    social_only = bool(criteria.sources) and not (
        {SourceKind.PUBLIC_WEB, SourceKind.COMPANY_WEBSITES, SourceKind.BLOGS}
        & set(criteria.sources)
    )
    country = criteria.place_label()

    # Social profiles rarely state a location and their pages often will not open,
    # so most candidates would be dropped as unconfirmed.
    if country and criteria.require_confirmed_location and social_only:
        notes.append(EstimateWarning("confirmed_location_social", {"country": country}))
    # A two-line profile description often shows no language at all.
    if criteria.languages and criteria.require_confirmed_language and social_only:
        notes.append(EstimateWarning("confirmed_language_social"))
    # All of them at once, each proven by a quote from the profile.
    required = [r for r in criteria.effective_requirements() if r.required]
    if len(required) > 1:
        notes.append(EstimateWarning("many_must_have", {"count": str(len(required))}))
    # Gates hard and is worth no points: it needs a date the page states.
    if any(r.id == SignalType.ACTIVITY for r in required):
        notes.append(EstimateWarning("activity_must_have"))
    # Without a term of their own the queries fall back to the niche's generic
    # name — which is what the niche's famous brand accounts are called.
    if not criteria.keywords and not criteria.brands:
        notes.append(EstimateWarning("no_keywords"))
    # A query in another language carries the place in that language, so without
    # a country only the English pass runs: Ukrainian and Russian were chosen in a
    # measured run and not a single query was written in either.
    foreign = [name for name in criteria.languages if language_code(name) not in (None, "en")]
    if foreign and not criteria.focus_countries():
        notes.append(EstimateWarning("languages_without_country"))
    # Zero results for every query in every measured run, each one still billed.
    if SourceKind.THREADS_PUBLIC in criteria.sources:
        notes.append(EstimateWarning("threads_empty"))
    if criteria.location.city and criteria.require_confirmed_location:
        notes.append(EstimateWarning("city_narrow", {"city": criteria.location.city}))
    return notes
