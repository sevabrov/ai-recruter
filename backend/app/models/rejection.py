"""
The other half of a search result (spec §43).

The refusal *counters* answer "how many", and that was enough while the question
was whether the criteria were too strict. It is not enough for the question the
client actually asks after a thin run: **are we losing leads in there?** A number
cannot be checked. A list of addresses can be opened in a browser.

So every candidate a run turned away is stored with the address it was found at
and the reason in words. Together with the leads it is a complete account of what
the search saw — every discovered URL ends up in exactly one of the two lists —
and that is what makes the second list worth reading: a refusal that turns out to
be a real person is a bug with a URL attached to it, not a suspicion.

`read` is the field to look at first. A candidate refused on the evidence of a
page that was actually opened was judged on what the person published; one
refused on a two-line search snippet was judged on almost nothing, and that is
where a lost lead hides.
"""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.common import Platform


class RejectionReason(StrEnum):
    """
    Why a candidate is not in the lead list.

    The four middle values are `eligibility.Refusal` spelled the same way on
    purpose — one refusal is one string, whichever half of the pipeline recorded
    it. The other four are the stages that refuse *before* anything is judged.
    """

    #: The address is not a person's page at all: a shop, an article, a login form,
    #: a numeric page id. Refused at discovery, before anything was paid for.
    NOT_A_PROFILE = "not_a_profile"
    #: A profile, but on a platform this search was not given as a source.
    OFF_SOURCE = "off_source"
    #: The reader failed on this address, so nothing was ever read from it.
    UNREADABLE = "unreadable"
    NOT_A_PERSON = "not_a_person"
    WRONG_COUNTRY = "wrong_country"
    WRONG_LANGUAGE = "wrong_language"
    MISSING_SIGNALS = "missing_signals"
    #: The search already had the leads it was asked for and stopped. Never opened,
    #: never paid for — and the one refusal that says nothing about the candidate.
    NOT_EXAMINED = "not_examined"


#: Reasons where nobody ever looked at the page. A lead can hide behind any of
#: them, which is exactly what the client wants to be able to check.
UNSEEN_REASONS = frozenset(
    {
        RejectionReason.NOT_A_PROFILE,
        RejectionReason.OFF_SOURCE,
        RejectionReason.UNREADABLE,
        RejectionReason.NOT_EXAMINED,
    }
)


class RejectedCandidate(BaseModel):
    """One candidate that did not become a lead, and why."""

    id: str
    user_id: str
    search_id: str

    url: str
    canonical_url: str
    platform: Platform

    reason: RejectionReason
    #: The sentence that explains this particular refusal. Written where the
    #: refusal happens, so it can name the country, the language or the signal.
    detail: str = ""
    #: Whether the page itself was opened. False means the verdict rests on the
    #: search result alone — the single most useful thing to know about a refusal.
    read: bool = False

    #: Whatever the run knew this candidate as: the name the extractor found, else
    #: the handle in the address.
    name: str = ""
    title: str = ""
    snippet: str = ""
    #: Which of the run's queries produced this address.
    query: str = ""
    #: What the search result alone supported, 0–100 (`search/prospects.py`).
    #: None when the candidate was refused before anything was computed for it.
    promise: int | None = None

    #: On a refused post: the profile of the account that published it, when the
    #: run followed it. The post is not a person; its author may well be one.
    author_url: str | None = None
    #: What the run knew the author as, once judged.
    author_name: str = ""
    #: What became of the author: "lead", or the `RejectionReason` they were
    #: refused for. None when the author was never judged (not reached, or no
    #: author could be named).
    author_outcome: str | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
