def test_health_reports_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"  # spec §21
    assert body["phase"] == 2


def test_health_admits_it_is_running_on_fixtures(client):
    body = client.get("/health").json()

    assert body["pipeline"] == "fixture"
    assert body["storage"] == "memory"


def test_health_reports_providers_as_booleans_only(client):
    """Whether a key is configured is public; its value must never be (spec §55)."""
    body = client.get("/health").json()

    assert body["providers"] == {"braveSearch": False, "scrapegraph": False, "openai": False}
