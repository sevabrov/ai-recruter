# AI Recruiter

AI-assisted lead discovery across the **public web**: search criteria in, scored
candidates with evidence out.

**Current state: Phase 1 — clickable mock frontend.** No search API, scraper,
model or database is called. Every number comes from fixtures, and the whole
workflow (dashboard → wizard → simulated search → results → lead → save) is
clickable end to end.

```
ai-recruiter/
├── frontend/               Next.js 16 · React 19 · TypeScript · Tailwind 4 · Radix UI
│                           TanStack Query · Zustand
├── docker-compose.yml      PostgreSQL 17 + Redis 7 + Adminer (nothing installed on the host)
├── infra/postgres/init/    extensions created on first container start
└── .env.example            server-side config: DB, Redis, provider keys (Phase 2+)
```

Later phases add `backend/` (FastAPI, Celery workers, ScrapeGraphAI, Brave
Search) next to `frontend/` — the compose file already sketches those services.

---

## Running it

Requires Node 22+ (`nvm use 22`).

```bash
cd frontend
npm install            # already done if you cloned with node_modules
cp .env.local.example .env.local
npm run dev            # http://localhost:3000
```

Other commands:

```bash
npm run build          # production build
npx tsc --noEmit       # typecheck
npx eslint .           # lint
```

### Databases (Docker, nothing local)

Not needed for Phase 1 — here so Phase 3 starts with one command.

```bash
cp .env.example .env
docker compose up -d           # postgres :5432, redis :6379, adminer :8081
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

## Architecture — why the Phase 2 swap is a one-liner

No component imports mock data. Data flows:

```
page/component  →  TanStack Query hook  →  service interface  →  implementation
                   src/services/hooks.ts   src/services/types.ts   mock/ or api/
```

* [frontend/src/services/types.ts](frontend/src/services/types.ts) — the API contract: `Lead`, `LeadSignal`,
  `Search`, `SearchProgress`, `DashboardData`, plus the `SearchService`,
  `LeadService` and `DashboardService` interfaces.
* [frontend/src/services/index.ts](frontend/src/services/index.ts) — the registry. `NEXT_PUBLIC_DATA_SOURCE=mock|api`
  picks the implementation.
* [frontend/src/services/mock/](frontend/src/services/mock/) — fixtures + a localStorage-backed store so saved
  leads, statuses and notes survive a refresh.
* [frontend/src/services/api/](frontend/src/services/api/) — already written against the endpoints from the
  spec (`POST /searches`, `GET /searches/:id`, `GET /leads`, `PATCH /leads/:id`,
  …). Inactive until the backend exists.
* [frontend/src/mocks/](frontend/src/mocks/) — the fixture data itself (`leads.ts`, `searches.ts`,
  `dashboard.ts`, `search-progress.ts`).

Two rules the mock phase already follows so behaviour won't change later:

* **Scores are computed, not authored.** [frontend/src/lib/scoring.ts](frontend/src/lib/scoring.ts) turns signal
  confidence × weight into points. The model detects signals; the code does the
  arithmetic. Every lead page shows the full `+30 MLM / +20 Beauty / …`
  breakdown.
* **Progress is polled, not animated.** `GET /searches/:id` is polled every
  ~0.7 s and the mock service derives status and counters from elapsed time, so
  the progress screen reads real state rather than a client-side animation.

Provider keys (Brave, ScrapeGraphAI, OpenAI) live only in the server-side
`.env`. The browser sees `NEXT_PUBLIC_*` variables only.

---

## Screens

| Route | What it does |
|---|---|
| `/` | Dashboard: stat tiles, recent searches, source share, score distribution, weekly discovery |
| `/search/new` | 5-step wizard: who → where → signals & weights → sources → preview |
| `/search/:id/progress` | Simulated pipeline (~9 s), live counters, generated queries, usage & cost, cancel |
| `/search/:id/results` | Candidate table, filters (score/country/platform/signals/email/social), sorting, re-run |
| `/leads` | All / Saved / Archived across searches |
| `/leads/:id` | Score dial + breakdown, per-signal evidence with source links, AI summary, sources, notes, outreach draft |
| `/searches` | Search history, running searches separated |
| `/settings` | Theme picker, search defaults, integration status, concurrency limits, reset demo data |

The wizard's **Fill example** button loads the MIHI / Spain scenario from the
spec, which is the fastest way to walk the whole flow.

---

## Known limitations (Phase 1, by design)

* **Mock data only.** Nothing external is called. Dashboard aggregates describe a
  fuller workspace than the fixture list — searches you start add to them.
* **Search results are cloned from the fixture pool.** A new search re-scores
  those candidates against *your* weights and geography (so criteria visibly
  change scores and ranking), but it cannot discover new people.
* **Simulated pipeline is ~9 s** and the counters are scripted, not measured.
* **No authentication and no server state.** Saved leads, statuses and notes live
  in browser localStorage; Settings → *Reset demo data* clears them.
* **Deduplication, cost tracking and evidence are represented, not implemented** —
  the UI shows what the backend will produce.
* **Outreach drafts come from a template**, not a model. The request shape already
  matches `POST /leads/:id/outreach`.
* **Export, bulk actions and pagination controls are not built** (the contract
  supports pagination; the demo lists fit one page).

---

## Next: Phase 2

Backend skeleton — FastAPI with `GET /health`, the endpoints from spec §57, and
`NEXT_PUBLIC_DATA_SOURCE=api` flipping the frontend over. No UI rewrite needed.
