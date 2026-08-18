"""
What the database is actually for (spec §23).

Phase 2's store lived in the API process, so every one of these tests would have
failed by definition: a restart was a reset. They are written the way the product
is used — through HTTP — and the restart is a second app object against the same
database, which is what `docker compose restart backend` looks like from the
outside.
"""

import asyncio

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.db.bootstrap import upgrade_schema
from app.db.engine import create_session_factory
from app.db.tables import Base
from app.main import create_app
from tests.conftest import run_search, wait_for

#: A port nothing listens on — a database that is simply not there.
UNREACHABLE = "postgresql+asyncpg://nobody:nothing@127.0.0.1:1/nowhere"


def restart(settings: Settings) -> TestClient:
    """A second app against the same database — one container restart."""
    return TestClient(create_app(settings))


# ------------------------------------------------------------------- durability


def test_a_finished_search_and_its_leads_survive_a_restart(client, settings):
    search = run_search(client, name="Survives a restart")

    with restart(settings) as reborn:
        after = reborn.get(f"/searches/{search['id']}").json()
        leads = reborn.get("/leads", params={"search_id": search["id"]}).json()

    assert after["status"] == "completed"
    assert after["leadCount"] == search["leadCount"]
    assert after["usage"]["estimatedCostEur"] == search["usage"]["estimatedCostEur"]
    assert leads["total"] == search["leadCount"]


def test_an_edited_lead_keeps_its_edits_and_notes(client, settings):
    lead = client.get("/leads").json()["items"][0]
    client.patch(f"/leads/{lead['id']}", json={"status": "contacted", "saved": True})
    client.post(f"/leads/{lead['id']}/notes", json={"body": "Answered on the second call"})

    with restart(settings) as reborn:
        after = reborn.get(f"/leads/{lead['id']}").json()

    assert after["status"] == "contacted"
    assert after["saved"] is True
    assert after["notes"][-1]["body"] == "Answered on the second call"


def test_the_seed_is_applied_once_not_on_every_boot(client, settings):
    """
    The whole point of the marker row: without it the demo data would grow by 24
    leads on every restart.
    """
    before = client.get("/leads", params={"page_size": 500}).json()["total"]
    searches = len(client.get("/searches").json())

    with restart(settings) as second, restart(settings) as third:
        assert second.get("/leads", params={"page_size": 500}).json()["total"] == before
        assert len(third.get("/searches").json()) == searches


def test_a_reset_drops_new_work_and_restores_the_seed(client):
    search = run_search(client, name="Discarded by the reset")
    lead = client.get("/leads").json()["items"][0]
    client.patch(f"/leads/{lead['id']}", json={"archived": True})

    client.post("/admin/reset")

    assert client.get(f"/searches/{search['id']}").status_code == 404
    assert client.get(f"/leads/{lead['id']}").json()["archived"] is False


def test_a_search_interrupted_by_a_restart_is_picked_up_again(client, settings):
    """
    A crashed worker leaves a search stored mid-flight. With
    `resume_running_searches` on — the container's default — the next start re-queues
    it instead of leaving it frozen at 58% forever.
    """
    search_id = run_search(client, name="Interrupted by a restart")["id"]
    # Put it back the way a kill -9 during the extraction stage would leave it.
    asyncio.run(_force_running(settings.database_url, search_id))

    with restart(settings.model_copy(update={"resume_running_searches": True})) as reborn:
        assert wait_for(reborn, search_id)["status"] == "completed"


# ---------------------------------------------------------------------- queries


def test_wildcards_typed_into_the_search_box_are_literal_text(client):
    """`%` reaches SQL as an escaped literal, not as "match everything"."""
    everything = client.get("/leads").json()["total"]

    assert everything > 0
    assert client.get("/leads", params={"q": "%"}).json()["total"] == 0
    assert client.get("/leads", params={"q": "_"}).json()["total"] == 0


def test_paging_has_a_total_order_so_no_lead_appears_twice(client):
    """
    LIMIT/OFFSET without a tiebreak is free to shuffle equal rows between pages.
    Score has plenty of ties in the seed, which is what makes this worth asserting.
    """
    seen: list[str] = []
    for page in (1, 2, 3, 4, 5, 6):
        body = client.get("/leads", params={"page": page, "page_size": 4}).json()
        seen.extend(lead["id"] for lead in body["items"])

    assert len(seen) == len(set(seen))
    assert len(seen) == min(24, client.get("/leads").json()["total"])


# ------------------------------------------------------------------- failure


def test_a_database_that_stops_answering_is_a_503_with_a_code(client):
    """
    A dropped connection is not a bug in the request: it must map to 503 with the
    code the frontend can act on, and the driver's message — which contains the
    connection string — must not reach the browser.
    """
    # What losing the server looks like from inside a running API.
    client.app.state.container.repository._session = create_session_factory(
        create_async_engine(UNREACHABLE, poolclass=NullPool)
    )

    response = client.get("/leads")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "The database is not available",
        "code": "database_unavailable",
    }
    assert client.get("/health").json()["status"] == "degraded"


def test_the_api_refuses_to_start_without_its_database(settings):
    """
    Fail fast instead of serving empty screens: compose restarts the container until
    the database is reachable (`restart: unless-stopped`).
    """
    unreachable = create_app(settings.model_copy(update={"database_url": UNREACHABLE}))

    # The driver's error type is its own business; that startup fails is the point.
    with pytest.raises(Exception), TestClient(unreachable):  # noqa: B017
        pass


# ----------------------------------------------------------------- migrations


def test_the_migrations_match_the_models(database_url):
    """
    A column added to `tables.py` without a migration is a production bug waiting
    for the next deploy, so it fails here instead.
    """
    assert asyncio.run(_schema_diff(database_url)) == []


def test_the_migration_can_be_rolled_back(database_url):
    upgrade_schema(database_url)  # ensure a known starting point
    _alembic(database_url, "base")

    assert asyncio.run(_table_count(database_url)) == 0

    upgrade_schema(database_url)
    assert asyncio.run(_schema_diff(database_url)) == []


def _alembic(database_url: str, revision: str) -> None:
    from alembic import command

    from app.db.bootstrap import alembic_config

    command.downgrade(alembic_config(database_url), revision)


async def _force_running(database_url: str, search_id: str) -> None:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "UPDATE searches SET status = 'extracting', completed_at = NULL WHERE id = :id"
                ),
                {"id": search_id},
            )
    finally:
        await engine.dispose()


async def _schema_diff(database_url: str) -> list:
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: compare_metadata(
                    MigrationContext.configure(sync_connection, opts={"compare_type": True}),
                    Base.metadata,
                )
            )
    finally:
        await engine.dispose()


async def _table_count(database_url: str) -> int:
    from sqlalchemy import inspect

    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            names = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
            return len([name for name in names if name != "alembic_version"])
    finally:
        await engine.dispose()
