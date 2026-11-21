"""
Requirements written per search, and how a candidate is judged against them.

The product recruits for any role, so "Python" and "Django" have to be as much a
requirement as the built-in network-marketing signals. No test reaches OpenAI: the
judge takes its HTTP client, and its transport is a canned answer.
"""

import json

import httpx

from app.models.common import DEFAULT_SIGNAL_WEIGHTS, GeoLocation, Platform, SignalType
from app.models.profile import ExtractedProfile
from app.models.search import Importance, Requirement, SearchCriteria, balanced
from app.models.source import LeadSource
from app.services.extraction.signal_detector import (
    BudgetedSignalDetector,
    FixtureSignalDetector,
    LlmSignalDetector,
    profile_text,
    quoted,
)
from app.services.scoring.scoring_service import ScoringService


def developer() -> ExtractedProfile:
    return ExtractedProfile(
        url="https://www.linkedin.com/in/olena-dev/",
        canonical_url="https://linkedin.com/in/olena-dev",
        platform=Platform.LINKEDIN,
        name="Olena Kovalenko",
        headline="Senior Python Developer at SoftServe",
        location={"country": "Poland", "city": "Warszawa"},
        languages=["Ukrainian", "Polish"],
        summary="Backend engineer, 7 years of Python, FastAPI and PostgreSQL.",
        sources=[
            LeadSource(
                id="s1",
                platform=Platform.LINKEDIN,
                url="https://www.linkedin.com/in/olena-dev/",
                title="Olena Kovalenko – Senior Python Developer – SoftServe | LinkedIn",
                snippet="Warszawa · Python, FastAPI, PostgreSQL",
            )
        ],
    )


def developer_search() -> SearchCriteria:
    return SearchCriteria(
        keywords=["Python developer"],
        location={"country": "Poland"},
        requirements=balanced(
            [
                Requirement(id="r1", label="Python", terms=["Python"], importance="required"),
                Requirement(id="r2", label="Django", terms=["Django"], importance="high"),
                Requirement(id="location"),
            ]
        ),
    )


# ------------------------------------------------------------------- the points


def test_points_follow_importance_and_add_up_to_100():
    shared = balanced(
        [
            Requirement(id="a", importance=Importance.REQUIRED),
            Requirement(id="b", importance=Importance.HIGH),
            Requirement(id="c", importance=Importance.NORMAL),
            Requirement(id="activity", importance=Importance.REQUIRED),
        ]
    )

    weights = {r.id: r.weight for r in shared}
    assert sum(weights.values()) == 100
    assert weights["a"] > weights["b"] > weights["c"] > 0
    # Shown, never scored (spec §37).
    assert weights["activity"] == 0


def test_a_search_recorded_before_requirements_is_scored_as_it_was():
    legacy = SearchCriteria(must_have=[SignalType.MLM], signal_weights=DEFAULT_SIGNAL_WEIGHTS)

    derived = {r.id: r for r in legacy.effective_requirements()}

    assert {key: r.weight for key, r in derived.items()} == {
        str(key): value for key, value in DEFAULT_SIGNAL_WEIGHTS.items()
    }
    assert derived["mlm"].required and not derived["beauty"].required


# ------------------------------------------------------------- without a model


async def test_the_keyword_judge_quotes_the_requirements_words():
    signals = await FixtureSignalDetector().detect(developer(), developer_search())
    by_id = {s.type: s for s in signals}

    assert [s.type for s in signals] == ["r1", "r2", "location"]
    assert by_id["r1"].detected and "Python" in by_id["r1"].evidence
    assert by_id["r1"].label == "Python"
    assert not by_id["r2"].detected
    # The country is compared by code, and the profile's own country is the evidence.
    assert by_id["location"].detected and "Poland" in by_id["location"].evidence


async def test_the_score_is_the_requirements_arithmetic():
    criteria = developer_search()
    signals = await FixtureSignalDetector().detect(developer(), criteria)

    score, breakdown = ScoringService().score(signals, criteria.effective_requirements())

    assert [row.type for row in breakdown] == ["r1", "r2", "location"]
    assert [row.label for row in breakdown] == ["Python", "Django", None]
    assert breakdown[1].awarded == 0
    assert score == sum(row.awarded for row in breakdown) > 0


# ---------------------------------------------------------------- with a model


def judge(answer: dict | None = None, status: int = 200, seen: list | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(json.loads(request.content))
        if status != 200:
            return httpx.Response(status, json={"error": {"message": "down"}})
        reply = answer or {"results": []}
        if "candidates" not in reply:
            # One candidate, written in the single shape for readability.
            reply = {
                "candidates": [
                    {
                        "candidate": 1,
                        "is_person": reply.get("is_person", True),
                        "not_person_reason": reply.get("not_person_reason", ""),
                        "country": reply.get("country", ""),
                        "country_evidence": reply.get("country_evidence", ""),
                        "results": reply.get("results", []),
                    }
                ]
            }
        content = json.dumps(reply)
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    return LlmSignalDetector(
        "sk-test", "test-model", client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )


async def test_the_judge_keeps_what_it_can_quote_and_drops_what_it_cannot():
    answer = {
        "results": [
            {"id": "r1", "met": True, "confidence": 0.95, "evidence": "7 years of Python"},
            # Django is nowhere on the profile: an invented quote is a requirement not met.
            {"id": "r2", "met": True, "confidence": 0.9, "evidence": "Django REST expert"},
        ]
    }
    seen: list = []
    signals = await judge(answer, seen=seen).detect(developer(), developer_search())
    by_id = {s.type: s for s in signals}

    assert by_id["r1"].detected
    assert by_id["r1"].evidence == "7 years of Python"
    assert by_id["r1"].confidence == 0.9  # capped: a model's reading is not certainty
    assert not by_id["r2"].detected
    # The location is not the model's question.
    asked = seen[0]["messages"][-1]["content"]
    assert "id=r1" in asked and "id=location" not in asked
    assert by_id["location"].detected


async def test_a_failing_judge_falls_back_to_the_words_instead_of_losing_the_candidate():
    signals = await judge(status=500).detect(developer(), developer_search())

    assert {s.type: s.detected for s in signals} == {"r1": True, "r2": False, "location": True}


def test_a_quote_must_really_be_on_the_profile():
    text = profile_text(developer())

    assert quoted("senior   python developer", text)  # whitespace and case forgiven
    assert quoted("Senior Python Developer … FastAPI and PostgreSQL", text)
    assert not quoted("Senior Java Developer", text)
    assert not quoted("", text)


async def test_the_paid_judge_stops_at_the_search_budget():
    """Past the budget candidates are judged by their words, so the quote holds."""
    seen: list = []
    answer = {"results": [{"id": "r1", "met": True, "confidence": 0.9, "evidence": "Python"}]}
    budgeted = BudgetedSignalDetector(judge(answer, seen=seen), limit=2)

    for _ in range(5):
        signals = await budgeted.detect(developer(), developer_search())
        assert {s.type for s in signals} == {"r1", "r2", "location"}

    assert budgeted.paid_calls == 2
    assert len(seen) == 2


async def test_the_judge_says_when_a_page_is_not_a_person():
    """A lyceum called "Leader" passed the name heuristics; the judge reads the page."""
    answer = {
        "is_person": False,
        "not_person_reason": "A school's page.",
        "results": [{"id": "r1", "met": False, "confidence": 0, "evidence": ""}],
    }
    judgement = await judge(answer).assess(developer(), developer_search())

    assert judgement.is_person is False
    assert judgement.reason == "A school's page."


def test_a_country_outside_the_allowed_places_is_refused():
    from app.services.search.eligibility import admit

    criteria = SearchCriteria(countries=["Ukraine"], region="europe")
    abroad = developer().model_copy(update={"location": GeoLocation(country="Indonesia")})
    nearby = developer().model_copy(update={"location": GeoLocation(country="Romania")})

    assert not admit(abroad, criteria).admitted
    assert admit(nearby, criteria).admitted


def test_the_judging_budget_follows_the_leads_asked_for(settings):
    from app.services.search.estimate import judging_budget_for

    tuned = settings.model_copy(
        update={"judgements_per_lead": 10, "max_judgements_per_search": 300}
    )

    assert judging_budget_for(SearchCriteria(target_leads=10), tuned) == 100
    assert judging_budget_for(SearchCriteria(target_leads=5), tuned) == 50
    # The server's ceiling holds whatever is asked for.
    assert judging_budget_for(SearchCriteria(target_leads=100), tuned) == 300


async def test_a_batch_is_one_call_and_each_candidate_keeps_its_own_quotes():
    other = developer().model_copy(
        update={
            "url": "https://www.linkedin.com/in/ivan/",
            "canonical_url": "https://linkedin.com/in/ivan",
            "name": "Ivan Petrenko",
            "headline": "Django developer",
            "summary": "Builds Django apps.",
            "sources": [],
        }
    )
    answer = {
        "candidates": [
            {"candidate": 1, "is_person": True, "not_person_reason": "", "results": [
                {"id": "r1", "met": True, "confidence": 0.9, "evidence": "7 years of Python"},
            ]},
            # Candidate 2 quoting candidate 1's text: not on its own profile, not met.
            {"candidate": 2, "is_person": True, "not_person_reason": "", "results": [
                {"id": "r1", "met": True, "confidence": 0.9, "evidence": "7 years of Python"},
                {"id": "r2", "met": True, "confidence": 0.9, "evidence": "Builds Django apps."},
            ]},
        ]
    }  # fmt: skip
    seen: list = []
    first, second = await judge(answer, seen=seen).assess_many(
        [developer(), other], developer_search()
    )

    assert len(seen) == 1
    assert {s.type: s.detected for s in first.signals}["r1"] is True
    by_id = {s.type: s.detected for s in second.signals}
    assert by_id["r1"] is False
    assert by_id["r2"] is True


def smm_manager() -> ExtractedProfile:
    """An Instagram bio that names a town, not a country — no word list knows it."""
    return ExtractedProfile(
        url="https://www.instagram.com/bulutovav/",
        canonical_url="https://instagram.com/bulutovav",
        platform=Platform.INSTAGRAM,
        name="Булутова Виктория",
        summary="⚓️ Девушка из солнечной Мордовии 👩🏻‍💻 SMM-менеджер",
    )


def kyiv_smm_search() -> SearchCriteria:
    return SearchCriteria(
        keywords=["SMM-менеджер"],
        location={"country": "Ukraine", "city": "Київ"},
        requirements=balanced(
            [
                Requirement(id="r1", label="SMM-менеджер", importance="required"),
                Requirement(id="location", importance="high"),
            ]
        ),
    )


async def test_the_judge_places_a_person_by_a_town_and_must_quote_it():
    from app.services.extraction.signal_detector import placed_by_judge

    answer = {
        "country": "Russia",
        "country_evidence": "из солнечной Мордовии",
        "results": [{"id": "r1", "met": True, "confidence": 0.9, "evidence": "SMM-менеджер"}],
    }
    judgement = await judge(answer).assess(smm_manager(), kyiv_smm_search())

    assert judgement.country == "Russia"
    located, _ = placed_by_judge(smm_manager(), kyiv_smm_search(), judgement)
    assert located.location.country == "Russia"
    assert kyiv_smm_search().in_allowed_place(located.location.country) is False

    # A country with no words behind it is a guess, and a guess is dropped.
    guessed = {**answer, "country_evidence": "lives in Kazan"}
    assert (await judge(guessed).assess(smm_manager(), kyiv_smm_search())).country is None


async def test_a_place_the_judge_read_inside_the_search_meets_the_place_requirement():
    from app.services.extraction.signal_detector import placed_by_judge

    profile = smm_manager().model_copy(update={"summary": "SMM-менеджер, Київ 🇺🇦"})
    answer = {
        "country": "Ukraine",
        "country_evidence": "Київ",
        "results": [{"id": "r1", "met": True, "confidence": 0.9, "evidence": "SMM-менеджер"}],
    }
    judgement = await judge(answer).assess(profile, kyiv_smm_search())
    located, signals = placed_by_judge(profile, kyiv_smm_search(), judgement)

    assert located.location.country == "Ukraine"
    assert {s.type: s.detected for s in signals}["location"] is True


def test_field_labels_are_not_evidence():
    """'Address: https://www.instagram.com/… Name: …' was quoted for 'runs Instagram'."""
    text = profile_text(developer())

    assert not quoted("Address: https://www.linkedin.com/in/olena-dev/", text)
    assert quoted("Senior Python Developer at SoftServe", text)
