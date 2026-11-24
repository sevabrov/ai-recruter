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

Without them nothing calls out, and searches find no one: the app ships no demo
data. `/health` always says which stage is real:

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
docker compose run --rm backend pytest -q            # 306 tests (needs postgres)
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
users ─┬─< searches ─┬─< leads ─< lead_notes
       │             └─< search_rejections   (what the run turned away, and why)
       └─< jobs                 scrape_cache (one row per page ever read)
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
* **A new database starts empty.** The first boot creates the owner row and
  nothing else; migration `0007` removed the demo workspace earlier versions
  inserted.

Adminer at <http://localhost:8081> (server `postgres`) is the quickest way to look
at the rows.

---

## Endpoints

| Method | Path | Notes |
|---|---|---|
| GET | `/health` | spec §21 — `{"status": "ok"}` plus what is wired up; queries the database |
| POST | `/searches` | returns `202` immediately with `{searchId, status}` (§39) |
| POST | `/searches/estimate` | prices a search and previews its queries; creates nothing |
| GET | `/searches` | history, newest first |
| GET | `/searches/:id` | status, progress, usage, queries — the polling target (§43) |
| GET | `/searches/:id/leads` | results, same filters as `/leads` |
| GET | `/searches/:id/rejected` | the candidates it turned away, with the reason and the address (`?reason=`, `?limit=`) |
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
  that would fail (`services/search/markets.py`).
* **And a language, per query.** A search for Ukraine, written in English, finds
  English pages *about* Ukraine: company directories, "Top 10 MLM companies"
  listicles, the Romanian representative of a global brand. So each language the
  client asked for gets its own set of queries, written in that language and put
  to that language's index — `Україна`, `мережевий маркетинг`, `search_lang=uk`.
  The phrasebook is small and hand-checked (`services/search/phrasebook.py`); a
  language it cannot name the place in is not asked in at all, because that would
  only be the English query with a foreign label on it. The round-robin in
  `_interleave` is what stops `MAX_QUERIES_PER_SEARCH` from spending the whole
  allowance on one language.
* **English is a language you have to ask for.** The untagged pass writes the
  client's words unchanged, which in practice means English words put to the
  English index — and running it regardless spent a quarter of a Ukrainian
  search's calls on `site:instagram.com "network marketing" Ukraine`: the widest
  phrase in the niche, asked in the language of the niche's *global brands*. Back
  came Network Marketing Pro, Network Marketing Quotes and Eric Worre — 17 of that
  run's 41 addresses, not one of them a person in Ukraine. So it runs when English
  is one of the chosen languages, when none was chosen, and as the fallback when
  no chosen language can be written at all (`_passes`).
* **The client's industry reaches the queries, not only the score.** The industry
  and a role word (`дистриб'ютор`, `distributor`) join every `site:` query whose
  keyword list holds one entry — which is what a search with no keywords of its
  own has, and its one keyword is the niche's generic name. That is precisely what
  the niche's brand accounts are called: one run refused 22 of 26 candidates as
  organisations. Until now the industry reached only the open-web templates, so a
  social-only search scored people it had had no hand in finding.
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

### Only the sources that were asked for

Three of the templates carry no `site:` operator — they are how a personal website
or a directory entry is found. With only social sources selected they were about a
third of the billed calls, spent outside the sources, and that is how
`pravo.ua/articles/setevoj-marketing` — a legal journal on network-marketing
legislation — became a run's only lead. Two rules now, deliberately overlapping:

* **no `site:`-less query unless an open-web source was selected**
  (`PUBLIC_WEB`, `COMPANY_WEBSITES`, `BLOGS`);
* **a discovered URL is dropped unless its platform is covered by a chosen source**
  (`url_tools.PLATFORMS_BY_SOURCE`), counted as `rejectedOffSource`.

The second is not redundant: `site:` is a request, not a guarantee. Enforcing the
instruction where the money is spent *and* where the results arrive is what makes
"look only where I said" true rather than likely.

### Hashtags, and the post that names its author

Generated hashtag queries were an obvious-looking idea that measurement killed:
all six of them, across Instagram and Threads, returned exactly zero results — a
quoted `"#tag"` inside a `site:` query is not a question the index answers, and a
third of that run's billed calls bought nothing. Hashtags now live only in
`customQueries`, where the client writes the form that works for their market and
sees at once whether it returns anything.

The mechanism they were for matters far beyond hashtags: searching a social
network for a *phrase* returns content — reels, videos, photos, posts — much more
often than it returns accounts. `classify` rightly refuses a post as a candidate,
so `url_tools.promote_posts` exchanges it for the profile it points at, keeping
the post's own words as the evidence that was found.

The author is written down in two places, and the address is the one that counts.
`instagram.com/yanarogozha/reel/C3Z5y19owoo` names `yanarogozha` in its first
segment; anything shaped `{handle}/{reel|p|videos|posts|…}/…` does, on Instagram,
Threads and Facebook alike. One run threw away three real people — two Instagram
reels and a Facebook video — as "not a person" while their handle sat in the URL
we had been handed. The second place is the result title
("Марина Іванова (@marina.mlm) on Instagram: …"), which is where Instagram and
Threads put the handle when the address carries none (`instagram.com/p/Cxyz`).
Nothing is invented either way: the handle is verbatim from the provider's own
address or text, and the profile URL is the platform's documented shape.

The same shape check works the other way. A social platform publishes profiles in
one documented form, so an address that is not that form is not a person we
failed to recognise — `instagram.com/accounts/login`, `facebook.com/photo.php?…`,
`facebook.com/581399108893746` and `instagram.com/popular/…` are a login form, a
photograph, a page's internal id and a directory. They used to reach the scoring
stage and land on the results screen counted as "not a person", which reads as
"the search found somebody unsuitable" when it had found nothing at all.

### Queries the client writes

`criteria.customQueries` are run ahead of every generated query and are never
dropped by `MAX_QUERIES_PER_SEARCH` — the cap eats templates instead. A template
knows the criteria; it does not know that a market distributes `джерелія`, and
somebody who does can write that in one word. The language is read off the query
itself (`extraction/language.detect_codes`), so a Cyrillic query reaches the
Cyrillic index without being told twice.

**A query with no `site:` operator inherits the search's sources.** Asked to write
the query, the client wrote `джерелія` — the right word, put to the whole indexed
web, which answered with the brand's own site, four shops, a catalogue, an
app-store listing and a hotel called Jerelia. Eighteen of those twenty results
were then dropped as off-source, and the results screen reported them as "found on
a platform you did not select", which read as though the search had gone
somewhere it was not asked to. It had not. Now the query is asked of each chosen
platform (`site:instagram.com джерелія`, …); when the open web is among the
sources the bare query is a fair question and stays as written. The wizard makes
the same thing explicit: *where* is a row of platform buttons, *what* is a text
field, and the composed queries are shown before they are added — nobody should
have to know that `site:` is what turns a brand name into a question about people.

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
* **How the page is fetched decides whether it opens at all.** Sending only
  `{url, prompt, schema}` — no `fetchConfig` — is what a measured run cost: 20 of 23
  Instagram pages and 15 of 15 Facebook pages answered 502/504, because the
  provider's default is a datacentre address, which is the request a social network
  is surest to refuse. Social profiles are now fetched with `stealth` (a residential
  proxy plus anti-bot headers), a settle-time `wait`, and `country` set to the
  country being searched — which also makes the page arrive in the form a local
  visitor sees, city included. Only the platforms that need it pay the surcharge
  (`STEALTH_PLATFORMS`); a personal website is read the cheap way.
* **…and sending a config the service will not honour costs more than sending
  none.** `mode: "js"` is a documented value and reads like the right one for a
  profile page, but on Instagram, Facebook and LinkedIn the service answers
  `400 fetch_provider_config` — measured one key at a time against live URLs;
  `stealth`, `country` and `wait` are each accepted, `js` alone is not. A 400 is
  correctly not retryable, so the chain below switched page reading off for the
  whole run: three searches finished in seven seconds with 0 pages read, 0 credits
  spent and every candidate judged on two lines of search-result text. The mode is
  `auto` now, and a refused `fetchConfig` is *dropped* — the page is asked for again
  plainly, and the refusal is remembered so the rest of the process does not pay a
  wasted round trip per page. One unsupported key can no longer end a search.
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

### Only people, and only where you asked (spec §32, §35)

A measured run for Ukraine returned four leads: a beauty distributor in Zagreb, a
listicle titled *"Top 10 MLM Companies in the Ukraine"*, a Facebook page for a
magazine with ten likes, and one real distributor — in Romania. All four scored,
because the country was worth ten points rather than being a requirement, and all
four passed the name check, because "Orbico Beauty Croatia" *is* shaped like a
name: capitalised words, no company suffix.

Three criteria therefore stopped being weights and became gates
(`services/search/eligibility.py`, applied before the detector runs, so a refused
candidate is never paid for):

| Gate | Refuses when | Switch |
|---|---|---|
| person | `personhood.assess` says the page is an organisation | always on |
| country | the profile places the person **somewhere else** | `requireLocation` |
| country | …or says nothing about it | `requireConfirmedLocation` (off) |
| language | the profile publishes **only in other** languages | `requireLanguage` |
| language | …or shows no language at all | `requireConfirmedLanguage` (off) |

**A gate refuses a contradiction, not a silence.** The first version treated "this
person is in Romania" and "we could not tell" as one answer, and a search for ten
leads returned none: of 24 candidates refused, 19 went on geography and exactly
*one* was actually somewhere else. The rest were Instagram profiles whose page
would not open and whose two-line description named no city — no evidence, not
contrary evidence. So an unproven criterion passes and pays for it in points (the
signal stays `detected: false`, so the lead sorts below the confirmed ones), and
the `requireConfirmed*` switches restore the strict reading for a client who would
rather have five certain people than fifty likely ones.

The client's own search terms count as evidence too. `vocabulary.py` holds general
words — "network marketing", "distribuidora", "сетевой маркетинг" — and has never
heard of Jerelia, Farmasi or MIHI, so a search for Jerelia distributors found them
and then refused them for missing the MLM signal while their profiles said the
brand's name in the first line. `FixtureSignalDetector` now fills that gap from
`keywords` + `businessTypes` (the MLM signal) and `industry` (the industry signal),
quoted like anything else, and never overwriting what the page itself said.

`services/extraction/personhood.py` asks three questions past the name's shape,
and any one of them refuses: **the words** (community, news, magazine, academy, a
legal form), **the place** — people are not named after countries and cities, which
is what catches brand-plus-market naming a wordlist never finishes covering — and
**the voice**: a company writes "we are", "our clients", "founded in 1984", a
person writes "I". Platform structure cuts both ways: `/in/<slug>` on LinkedIn is a
person by construction and settles the question before any wordlist gets an
opinion, while a Facebook page announces itself with a like count and a category.

Both filters are per search because their honest cost is the person whose bio
never says where they live. The refusals are counted on the search's progress
record — `rejectedNotAPerson`, `rejectedUnreadable`, `rejectedCountry`,
`rejectedLanguage`, `rejectedSignals` — so four leads out of forty is explained
rather than mysterious, and every one of them is also listed by address (below).

Two supporting changes make the country gate survivable: `find_place` reads cities
and inflected Slavic forms ("Київ", "з України"), because a bio names its city far
more often than its country; and `services/extraction/language.py` gives the
crawler's language tag a second opinion from the text's own script and function
words, since one tag on a whole page decided too much.

### The other half of the result (spec §43)

A run that returns four leads out of fifty candidates used to answer *why* with a
set of counters. A counter cannot be checked, and it does not answer the question
the client actually asks: **are we losing leads in there?**

So every candidate a run turns away is now stored with the address it was found at
and the reason in words (`models/rejection.py`, table `search_rejections`,
`GET /searches/:id/rejected`). Together with the leads it is a complete account of
what the search saw — every discovered URL is in exactly one of the two lists —
and a refusal that turns out to be a real person is then a bug with a URL attached
to it rather than a suspicion.

| Reason | Recorded at | Paid for |
|---|---|---|
| `not_a_profile` | discovery — a shop, an article, a login form, a numeric page id | no |
| `off_source` | discovery — a real profile on a platform that was not a source | no |
| `unreadable` | extraction — the reader failed on the address | attempt only |
| `not_a_person` | extraction — the page was read and named nobody | yes |
| `wrong_country` / `wrong_language` / `missing_signals` | judging | yes |
| `not_examined` | the lead target was reached and the run stopped here | no |

Two fields carry most of the value. `read` says whether the page itself was ever
opened: a candidate refused on what they published was judged on evidence, one
refused on a two-line search snippet was judged on almost nothing — and that is
where a lost lead hides. `promise` is the ranking score the run gave the candidate
before spending anything (`services/search/prospects.py`), so the list is ordered
by *what the run itself thought was most worth reading*, and the first rows are the
refusals worth a second look.

Two consequences for the counters. `unreadable` is split out of
`rejectedNotAPerson`, which used to hold both — "we opened the page and there was
no person on it" is a verdict about the candidate, "we never got the page" is a
verdict about the reader. And a post whose author *was* followed
(`instagram.com/anna/reel/C3Z…` → `instagram.com/anna`) says so in its refusal
line, because otherwise it reads as a person thrown away while that person is
sitting in the lead list.

### What one search may spend

A live search finds a hundred candidate pages without trying. Reading all of them is
the difference between a search costing cents and a search costing a plan, so both
ends are configuration:

| Setting | Means | Default |
|---|---|---|
| `MAX_PAGES_PER_SEARCH` | paid page reads per search; the rest become snippet leads | `25` |
| `TARGET_LEADS` | stop reading and judging once this many leads qualify | `0` (no target) |
| `PAGES_PER_LEAD` | how many paid pages one lead costs — turns a target into a budget | `3` |
| `MAX_QUERIES_PER_SEARCH` | generated queries, and so billed search calls — across all waves | `96` |
| `QUERIES_PER_WAVE` | with a lead target, queries sent per wave; another wave goes out only while short of the target | `12` |
| `MAX_RESULT_PAGES` | pages of results one query may ask for, when its last page came back full | `3` |
| `SCRAPEGRAPH_READ_ATTEMPTS` | attempts per page — a served request is billed either way | `1` |
| `SCRAPEGRAPH_CREDITS_PER_PAGE` | what one page costs in plan units; the API reports none | `5` |
| `SCRAPEGRAPH_STEALTH` | read social profiles through the residential proxy | `true` |
| `SCRAPEGRAPH_STEALTH_CREDITS` | what that proxy adds per page | `5` |

The lead target moved into the search itself: the wizard asks *"how many leads do
you want?"*, `POST /searches/estimate` prices it, and the run is given exactly the
budget that was quoted — `targetLeads × PAGES_PER_LEAD`, capped by
`MAX_PAGES_PER_SEARCH`. The quote is a **ceiling, not a forecast**, and it is
enforceable precisely because `services/search/estimate.py` produces both numbers:

    cost ≤ queries × price(search call) + pages × price(page)

`PAGES_PER_LEAD` is the one figure in that arithmetic that is an assumption. A
finished search reports `pagesRead` and its lead count, so it is meant to be set
from measurement rather than left alone.

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
| Extraction (§33–34) | **`ScrapeGraphProfileExtractor`** when a key is set (cached, with the snippet extractor as fallback), `FixtureProfileExtractor` offline (finds no one outside the tests) | — |
| Scrape cache (§53) | real, PostgreSQL, per canonical URL | — |
| Signal detection (§36) | `FixtureSignalDetector` — keyword sightings from the page's own text | Phase 6 — `LlmSignalDetector` |
| Scoring (§37–38) | real, deterministic | — |
| Deduplication (§45) | real, strong keys only — now including the links a page publishes | later: entity resolution |
| Cost tracking (§54) | real: search calls, pages read / cached / skipped, credits in plan units, unit costs from config | — |
| Storage (§23) | **PostgreSQL 17 + Alembic** | — |
| Jobs (§39–41) | asyncio tasks in the API process, recorded in the database | Phase 7 — Celery + Redis |
| Auth (§55) | one owner row, every query scoped by `user_id` | Phase 8 |

Swapping an adapter is a decision in [app/services/adapters.py](app/services/adapters.py): a
provider is used as soon as its key is configured, otherwise a stand-in keeps the
product working. Nothing else in the codebase names a vendor — `SEARCH_PROVIDER=fixture`
forces the offline stand-ins even with a key present, which is what the test suite uses.

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
    postgres.py      the SQL implementation: filters, locking
    tables.py        the schema — what is a column and what is JSONB
    mappers.py       rows ↔ domain models, and the query mirrors
    engine.py        the connection pool
    bootstrap.py     `alembic upgrade head`
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
tests/               306 tests: contract, scoring, pipeline units, lifecycle, filters,
                     persistence, the Brave provider, the ScrapeGraphAI reader, the
                     scrape cache, snippet extraction, the person/country/language
                     gates, the refused-candidate list, localized queries, the cost
                     estimate, and two live end-to-end runs
```

### Test data

The app ships no data. The test suite has its own workspace in
`tests/data/workspace.json` (four searches, 24 leads): `tests/conftest.py` inserts
it before each test and hands its leads to the offline stand-ins, so a test search
rediscovers those people through the real pipeline and re-scores them against the
criteria. Timestamps are rebased when the file is loaded, so "3 hours ago" stays
true however long it sits in git.

### Configuration

All of it is environment (spec §22, §52) — see `../.env.example`. Provider keys
are read in `core/config.py` and nowhere else, and never leave the server:
`/health` reports whether a key is set, never its value.

`PIPELINE_STEP_DELAY_MS` (default 250) is offline pacing only: the stand-ins
answer instantly, so without it a search finishes in about a second and the
progress screen is never seen. It is ignored in live mode — Brave brings its own
latency — and `0` gives an instant fixture run.

The unit prices behind `usage.estimatedCostEur` are configuration as well
(`COST_PER_SEARCH_CALL_EUR`, `COST_PER_PAGE_EUR`, `COST_PER_LLM_CALL_EUR`). Pages are
billed by what was *read*: charging again for a cached page would make the cache
invisible in the only place it matters.

The suite runs against `DATABASE_URL`'s database name with `_test` appended,
created on demand — it never touches the workspace database.
