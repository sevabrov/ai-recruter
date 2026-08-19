from fastapi.testclient import TestClient

from app.main import create_app


def test_health_reports_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"  # spec §21
    assert body["phase"] == 4


def test_health_answers_from_the_database_not_from_a_constant(client):
    """A store that stopped answering must not be reported as healthy."""
    body = client.get("/health").json()

    assert body["storage"] == "postgres"
    assert body["database"] is True


def test_health_admits_it_is_running_on_fixture_providers(client):
    body = client.get("/health").json()

    assert body["pipeline"] == "fixture"
    assert body["stages"] == {"search": "fixture", "extraction": "fixture", "signals": "fixture"}


def test_health_names_the_stage_that_went_live(settings):
    """
    With a Brave key configured the search stage is real while reading and judging
    are still stand-ins — "partial" is the honest word for that, and the stages say
    which is which (spec §21, §46).
    """
    live = settings.model_copy(
        update={"brave_search_api_key": "test-token", "search_provider": "brave"}
    )

    with TestClient(create_app(live)) as client:
        response = client.get("/health")

    body = response.json()
    assert body["pipeline"] == "partial"
    assert body["stages"] == {"search": "brave", "extraction": "snippet", "signals": "fixture"}
    assert body["providers"]["braveSearch"] is True
    assert "test-token" not in response.text  # spec §55


def test_health_reports_providers_as_booleans_only(client):
    """Whether a key is configured is public; its value must never be (spec §55)."""
    body = client.get("/health").json()

    assert body["providers"] == {"braveSearch": False, "scrapegraph": False, "openai": False}
