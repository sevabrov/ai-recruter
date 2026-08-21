"""
What one search may spend on reading pages (spec §52, §54).

A live search finds a hundred candidate pages without trying, and reading all of
them costs real credits — the difference between "a search costs cents" and "a
search costs a plan". So the number of *paid* reads per search is configuration,
enforced next to the thing that spends the money rather than trusted to whatever
calls it.

Three properties this is built for:

* **cache hits are free**, so they are not budgeted. The budget sits behind the
  cache, and a page that was read last week costs nothing to reuse (spec §53).
* **a refused page is not a lost lead.** The reader answers `SKIPPED`, the chain
  falls back to the search snippet, and the lead survives with lower confidence —
  the limit costs depth, not coverage.
* **the counter is per search**, like every other cost counter, which is why the
  extractor chain is built per job (`services/adapters.py`).

Nothing here is thread-safe and nothing needs to be: the event loop runs one
coroutine at a time, and `take()` is a whole decision between two awaits.
"""

from dataclasses import dataclass

from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class PageBudget:
    """`limit` paid reads, then nothing. A limit of 0 means unlimited."""

    limit: int = 0
    spent: int = 0
    skipped: int = 0

    @property
    def unlimited(self) -> bool:
        return self.limit <= 0

    @property
    def exhausted(self) -> bool:
        return not self.unlimited and self.spent >= self.limit

    @property
    def remaining(self) -> int | None:
        """None when unlimited — a number no caller should invent."""
        return None if self.unlimited else max(0, self.limit - self.spent)

    def refund(self) -> None:
        """
        Give the slot back. A request the service refused — a 429, an empty balance,
        a connection that never opened — cost nothing, so it must not cost a page
        either: otherwise one bad minute silently shrinks the search.
        """
        self.spent = max(0, self.spent - 1)

    def take(self) -> bool:
        """
        Claim one paid read. False means the search has spent its budget, and the
        caller must not send the request.
        """
        if self.exhausted:
            self.skipped += 1
            if self.skipped == 1:
                # Once per search: the interesting event is the boundary, not each
                # of the ninety URLs behind it.
                log.info("page_budget_spent", extra={"limit": self.limit})
            return False
        self.spent += 1
        return True
