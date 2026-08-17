"""
Test fixtures.

The app is built with injected settings: no step delays, no startup resume, and
explicitly empty provider keys so a stray `.env` on someone's machine cannot make
the suite talk to a real service.
"""

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

#: The wizard's "Fill example" scenario, in the shape the frontend posts.
MIHI_SPAIN: dict[str, Any] = {
    "industry": ["Beauty", "Cosmetics"],
    "businessTypes": ["MLM", "Network marketing"],
    "keywords": ["MIHI", "beauty", "network marketing", "team leader", "distributor"],
    "negativeKeywords": ["customer", "shop", "beauty salon"],
    "location": {"country": "Spain"},
    "languages": ["Spanish", "English", "Russian"],
    "mustHave": ["mlm", "beauty", "activity"],
    "niceToHave": ["leadership", "recruiting", "personalBrand"],
    "signalWeights": {
        "mlm": 30,
        "beauty": 20,
        "recruiting": 20,
        "leadership": 15,
        "location": 10,
        "personalBrand": 5,
    },
    "sources": ["public_web", "instagram_public", "linkedin_public", "facebook_public"],
}


@pytest.fixture
def settings() -> Settings:
    return Settings(
        debug=True,
        pipeline_step_delay_ms=0,
        resume_running_searches=False,
        brave_search_api_key="",
        scrapegraph_api_key="",
        openai_api_key="",
    )


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def slow_client(settings: Settings):
    """A pipeline that takes about a second, so a running search can be observed."""
    with TestClient(create_app(settings.model_copy(update={"pipeline_step_delay_ms": 25}))) as c:
        yield c


def start_search(client: TestClient, name: str = "MIHI Beauty Leaders Spain", **overrides) -> str:
    criteria = {**MIHI_SPAIN, **overrides}
    response = client.post("/searches", json={"name": name, "criteria": criteria})
    assert response.status_code == 202, response.text
    return response.json()["searchId"]


def wait_for(client: TestClient, search_id: str, *, timeout: float = 20.0) -> dict:
    """Poll exactly as the UI does, until the search stops running."""
    deadline = time.monotonic() + timeout
    payload: dict = {}
    while time.monotonic() < deadline:
        payload = client.get(f"/searches/{search_id}").json()
        if payload["status"] in {"completed", "failed", "cancelled"}:
            return payload
        time.sleep(0.05)
    raise AssertionError(f"search {search_id} still {payload.get('status')} after {timeout}s")


def run_search(client: TestClient, **kwargs) -> dict:
    return wait_for(client, start_search(client, **kwargs))
