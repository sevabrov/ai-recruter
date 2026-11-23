"""Dashboard aggregates (spec §7), counted from the workspace's own data."""

from tests.conftest import run_search


def test_dashboard_counts_the_workspace(client):
    body = client.get("/dashboard").json()
    leads = client.get("/leads", params={"include_archived": True, "page_size": 500}).json()
    searches = client.get("/searches").json()

    assert body["stats"]["totalLeads"]["value"] == leads["total"] > 0
    assert body["stats"]["searches"]["value"] == len(searches)
    assert len(body["recentSearches"]) <= 5
    assert sum(bucket["count"] for bucket in body["scoreDistribution"]) == leads["total"]
    assert len(body["weeklyLeads"]) == 7
    # Shares are rounded per platform, so they may miss 100 by one per row.
    shares = [row["share"] for row in body["sourceBreakdown"]]
    assert abs(sum(shares) - 100) <= len(shares)


def test_a_new_workspace_shows_zeros(fresh_client):
    body = fresh_client.get("/dashboard").json()

    assert {stat["value"] for stat in body["stats"].values()} == {0}
    assert all(stat.get("delta") is None for stat in body["stats"].values())
    assert body["recentSearches"] == []
    assert body["sourceBreakdown"] == []
    assert {bucket["count"] for bucket in body["scoreDistribution"]} == {0}
    assert {point["count"] for point in body["weeklyLeads"]} == {0}


def test_starting_a_search_moves_the_tiles(client):
    before = client.get("/dashboard").json()["stats"]

    search = run_search(client, name="Dashboard run")

    after = client.get("/dashboard").json()["stats"]
    assert after["searches"]["value"] == before["searches"]["value"] + 1
    assert after["totalLeads"]["value"] == before["totalLeads"]["value"] + search["leadCount"]


def test_new_leads_land_on_today(client):
    today_before = client.get("/dashboard").json()["weeklyLeads"][-1]["count"]

    search = run_search(client, name="Counted today")

    today_after = client.get("/dashboard").json()["weeklyLeads"][-1]["count"]
    assert today_after == today_before + search["leadCount"]


def test_saving_a_lead_moves_the_saved_tile(client):
    lead = client.get("/leads").json()["items"][0]
    before = client.get("/dashboard").json()["stats"]["savedLeads"]["value"]

    client.post(f"/leads/{lead['id']}/save")

    after = client.get("/dashboard").json()["stats"]["savedLeads"]
    assert after["value"] == before + (0 if lead["saved"] else 1)


def test_recent_searches_are_newest_first(client):
    search = run_search(client, name="Most recent")

    recent = client.get("/dashboard").json()["recentSearches"]

    assert recent[0]["id"] == search["id"]
