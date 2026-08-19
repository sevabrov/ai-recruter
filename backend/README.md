# AI Recruiter API

FastAPI backend. **Phase 4 — real web search**: the endpoints from spec §57 behind
the contract the frontend already speaks, the pipeline running end to end, the
workspace in a versioned PostgreSQL schema — and, with one key set, candidates
discovered on the live public web instead of in the seeded catalogue.

```bash
BRAVE_SEARCH_API_KEY=…   # in .env — that is the whole switch
```

Without it nothing calls out and the demo works exactly as before. `/health` always
says which stage is real:

```json
{"pipeline": "partial",
 "stages": {"search": "brave", "extraction": "snippet", "signals": "fixture"}}
```

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
docker compose run --rm backend pytest -q            # 143 tests (needs postgres)
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
`502 provider_unavailable` (a timeout or a rate limit — worth retrying),
`502 provider_auth_failed` (the provider rejected our key) and
`503 database_unavailable` (the store is unreachable). None of them quote a key or
a connection string; a provider failure inside a search is stored on the search as
`error` instead, which is what the results screen shows.

---

## Live web search (spec §27–30, §46–48)

```
criteria → 4–12 generated queries → Brave (one billed call each, ≤20 results)
        → canonicalize → classify → dedup → real candidate URLs
```

Set `BRAVE_SEARCH_API_KEY` and restart the backend. What changes:

* **Queries carry a market.** `country=ES` for a Spain search — a much stronger
  signal than the country's name in the query text. Brave has no market for
  Czechia or Ukraine, and those searches go worldwide rather than send a parameter
  that would fail (`services/search/markets.py`). `search_lang` is only sent when
  the user asked for exactly one language: three languages means "any of them".
* **One query is one billed call.** `count` is capped at Brave's maximum of 20 and
  no paging is attempted, so `usage.searchApiCalls` on the search record is exactly
  what was spent (§54).
* **The rate limit belongs to the key, not to the search.** The free and Base plans
  allow one request per second no matter how many searches are running, so the
  provider is built once per process and every job queues behind the same limiter
  (`BRAVE_RATE_LIMIT_PER_SECOND`). A live search therefore takes roughly a second
  per query, and the progress screen shows it happening.
* **Failures are classified** (§51). A timeout, a 429 or a 5xx is retried with
  backoff — and a 429's `Retry-After` moves the limiter, so the next attempt waits
  as long as Brave asked. A 401/403 is *not* retried: a wrong key would otherwise
  cost three calls per query, and the search fails with "check
  BRAVE_SEARCH_API_KEY" instead. One query failing no longer fails the search;
  only a search where nothing came back does.
* **The key stays server-side** (§55): it travels in `X-Subscription-Token`, never
  in a URL, a log line or an error message.

### The extraction gap

Phase 5 is what reads a candidate's page. Until then, live searches are extracted
by `SnippetProfileExtractor`, which builds a profile from **the result metadata the
search API already returned** — title, description, the index's page age and
language — and never opens a URL. It is honest about being thin:

* every profile records `extractor: "snippet"`;
* confidence is capped at 0.65, because a description is not a page;
* a title it cannot read a person's name out of returns nothing, so shops, brand
  accounts and articles do not become leads;
* signals are keyword sightings (`services/extraction/vocabulary.py`, one file so
  Phase 6 can delete it in one commit) with the sentence they were found in as
  evidence. Judging them stays the detector's and the scoring service's job.

The visible consequence: leads found on the open web score lower than the seeded
ones, and one person appearing on Instagram *and* on their own domain stays two
leads — the strong keys `deduplicate` merges on (shared URL, handle, e-mail,
website) are exactly what a snippet does not carry. Both improve in Phase 5, when
the page itself is read.

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
| Search provider (§27–28) | **`BraveSearchProvider`** when a key is set, `FixtureSearchProvider` otherwise | — |
| URL normalization + discovery (§31–32) | real | — |
| Extraction (§33–34) | `SnippetProfileExtractor` in live mode, `FixtureProfileExtractor` in the demo | Phase 5 — `ScrapeGraphProfileExtractor` |
| Signal detection (§36) | `FixtureSignalDetector` | Phase 6 — `LlmSignalDetector` |
| Scoring (§37–38) | real, deterministic | — |
| Deduplication (§45) | real, strong keys only | later: entity resolution |
| Cost tracking (§54) | real, unit costs from config | — |
| Storage (§23) | **PostgreSQL 17 + Alembic** | — |
| Jobs (§39–41) | asyncio tasks in the API process, recorded in the database | Phase 7 — Celery + Redis |
| Auth (§55) | one demo user row, every query scoped by `user_id` | Phase 8 |

Swapping an adapter is a decision in [app/services/adapters.py](app/services/adapters.py): a
provider is used as soon as its key is configured, otherwise a stand-in keeps the
product working. Nothing else in the codebase names a vendor — `SEARCH_PROVIDER=fixture`
forces the demo back on even with a key present, which is what the test suite uses.

---

## Layout

```
app/
  main.py            app factory, CORS, lifespan, error handlers
  api/               routers, query parameters, the composition root (deps.py)
  core/              config, structured logging, errors, retry, rate limits
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
    search/          query generator, providers, url_tools, markets, dedup, pipeline
    scraping/        extraction interface + adapters (scrapegraph, snippet, fixture)
    extraction/      signal detection interface + adapters, keyword vocabulary
    scoring/         the deterministic scoring engine
    leads/           lifecycle, notes, outreach drafting
    dashboard/       aggregates
    adapters.py      which implementation is wired to what
  workers/           job service + the run_search task
alembic/versions/    the schema, versioned
tests/               143 tests: contract, scoring, pipeline units, lifecycle, filters,
                     persistence, the Brave provider, snippet extraction, a live search
```

### Seed data

`app/db/seed/fixtures.json` is generated from the Phase 1 frontend fixtures, so
the demo content the client already approved is served by the API rather than
re-typed. Timestamps are rebased when the file is loaded and then **inserted once**,
so the workspace ages like real data; a search that was still running when the seed
was captured is re-queued at startup — the same thing a worker pool does after a
restart.

Without a Brave key, new searches rediscover those same people through the pipeline
and re-score them against the criteria you chose, so geography and weights visibly
change the result — they just cannot find anybody new. With a key, the catalogue is
out of the picture entirely: the URLs come from the web and the seeded people are
unreachable, because none of their URLs exist.

### Configuration

All of it is environment (spec §22, §52) — see `../.env.example`. Provider keys
are read in `core/config.py` and nowhere else, and never leave the server:
`/health` reports whether a key is set, never its value.

`PIPELINE_STEP_DELAY_MS` (default 250) is demo pacing only: fixture adapters
answer instantly, so without it a search finishes in about a second and the
progress screen is never seen. It is ignored in live mode — Brave brings its own
latency — and `0` gives an instant fixture run.

The suite runs against `DATABASE_URL`'s database name with `_test` appended,
created on demand — it never touches the workspace database.
