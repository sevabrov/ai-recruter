"""
Search lifecycle — the flow the client clicks through (spec §12–14, §39, §43).
"""

import time

from tests.conftest import MIHI_SPAIN, run_search, start_search, wait_for, wait_for_job


def test_create_returns_immediately_with_a_queued_search(client):
    response = client.post("/searches", json={"name": "MIHI Spain", "criteria": MIHI_SPAIN})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "queued"  # spec §39: no waiting on the HTTP call
    assert body["searchId"].startswith("srch_")


def test_search_runs_to_completion_and_produces_leads(client):
    search = run_search(client)

    assert search["status"] == "completed"
    assert search["progress"]["percent"] == 100
    assert search["progress"]["stage"] == "done"
    assert search["leadCount"] > 0
    assert search["leadCount"] == search["progress"]["qualified"]

    leads = client.get(f"/searches/{search['id']}/leads").json()
    assert leads["total"] == search["leadCount"]
    assert all(lead["searchId"] == search["id"] for lead in leads["items"])


def test_progress_is_measured_not_invented(client):
    """
    Spec §43: the counters come from the worker. They must be internally
    consistent — queries actually fired, pages actually analysed.
    """
    search = run_search(client)
    progress = search["progress"]

    assert progress["queries"] > 0
    assert progress["queriesCompleted"] == progress["queries"]
    assert progress["urlsDiscovered"] >= progress["profilesDiscovered"]
    assert progress["profilesProcessed"] == progress["profilesDiscovered"]
    assert progress["qualified"] <= progress["profilesProcessed"]
    assert progress["highQuality"] <= progress["qualified"]

    assert search["usage"]["searchApiCalls"] == progress["queriesCompleted"]
    assert search["usage"]["pagesAnalyzed"] == progress["profilesProcessed"]


def test_generated_queries_are_recorded_with_their_hit_counts(client):
    search = run_search(client)

    assert len(search["queries"]) > 3
    assert all(entry["provider"] == "fixture" for entry in search["queries"])
    assert sum(entry["resultCount"] for entry in search["queries"]) > 0


def test_cost_is_tracked_from_the_first_run(client):
    """Spec §54: usage is money, so it is accounted per search."""
    search = run_search(client)

    assert search["usage"]["estimatedCostEur"] > 0
    assert search["usage"]["llmCalls"] > 0


def test_criteria_decide_who_is_found_and_how_they_score(client):
    """
    The same catalogue, two geographies: a candidate outside the target country
    loses the location points, so criteria visibly change the outcome.
    """
    spain = run_search(client, name="Spain run")
    germany = run_search(client, name="Germany run", location={"country": "Germany"})

    spanish_leads = client.get(f"/searches/{spain['id']}/leads").json()["items"]
    german_leads = client.get(f"/searches/{germany['id']}/leads").json()["items"]

    def location_points(lead: dict) -> int:
        return next(row["awarded"] for row in lead["scoreBreakdown"] if row["type"] == "location")

    def country(lead: dict) -> str | None:
        return (lead.get("location") or {}).get("country")

    spanish_hits = [lead for lead in spanish_leads if country(lead) == "Spain"]
    assert spanish_hits, "a Spain search should surface Spanish profiles"
    assert all(location_points(lead) > 0 for lead in spanish_hits)

    non_german = [lead for lead in german_leads if country(lead) != "Germany"]
    assert all(location_points(lead) == 0 for lead in non_german)


def test_must_have_signals_are_a_hard_gate(client):
    """Spec §10: "must have" means required, not preferred."""
    search = run_search(client, name="Leadership required", mustHave=["leadership"])
    leads = client.get(f"/searches/{search['id']}/leads").json()["items"]

    assert leads
    for lead in leads:
        detected = {signal["type"] for signal in lead["signals"] if signal["detected"]}
        assert "leadership" in detected


def test_duplicates_are_merged_into_one_person(client):
    """
    The fixture provider returns the same person from several queries and
    platforms; only one lead may come out (spec §45).
    """
    search = run_search(client)
    leads = client.get(f"/searches/{search['id']}/leads").json()["items"]

    names = [lead["name"] for lead in leads]
    assert len(names) == len(set(names))


def test_cancel_stops_a_running_search(slow_client):
    search_id = start_search(slow_client, name="Cancel me")
    response = slow_client.post(f"/searches/{search_id}/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    # It must stay cancelled — a late progress write may not resurrect it.
    time.sleep(0.5)
    assert slow_client.get(f"/searches/{search_id}").json()["status"] == "cancelled"


def test_cancelling_a_finished_search_is_a_conflict(client):
    search = run_search(client)

    response = client.post(f"/searches/{search['id']}/cancel")

    assert response.status_code == 409
    assert "cannot be cancelled" in response.json()["detail"]


def test_history_lists_newest_first_and_includes_new_searches(client):
    before = client.get("/searches").json()
    search = run_search(client, name="Newest run")
    after = client.get("/searches").json()

    assert len(after) == len(before) + 1
    assert after[0]["id"] == search["id"]


def test_unknown_search_is_404(client):
    assert client.get("/searches/srch_nope").status_code == 404


def test_invalid_criteria_are_rejected(client):
    """`activity` carries no points, so weighting it is a contract violation."""
    response = client.post(
        "/searches",
        json={
            "name": "Bad weights",
            "criteria": {"signalWeights": {"activity": 20}},
        },
    )

    assert response.status_code == 422


def test_jobs_are_recorded_for_every_search(client):
    search = run_search(client)

    job = wait_for_job(client, search["id"])

    assert job["kind"] == "run_search"
    assert job["status"] == "succeeded"
    assert job["attempts"] == 1


def test_two_searches_do_not_block_each_other(client):
    """Spec §41: concurrent searches must make progress independently."""
    first = start_search(client, name="Concurrent A")
    second = start_search(client, name="Concurrent B")

    for search_id in (first, second):
        assert wait_for(client, search_id)["status"] == "completed"
