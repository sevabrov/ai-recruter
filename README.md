# AI Recruiter

AI-assisted lead discovery across the **public web**: search criteria in, scored
candidates with evidence out.

**Current state: Phase 2 — backend skeleton.** The FastAPI service is live and
the frontend runs against it: the browser talks to `http://localhost:8000`, and
the whole workflow (dashboard → wizard → search → results → lead → save) works
over HTTP.

Still no external service and no database. Web search, page extraction and
signal detection are fixture adapters — the pipeline around them is real, and
`/health` reports `"pipeline": "fixture"` so demo output is never mistaken for
live results.

```
ai-recruiter/
├── frontend/               Next.js 16 · React 19 · TypeScript · Tailwind 4 · Radix UI
│                           TanStack Query · Zustand
├── backend/                FastAPI · Pydantic · pytest — the API and the search pipeline
├── docker-compose.yml      backend + PostgreSQL 17 + Redis 7 + Adminer (nothing on the host)
├── infra/postgres/init/    extensions created on first container start
└── .env.example            server-side config: DB, Redis, provider keys, limits
```

Postgres and Redis are running-ready but unused: Phase 3 gives the backend a
database, Phase 7 gives it workers.

---

## Running it

Two commands: the API in Docker, the frontend on Node 22+ (`nvm use 22`).

```bash
docker compose up -d backend      # API on http://localhost:8000

cd frontend
npm install                       # already done if you cloned with node_modules
cp .env.local.example .env.local  # NEXT_PUBLIC_DATA_SOURCE=api
npm run dev                       # http://localhost:3000
```

If the API is not running the app says so in the sidebar and in Settings rather
than looking empty. To work without it, set `NEXT_PUBLIC_DATA_SOURCE=mock` and
restart `npm run dev` — the Phase 1 fixtures still work.

Other commands:

```bash
# frontend
npm run build                                            # production build
npx tsc --noEmit                                         # typecheck
npx eslint .                                             # lint

# backend (nothing installed on the host)
docker compose logs -f backend                           # structured JSON logs
docker compose run --rm --no-deps backend pytest -q      # 79 tests
docker compose run --rm --no-deps backend ruff check .   # lint
docker compose build backend                             # after a dependency change
```

API docs are served at <http://localhost:8000/docs>.

### Databases (Docker, nothing local)

Not needed yet — here so Phase 3 starts with one command.

```bash
cp .env.example .env
docker compose up -d           # backend :8000, postgres :5432, redis :6379, adminer :8081
docker compose ps              # health
docker compose down            # stop, data kept in named volumes
docker compose down -v         # stop and wipe data
```

Adminer opens at <http://localhost:8081> (server `postgres`, user/password from
`.env`).

---

## Themes

Two palettes, switchable from the top bar or Settings, plus "follow system":

| Theme | Look |
|---|---|
| **Daylight** | paper-cool light, mulberry accent `#a63d62` |
| **Graphite** | violet-tinted dark, rose accent `#d9648a` |

Everything is token-driven. Components never reference a hex value — they use
semantic utilities (`bg-surface`, `text-fg-muted`, `border-line`, `text-accent`,
`bg-good-soft`, …) that resolve through CSS custom properties.

**Adding a third theme is two steps and touches no component:**

1. add a palette block in [frontend/src/app/globals.css](frontend/src/app/globals.css) keyed by `[data-theme="<id>"]`
2. add an entry to `THEMES` in [frontend/src/lib/themes.ts](frontend/src/lib/themes.ts)

It then appears in the switcher and the Settings picker automatically. The
palette resolves in all three viewer states: no stamp + light OS, no stamp +
dark OS, and an explicit `data-theme` stamp (written by an inline script in
`<head>`, so there is no flash on first paint).

Semantic colours (`good` / `warn` / `bad` / `info`) are deliberately separate
from the accent hue, so score tiers never collide with brand colour.

Type: **Instrument Sans** (display) · **IBM Plex Sans** (body) · **IBM Plex
Mono** (labels, queries, data).

---

## Architecture — one switch, two data sources

No component imports a data source. Data flows:

```
page/component  →  TanStack Query hook  →  service interface  →  implementation
                   src/services/hooks.ts   src/services/types.ts   mock/ or api/
```

`NEXT_PUBLIC_DATA_SOURCE` in [frontend/src/services/index.ts](frontend/src/services/index.ts) picks the
implementation — `api` (default, the FastAPI backend) or `mock` (the Phase 1
fixtures, useful with nothing else running). Not a single component changed when
the backend arrived.

* [frontend/src/services/types.ts](frontend/src/services/types.ts) — the contract both sides implement:
  `Lead`, `LeadSignal`, `Search`, `SearchProgress`, `DashboardData`, `HealthStatus`.
  [backend/tests/test_contract.py](backend/tests/test_contract.py) asserts the API keeps matching it.
* [frontend/src/services/api/](frontend/src/services/api/) — the HTTP client.
* [frontend/src/services/mock/](frontend/src/services/mock/) — fixtures + a localStorage store.
* [backend/app/schemas/](backend/app/schemas/) — the same contract in Pydantic; camelCase over the
  wire, snake_case query parameters.

Three rules the product follows in both modes:

* **Scores are computed, not authored.** [backend/app/services/scoring/scoring_service.py](backend/app/services/scoring/scoring_service.py)
  turns `confidence × weight` into points. The model detects signals; code does
  the arithmetic. Every lead page shows the `+30 MLM / +20 Beauty / …` breakdown.
* **Progress is measured, not animated.** The worker writes counters as it goes;
  the UI polls `GET /searches/:id` and renders what it is told.
* **Keys never reach the browser.** Brave, ScrapeGraphAI and OpenAI keys are read
  by the backend only; `/health` reports whether one is configured, never its
  value.

### Where the real providers plug in

The pipeline is real end to end; three adapters at its edges are fixtures.
Details and the phase-by-phase swap table are in [backend/README.md](backend/README.md).

---

## Screens

| Route | What it does |
|---|---|
| `/` | Dashboard: stat tiles, recent searches, source share, score distribution, weekly discovery |
| `/search/new` | 5-step wizard: who → where → signals & weights → sources → preview |
| `/search/:id/progress` | Live pipeline (~3 s), measured counters, generated queries, usage & cost, cancel |
| `/search/:id/results` | Candidate table, filters (score/country/platform/signals/email/social), sorting, re-run |
| `/leads` | All / Saved / Archived across searches |
| `/leads/:id` | Score dial + breakdown, per-signal evidence with source links, AI summary, sources, notes, outreach draft |
| `/searches` | Search history, running searches separated |
| `/settings` | Theme picker, search defaults, live backend status, concurrency limits, reset demo data |

The wizard's **Fill example** button loads the MIHI / Spain scenario from the
spec, which is the fastest way to walk the whole flow.

---

## Known limitations (Phase 2, by design)

* **No new people are discovered.** The search provider and the extractor are
  fixtures over a seeded catalogue of 24 candidates. A search runs the real
  pipeline over them and re-scores them against your weights and geography — so
  criteria visibly change the outcome — but it cannot reach the open web. That is
  Phase 4–5.
* **Signals come from the seed, not a model.** The scoring, evidence and
  breakdown are real; detecting the signals is Phase 6.
* **Nothing is persisted.** State lives in the API process, so a
  `docker compose restart backend` returns to the seed. Phase 3 adds PostgreSQL.
* **Jobs run inside the API process** as asyncio tasks. Concurrent searches
  already do not block each other, but they do not survive a restart and cannot
  scale across machines. Phase 7 moves them to Celery + Redis.
* **No authentication.** Every request is attributed to one demo user, though
  every query is already scoped by `user_id`. Phase 8.
* **Outreach drafts come from a template**, not a model.
* **Search runs are paced deliberately** (`PIPELINE_STEP_DELAY_MS=250`): fixture
  adapters answer instantly and the progress screen would otherwise never be seen.
* **Export, bulk actions and pagination controls are not built** (the API supports
  pagination; the demo lists fit one page).

---

## Next: Phase 3

Database — PostgreSQL behind the existing `Repository` protocol, the entities
from spec §23, and the seed loaded once instead of on every boot. The services
and the API do not change.
