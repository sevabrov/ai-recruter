# AI Recruiter

AI-assisted lead discovery across the **public web**: search criteria in, scored
candidates with evidence out.

**Current state: Phase 5 — reading the pages.** The FastAPI service is live, the
frontend runs against it, the workspace is stored in PostgreSQL, searches reach the
open web, and each candidate's page is now opened and read:

```bash
BRAVE_SEARCH_API_KEY=…   # criteria → real queries → real URLs          (Phase 4)
SCRAPEGRAPH_API_KEY=…    # those URLs → the profile the page states     (Phase 5)
```

Both are optional. With neither, the app runs exactly as before over a seeded
catalogue of 24 candidates, so the demo works offline; with only the first, profiles
are built from search results instead of pages. Judging a profile with a model is
still a stand-in (Phase 6), and `/health` names the adapter behind every stage — demo
output is never dressed up as live results.

```
ai-recruiter/
├── frontend/               Next.js 16 · React 19 · TypeScript · Tailwind 4 · Radix UI
│                           TanStack Query · Zustand
├── backend/                FastAPI · SQLAlchemy · Alembic · pytest — API, pipeline, schema
├── docker-compose.yml      backend + PostgreSQL 17 + Redis 7 + Adminer (nothing on the host)
├── infra/postgres/init/    extensions created on first container start
└── .env.example            server-side config: DB, Redis, provider keys, limits
```

Redis is running-ready but unused: Phase 7 moves jobs onto it.

---

## Running it

Two commands: the API in Docker, the frontend on Node 22+ (`nvm use 22`).

```bash
docker compose up -d backend      # API on http://localhost:8000 (starts postgres too)

cd frontend
npm install                       # already done if you cloned with node_modules
cp .env.local.example .env.local  # NEXT_PUBLIC_DATA_SOURCE=api
npm run dev                       # http://localhost:3000
```

The API migrates its schema on start and seeds an empty database once, so the first
run needs nothing extra. If the API — or its database — is not running, the app says
so in the sidebar and in Settings rather than looking empty. To work without a
backend at all, set `NEXT_PUBLIC_DATA_SOURCE=mock` and restart `npm run dev`; the
Phase 1 fixtures still work.

### Searching the real web

```bash
cp .env.example .env                       # if you have not already
# BRAVE_SEARCH_API_KEY=…                   from https://api-dashboard.search.brave.com
docker compose up -d backend               # restart picks the key up
curl -s localhost:8000/health | jq .stages # {"search": "brave", …}
```

The free plan is enough to try it. One generated query is one billed request (≤20
results), a search fires four to twelve of them, and the plan's one-request-per-second
limit is honoured across every search running at once — so a live search takes a few
seconds and the progress screen shows it happening. Searches started before the key
was added keep their old results; new ones go to the web. Settings → *Pipeline stages*
shows the same thing the `/health` call above does.

### Reading the pages it finds

```bash
# SCRAPEGRAPH_API_KEY=…                    sign in at https://scrapegraphai.com/login
docker compose up -d backend               # restart picks the key up
curl -s localhost:8000/health | jq .stages # {"extraction": "scrapegraph", …}
curl -s localhost:8000/sources             # which platforms actually let us in
```

Now a candidate's own page is what becomes the lead: headline, city, languages,
follower count, contacts and the links they publish — which is also what lets one
person found on Instagram *and* on their own site stop being two leads. Reading a page
costs a credit, so every page is read once and cached for a week (`SCRAPE_CACHE_TTL_HOURS`),
and the usage card separates *pages read* from *from cache*.

Not every URL can be read — Instagram often shows a login wall to a server. Those
pages fall back to the search result rather than losing the lead, and every outcome is
counted per platform in Settings → *Reading the sources*.

**You say how many leads you want, and the wizard prices it.** The last step of a new
search asks for a number, and the backend answers with the queries it will run and
what they may cost: *N search calls, up to M paid pages, at most €X*. That figure is a
ceiling rather than a forecast — the same function produces it and the run's page
budget (`targetLeads × PAGES_PER_LEAD`, capped by `MAX_PAGES_PER_SEARCH`) — so a search
cannot cost more than it was quoted for. Candidates are read best-first, and the pages
past the budget still become leads from their search result, so a limit costs depth,
not coverage.

**Your own queries, next to the generated ones.** The review step lists every query
the search will run and lets you add your own. You pick where — Instagram,
LinkedIn, Facebook — and type what: `джерелія`. No operators to remember; the
composed queries are shown before they are added, and a bare word never leaks
into the whole web when only social platforms were chosen. Hand-written queries
run first and are never dropped by the query cap, and a Cyrillic one is put to the
Cyrillic index automatically.

Searching a social network returns posts far more often than profiles, so a reel,
a video or a photo is exchanged for the person who published it — the handle is in
the address (`instagram.com/yanarogozha/reel/…`) or in the result's own title.

**People only, and only where you asked.** Choosing a country and languages makes them
requirements, not points: a candidate who is not a person, or whose profile places
them in another country, or who publishes only in other languages, never becomes a
lead. A profile that says *nothing* about where it is passes and scores lower —
"we could not tell" is not "somewhere else", and treating the two the same emptied a
search once. The strict reading — *only if it can be confirmed* — is a switch of its
own on the *Geography* step.

The same choice also shapes the questions: a search for Ukraine in Ukrainian is
asked in Ukrainian words, against the Ukrainian index. The chosen sources are a
restriction too — no query leaves them, and a result from a platform you did not
pick is dropped rather than scored. Every requirement is switchable per search, the
wizard warns before you spend anything if a combination is likely to come back
empty, and if a search does return nobody the results screen breaks down who was
turned away, by which requirement, and what to change.

A result is two lists, not one. Alongside the people a search selected, it keeps
every candidate it turned away — with the address, the reason in words, and
whether anybody ever opened the page. That last column is the point: a candidate
refused on what they published was judged on evidence, one refused on a two-line
search snippet was judged on almost nothing, and the screen counts those
separately so *"are we losing leads in there?"* can be answered by opening them
rather than by trusting a number.

Other commands:

```bash
# frontend
npm run build                                            # production build
npx tsc --noEmit                                         # typecheck
npx eslint .                                             # lint

# backend (nothing installed on the host)
docker compose logs -f backend                           # structured JSON logs
docker compose run --rm backend pytest -q                # 306 tests (needs postgres)
docker compose run --rm --no-deps backend ruff check .   # lint
docker compose run --rm backend alembic current          # schema revision
docker compose build backend                             # after a dependency change
```

API docs are served at <http://localhost:8000/docs>.

### Databases (Docker, nothing local)

```bash
cp .env.example .env           # optional: the defaults already work
docker compose up -d           # backend :8000, postgres :5432, redis :6379, adminer :8081
docker compose ps              # health
docker compose down            # stop, data kept in named volumes
docker compose down -v         # stop and wipe the workspace
```

The workspace lives in the `postgres-data` volume. To start over from the seed,
either `POST /admin/reset` (the *Reset demo data* button in Settings) or
`docker compose down -v && docker compose up -d backend`.

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

Four rules the product follows in both modes:

* **Scores are computed, not authored.** [backend/app/services/scoring/scoring_service.py](backend/app/services/scoring/scoring_service.py)
  turns `confidence × weight` into points. The model detects signals; code does
  the arithmetic. Every lead page shows the `+30 MLM / +20 Beauty / …` breakdown.
* **Progress is measured, not animated.** The worker writes counters as it goes;
  the UI polls `GET /searches/:id` and renders what it is told.
* **Keys never reach the browser.** Brave, ScrapeGraphAI and OpenAI keys are read
  by the backend only; `/health` reports whether one is configured and which
  adapter each stage is running, never a key's value.
* **Questions travel to the store, not rows to Python.** The `/leads` filters,
  sorting and paging are one SQL statement behind
  [backend/app/db/repository.py](backend/app/db/repository.py) — the protocol the
  services depend on, so nothing above it knows there is a database.

### Where the real providers plug in

The pipeline is real end to end. Two of its three edges are real providers as soon as
their keys are set — web search and page extraction — and signal detection is a
stand-in until Phase 6. Details and the phase-by-phase swap table are in
[backend/README.md](backend/README.md).

---

## Screens

| Route | What it does |
|---|---|
| `/` | Dashboard: stat tiles, recent searches, source share, score distribution, weekly discovery |
| `/search/new` | 5-step wizard: who → where → signals & weights → sources → preview |
| `/search/:id/progress` | Live pipeline (~3 s on fixtures, longer live), measured counters, generated queries, pages read vs. cached, usage & cost, cancel |
| `/search/:id/results` | Two lists — **Selected** (filters by score/country/platform/signals/email/social, sorting, re-run) and **Filtered out** (every refused candidate with its address, reason and whether the page was ever read) |
| `/leads` | All / Saved / Archived across searches |
| `/leads/:id` | Score dial + breakdown, per-signal evidence with source links, AI summary, sources, notes, outreach draft |
| `/searches` | Search history, running searches separated |
| `/settings` | Theme picker, search defaults, live backend status, which adapter each pipeline stage runs, which sources can be read, concurrency limits, reset demo data |

The wizard's **Fill example** button loads the MIHI / Spain scenario from the
spec, which is the fastest way to walk the whole flow.

---

## Known limitations (Phase 5, by design)

* **Nobody is discovered without a key.** Out of the box the search provider and the
  extractor work over the seeded catalogue of 24 candidates: the real pipeline runs
  and re-scores them against your weights and geography, but it cannot reach the open
  web. Set `BRAVE_SEARCH_API_KEY` and it can.
* **Without `SCRAPEGRAPH_API_KEY`, a live search reads result snippets, not pages.**
  Those profiles are built from what the search API returned — title, description,
  page age, language — so they are thinner than the seeded ones and score lower.
* **A search reads 25 pages by default, not every candidate it finds.** That is the
  page budget (`MAX_PAGES_PER_SEARCH`), and it exists because a live search finds a
  hundred-plus candidates and reading them all spends a plan. The rest become leads
  from their search result, `pagesSkipped` says how many, and candidates are read
  best-first so the budget goes where it is likeliest to pay off. Raise it, or set
  `TARGET_LEADS` to stop at a number of leads instead.
* **The credit figure is configured, not measured.** The v2 API reports tokens but no
  credits, so `SCRAPEGRAPH_CREDITS_PER_PAGE` (10) is an assumption: run one search,
  compare your dashboard, set it to what actually moved. `PAGES_PER_LEAD` (3), which
  turns "find me ten leads" into a page budget and a price, is the same kind of
  number: a finished search reports both halves of it.
* **A hard country filter drops people whose bio never says where they live.** That is
  the honest cost of the requirement, and why it is a switch on the *Geography* step
  rather than a permanent rule. The same is true of the language filter: it reads the
  index's tag plus the profile's own script and words, and a two-line bio can support
  neither. If a country returns very few people, turn one of the two off before
  concluding the country is empty.
* **Deciding who is a person is still a heuristic.** Vocabulary, place names, a
  corporate voice and the platform's URL shape — not a model reading the page. It
  refuses the company accounts and directory pages that reached the client's list, and
  it will occasionally refuse a person whose name is also a brand. Phase 6's LLM
  detector is what replaces the guessing.
* **The phrasebook covers nine languages, shallowly.** Query translation is a
  hand-checked table of a handful of concepts and place names
  (`services/search/phrasebook.py`), so a language or country it does not know is
  simply searched in the client's own wording rather than badly.
* **Some platforms are hard to read.** Measured over this workspace's own attempts
  *before* the residential proxy was switched on: LinkedIn opened about half the
  time, Instagram once in twenty-three, Facebook never. Social pages are now
  fetched through ScrapeGraphAI's proxy with the page rendered (`SCRAPEGRAPH_STEALTH`,
  on by default, which doubles the credits those pages cost), and this is the number
  to re-measure after a run — expect improvement, not a solved problem. Those leads fall back to the search snippet and say
  so, which is why the wording of the *query* matters most on Instagram — a post
  caption found by a hashtag carries more about a person than a profile page nobody
  can open. `GET /sources` and Settings → *Reading the sources* report the hit rate
  per platform, so this is checkable rather than a claim.
* **One person can still appear twice** when the pages that would connect them are the
  ones that would not open. Merging is on strong keys only — shared URL, handle,
  e-mail, website — and a page that was read contributes the links a snippet cannot.
* **Signals are keyword sightings, not judgement.** The page reader quotes what the
  page says and the scoring is real and deterministic, but nothing weighs context,
  irony or negation yet. A model reading the profile is Phase 6.
* **Jobs run inside the API process** as asyncio tasks. Concurrent searches do not
  block each other and the job records are persisted, but a restart cannot resume a
  job in the middle of a stage — it re-queues the whole search — and they cannot
  scale across machines. Phase 7 moves them to Celery + Redis.
* **The dashboard's charts stay seeded.** The tiles are counted by the database and
  react to what you do; the source split, score distribution and weekly curve are
  still the fixture aggregates.
* **No authentication.** Every request is attributed to one demo user row, though
  every query is already scoped by `user_id`. Phase 8.
* **Outreach drafts come from a template**, not a model, and are not stored.
* **Fixture runs are paced deliberately** (`PIPELINE_STEP_DELAY_MS=250`): the
  stand-in adapters answer instantly and the progress screen would otherwise never
  be seen. Live searches ignore it.
* **Export, bulk actions and pagination controls are not built** (the API supports
  pagination; the demo lists fit one page).

---

## Next: Phase 6

AI candidate analysis — `LlmSignalDetector` behind the existing `SignalDetector`
interface, used as soon as `OPENAI_API_KEY` is set. Each signal is judged on the text
the page reader extracted, one structured call per profile: detected, confidence, the
verbatim evidence and where it came from. The model never sees or returns a score —
the backend keeps the arithmetic (spec §37) — and `services/extraction/vocabulary.py`,
the keyword list standing in for judgement today, is deleted in one commit. Nothing
above `services/adapters.py` changes.
