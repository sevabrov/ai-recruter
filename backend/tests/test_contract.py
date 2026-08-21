"""
Contract tests.

The frontend's `services/types.ts` is the shared truth. If a key here stops
matching it, the UI breaks silently at runtime — so the payload shape is asserted
explicitly rather than trusted.
"""

from app.models.common import (
    SCORED_SIGNALS,
    LeadStatus,
    Platform,
    SearchStage,
    SearchStatus,
    SignalType,
    SourceKind,
)

LEAD_KEYS = {
    "id",
    "searchId",
    "searchName",
    "name",
    "headline",
    "languages",
    "score",
    "scoreBreakdown",
    "platforms",
    "summary",
    "signals",
    "sources",
    "contacts",
    "status",
    "saved",
    "archived",
    "notes",
    "createdAt",
}

SEARCH_KEYS = {
    "id",
    "name",
    "status",
    "createdAt",
    "leadCount",
    "highQualityCount",
    "target",
    "sources",
    "criteria",
    "progress",
    "usage",
    "queries",
}

PROGRESS_KEYS = {
    "queries",
    "queriesCompleted",
    "urlsDiscovered",
    "profilesDiscovered",
    "profilesProcessed",
    "qualified",
    "highQuality",
    "percent",
    "stage",
}


def test_lead_payload_is_camel_case_and_complete(client):
    lead = client.get("/leads").json()["items"][0]

    assert set(lead) >= LEAD_KEYS
    assert not [key for key in lead if "_" in key]
    # Ownership and internal merge bookkeeping stay server-side.
    assert "userId" not in lead
    assert "mergedUrls" not in lead


def test_pagination_envelope(client):
    body = client.get("/leads", params={"page": 1, "page_size": 5}).json()

    assert set(body) == {"items", "total", "page", "pageSize"}
    assert len(body["items"]) == 5
    assert body["total"] > 5


def test_signals_carry_evidence_not_bare_booleans(client):
    """Spec §16: a signal without provenance is not acceptable."""
    lead = client.get("/leads").json()["items"][0]

    signal = next(entry for entry in lead["signals"] if entry["detected"])
    assert set(signal) >= {"type", "detected", "confidence", "evidence", "sourceUrl"}
    assert 0 <= signal["confidence"] <= 1


def test_score_breakdown_explains_the_total(client):
    """Spec §38: the score is the sum of its parts, visibly."""
    lead = client.get("/leads").json()["items"][0]

    assert [row["type"] for row in lead["scoreBreakdown"]] == [s.value for s in SCORED_SIGNALS]
    assert sum(row["awarded"] for row in lead["scoreBreakdown"]) == lead["score"]
    assert all(row["awarded"] <= row["max"] for row in lead["scoreBreakdown"])


def test_search_payload_shape(client):
    summaries = client.get("/searches").json()
    assert summaries, "the seed should provide search history"

    search = client.get(f"/searches/{summaries[0]['id']}").json()
    assert set(search) >= SEARCH_KEYS
    assert set(search["progress"]) == PROGRESS_KEYS
    assert set(search["usage"]) == {
        "searchApiCalls",
        "pagesAnalyzed",
        "pagesRead",
        "pagesCached",
        "pagesSkipped",
        "scrapeCredits",
        "llmCalls",
        "estimatedCostEur",
    }
    assert set(search["criteria"]) >= {
        "industry",
        "businessTypes",
        "negativeKeywords",
        "mustHave",
        "niceToHave",
        "signalWeights",
        "sources",
        "location",
    }


def test_dashboard_payload_shape(client):
    body = client.get("/dashboard").json()

    assert set(body) == {
        "stats",
        "recentSearches",
        "sourceBreakdown",
        "scoreDistribution",
        "weeklyLeads",
    }
    assert set(body["stats"]) == {"totalLeads", "highQuality", "searches", "savedLeads"}
    assert set(body["scoreDistribution"][0]) == {"label", "from", "to", "count"}


def test_enum_values_match_the_typescript_unions():
    assert {s.value for s in SearchStatus} == {
        "draft",
        "queued",
        "searching",
        "extracting",
        "scoring",
        "completed",
        "failed",
        "cancelled",
    }
    assert {s.value for s in SearchStage} == {
        "queued",
        "generating_queries",
        "web_search",
        "discovering_profiles",
        "extracting",
        "scoring",
        "deduplicating",
        "done",
    }
    assert {s.value for s in SignalType} == {
        "mlm",
        "beauty",
        "recruiting",
        "leadership",
        "location",
        "personalBrand",
        "activity",
    }
    assert {s.value for s in Platform} == {
        "instagram",
        "linkedin",
        "facebook",
        "threads",
        "website",
        "blog",
    }
    assert {s.value for s in LeadStatus} == {
        "new",
        "reviewed",
        "qualified",
        "contact_later",
        "contacted",
        "rejected",
    }
    assert {s.value for s in SourceKind} == {
        "public_web",
        "instagram_public",
        "linkedin_public",
        "facebook_public",
        "threads_public",
        "company_websites",
        "blogs",
    }
    # `activity` is detected but never scored (spec §37).
    assert SignalType.ACTIVITY not in SCORED_SIGNALS


def test_unknown_ids_are_404_with_a_detail(client):
    response = client.get("/leads/lead_does_not_exist")

    assert response.status_code == 404
    assert "detail" in response.json()
