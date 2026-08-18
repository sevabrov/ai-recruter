# AI Recruiter API

FastAPI backend. **Phase 3 — PostgreSQL**: the endpoints from spec §57 behind the
contract the frontend already speaks, the search pipeline running end to end, and
the workspace stored in a versioned database instead of the API process.

No external service is called yet. The three edges that would call out — web
search, page extraction, signal detection — are fixture adapters, and `/health`
says so (`"pipeline": "fixture"`).

---

## Running it

Nothing is installed on the host; Python and Postgres live in containers.

```bash
cd ..                                   # repository root, next to docker-compose.yml
docker compose up -d backend            # starts postgres too, then http://localhost:8000
docker compose logs -f backend          # structured JSON logs
docker compose down                     # stop; the data volume survives
```

Interactive API docs: <http://localhost:8000/docs>.

```bash
docker compose run --rm backend pytest -q            # 91 tests (needs postgres)
docker compose run --rm --no-deps backend ruff check .
docker compose run --rm --no-deps backend ruff format .
```

`app/`, `tests/` and `alembic/` are mounted, so edits reload without a rebuild.
Rebuild only when dependencies change: `docker compose build backend`.

Without Docker: `pip install -r requirements-dev.txt && uvicorn app.main:app --reload`
against a reachable `DATABASE_URL`.

---

## Storage (spec §23)

```
users ─┬─< searches ─< leads ─< lead_notes
       └─< jobs                 seed_state   (the "seeded once" marker)
```

Migrations are the source of truth for the schema — `alembic/versions/` — and the
API runs `alembic upgrade head` at startup, so an empty volume needs no extra step.

```bash
docker compose run --rm backend alembic current
docker compose run --rm backend alembic history
docker compose run --rm backend alembic revision --autogenerate -m "add x"
docker compose run --rm backend alembic downgrade -1
```

Two tests keep this honest: one asserts the migrations and `app/db/tables.py` agree
(a model change without a migration fails the suite), the other rolls the schema
back to empty and forward again.

What is a column and what is a document: anything the product filters, sorts or
counts by is a column — score, country, status, saved, archived, created_at. The
evidence-bearing value objects (signals, score breakdown, platforms, sources,
criteria, progress, usage) are JSONB, because they are read and written whole and
their shape is already defined once, in the Pydantic models. `platforms` and
`signals` are needed for both, so a flat `text[]` mirror with a GIN index backs the
platform and signal filters — derived on every write in `app/db/mappers.py`, never
set by a caller.

Three consequences worth knowing:

* **`/leads` is one statement.** Filters are WHERE, `sort` is ORDER BY (always with
  a primary-key tiebreak, so paging cannot repeat a row), the page is LIMIT/OFFSET
  and the total is a COUNT over the same predicate. The Python filtering from Phase
  2 is gone.
* **Progress writes lock the row.** `patch_search` is one transaction with
  `SELECT … FOR UPDATE`, so a cancel arriving mid-stage cannot be overwritten by the
  worker's next progress write.
* **The seed is applied once**, on the first boot against an empty database, and
  the workspace ages from there. `POST /admin/reset` empties the tables and
  re-applies it.

Adminer at <http://localhost:8081> (server `postgres`) is the quickest way to look
at the rows.

---

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | spec §21 — `{"status": "ok"}` plus what is wired up; queries the database |
| POST | `/searches` | returns `202` immediately with `{searchId, status}` (§39) |
| GET | `/searches` | history, newest first |
| GET | `/searches/:id` | status, progress, usage, queries — the polling target (§43) |
| GET | `/searches/:id/leads` | results, same filters as `/leads` |
| POST | `/searches/:id/cancel` | `409` if it is not running |
| GET | `/leads` | filter, sort, paginate |
| GET | `/leads/facets` | countries and platforms actually present |
| GET | `/leads/:id` | |
| PATCH | `/leads/:id` | status / saved / archived |
| POST · DELETE | `/leads/:id/save` | §57's explicit save and unsave |
| POST | `/leads/:id/notes` | appended as its own row |
| POST | `/leads/:id/outreach` | drafts a message (template until Phase 8) |
| GET | `/dashboard` | tiles, recent searches, distributions |
| GET | `/jobs`, `/jobs/:id` | operator view of background work; survives a restart |
| POST | `/admin/reset` | re-seeds the workspace; debug builds only |

Responses are camelCase to match `frontend/src/services/types.ts`; query
parameters are snake_case (`min_score`, `page_size`), which is what the frontend
client sends. Optional fields are omitted rather than sent as `null`, because
that is what `field?:` means in TypeScript.

Errors always carry a code: `404 not_found`, `409 conflict`, `502 provider_error`,
`503 database_unavailable` (the store is unreachable — the driver's message, which
contains the connection string, never reaches the browser).

---

## What is real and what is a stand-in

The pipeline (spec §44) runs for real:

```
criteria → query generation → provider → URL normalization → dedup
        → candidate discovery → extraction → signal detection → scoring
        → lead dedup → storage
```

| Piece | Today | Replaced in |
|---|---|---|
| Query generation (§29) | deterministic templates | — (an AI generator is optional later) |
| Search provider (§27–28) | `FixtureSearchProvider` over the seeded catalogue | Phase 4 — `BraveSearchProvider` |
| URL normalization + discovery (§31–32) | real | — |
| Extraction (§33–34) | `FixtureProfileExtractor` | Phase 5 — `ScrapeGraphProfileExtractor` |
| Signal detection (§36) | `FixtureSignalDetector` | Phase 6 — `LlmSignalDetector` |
| Scoring (§37–38) | real, deterministic | — |
| Deduplication (§45) | real, strong keys only | later: entity resolution |
| Cost tracking (§54) | real, unit costs from config | — |
| Storage (§23) | **PostgreSQL 17 + Alembic** | — |
| Jobs (§39–41) | asyncio tasks in the API process, recorded in the database | Phase 7 — Celery + Redis |
| Auth (§55) | one demo user row, every query scoped by `user_id` | Phase 8 |

Swapping an adapter is a decision in [app/services/adapters.py](app/services/adapters.py): a
provider is used as soon as its key is configured, otherwise the fixture keeps
the product working. Nothing else in the codebase names a vendor.

---

## Layout

```
app/
  main.py            app factory, CORS, lifespan, error handlers
  api/               routers, query parameters, the composition root (deps.py)
  core/              config, structured logging, errors, retry
  models/            domain entities and the query objects (Pydantic, snake_case)
  schemas/           API DTOs (camelCase aliases) — the contract
  db/
    repository.py    the storage protocol every service depends on
    postgres.py      the SQL implementation: filters, locking, seeding, reset
    tables.py        the schema — what is a column and what is JSONB
    mappers.py       rows ↔ domain models, and the query mirrors
    engine.py        the connection pool
    bootstrap.py     `alembic upgrade head`
    seed.py          the demo workspace, generated from the Phase 1 fixtures
  services/
    search/          query generator, providers, url_tools, deduplicator, pipeline
    scraping/        extraction interface + adapters
    extraction/      signal detection interface + adapters
    scoring/         the deterministic scoring engine
    leads/           lifecycle, notes, outreach drafting
    dashboard/       aggregates
    adapters.py      which implementation is wired to what
  workers/           job service + the run_search task
alembic/versions/    the schema, versioned
tests/               91 tests: contract, scoring, pipeline units, lifecycle, filters, persistence
```

### Seed data

`app/db/seed/fixtures.json` is generated from the Phase 1 frontend fixtures, so
the demo content the client already approved is served by the API rather than
re-typed. Timestamps are rebased when the file is loaded and then **inserted once**,
so the workspace ages like real data; a search that was still running when the seed
was captured is re-queued at startup — the same thing a worker pool does after a
restart.

New searches rediscover those same people through the pipeline and re-score them
against the criteria you chose, so geography and weights visibly change the
result. What the fixture adapters cannot do is find anybody new; that starts in
Phase 4.

### Configuration

All of it is environment (spec §22, §52) — see `../.env.example`. Provider keys
are read in `core/config.py` and nowhere else, and never leave the server:
`/health` reports whether a key is set, never its value.

`PIPELINE_STEP_DELAY_MS` (default 250) is demo pacing only: fixture adapters
answer instantly, so without it a search finishes in about a second and the
progress screen is never seen. Set it to `0` for an instant run; it disappears
when real providers bring their own latency.

The suite runs against `DATABASE_URL`'s database name with `_test` appended,
created on demand — it never touches the workspace database.
