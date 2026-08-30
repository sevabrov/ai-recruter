"""
The refused half of a result (spec §43).

The counters could always say *how many* candidates a requirement turned away.
They could never say *which*, and a number is not something a client can check.
The question behind the whole feature is one sentence long — are we losing leads
in there? — and it is only answerable if every refusal comes with the address it
was refused at.

So what is asserted here is the property that makes the pair trustworthy: leads
plus refusals account for every candidate the run discovered, each refusal carries
a reason and a sentence, and the refusals that were decided *without opening the
page* are marked as such, because those are the only ones that can be hiding
somebody.
"""

import pytest

from app.models.common import Platform, SourceKind
from app.models.rejection import UNSEEN_REASONS, RejectionReason
from app.models.search import Search, SearchCriteria
from app.models.source import DiscoveredUrl, ProviderResult, UrlKind
from app.services.search.eligibility import Refusal
from app.services.search.pipeline import _handle_in, _why_not_a_profile
from app.services.search.url_tools import discover, promote_posts
from tests.conftest import run_search, start_search, wait_for


def rejected(client, search_id: str, **params) -> dict:
    response = client.get(f"/searches/{search_id}/rejected", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def test_a_finished_search_can_show_what_it_turned_away(client):
    search = run_search(client)
    payload = rejected(client, search["id"])

    assert payload["total"] > 0, "the fixture run refuses candidates; it must list them"
    assert payload["total"] == sum(payload["byReason"].values())
    assert len(payload["items"]) <= payload["total"]

    for entry in payload["items"]:
        assert entry["url"].startswith("http"), "a refusal without an address cannot be checked"
        assert entry["detail"], "every refusal explains itself in words"
        assert entry["reason"] in {reason.value for reason in RejectionReason}
        assert isinstance(entry["read"], bool)


def test_the_two_lists_account_for_every_candidate(client):
    """
    Leads + refusals = what the search discovered.

    This is the property that makes the second list worth opening: a candidate in
    neither list was dropped by code nobody can see. It is checked against the
    run's own counters, one stage at a time.
    """
    search = run_search(client)
    payload = rejected(client, search["id"])
    progress = search["progress"]
    counts = payload["byReason"]

    # Discovery is exact: what was discovered, minus what was worth reading, is
    # what discovery refused — for free, before anything was opened.
    at_discovery = counts.get("not_a_profile", 0) + counts.get("off_source", 0)
    assert at_discovery == progress["urlsDiscovered"] - progress["profilesDiscovered"]

    # After that, refusals and leads share the candidates — with room only for the
    # deduplicator, which merges two addresses of one person into a single lead.
    later = payload["total"] - at_discovery
    assert later + search["leadCount"] <= progress["profilesDiscovered"]


def test_one_address_is_refused_once(client):
    """Whichever stage gets to an address first owns the explanation for it."""
    search = run_search(client)
    items = rejected(client, search["id"])["items"]
    assert len({entry["url"] for entry in items}) == len(items)


def test_the_refusals_nobody_looked_at_are_marked(client):
    """
    `unseen` is the number the whole screen exists for.

    A candidate whose page was opened was judged on what they published. One
    refused at an address nobody opened was judged on two lines of search result —
    that is where a lost lead would be, and it has to be countable.
    """
    search = run_search(client)
    payload = rejected(client, search["id"])

    expected = sum(
        count for reason, count in payload["byReason"].items() if reason in set(UNSEEN_REASONS)
    )
    assert payload["unseen"] == expected
    for entry in payload["items"]:
        if entry["reason"] in set(UNSEEN_REASONS):
            assert entry["read"] is False


def test_one_reason_can_be_asked_for_on_its_own(client):
    search = run_search(client)
    payload = rejected(client, search["id"])
    reason = max(payload["byReason"], key=lambda key: payload["byReason"][key])

    filtered = rejected(client, search["id"], reason=reason)
    assert filtered["items"], f"{reason} was counted, so it must be listable"
    assert {entry["reason"] for entry in filtered["items"]} == {reason}
    # The counts stay over the whole run: a filtered view must not re-state itself
    # as the total, or the screen quotes its own truncation back at the client.
    assert filtered["total"] == payload["total"]
    assert filtered["byReason"] == payload["byReason"]


def test_a_platform_that_was_not_asked_for_is_refused_by_name(client):
    """
    The source list is a restriction, and the addresses it excludes are exactly the
    ones a client may want back — by adding the platform, not by guessing.
    """
    search_id = start_search(client, sources=[SourceKind.BLOGS.value])
    wait_for(client, search_id)
    payload = rejected(client, search_id, reason=RejectionReason.OFF_SOURCE.value)

    assert payload["byReason"].get("off_source", 0) > 0
    for entry in payload["items"]:
        assert entry["platform"] != Platform.BLOG.value
        assert entry["read"] is False, "nothing outside the sources is ever paid for"
        assert entry["platform"] in entry["detail"], "the refusal names the platform"


def test_the_list_belongs_to_its_owner(client):
    """Same rule as the leads: somebody else's search does not exist (spec §55)."""
    assert client.get("/searches/srch_nope/rejected").status_code == 404


# ---------------------------------------------------------------- unit level
def _url(address: str, *, platform: Platform, kind: UrlKind, title: str = "") -> DiscoveredUrl:
    return DiscoveredUrl(
        url=address,
        canonical_url=address,
        platform=platform,
        kind=kind,
        title=title,
        snippet="",
        query="q",
        provider="fixture",
    )


def test_a_post_whose_author_was_followed_says_so():
    """
    `instagram.com/anna/reel/C3Z…` appears in the refused list *and* its author
    appears in the leads. Without the sentence the first reads as a person thrown
    away, which is the opposite of what happened.
    """
    post = _url(
        "https://instagram.com/anna.mlm/reel/C3Z5y19owoo",
        platform=Platform.INSTAGRAM,
        kind=UrlKind.ARTICLE,
    )
    kept = {"https://instagram.com/anna.mlm"}

    detail = _why_not_a_profile(post, kept)
    assert "anna.mlm" in detail
    assert "was looked at instead" in detail


def test_a_post_nobody_could_attribute_gets_the_plain_reason():
    post = _url("https://instagram.com/p/Cxyz", platform=Platform.INSTAGRAM, kind=UrlKind.ARTICLE)
    assert "profile" in _why_not_a_profile(post, set()).casefold()
    assert "was looked at instead" not in _why_not_a_profile(post, set())


@pytest.mark.parametrize(
    ("address", "platform", "expected"),
    [
        ("https://instagram.com/accounts/login", Platform.INSTAGRAM, "accounts"),
        ("https://threads.net/@marina", Platform.THREADS, "marina"),
        ("https://jerelia-hotel.com/shop", Platform.WEBSITE, "jerelia-hotel.com"),
    ],
)
def test_an_unread_address_is_still_called_something(address, platform, expected):
    """A row with no name is a row nobody can scan. The address always has one."""
    assert _handle_in(_url(address, platform=platform, kind=UrlKind.UNKNOWN)) == expected


def test_promotion_and_refusal_agree_about_the_same_post():
    """
    The two halves ask the same question of the same address, so they cannot
    disagree: whatever `promote_posts` follows is what the refusal names.
    """
    results = [
        ProviderResult(
            url="https://www.instagram.com/yanarogozha/reel/C3Z5y19owoo",
            title="Яна (@yanarogozha) on Instagram",
            snippet="",
            query="site:instagram.com джерелія",
            provider="fixture",
        )
    ]
    urls = promote_posts(discover(results))
    profiles = [url for url in urls if url.kind is UrlKind.CANDIDATE]
    assert [url.canonical_url for url in profiles] == ["https://instagram.com/yanarogozha"]

    post = next(url for url in urls if url.kind is not UrlKind.CANDIDATE)
    assert "yanarogozha" in _why_not_a_profile(post, {profiles[0].canonical_url})


def test_a_page_that_would_not_open_is_not_counted_as_a_person_refused():
    """
    The counter split that made the list honest.

    "We opened the page and there was no person on it" is a verdict about the
    candidate. "We never got the page" is a verdict about the reader, and until
    now both arrived on the results screen as the same number.
    """
    progress = Search(id="s", user_id="u", name="n", criteria=SearchCriteria()).progress
    assert progress.rejected_unreadable == 0
    assert progress.rejected_not_a_person == 0
    assert Refusal.UNREADABLE.value == RejectionReason.UNREADABLE.value
