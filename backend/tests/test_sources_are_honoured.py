"""
Look only where you were told to look (spec §29, §31–32).

A run asked for Instagram, LinkedIn and Facebook, in Russian and Ukrainian, for
ten leads. It produced one, and the one was this:

    https://pravo.ua/articles/setevoj-marketing/
    name: "СЕТЕВОЙ МАРКЕТИНГ"   headline: "PRAVO.UA"

A legal journal's article about network-marketing legislation. Three separate
defects let it through, and each one gets a test here, because any single fix
would have hidden the other two:

* **the queries left the sources.** Three of the templates carry no `site:`
  operator, so with only social sources selected roughly a third of the billed
  calls searched the whole web.
* **the URL was not recognised as an article.** The hint list held `/article/`
  and the URL says `/articles/`, so it fell through to "unknown", which is the
  bucket a personal website lives in and is therefore kept.
* **the name looked like a person.** Two capitalised words, no company noun, no
  place, and a Russian summary with no corporate voice: every existing rule
  passed it. What gives it away is that the name is nothing but the vocabulary
  the search itself is built from.

The fourth test is the rule the client stated: *"искать только там где указал
пользователь"* — enforced at discovery as well as in the queries, because a
`site:` operator is a request and not a guarantee.
"""

import pytest

from app.models.common import Platform, SourceKind
from app.models.profile import ExtractedProfile
from app.models.search import SearchCriteria
from app.models.source import DiscoveredUrl, ProviderResult, UrlKind
from app.services.extraction import personhood
from app.services.scraping.snippet_extractor import SnippetProfileExtractor
from app.services.search.query_generator import TemplateQueryGenerator
from app.services.search.url_tools import candidates, classify, discover, promote_posts

pytestmark = pytest.mark.anyio

SOCIAL = [
    SourceKind.INSTAGRAM_PUBLIC.value,
    SourceKind.LINKEDIN_PUBLIC.value,
    SourceKind.FACEBOOK_PUBLIC.value,
]


def criteria(**overrides) -> SearchCriteria:
    return SearchCriteria.model_validate(
        {
            "keywords": ["network marketing", "beauty"],
            "industry": ["beauty"],
            "business_types": ["MLM"],
            "location": {"country": "Ukraine"},
            "languages": ["Russian", "Ukrainian"],
            "must_have": ["mlm"],
            "sources": SOCIAL,
            **overrides,
        }
    )


def result(url: str, title: str = "", snippet: str = "") -> ProviderResult:
    return ProviderResult(
        url=url, title=title, snippet=snippet, query="q", provider="brave", language="ru"
    )


# ------------------------------------------------------- the queries stay on-source


def test_no_query_leaves_the_selected_sources():
    plans = TemplateQueryGenerator().generate(criteria(), limit=24)

    assert plans
    for plan in plans:
        assert "site:" in plan.query, plan.query


def test_asking_for_the_open_web_brings_the_open_web_queries_back():
    plans = TemplateQueryGenerator().generate(
        criteria(sources=[*SOCIAL, SourceKind.PUBLIC_WEB.value]), limit=24
    )

    assert any("site:" not in plan.query for plan in plans)


def test_no_hashtag_queries_are_generated():
    """
    They looked obviously right — a hashtag is how somebody labels themselves — and
    measurement said otherwise: all six generated hashtag queries returned exactly
    zero results, a third of that run's billed calls. A quoted `"#tag"` inside a
    `site:` query is not a question the index answers.

    Hashtags belong in `customQueries`, where the client writes the form that works
    for their market and sees at once whether it returns anything.
    """
    plans = TemplateQueryGenerator().generate(criteria(), limit=24)

    assert plans, "the generator must still produce queries"
    assert not [plan for plan in plans if "#" in plan.query]


def test_a_hashtag_the_client_writes_is_still_run():
    written = 'site:instagram.com "#млмукраина"'

    plans = TemplateQueryGenerator().generate(criteria(custom_queries=[written]), limit=24)

    assert plans[0].query == written


# -------------------------------------------------- and neither do the results kept


def test_a_news_site_is_dropped_when_only_social_sources_were_asked_for():
    urls = discover(
        [
            result(
                "https://pravo.ua/articles/setevoj-marketing/",
                "СЕТЕВОЙ МАРКЕТИНГ - PRAVO.UA",
                "Авторы законопроекта считают…",
            ),
            result(
                "https://www.instagram.com/oksana.mlm/",
                "Оксана (@oksana.mlm) • Instagram",
                "Дистриб'ютор, Київ",
            ),
        ]
    )

    kept = candidates(urls, criteria().sources)

    assert [url.platform for url in kept] == [Platform.INSTAGRAM]


def test_the_open_web_is_kept_when_it_was_asked_for():
    urls = discover([result("https://oksanabeauty.com.ua/pro-mene", "Оксана Мельник — про мене")])

    assert candidates(urls, [SourceKind.PUBLIC_WEB.value])
    assert not candidates(urls, criteria().sources)


def test_no_sources_at_all_restricts_nothing():
    """An empty source list is "nothing was asked for", not "nothing is allowed"."""
    urls = discover([result("https://oksanabeauty.com.ua/pro-mene", "Оксана Мельник")])

    assert candidates(urls, []) == candidates(urls)


def test_an_articles_url_is_an_article():
    """`/article/` was in the hint list. The URL that got through says `/articles/`."""
    assert classify("https://pravo.ua/articles/setevoj-marketing", Platform.WEBSITE) is (
        UrlKind.ARTICLE
    )
    assert classify("https://blog.example.com/2026/08/mlm", Platform.WEBSITE) is UrlKind.ARTICLE
    # A person's own page still is not an article.
    assert classify("https://oksanabeauty.com.ua/pro-mene", Platform.WEBSITE) is UrlKind.UNKNOWN


# --------------------------------------------------------- and the name is checked


async def test_the_headline_of_an_article_is_not_a_person():
    profile = await SnippetProfileExtractor().extract(
        DiscoveredUrl(
            url="https://pravo.ua/articles/setevoj-marketing/",
            canonical_url="https://pravo.ua/articles/setevoj-marketing",
            platform=Platform.WEBSITE,
            kind=UrlKind.UNKNOWN,
            title="СЕТЕВОЙ МАРКЕТИНГ - PRAVO.UA",
            snippet="Авторы и сторонники законопроекта считают, что он будет содействовать…",
            query="q",
            provider="brave",
            language="ru",
        )
    )

    # The extractor still reads a name out of the title — it is shaped like one.
    # The gate is what refuses it, and it says which rule did.
    assert profile is not None
    verdict = personhood.assess(profile)
    assert not verdict.is_person
    assert "subject being searched for" in verdict.detail


def test_a_publication_as_a_name_is_not_a_person():
    """The article's headline was "СЕТЕВОЙ МАРКЕТИНГ"; its byline was "PRAVO.UA"."""
    verdict = personhood.assess(_named("PRAVO.UA"))

    assert not verdict.is_person
    assert "web address" in verdict.detail


def _named(name: str) -> ExtractedProfile:
    return ExtractedProfile(
        url="https://pravo.ua/",
        canonical_url="https://pravo.ua/",
        platform=Platform.WEBSITE,
        name=name,
        extractor="snippet",
    )


# ------------------------------------------------- a post is exchanged for a person


def test_a_hashtag_result_becomes_the_person_who_posted_it():
    """
    A hashtag search returns posts, and a post is not a profile — but its title
    names the author, and the author is who the search was for.
    """
    urls = discover(
        [
            result(
                "https://www.instagram.com/p/C9xYzAbCdEf/",
                'Марина Іванова (@marina.mlm) on Instagram: "Мій шлях у мережевому маркетингу"',
                "#мережевиймаркетинг #київ",
            )
        ]
    )

    promoted = promote_posts(urls)
    kept = candidates(promoted, [SourceKind.INSTAGRAM_PUBLIC.value])

    assert [url.canonical_url for url in kept] == ["https://instagram.com/marina.mlm"]
    # The post's own words travel with it: that is the evidence that was found.
    assert "#мережевиймаркетинг" in kept[0].snippet


def test_a_post_nobody_signed_is_left_alone():
    urls = discover([result("https://www.instagram.com/p/C9xYzAbCdEf/", "Instagram", "Photo")])

    assert candidates(promote_posts(urls), [SourceKind.INSTAGRAM_PUBLIC.value]) == []


def test_the_address_of_a_post_names_its_author_and_that_is_enough():
    """
    The loss this fixes, verbatim from a run that returned nobody: three real
    people thrown away as "not a person" because we looked at their reel instead
    of at them, while their handle sat in the first segment of the URL.

        instagram.com/yanarogozha/reel/C3Z5y19owoo
        instagram.com/iriska.kononova/reel/DDHwmwvtuTo
        facebook.com/ajzan.balakesova/videos/сетевой-маркетинг-vs-…

    No title needed and nothing inferred: `{handle}/{reel|p|videos|posts}/…` is the
    platform writing the author down.
    """
    urls = discover(
        [
            result("https://www.instagram.com/yanarogozha/reel/C3Z5y19owoo", "Instagram"),
            result("https://www.instagram.com/iriska.kononova/reel/DDHwmwvtuTo", "Instagram"),
            result("https://www.facebook.com/ajzan.balakesova/videos/сетевой-маркетинг/9571", "FB"),
        ]
    )

    kept = candidates(promote_posts(urls), SOCIAL)

    assert sorted(url.canonical_url for url in kept) == [
        "https://facebook.com/ajzan.balakesova",
        "https://instagram.com/iriska.kononova",
        "https://instagram.com/yanarogozha",
    ]


def test_two_posts_by_one_person_are_one_candidate():
    """`yanarogozha` appeared twice in that run — as a reel and as a post."""
    urls = discover(
        [
            result("https://www.instagram.com/yanarogozha/reel/C3Z5y19owoo", "Instagram"),
            result("https://www.instagram.com/yanarogozha/p/CEw0oqXnG-L", "Instagram"),
        ]
    )

    kept = candidates(promote_posts(urls), SOCIAL)

    assert [url.canonical_url for url in kept] == ["https://instagram.com/yanarogozha"]


def test_the_platform_s_own_pages_are_not_people():
    """
    Each of these reached the scoring stage and was counted as "not a person",
    which reads on the results screen as "the search found somebody unsuitable".
    It found a login form, a photograph, a page's internal id and a directory.
    """
    urls = discover(
        [
            result("https://www.instagram.com/accounts/login", "Login • Instagram"),
            result("https://www.facebook.com/photo.php?fbid=8880867795335349", "Facebook"),
            result("https://www.facebook.com/581399108893746", "Facebook"),
            result("https://www.instagram.com/popular/сетевой-маркетинг-обучение", "Instagram"),
        ]
    )

    assert candidates(promote_posts(urls), SOCIAL) == []


def test_a_real_profile_still_passes():
    """The shape check must not cost the thing it protects."""
    urls = discover(
        [
            result("https://www.instagram.com/oksana.beauty.ua/", "Оксана"),
            result("https://www.facebook.com/farmasiukraine", "Farmasi Ukraine"),
            result("https://www.linkedin.com/in/mborodaenko", "M. Borodaenko"),
        ]
    )

    kept = candidates(promote_posts(urls), SOCIAL)

    assert len(kept) == 3, "a page that names itself is a candidate; personhood judges it later"


def test_a_profile_that_is_already_known_is_not_promoted_twice():
    urls = discover(
        [
            result(
                "https://www.instagram.com/p/C9xYzAbCdEf/",
                'Марина (@marina.mlm) on Instagram: "…"',
            ),
            result("https://www.instagram.com/marina.mlm/", "Марина (@marina.mlm) • Instagram"),
        ]
    )

    promoted = promote_posts(urls)

    assert len([url for url in promoted if url.canonical_url.endswith("marina.mlm")]) == 1


# ----------------------------------------------------------- the client's own query


def test_a_query_the_client_wrote_is_run_first_and_never_dropped():
    written = 'site:instagram.com "#млмукраина" "#бизнесонлайн"'

    plans = TemplateQueryGenerator().generate(criteria(custom_queries=[written]), limit=3)

    assert plans[0].query == written
    assert len(plans) == 3, "the cap should have eaten a template, not the client's query"


def test_a_cyrillic_query_reaches_the_cyrillic_index():
    plans = TemplateQueryGenerator().generate(
        criteria(custom_queries=['site:instagram.com "#млмукраїна"']), limit=6
    )

    assert plans[0].language == "uk"


def test_a_query_with_no_site_operator_inherits_the_sources():
    """
    What the client typed was `джерелія` — the right word, asked of the whole
    indexed web. Brave answered with the brand's own site, four shops, a
    catalogue, an app-store listing and a hotel called Jerelia; 18 of those 20
    results were then dropped as off-source. They meant "find me this on the
    platforms I chose", so that is the question now asked.
    """
    plans = TemplateQueryGenerator().generate(criteria(custom_queries=["джерелія"]), limit=24)

    written = [plan.query for plan in plans[:3]]
    assert written == [
        "site:instagram.com джерелія",
        "site:linkedin.com/in джерелія",
        "site:facebook.com джерелія",
    ]
    # The language belongs to the client's word, not to the operator in front of it.
    assert {plan.language for plan in plans[:3]} == {"uk"}


def test_a_bare_query_stays_bare_when_the_open_web_was_asked_for():
    """Then it is a fair question, and scoping it would narrow what was wanted."""
    plans = TemplateQueryGenerator().generate(
        criteria(custom_queries=["джерелія"], sources=[*SOCIAL, SourceKind.PUBLIC_WEB.value]),
        limit=24,
    )

    assert plans[0].query == "джерелія"


def test_a_query_that_names_its_own_site_is_left_exactly_as_written():
    plans = TemplateQueryGenerator().generate(
        criteria(custom_queries=['site:instagram.com "джерелія" консультант']), limit=24
    )

    assert plans[0].query == 'site:instagram.com "джерелія" консультант'


def test_blank_and_duplicate_queries_are_ignored():
    plans = TemplateQueryGenerator().generate(
        criteria(custom_queries=["  ", 'site:instagram.com "#млм"', 'site:instagram.com "#млм"']),
        limit=6,
    )

    assert [plan.query for plan in plans].count('site:instagram.com "#млм"') == 1


def test_facebook_s_other_profile_addresses_are_followed():
    """
    `/p/Name-ID`, `/people/Name/ID` and `profile.php?id=` are somebody's (or some
    page's) own address; whether it is a person is the judge's call, not the URL's.
    A page addressed by number is followed from its photos to the page itself.
    """
    urls = discover(
        [
            result("https://www.facebook.com/p/Мережевий-маркетинг-100067957290251", "Facebook"),
            result("https://www.facebook.com/people/Олена-Коваль/100090/", "Facebook"),
            result("https://www.facebook.com/100066734753457/photos/a.1/2/", "МЛМ"),
        ]
    )

    kept = {url.canonical_url for url in candidates(promote_posts(urls), SOCIAL)}

    assert "https://facebook.com/p/Мережевий-маркетинг-100067957290251" in kept
    assert "https://facebook.com/people/Олена-Коваль/100090" in kept
    assert "https://facebook.com/100066734753457" in kept
