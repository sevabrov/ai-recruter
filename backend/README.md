# AI Recruiter API

FastAPI backend. **Phase 5 — reading the pages**: the endpoints from spec §57 behind
the contract the frontend already speaks, the pipeline running end to end, the
workspace in a versioned PostgreSQL schema, candidates discovered on the live public
web (Phase 4) — and now each candidate's page opened and extracted into the strict
schema from §34.

```bash
BRAVE_SEARCH_API_KEY=…   # in .env — finds real URLs
SCRAPEGRAPH_API_KEY=…    # in .env — reads what is on them
```

Neither is required: without them nothing calls out and the demo works exactly as
before. `/health` always says which stage is real:

```json
{"pipeline": "partial",
 "stages": {"search": "brave", "extraction": "scrapegraph", "signals": "fixture"}}
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
docker compose run --rm backend pytest -q            # 220 tests (needs postgres)
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
       └─< jobs                 seed_state    (the "seeded once" marker)
                                scrape_cache  (one row per page ever read)
```

`scrape_cache` is the one table with no `user_id`: a page is a page, nothing in it
is derived from anyone's criteria, and two users searching for the same person should
not pay twice. Its key is a hash of the canonical URL, so a profile link with a long
query string cannot outgrow the index. `POST /admin/reset` deliberately leaves it
alone — those pages were paid for in credits.

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
| GET | `/sources` | which platforms can actually be read, counted from the scrape cache |
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

---

## Reading the pages (spec §33–35, §53)

```
candidate URL → scrape cache → POST v2-api.scrapegraphai.com/api/extract
             → PageExtraction (§34) → ExtractedProfile + one observation per
                signal, each with the quote that justifies it
```

Set `SCRAPEGRAPH_API_KEY` and restart. Keys come from the current ScrapeGraphAI
platform (sign in at scrapegraphai.com/login); the `dashboard.scrapegraphai.com`
dashboard and its `v1/smartscraper` endpoint are deprecated, and `SCRAPEGRAPH_ENDPOINT`
is configuration so an account on either one works. What changes:

* **The profile comes from the page.** Headline, company, city, languages, handle,
  follower and post counts, e-mail, and the links the person publishes — instead of
  a search result's title and description.
* **Structured output only** (§34). The request is `{url, prompt, schema}` and the
  schema is `PageExtraction`'s (`services/scraping/page_schema.py`), so the model
  cannot answer in prose, and a response that does not fit it is treated as an
  unreadable page rather than parsed loosely. Reading a malformed answer generously
  is precisely how invented data gets in.
* **No quote, no signal.** Every signal must arrive with a verbatim quote from the
  page; a `detected: true` with nothing behind it is recorded as not detected. Page
  confidence is capped at 0.9 — a model summarised what it saw, and Phase 6 is what
  re-judges it.
* **One person on two platforms is now one lead.** Her Instagram bio links to her
  site, so both records carry the same website and `deduplicate` merges them on a
  strong key (§45). That link is exactly what a search snippet never carries — it is
  the clearest thing page reading buys.
* **A page is read once** (§53). The cache is keyed by canonical URL and stores the
  *outcome*, so a login wall costs one credit rather than one per search. Cached
  pages are free and the search's usage says so: `pagesRead` is what was billed,
  `pagesCached` is what an earlier search paid for. `SCRAPE_CACHE_TTL_HOURS=0`
  disables reuse without losing the record. The tokens the service reports
  (`usage.promptTokens` / `completionTokens`) are counted per search and logged;
  they reach the usage screen in Phase 6, when the LLM stage starts spending them too.
* **Concurrency is bounded** by `EXTRACTION_CONCURRENCY` (§35), never one URL at a
  time and never unlimited. The per-key rate limit is shared by every search in the
  process, like Brave's.
* **The key stays server-side** (§55): `SGAI-APIKEY`, never a URL, a log line or an
  error message.

### Not every URL can be read

The milestone is explicit about this, and it is true: Instagram shows a login wall
to a datacentre IP more often than not, Facebook shows a consent screen, LinkedIn
depends on the day. So the stage is a chain (`services/scraping/fallback.py`):

| The page… | What happens | Recorded as |
|---|---|---|
| opened | the profile it states, `extractor: "scrapegraph"` | `ok` |
| is a shop, a brand, an article | nothing, and the snippet gets no second vote | `not_a_person` |
| would not open | the search result is used instead, `extractor: "snippet"` | `blocked` |
| yielded nothing usable | same fallback | `empty` |
| the reader failed | same fallback; a refused key or an empty balance stops the reader for the rest of the search | `failed` |

| the budget refused it | the search result is used instead | nothing — see below |

Failures are classified from the API's own error envelope — `auth_invalid_key` (403)
and `insufficient_credits` (402) are not retried, `rate_limited` (429) moves the
limiter by `Retry-After`, `internal_error` (5xx) is retried with backoff (§51). A
**timeout is not retried**: the service served the request and billed it, so trying
again pays for the same page twice (`SCRAPEGRAPH_READ_ATTEMPTS`, one by default).

Set `SCRAPEGRAPH_FALLBACK_TO_SNIPPETS=false` to drop unreadable pages instead. Either
way the outcome is counted, and `GET /sources` reports it per platform — which is
Milestone 5's "record which sources consistently provide usable content", measured
rather than assumed:

```json
{"reader": "scrapegraph", "live": true, "cacheTtlHours": 168,
 "items": [{"platform": "linkedin", "pages": 24, "usable": 19, "blocked": 3,
            "notAPerson": 2, "usableShare": 0.792}]}
```

Settings → *Reading the sources* shows the same table.

### What one search may spend

A live search finds a hundred candidate pages without trying. Reading all of them is
the difference between a search costing cents and a search costing a plan, so both
ends are configuration:

| Setting | Means | Default |
|---|---|---|
| `MAX_PAGES_PER_SEARCH` | paid page reads per search; the rest become snippet leads | `25` |
| `TARGET_LEADS` | stop reading and judging once this many leads qualify | `0` (no target) |
| `SCRAPEGRAPH_READ_ATTEMPTS` | attempts per page — a served request is billed either way | `1` |
| `SCRAPEGRAPH_CREDITS_PER_PAGE` | what one page costs in plan units; the API reports none | `10` |

Three properties make the budget usable rather than arbitrary:

* **Candidates are read best-first.** `services/search/prospects.py` ranks them by
  what their search result alone already supports — the same scoring the product
  uses — plus a small per-platform prior for how readable a source tends to be.
  Nothing is dropped: ranking decides the *order*, and a snippet may never
  disqualify a page. Before this the budget went to whichever coroutine started
  first, which made the limit meaningless.
* **A refused page is not a lost lead.** It falls back to its search result, so the
  limit costs depth, not coverage. `pagesSkipped` says how many, so a thinner result
  is explained by the ceiling instead of looking like a bad search.
* **Cache hits are free and unbudgeted.** The budget sits behind the cache: a page
  read last week costs nothing to reuse, so a second identical search spends no
  budget at all. Requests the service refused (429, empty balance) give their slot
  back — one bad minute must not shrink the search.

`TARGET_LEADS` is what makes "find me twenty leads" cheap: candidates are read in
waves, each wave is judged as it lands, and the search stops as soon as it has
enough. One wave is the granularity, so at most `EXTRACTION_CONCURRENCY` pages are
read past the point where the target was met.

Cost is billed on what the *provider served*, not on what we could use: a page that
answered too late still spent its credits. Judging is only priced once a detector
that really calls an LLM is plugged in — the keyword stand-in is free, and pricing it
put a quarter of a euro on a search that spent nothing.

### The snippet extractor is still there

Without a ScrapeGraphAI key, live searches are extracted by
`SnippetProfileExtractor`, which builds a profile from the result metadata the search
API already returned and never opens a URL. It is honest about being thin: every
profile records `extractor: "snippet"`, confidence is capped at 0.65, a title it
cannot read a name out of returns nothing, and signals are keyword sightings
(`services/extraction/vocabulary.py`, one file so Phase 6 can delete it in one
commit) quoted with the sentence they were found in. It is also the fallback above,
which is why it did not become dead code.

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
| Page budget (§52) | real: `MAX_PAGES_PER_SEARCH`, `TARGET_LEADS`, candidates read best-first | — |
| Extraction (§33–34) | **`ScrapeGraphProfileExtractor`** when a key is set (cached, with the snippet extractor as fallback), `FixtureProfileExtractor` in the demo | — |
| Scrape cache (§53) | real, PostgreSQL, per canonical URL | — |
| Signal detection (§36) | `FixtureSignalDetector` — keyword sightings from the page's own text | Phase 6 — `LlmSignalDetector` |
| Scoring (§37–38) | real, deterministic | — |
| Deduplication (§45) | real, strong keys only — now including the links a page publishes | later: entity resolution |
| Cost tracking (§54) | real: search calls, pages read / cached / skipped, credits in plan units, unit costs from config | — |
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
    scraping/        base.py       the extraction and page-reading interfaces
                     page_schema.py the strict §34 schema, the prompt, the mapping
                     scrapegraph_extractor.py  the real page reader
                     cache.py      read once, remember the outcome (§53)
                     fallback.py   what to do when a page will not open
                     names.py      is this the name of a person?
                     snippet_extractor.py / fixture_extractor.py  the stand-ins
    extraction/      signal detection interface + adapters, keyword vocabulary
    scoring/         the deterministic scoring engine
    leads/           lifecycle, notes, outreach drafting
    dashboard/       aggregates
    adapters.py      which implementation is wired to what
  workers/           job service + the run_search task
alembic/versions/    the schema, versioned
tests/               220 tests: contract, scoring, pipeline units, lifecycle, filters,
                     persistence, the Brave provider, the ScrapeGraphAI reader, the
                     scrape cache, snippet extraction, and two live end-to-end runs
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
unreachable, because none of their URLs exist. The seeded searches carry `pagesRead`
and `pagesCached` figures too, so the usage card reads the same before and after a
real run.

### Configuration

All of it is environment (spec §22, §52) — see `../.env.example`. Provider keys
are read in `core/config.py` and nowhere else, and never leave the server:
`/health` reports whether a key is set, never its value.

`PIPELINE_STEP_DELAY_MS` (default 250) is demo pacing only: fixture adapters
answer instantly, so without it a search finishes in about a second and the
progress screen is never seen. It is ignored in live mode — Brave brings its own
latency — and `0` gives an instant fixture run.

The unit prices behind `usage.estimatedCostEur` are configuration as well
(`COST_PER_SEARCH_CALL_EUR`, `COST_PER_PAGE_EUR`, `COST_PER_LLM_CALL_EUR`). Pages are
billed by what was *read*: charging again for a cached page would make the cache
invisible in the only place it matters.

The suite runs against `DATABASE_URL`'s database name with `_test` appended,
created on demand — it never touches the workspace database.
