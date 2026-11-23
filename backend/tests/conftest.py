"""
Test fixtures.

The suite runs against a real PostgreSQL — the same server the app uses, in a
database called `<name>_test` that is created on demand. There is no in-memory
substitute on purpose: the filters, the sort order and the locked progress writes
*are* SQL now, and a fake store would test something the product does not do.

Each test starts from the test workspace (`tests/workspace.py`): the tables are
truncated, then its searches and leads are inserted, and the app is handed its
leads as the catalogue the offline stand-ins search. The app itself ships no data.
The schema is migrated once per session with the same Alembic revisions the
container runs.

Settings are injected: no step delays, no startup resume, no migrations at app
startup, and explicitly empty provider keys so a stray `.env` on someone's machine
cannot make the suite talk to a real service.
"""

import asyncio
import time
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.db.bootstrap import upgrade_schema
from app.main import create_app
from app.models.lead import Lead
from tests.workspace import insert_workspace, load_workspace

#: Cleared between tests, `scrape_cache` included: a page read by one test must not
#: be a cache hit in the next one.
TABLES = "lead_notes, leads, search_rejections, jobs, searches, users, scrape_cache"

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


@pytest.fixture(scope="session")
def database_url() -> str:
    """A migrated `<database>_test`, created next to the real one if missing."""
    url = _render(make_url(Settings().database_url).set(database=_test_database_name()))
    try:
        asyncio.run(_create_database(url))
    except OSError as error:  # unreachable server — say what to do about it
        pytest.exit(
            f"PostgreSQL is not reachable ({error}). Start it with:\n"
            "    docker compose up -d postgres",
            returncode=1,
        )
    upgrade_schema(url)
    return url


@pytest.fixture
def empty_database(database_url: str) -> str:
    """Empty tables, nothing inserted: what a fresh install starts from."""
    asyncio.run(_truncate(database_url))
    return database_url


@pytest.fixture
def clean_database(empty_database: str) -> str:
    """Empty tables, then the test workspace."""
    asyncio.run(insert_workspace(empty_database, load_workspace(Settings().dev_user_id)))
    return empty_database


@pytest.fixture
def catalogue() -> list[Lead]:
    return load_workspace(Settings().dev_user_id).catalogue


def make_settings(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        # The session fixture already migrated; each app start would redo the work.
        run_migrations_on_startup=False,
        pipeline_step_delay_ms=0,
        resume_running_searches=False,
        brave_search_api_key="",
        scrapegraph_api_key="",
        openai_api_key="",
        # Belt and braces: even handed a key, nothing here may call the live web.
        # The tests that do exercise the providers build them themselves, with a
        # mock transport (test_brave_provider, test_scrapegraph_extractor,
        # test_live_search, test_scrape_cache).
        search_provider="fixture",
    )


@pytest.fixture
def settings(clean_database: str) -> Settings:
    return make_settings(clean_database)


@pytest.fixture
def client(settings: Settings, catalogue: list[Lead]):
    with TestClient(create_app(settings, catalogue)) as test_client:
        yield test_client


@pytest.fixture
def slow_client(settings: Settings, catalogue: list[Lead]):
    """A pipeline that takes about a second, so a running search can be observed."""
    slow = settings.model_copy(update={"pipeline_step_delay_ms": 25})
    with TestClient(create_app(slow, catalogue)) as c:
        yield c


@pytest.fixture
def fresh_client(empty_database: str):
    """The app as a new install sees it: an empty database and no catalogue."""
    with TestClient(create_app(make_settings(empty_database))) as test_client:
        yield test_client


def start_search(client: TestClient, name: str = "MIHI Beauty Leaders Spain", **overrides) -> str:
    criteria = {**MIHI_SPAIN, **overrides}
    response = client.post("/searches", json={"name": name, "criteria": criteria})
    assert response.status_code == 202, response.text
    return response.json()["searchId"]


def wait_for(client: TestClient, search_id: str, *, timeout: float = 30.0) -> dict:
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


def wait_for_job(client: TestClient, search_id: str, *, timeout: float = 10.0) -> dict:
    """
    The job record reaches its terminal status just *after* the search does — the
    pipeline completes the search, then the job service closes the job — so a test
    that reads `/jobs` the instant a search finishes can catch it mid-write.
    """
    deadline = time.monotonic() + timeout
    job: dict = {}
    while time.monotonic() < deadline:
        jobs = client.get("/jobs").json()["items"]
        job = next((entry for entry in jobs if entry["searchId"] == search_id), {})
        if job.get("status") not in {None, "queued", "running"}:
            return job
        time.sleep(0.05)
    raise AssertionError(f"job for {search_id} still {job.get('status')} after {timeout}s")


# --------------------------------------------------------------------- plumbing
def _test_database_name() -> str:
    return f"{make_url(Settings().database_url).database}_test"


def _render(url: URL) -> str:
    """`str(URL)` masks the password with asterisks, which asyncpg then sends."""
    return url.render_as_string(hide_password=False)


async def _create_database(url: str) -> None:
    """
    CREATE DATABASE cannot run inside a transaction, hence the autocommit
    connection to the server's default database.
    """
    target = make_url(url)
    engine = create_async_engine(
        _render(target.set(database="postgres")),
        isolation_level="AUTOCOMMIT",
        poolclass=NullPool,
    )
    try:
        async with engine.connect() as connection:
            exists = await connection.scalar(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": target.database},
            )
            if not exists:
                await connection.execute(text(f'CREATE DATABASE "{target.database}"'))
    finally:
        await engine.dispose()


async def _truncate(url: str) -> None:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(text(f"TRUNCATE TABLE {TABLES} CASCADE"))
    finally:
        await engine.dispose()
