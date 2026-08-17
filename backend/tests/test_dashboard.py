"""Dashboard aggregates (spec §7) and the demo reset."""

from tests.conftest import run_search


def test_dashboard_reports_the_seeded_workspace(client):
    body = client.get("/dashboard").json()

    assert body["stats"]["totalLeads"]["value"] > 0
    assert len(body["recentSearches"]) <= 5
    assert sum(row["share"] for row in body["sourceBreakdown"]) == 100


def test_starting_a_search_moves_the_tiles(client):
    before = client.get("/dashboard").json()["stats"]

    search = run_search(client, name="Dashboard run")

    after = client.get("/dashboard").json()["stats"]
    assert after["searches"]["value"] == before["searches"]["value"] + 1
    assert after["totalLeads"]["value"] == before["totalLeads"]["value"] + search["leadCount"]


def test_saving_a_lead_moves_the_saved_tile(client):
    lead = client.get("/leads").json()["items"][0]
    before = client.get("/dashboard").json()["stats"]["savedLeads"]["value"]

    client.post(f"/leads/{lead['id']}/save")

    after = client.get("/dashboard").json()["stats"]["savedLeads"]
    assert after["value"] == before + (0 if lead["saved"] else 1)
    assert "saved in this workspace" in after["hint"]


def test_recent_searches_are_newest_first(client):
    search = run_search(client, name="Most recent")

    recent = client.get("/dashboard").json()["recentSearches"]

    assert recent[0]["id"] == search["id"]


def test_reset_returns_the_workspace_to_the_seed(client):
    lead = client.get("/leads").json()["items"][0]
    client.patch(f"/leads/{lead['id']}", json={"status": "contacted", "saved": True})
    run_search(client, name="Will be discarded")

    response = client.post("/admin/reset")

    assert response.status_code == 200
    assert client.get(f"/leads/{lead['id']}").json()["status"] == lead["status"]
    assert len(client.get("/searches").json()) == response.json()["searches"]
