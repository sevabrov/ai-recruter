"""
A post is not a person — its author may well be one (spec §31–32).

One measured run (Network Marketing Leaders — Poland) refused 34 addresses as
"not a profile". Sixteen were posts whose author *was* followed, and five of
those authors were then refused for "no mlm" and "no activity" while the post that
found them was literally titled "Czym jest network marketing?" and dated. Seven
more were Instagram posts naming nobody in the address, thrown away unread. And a
public figure's Page ("Piotr Krenig …, promotor MLM") was refused as a brand for
having likes.

What is asserted here is each of those, fixed: the author is found wherever the
platform writes them down, the post travels with the author as evidence, a dated
post is the activity it is, and the refused post says what became of its author.
"""

import asyncio
from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.models.common import Platform, SignalType, SourceKind
from app.models.lead import Lead, LeadSignal
from app.models.profile import ExtractedProfile
from app.models.rejection import RejectedCandidate, RejectionReason
from app.models.search import Requirement, Search, SearchCriteria
from app.models.source import DiscoveredUrl, LeadSource, LeadSourceKind, ProviderResult, UrlKind
from app.services.extraction import personhood
from app.services.extraction.posts import POST_ACTIVITY_CONFIDENCE, with_posts
from app.services.extraction.signal_detector import LlmSignalDetector, profile_text
from app.services.scraping.browser_reader import parse_post
from app.services.scraping.snippet_extractor import SnippetProfileExtractor
from app.services.search.pipeline import SearchPipeline, _with_author_outcomes
from app.services.search.url_tools import (
    attach_posts,
    author_profile,
    candidates,
    discover,
    needs_opening,
    promote_posts,
)

SOCIAL = [SourceKind.INSTAGRAM_PUBLIC, SourceKind.FACEBOOK_PUBLIC, SourceKind.LINKEDIN_PUBLIC]


def result(url: str, title: str = "", snippet: str = "", age: datetime | None = None):
    return ProviderResult(
        url=url, title=title, snippet=snippet, query="q", provider="brave", page_age=age
    )


def by_url(urls: list[DiscoveredUrl]) -> dict[str, DiscoveredUrl]:
    return {url.canonical_url: url for url in urls}


# --------------------------------------------------------------- finding authors
def test_a_linkedin_post_names_its_author_before_the_underscore():
    urls = promote_posts(
        discover(
            [
                result(
                    "https://www.linkedin.com/posts/anna-kowalska-7b1a2_networkmarketing-"
                    "activity-7123456789012345678-AbCd",
                    "Anna Kowalska on LinkedIn: Dlaczego network marketing?",
                )
            ]
        )
    )
    kept = candidates(urls, SOCIAL)

    assert [url.canonical_url for url in kept] == ["https://linkedin.com/in/anna-kowalska-7b1a2"]
    assert kept[0].posts and "Dlaczego network marketing" in kept[0].posts[0].title


def test_a_facebook_story_permalink_names_its_author_by_id():
    url = discover(
        [result("https://www.facebook.com/permalink.php?story_fbid=1234&id=100012345678901")]
    )[0]

    assert url.kind is not UrlKind.CANDIDATE, "permalink.php is not somebody's handle"
    assert author_profile(url) == "https://facebook.com/profile.php?id=100012345678901"


def test_every_post_by_one_author_travels_with_their_profile():
    old = datetime.now(UTC) - timedelta(days=400)
    recent = datetime.now(UTC) - timedelta(days=5)
    urls = promote_posts(
        discover(
            [
                result("https://www.instagram.com/lidiadabr/reel/AAA", "Dlaczego MLM?", age=old),
                result("https://www.instagram.com/lidiadabr/p/BBB", "Mój zespół", age=recent),
            ]
        )
    )
    found = by_url(urls)
    profile = found["https://instagram.com/lidiadabr"]

    assert [post.title for post in profile.posts] == ["Mój zespół", "Dlaczego MLM?"], "newest first"
    assert found["https://instagram.com/lidiadabr/reel/AAA"].author_url == profile.canonical_url


def test_a_profile_found_on_its_own_still_gets_the_posts():
    urls = promote_posts(
        discover(
            [
                result("https://www.instagram.com/lidiadabr", "Lidia (@lidiadabr)"),
                result("https://www.instagram.com/lidiadabr/reel/AAA", "Dlaczego MLM?"),
            ]
        )
    )
    profile = by_url(urls)["https://instagram.com/lidiadabr"]

    assert profile.title == "Lidia (@lidiadabr)", "the profile's own result is kept"
    assert [post.title for post in profile.posts] == ["Dlaczego MLM?"]


def test_an_instagram_post_that_names_nobody_is_marked_for_opening():
    urls = promote_posts(discover([result("https://www.instagram.com/p/DKhU1v5IW52/", "Czy…")]))
    post = urls[0]

    assert needs_opening(post)
    opened = post.model_copy(
        update={"author_url": "https://instagram.com/renata.kierszka", "snippet": "Czy MLM…"}
    )
    after = attach_posts(urls, [opened])
    author = by_url(after)["https://instagram.com/renata.kierszka"]

    assert author.kind is UrlKind.CANDIDATE
    assert author.posts[0].snippet == "Czy MLM…"
    assert by_url(after)[post.canonical_url].author_url == author.canonical_url
    assert candidates(after, SOCIAL) == [author]


def test_a_post_page_says_who_published_it_and_when():
    handle, published, caption = parse_post(
        '32 likes, 2 comments - renata.kierszka on June 5, 2025: "Czy marketing sieciowy '
        "to piramida finansowa? 💵😎\n\nNie, to nie piramida"
    )

    assert handle == "renata.kierszka"
    assert published == datetime(2025, 6, 5, tzinfo=UTC)
    assert caption.startswith("Czy marketing sieciowy to piramida finansowa?")
    assert parse_post("Instagram") is None
    assert parse_post("Log into Instagram") is None


def test_opening_posts_turns_their_authors_into_candidates():
    class Reader:
        async def read_post(self, url):
            return url.model_copy(update={"author_url": "https://instagram.com/monika_w"})

    pipeline = SearchPipeline.__new__(SearchPipeline)
    pipeline.post_reader = Reader()
    pipeline.settings = Settings()
    search = Search(
        id="s",
        user_id="u",
        name="n",
        criteria=SearchCriteria(sources=[SourceKind.INSTAGRAM_PUBLIC]),
    )
    urls = promote_posts(discover([result("https://www.instagram.com/reel/C84TeepIrOQ/", "x")]))

    after = asyncio.run(pipeline._open_posts(search, urls))

    assert "https://instagram.com/monika_w" in by_url(after)


def test_posts_are_not_opened_when_instagram_was_not_asked_for():
    class Reader:
        async def read_post(self, url):  # pragma: no cover - must not be called
            raise AssertionError("opened a post on a platform nobody asked for")

    pipeline = SearchPipeline.__new__(SearchPipeline)
    pipeline.post_reader = Reader()
    pipeline.settings = Settings()
    search = Search(
        id="s", user_id="u", name="n", criteria=SearchCriteria(sources=[SourceKind.LINKEDIN_PUBLIC])
    )
    urls = promote_posts(discover([result("https://www.instagram.com/p/X1/", "x")]))

    assert asyncio.run(pipeline._open_posts(search, urls)) == urls


# ------------------------------------------------------------- posts as evidence
def _profile(url: DiscoveredUrl, **update) -> ExtractedProfile:
    return ExtractedProfile(
        url=url.url,
        canonical_url=url.canonical_url,
        platform=url.platform,
        name="Aga Przybylska",
        summary="Kreatorka kariery | Liderka",
        sources=[
            LeadSource(
                id="src_1", platform=url.platform, url=url.url, title=url.title, snippet=url.snippet
            )
        ],
        **update,
    )


def _promoted(age: datetime | None) -> DiscoveredUrl:
    urls = promote_posts(
        discover(
            [
                result(
                    "https://www.facebook.com/aga.przybylska.1/videos/czym-jest-network-marketing/1",
                    "Czym jest network marketing? Marketing sieciowy kształtuje liderów",
                    age=age,
                )
            ]
        )
    )
    return by_url(urls)["https://facebook.com/aga.przybylska.1"]


def test_the_post_becomes_a_source_of_its_own_kind():
    url = _promoted(None)
    profile = with_posts(_profile(url), url)

    posts = [source for source in profile.sources if source.kind is LeadSourceKind.POST]
    assert len(posts) == 1 and "network marketing" in posts[0].title
    assert "/videos/" in posts[0].url, "the post's own address, not the profile's"
    assert len(profile.sources) == 1, "the reader's copy of the post result is replaced"
    assert "Their own post: Czym jest network marketing?" in profile_text(profile)


def test_a_recent_post_is_activity_and_an_old_one_is_not():
    recent = _promoted(datetime.now(UTC) - timedelta(days=3))
    old = _promoted(datetime.now(UTC) - timedelta(days=900))

    def activity(url):
        profile = with_posts(_profile(url), url)
        return next((s for s in profile.observations if s.type == SignalType.ACTIVITY), None)

    seen = activity(recent)
    assert seen is not None and seen.detected
    assert seen.confidence == POST_ACTIVITY_CONFIDENCE
    assert "Published a post on" in seen.evidence and "/videos/" in seen.source_url
    assert activity(old) is None
    assert "(published " in profile_text(with_posts(_profile(recent), recent))


def test_the_judge_cannot_unsee_a_date_it_was_never_shown():
    requirement = Requirement(id=SignalType.ACTIVITY, importance="required")
    profile = ExtractedProfile(url="u", canonical_url="u", platform=Platform.FACEBOOK, name="A B")
    dated = LeadSignal(type=SignalType.ACTIVITY, detected=True, confidence=0.6, evidence="Posted")
    counted = dated.model_copy(update={"confidence": 0.4, "evidence": "13 posts"})
    said_no = {"met": False, "evidence": "", "confidence": 0}

    kept = LlmSignalDetector._verdict(dated, requirement, said_no, "text", profile)
    dropped = LlmSignalDetector._verdict(counted, requirement, said_no, "text", profile)

    assert kept.detected, "a post's date is a fact the code read"
    assert not dropped.detected, "a post count says nothing about recency"


# --------------------------------------------------------- public-figure Pages
def test_a_public_figures_page_is_named_after_them():
    url = discover(
        [
            result(
                "https://www.facebook.com/PiotrKrenigPrzedsiebiorca",
                "Piotr Krenig o przedsiębiorczości, marketingu i rozwoju | Facebook",
                "Piotr Krenig - przedsiębiorca, mówca motywacyjny, mentor i promotor MLM.",
            )
        ]
    )[0]
    profile = asyncio.run(SnippetProfileExtractor().extract(url))

    assert profile is not None and profile.name == "Piotr Krenig"
    assert profile.headline and profile.headline.startswith("o przedsiębiorczości")


def test_a_leading_name_the_address_does_not_spell_is_not_taken():
    url = discover(
        [result("https://www.facebook.com/somepage", "Network Marketing o sukcesie | Facebook")]
    )[0]

    assert asyncio.run(SnippetProfileExtractor().extract(url)) is None


def test_likes_alone_do_not_make_a_person_a_brand():
    def page(name: str) -> ExtractedProfile:
        return ExtractedProfile(
            url="https://facebook.com/x",
            canonical_url="https://facebook.com/x",
            platform=Platform.FACEBOOK,
            name=name,
            summary=f"{name}. 20,872 likes · 131 talking about this.",
        )

    assert personhood.assess(page("Piotr Krenig")).is_person
    assert not personhood.assess(page("Zdrowie i uroda")).is_person
    magazine = page("Anna Nowak").model_copy(update={"summary": "1,200 likes · Magazine"})
    assert not personhood.assess(magazine).is_person, "a category still refuses"


# ------------------------------------------------------------ the refused post
def _refused(url: str, reason: RejectionReason, **extra) -> RejectedCandidate:
    return RejectedCandidate(
        id=url,
        user_id="u",
        search_id="s",
        url=url,
        canonical_url=url,
        platform=Platform.INSTAGRAM,
        reason=reason,
        **extra,
    )


def test_a_refused_post_says_what_became_of_its_author():
    post_a = _refused("p/a", RejectionReason.NOT_A_PROFILE, author_url="https://instagram.com/a")
    post_b = _refused("p/b", RejectionReason.NOT_A_PROFILE, author_url="https://instagram.com/b")
    post_c = _refused("p/c", RejectionReason.NOT_A_PROFILE, author_url="https://instagram.com/c")
    author_b = _refused("https://instagram.com/b", RejectionReason.WRONG_COUNTRY, name="Yana")
    lead = Lead(
        id="l",
        user_id="u",
        search_id="s",
        search_name="n",
        name="Anna",
        headline="",
        score=70,
        summary="",
        merged_urls=["https://instagram.com/a"],
    )

    out = {
        entry.id: entry
        for entry in _with_author_outcomes([post_a, post_b, post_c, author_b], [lead])
    }

    assert (out["p/a"].author_outcome, out["p/a"].author_name) == ("lead", "Anna")
    assert (out["p/b"].author_outcome, out["p/b"].author_name) == ("wrong_country", "Yana")
    assert out["p/c"].author_outcome is None, "never judged: nothing to say"
