# CLAUDE.md — lead-bot

Technical context for AI assistants working in this repo. Read before changing things.

## What this is

A **Telegram sales bot** for **suslicketeam**: you DM it a 2GIS link + a few facts about a
local business → an LLM extracts structured fields → preview + confirm → it creates a
**Lead** in **Twenty CRM** (`https://crm.suslicketeam.com`). Plus pipeline read commands,
KPI, scheduled digests. It's the capture front-end for the studio's outbound sales.

- **Companion infra (separate):** the **Twenty CRM** itself lives on the same VPS but is a
  different system; its admin/schema lives in the main website repo's `CLAUDE.md`. This repo
  is **only the bot**.
- **Whitelisted** (only the owner's Telegram id). **Long-polling** (no public webhook).

## Stack

- **Python 3.12**, **aiogram v3** (Telegram), **httpx** (Twenty REST + OpenAI-compat LLM),
  **APScheduler** (digests), **sentry-sdk** (optional), **anthropic** (only if that provider).
- Docker; deployed to **`/opt/lead-bot`** on the `netcup` VPS, `network_mode: host` so it
  reaches Twenty at `127.0.0.1:4000` (Twenty's API is never exposed publicly).

## Architecture (`app/`)

Layered; one aiogram **Router per feature**; dependencies built once in `main.py` and
**injected** into handlers by parameter name (aiogram contextual data `dp["twenty"]`, …).

```
app/
  main.py        entrypoint — build deps, inject, wire routers (whitelist on each), start
  config.py      Settings (from env) + ConfigStore (runtime JSON: KPI goal, digest times, LLM caps)
  usage.py       UsageStore — per-user/day LLM token+request counters (data/usage.json)
  twenty.py      TwentyClient (Leads + Company/Opportunity records + Metadata-API options) + to_payload / to_company_payload / to_opportunity_payload
  llm.py         Extractor protocol + OpenAICompat/Anthropic extractors (return Extraction: fields + Usage) + provider registry + schema_with_options
  reference.py   OptionsRegistry — live niche/source Select options cached from Twenty (mirrored onto Company)
  stats.py       StatsService — pipeline counts, KPI (new prospects today), digest text
  scheduler.py   DigestScheduler (APScheduler, reschedulable at runtime)
  filters.py     Whitelist (applied per router)
  keyboards.py   confirm_kb / dup_kb / convert_kb
  timeutil.py    today-bounds (Asia/Almaty), ISO parse, progress bar
  handlers/      menu · common · capture · queries · kpi · digest · reference · usage · convert
```

- **menu.py** owns `/start` + `/menu` → a **persistent bottom panel** (`keyboards.main_kb`,
  ReplyKeyboard: Today · Pipeline · Convert · Currency · Niches · Usage · Help). A reply-button tap
  arrives as plain **text** (its label), so the `F.text.in_(NAV)` handler must run *before*
  capture's catch-all — `menu.router` is first in `get_routers()`, so it does. Both it and the
  typed commands funnel through one `_run(action, …)` render (no logic dupe — e.g.
  `convert.convertible()`). `main` also calls `set_my_commands` so the full command list shows in
  Telegram's blue "Menu". (Per-message lists like the convert picker stay **inline** — `convert_kb`.)

- **capture.py** is the core flow: text → `extractor.extract` (in a thread) → `to_payload`
  → **dedup** by `prospectLink` (then exact name) → preview with `confirm_kb` or `dup_kb`
  → callbacks `create:` / `update:` / `cancel:`. **Multi-lead:** the LLM returns `{leads:[…]}`
  (capture tolerates a flat lead too); **1** → the rich single draft; **N** → a compact summary +
  `batch_kb` "Create all" (intra-message dedupe via `_dedupe_within`, CRM dups skipped, `createall:`
  callback) — one LLM call for the whole batch. **Update refreshes facts only**
  (`_REFRESHABLE`: niche, hasWebsite, city, contact, prospectLink, addressText, reviewsCount,
  rating, language) — it must NOT touch `stage`/`nextStep`/`notes` (the user's pipeline work).
  Before spending a call it checks the **per-user daily LLM cap** (`usage.over_limit`) and hard-stops;
  after a successful extract it records the call's token usage.
- Commands: `/start` `/menu` `/today` `/pipeline` `/leads <stage>` `/kpi [set N]` `/digest [list|add HH:MM|remove HH:MM|off]` `/niche [add <name>]` `/source [add <name>]` `/convert` `/harvest` `/currency [CODE]` `/usage` `/llm set req|tok <n>` `/members [add|remove <id>]` `/settings` `/help`.
- **Runtime allowlist (`/members`, `app/handlers/members.py`):** env `ALLOWED_TELEGRAM_IDS` are **admins**; admins add/remove extra **members** (persisted in `config.json`). `filters.Whitelist` reads `admins ∪ config.members` **live** per event (not frozen at startup), so a new member works without a restart. Members may use the bot but not manage the allowlist. `/harvest` is also reachable from the bottom-panel **🌍 Harvest** button (a `harvest.router` `F.text==` handler, not in `menu.NAV`).

### Dynamic niche/source options (`app/reference.py` + Metadata API)

Niche/source are Twenty **Select** fields. Their options are NOT hardcoded at runtime — `OptionsRegistry`
reads them off the Lead object via the **Metadata API** (`POST /metadata` GraphQL) at startup and after
each `/niche add`, and feeds them to **both** coupling points: `schema_with_options()` (the enum the LLM may
pick) and `to_payload()` (label → option VALUE). `twenty.NICHE`/`SOURCE` remain as a **seed/fallback** so a
metadata hiccup degrades to old behaviour instead of mapping everything to OTHER.

- `/niche add <name>` calls `updateOneField` which **replaces the whole options array** → the bot must send
  back the live options (each with its real `id`); it `refresh()`es first and refuses to mutate from the
  un-synced seed (no ids), so it can't regenerate ids / orphan records. VALUE is derived `_option_value()`
  (ASCII UPPER_SNAKE; **RU is transliterated** so `Барбершоп`→`BARBERSHOP`).
- Verified live (query + add + restore) with the **bot's own** Twenty key — that key has metadata-write perms.
  Known ids: Lead object `52b9769d-…-78f6ed3098f8`; `niche` field `5577b72c-…`, `source` `27af265a-…`.

### 2GIS link enrichment (`app/twogis.py`, gated on `TWOGIS_API_KEY`)

Paste a 2GIS link → the bot pulls the facts itself (no LLM, no browser). `capture` detects
`firm/<id>` links (`find_firms`); if `TWOGIS_API_KEY` is set it calls the **Catalog API**
(`/3.0/items/byid`, `fields=items.reviews,items.rubrics,items.contact_groups,items.address,…`)
per firm and shapes the result **like the LLM's output dict** (`item_to_fields` → labels, not
VALUEs, so `to_payload` maps them unchanged). Rubric → niche via the `_RUBRIC_NICHE` keyword map
(unknown → "Other"). Then the same single/batch `_present_drafts` flow. **Unset key → the whole
branch is skipped** (`dp["twogis"]=None`), behaviour identical to text+LLM.

- **Why no keyless / headless** (tested empirically, don't re-litigate): a raw fetch of a 2GIS
  firm page is an anti-bot SPA shell (no data, no key); a headless Playwright render from the VPS
  IP gets a **2GIS CAPTCHA** (datacenter IP blocked); and the box has ~870 MB free RAM, no swap, so
  Chromium-per-capture would OOM-risk the CRM. The Catalog API (a **free demo key** works) is the
  only robust path. **Field caveats (verified on a demo key):** `reviews` works but the keys are
  `general_rating`/`general_review_count` (branch) with `org_*` fallback — NOT `rating`/`review_count`;
  `contact_groups` (phone/website) is **restricted** on the demo plan (absent from the response), so
  `contact` stays empty and `hasWebsite` defaults to "No" — fill those manually or upgrade the plan.
  Enrichment degrades gracefully when a field is missing.

### OSM harvest + enrichment (`app/osm.py` + `app/osm_tags.py` + `app/handlers/harvest.py`, gated on `OVERPASS_URL`)

Makes the bot a **source** of leads, not just a logger. Two modes, both off when
`OVERPASS_URL` is unset (`dp["overpass"]=None`; `/harvest` not advertised by `set_my_commands`):

- **Harvest (`/harvest`):** pick a niche (inline kb, from live niches ∩ `NICHE_TAG_MAP`) →
  send a city/district (FSM `Harvest.city`) → `OverpassClient.harvest()` runs an Overpass-QL
  `area["name"=…]` query and returns ≤ `HARVEST_LIMIT` (50) places → each `OsmPlace.to_fields()`
  (LLM/2GIS-shaped, labels) → `to_payload` → the **same `capture._present_drafts` batch flow**
  ("Create all", per-lead ✏️, dups skipped). So the harvest handler is thin — all the
  draft/dedup/confirm machinery is reused.
- **Enrichment:** on the **text→LLM** path, `capture._osm_enrich` backfills only-empty
  `addressText`/`contact` (+ stamps `osmId`, upgrades `hasWebsite`) from a **unique**
  `find_by_name(name, city)` match (>1 → don't guess). Best-effort: any Overpass error is
  swallowed, capture never blocks.

- **`NICHE_TAG_MAP`** (niche LABEL → OSM `(key,value)` tags) is a **product decision**, editable:
  `Cafe`=`amenity=cafe` only; `Beauty`=`shop=beauty`/`hairdresser`+`leisure=spa`+`shop=massage`;
  `Gaming club`=draft (`adult_gaming_centre`/`internet_cafe` — OSM coverage is weak, expect few).
  The label MUST match the niche vocabulary (else `to_payload`→OTHER).
- **OSM has no reviews/rating** — those stay empty (filled later from 2GIS). The stable
  `osm_type/id` (e.g. `node/123`) is written to **`Lead.osmId`**, the dedup key that survives the
  `prospectLink` being swapped to a 2GIS URL. **Dedup** (`capture.find_duplicate`) now matches
  `osmId` → `prospectLink` → name (city-scoped), so a re-harvest and a 2GIS twin both collapse.
- **Infra:** a **self-hosted Overpass** (`wiktorn/overpass-api`, Kazakhstan extract) runs on the
  **netcup-observ** box at `/opt/overpass` (NOT the CRM box — it's RAM-tight, no swap). The bot
  reaches it at `127.0.0.1:12347` via a **forward-only SSH tunnel** (systemd `overpass-tunnel.service`
  on the CRM host → observ `127.0.0.1:12347`, key restricted `permitopen=127.0.0.1:12347`). So
  `OVERPASS_URL=http://127.0.0.1:12347/api/interpreter` even though Overpass is on another host.
  Chosen over public Overpass (rate limits) and a public TLS endpoint (no nginx/cert on observ; the
  tunnel needs no firewall changes). Not Nominatim — enrichment matches by name+area via Overpass,
  so one instance serves both modes. (Geofabrik dropped `.osm.bz2` for KZ → the `.pbf` was converted
  to `.osm.bz2` with `osmium` and imported via `file://`; `OVERPASS_COMPRESSION=gz`, not `gzip`.)
- **Prod prerequisites (Metadata API, one-off on the live CRM — see website repo's CRM section):**
  add a **`osmId` TEXT field** to the Lead object and an **`OSM` option** to the `source` Select
  (and mirror it onto Company), *before* deploying — Twenty rejects unknown fields on `/rest/leads`.
- Design: website repo `docs/plans/2026-06-09-lead-bot-osm-design.md`.

### /today stats card + API metrics (`app/stats.py`, `app/card.py`, `app/metrics.py`)

- **`StatsService.today_data()`** is the single source of the numbers (counts/sources/due/created/
  worked/conv/goal + the resolved `kpi_value`/`kpi_label`); **both** renderers consume it.
  `status_text()` renders a text card — a monospace `<pre>` **funnel** (`timeutil.bar`,
  proportional) + conversion + source split + KPI bar.
- **Configurable KPI** (`stats.resolve_kpi`, `config.kpi_metric`, `/kpi metric <x>`): the KPI line
  counts one of `created` (new leads today, default) · `worked` (leads touched today, by
  `updatedAt`) · `won` · `stage:<STAGE>` (current count in a stage). `/kpi set <n>` sets the goal;
  the KPI bar scales value/goal. The PNG **funnel bars scale to the pipeline total** (a stage's real
  share), NOT to the biggest stage — so a goal change doesn't make a small stage look "full".
- **`card.py`** renders the same data as a **PNG** in the *site palette* (dark + violet brand —
  the real `globals.css` oklch tokens, converted oklch→sRGB in-module). Pillow only (no browser —
  light enough for the box, unlike Chromium). Font: `fonts-dejavu-core` (added to the Dockerfile;
  falls back to Pillow's default). `/today` (and the menu hub) attach a **🖼 Card** inline button
  (`handlers/cards.py`, `today_card` callback) → renders off-thread (`asyncio.to_thread`) →
  `answer_photo`.
- **`metrics.py`** — a process-global daily per-API counter (`data/api.json`), separate from
  `UsageStore` (that's per-*user* LLM tokens; this is per-*API* call volume). `hit("2gis")` in
  `twogis.fetch`, `hit("osm")` in `OverpassClient._post`; shown in **`/usage`** (🤖 LLM from
  UsageStore · 🗺 2GIS · 🧭 OSM) to watch the 2GIS demo quota / Overpass rate limit.

## LLM providers (Strategy pattern — `app/llm.py`)

Provider is pluggable via a registry. **Add a provider = one decorated function**, no central
`if/elif`:

```python
@provider("name")
def _build(settings) -> Extractor: ...
```

Existing: **`cloudflare`** (Workers AI direct, *no key* — default, `@cf/meta/llama-3.3-70b-instruct-fp8-fast`),
**`aigateway`** (Claude/GPT/Gemini via Cloudflare AI Gateway — model `provider/model`, needs
`LLM_API_KEY` OR a gateway-stored key + `CF_AIG_TOKEN`/BYOK), **`anthropic`** (native SDK).
Both OpenAI-compat providers use `response_format: json_schema`; `_loads` tolerates dict **or**
string content (Workers AI returns a dict). Extraction has a **60s timeout + 1 retry** on
transient errors. `SCHEMA` in `llm.py` is the single source for extracted fields.

### LLM usage accounting & limits (`app/usage.py` + caps in `ConfigStore`)

`extract()` returns an **`Extraction(fields, usage)`** dataclass — token counts (`prompt`/
`completion`, from the provider's `usage` block, which was previously discarded) travel *with*
the result rather than living on the extractor, so concurrent aiogram updates can't race over a
shared slot. `UsageStore` accumulates **per-user, per-day** counters in `data/usage.json` (keyed
by local-tz calendar day → resets at local midnight; trimmed to 30 days). `capture` calls
`usage.over_limit(uid, req_cap, tok_cap)` **before** the call and hard-stops if over; it records
usage **after** a successful extract.

- Caps are **per user, per day**, live in `ConfigStore` (`llm_max_requests` / `llm_max_tokens`,
  defaults 200 / 300k, **`0` = unlimited**) — set via **`/llm set req|tok <n>`**, shown in
  `/usage` and `/settings`. They're a **backstop** against runaway loops/abuse, not a daily gate:
  the Workers AI free tier (~10k Neurons/day) is far above normal manual capture.
- `over_limit` uses `>=` checked pre-call, so a cap of N lets exactly N calls through. Failed
  extractions (exception) are NOT recorded.

## Twenty integration (`app/twenty.py`)

- REST: `POST/GET/PATCH /rest/{leads,companies,opportunities}`. Auth = Bearer **bot's own API
  key** (`TWENTY_API_KEY`).
- **Field/value mapping** (label → option VALUE) and `STAGE_*` live here — keep in sync with
  the Lead object in Twenty (16 fields). **Reserved names:** `Link`→`prospectLink`,
  `Address`→`addressText`. Select payloads use the option **value** (e.g. `"CONTACTED"`).
- `to_payload` maps an extracted dict → a `/rest/leads` body; numbers (`reviewsCount`,
  `rating`) are included even when 0.
- **`language` is a MULTI_SELECT** (`RU`/`KK`/`EN` — a lead can speak several) the LLM detects
  from the business name / note / city (SYSTEM prompt). `_languages()` sanitises its guess into
  a valid list (tolerates a bare string / lowercase / unknown), always defaulting to `["RU"]`,
  so the REST payload is a list. `twenty.LANGUAGES` is the source set. Field id `41f2a057-…`.

### Relational layer & `/convert` (`app/handlers/convert.py`)

A cold **Lead** is a one-off prospect; once it engages you work it as a real **deal**. The CRM
uses Twenty's standard objects for that: **Company** (the account), **Opportunity** (the deal,
own pipeline + amount), with **Person** left for manual entry (2GIS gives a business, not a named
human). `/convert` lists leads in stage `REPLIED/QUALIFIED/PROPOSAL` not yet linked, and on tap:

1. **Dedup Company** by 2GIS link then name (`find_company`) — reuse the existing account or
   create one from `to_company_payload` (firmographics: niche/source/language/hasWebsite/reviews/
   rating/contact + the **composite re-shapes**: Lead `prospectLink` TEXT → Company LINKS
   `{primaryLinkUrl,…}`; `city`+`addressText` → ADDRESS `{addressStreet1,addressCity,addressCountry}`).
2. **Create Opportunity** (`to_opportunity_payload`) at stage `QUALIFIED`; `dealValue` NUMBER →
   `amount` CURRENCY `{amountMicros: value*1_000_000, currencyCode}`.
3. **Link** the Lead (`companyId`) and nudge its stage forward (never backward).

- **Multi-currency:** the deal currency is `config.deal_currency` (default `KZT`, set via
  **`/currency CODE`**, `twenty.CURRENCIES` = KZT/RUB/USD/EUR/GBP); each deal's currency is still
  editable in the CRM. Amounts are stored ×1e6 (`amountMicros`).
- **Option sync:** Company mirrors the Lead's `niche`/`source` Selects, so `/niche add` also adds
  the option to **Company** with the *same VALUE* (`OptionsRegistry._mirror_to_company`) — else a
  converted lead with a new niche would hit an unknown Company option. Custom **Opportunity stages**
  are `Qualified→Proposal→Negotiation→Won→Lost` (replaced the stock New→…→Customer).
- **Schema is migrated, not code-defined.** The Company/Opportunity custom fields + the relation +
  the stage rewrite were applied **once via the Metadata API** on the live CRM (one field per
  request; createOneField wraps `{field:{…}}`; relations use `relationCreationPayload`). All REST
  shapes (LINKS/ADDRESS/CURRENCY/relation) were verified live with create/link/dedup round-trips.
  Company object id `04c9d43d-…`, Opportunity `6c7e91b5-…`.

## CI/CD

`git push` to `main` (this repo) → **GitHub Actions** (`.github/workflows/deploy.yml`):
build image → push **`ghcr.io/suslicke/lead-bot`** (private) → SSH to netcup → `docker compose
pull && up -d`. The VPS deploy key is **restricted** (forced command = only that). The server
is logged into ghcr with a `read:packages` PAT to pull the private image. Secrets in the repo:
`SSH_HOST`, `SSH_USER`, `SSH_KEY`. Image tags: `:latest` + `:<sha>` (rollback). Doc-only
changes are skipped (`paths-ignore: **.md`).

## Conventions

- **Secrets never in git:** `.env`, `.twenty_key`, `*.key`, `data/` are gitignored. The real
  `.env` lives only on the server (`/opt/lead-bot/.env`, chmod 600). `.env.example` documents keys.
- KPI goal + digest times are **not** env — set live from the bot, persisted in
  `data/config.json` (a Docker volume).
- Conventional Commits, **no `Co-Authored-By` trailer** (keep history clean).
- Don't break the running bot: gate `pnpm`-style — compile (`python -m py_compile app/*.py
  app/handlers/*.py`) before pushing; CI redeploys on green.

## Run

- **Deploy:** just `git push` (CI does the rest).
- **Local dev:** `pip install -r requirements.txt`; `cp .env.example .env` + fill;
  `CONFIG_PATH=./data/config.json python -m app.main`.

## Design

`DESIGN.md` (capture pipeline + the command-center expansion + decisions).
