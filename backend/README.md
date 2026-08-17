# AI Recruiter API

FastAPI backend. **Phase 2 — backend skeleton**: the endpoints from spec §57
behind the contract the frontend already speaks, with the search pipeline running
end to end.

No external service is called and no database is required. The three edges that
would call out — web search, page extraction, signal detection — are fixture
adapters, and `/health` says so (`"pipeline": "fixture"`).

---

## Running it

Nothing is installed on the host; Python lives in the container.

```bash
cd ..                                   # repository root, next to docker-compose.yml
docker compose up -d backend            # http://localhost:8000
docker compose logs -f backend          # structured JSON logs
docker compose down backend
```

Interactive API docs: <http://localhost:8000/docs>.

```bash
docker compose run --rm --no-deps backend pytest -q      # 79 tests
docker compose run --rm --no-deps backend ruff check .
docker compose run --rm --no-deps backend ruff format .
```

`app/` and `tests/` are mounted, so edits reload without a rebuild. Rebuild only
when dependencies change: `docker compose build backend`.

Without Docker: `pip install -r requirements-dev.txt && uvicorn app.main:app --reload`.

---

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | spec §21 — `{"status": "ok"}` plus what is wired up |
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
| POST | `/leads/:id/notes` | |
| POST | `/leads/:id/outreach` | drafts a message (template until Phase 8) |
| GET | `/dashboard` | tiles, recent searches, distributions |
| GET | `/jobs`, `/jobs/:id` | operator view of background work |
| POST | `/admin/reset` | re-seeds the workspace; debug builds only |

Responses are camelCase to match `frontend/src/services/types.ts`; query
parameters are snake_case (`min_score`, `page_size`), which is what the frontend
client sends. Optional fields are omitted rather than sent as `null`, because
that is what `field?:` means in TypeScript.

---

## What is real and what is a stand-in

The pipeline (spec §44) runs for real:

```
criteria → query generation → provider → URL normalization → dedup
        → candidate discovery → extraction → signal detection → scoring
        → lead dedup → storage
```

| Piece | Phase 2 | Replaced in |
|---|---|---|
| Query generation (§29) | deterministic templates | — (an AI generator is optional later) |
| Search provider (§27–28) | `FixtureSearchProvider` over the seeded catalogue | Phase 4 — `BraveSearchProvider` |
| URL normalization + discovery (§31–32) | real | — |
| Extraction (§33–34) | `FixtureProfileExtractor` | Phase 5 — `ScrapeGraphProfileExtractor` |
| Signal detection (§36) | `FixtureSignalDetector` | Phase 6 — `LlmSignalDetector` |
| Scoring (§37–38) | real, deterministic | — |
| Deduplication (§45) | real, strong keys only | later: entity resolution |
| Cost tracking (§54) | real, unit costs from config | — |
| Jobs (§39–41) | asyncio tasks in the API process | Phase 7 — Celery + Redis |
| Storage (§23) | `InMemoryRepository` | Phase 3 — PostgreSQL |
| Auth (§55) | one demo user, every query scoped by `user_id` | Phase 8 |

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
  models/            domain entities (snake_case; Phase 3 makes them ORM models)
  schemas/           API DTOs (camelCase aliases) — the contract
  services/
    search/          query generator, providers, url_tools, deduplicator, pipeline
    scraping/        extraction interface + adapters
    extraction/      signal detection interface + adapters
    scoring/         the deterministic scoring engine
    leads/           filtering, notes, outreach drafting
    dashboard/       aggregates
    adapters.py      which implementation is wired to what
  workers/           job service + the run_search task
  db/                repository protocol, in-memory store, seed loader
tests/               79 tests: contract, scoring, pipeline units, lifecycle, filters
```

### Seed data

`app/db/seed/fixtures.json` is generated from the Phase 1 frontend fixtures, so
the demo content the client already approved is served by the API rather than
re-typed. Timestamps are rebased on load, so "3 hours ago" stays true. A search
that was still running when the seed was captured is re-queued at startup — the
same thing a worker pool does after a restart.

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
