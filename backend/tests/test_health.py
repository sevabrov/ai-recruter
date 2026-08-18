def test_health_reports_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"  # spec §21
    assert body["phase"] == 3


def test_health_answers_from_the_database_not_from_a_constant(client):
    """A store that stopped answering must not be reported as healthy."""
    body = client.get("/health").json()

    assert body["storage"] == "postgres"
    assert body["database"] is True


def test_health_admits_it_is_running_on_fixture_providers(client):
    assert client.get("/health").json()["pipeline"] == "fixture"


def test_health_reports_providers_as_booleans_only(client):
    """Whether a key is configured is public; its value must never be (spec §55)."""
    body = client.get("/health").json()

    assert body["providers"] == {"braveSearch": False, "scrapegraph": False, "openai": False}
