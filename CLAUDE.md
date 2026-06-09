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
  → callbacks `create:` / `update:` / `cancel:`. **Update refreshes facts only**
  (`_REFRESHABLE`: niche, hasWebsite, city, contact, prospectLink, addressText, reviewsCount,
  rating, language) — it must NOT touch `stage`/`nextStep`/`notes` (the user's pipeline work).
  Before spending a call it checks the **per-user daily LLM cap** (`usage.over_limit`) and hard-stops;
  after a successful extract it records the call's token usage.
- Commands: `/start` `/menu` `/today` `/pipeline` `/leads <stage>` `/kpi [set N]` `/digest [list|add HH:MM|remove HH:MM|off]` `/niche [add <name>]` `/source [add <name>]` `/convert` `/currency [CODE]` `/usage` `/llm set req|tok <n>` `/settings` `/help`.

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
