# Lead-bot — Telegram → LLM → Twenty pipeline (design)

A Telegram bot you message from your phone with a **2GIS link + a few facts**; it
extracts structured fields with a small LLM, shows a preview, and on confirm creates a
**Lead** in Twenty CRM. Faster and more fun than filling cards by hand.

Status: design locked (2026-06-09). Code in `lead-bot/`. Deploy target: `netcup` VPS.

## Goal & non-goals

- **Goal:** drop a messy line ("барбершоп на Абая, ~250 отзывов, без сайта, вотсап в
  карточке" + 2GIS link) → a `Lead` card appears in Twenty, stage `To contact`.
- **Non-goals (MVP):** scraping 2GIS for name/reviews/website (anti-bot, fragile —
  phase 2); multi-user; editing existing leads. The link is just stored in `Link`.

## Decisions (from brainstorming)

| Decision | Choice | Why |
|---|---|---|
| Field extraction | **Hosted LLM — Claude Haiku** | sub-second, best structured-output, ~$0 on tiny prompts, zero ops. Swappable to Gemini Flash. |
| Host | **netcup** (with Twenty) | bot calls Twenty at `127.0.0.1:4000` → API never exposed publicly |
| Telegram mode | **long-polling** | no public webhook/port, works behind any firewall |
| Confirm step | **yes — inline buttons** | LLM can misread; you eyeball before it writes to the CRM |
| Access | **whitelist your Telegram user-id** | a bot token is a public handle; whitelist = personal tool, not an open write endpoint |

## Flow

```
You (Telegram) ─► "<2gis link> + free-text facts"
   │
[bot.py — aiogram, long-polling]  (whitelist: only your TG id)
   │  Anthropic Messages API, tool_choice = save_lead (forced structured output)
[Claude Haiku] ─► { name, niche, city, hasWebsite, source, contact, prospectLink, notes, nextStep }
   │  map enum labels → Twenty option VALUES (Cafe→CAFE, No→NO, 2GIS→TWO_GIS …)
[preview in TG]  inline buttons: [✅ Create] [✖️ Cancel]
   │  on Create
[POST http://127.0.0.1:4000/rest/leads]  + Stage=TO_CONTACT
   │
[reply in TG] "✅ Created → <link to the card>"
```

## Components (`lead-bot/`)

- `bot.py` — aiogram v3 bot: whitelist, extract (Anthropic tool-use), preview keyboard,
  create via Twenty REST, reply with link. In-memory pending-store keyed by short id.
- `requirements.txt` — `aiogram`, `anthropic`, `httpx`.
- `Dockerfile` + `docker-compose.yml` — container, `restart: always`, joins host net or
  reaches `127.0.0.1:4000` (compose uses `network_mode: host` so localhost = the VPS).
- `.env.example` — required env (secrets live in a gitignored `.env`).

## Secrets (env, never in git)

| Var | Where to get it |
|---|---|
| `TELEGRAM_BOT_TOKEN` | @BotFather → /newbot |
| `ALLOWED_TELEGRAM_IDS` | your id from @userinfobot (comma-separated for several) |
| `ANTHROPIC_API_KEY` | console.anthropic.com |
| `TWENTY_API_KEY` | Twenty → Settings → API & Webhooks (the one in local `.twenty_key`) |
| `TWENTY_API_URL` | `http://127.0.0.1:4000` (co-located) |

## Field mapping (LLM label → Twenty value)

- niche: Cafe→`CAFE`, Beauty→`BEAUTY`, Gaming club→`GAMING_CLUB`, Dental→`DENTAL`,
  Detailing→`DETAILING`, Other→`OTHER`
- hasWebsite: No→`NO`, Weak→`WEAK`, Yes→`YES`
- source: 2GIS→`TWO_GIS`, Site→`SITE`, Instagram→`INSTAGRAM`, Referral→`REFERRAL`,
  Event→`EVENT`, Shirt→`SHIRT`
- stage: always `TO_CONTACT` on create. `Link` field API name = `prospectLink`.

## Error handling

- Non-whitelisted sender → ignored (no reply, no leak that the bot exists).
- LLM returns no/garbled tool call → bot replies "couldn't parse, try again" with a hint.
- Twenty POST non-201 → bot replies with the status + keeps your text so nothing is lost.
- Pending store entry expires (bot restart) → "session expired, resend".

## Future (phase 2, not now)

- 2GIS enrichment (Catalog API or scrape) to auto-fill name/reviews/website.
- "✏️ Edit niche/stage" inline buttons before create.
- Voice note → transcript → lead. Daily digest of `Due today` pushed to you in TG.
- Swap Haiku → self-hosted Ollama on `netcup-observ` (same interface) if desired.

---

## Update (2026-06-09) — command center + modular architecture

Scope grew from "capture only" to a full **sales command center**, and the code moved
from one file to a layered package.

**Added capabilities:**
- **Read:** `/today` (due + KPI), `/pipeline` (counts per stage), `/leads <stage>`.
- **KPI:** `/kpi`, `/kpi set <n>`. Metric = **new prospects added today** (`createdAt ≥`
  start-of-day Almaty) — auto-measurable and honest. Manual-only metrics (messages sent)
  are deliberately not tracked (the bot can't see WhatsApp).
- **Digests:** scheduled status push to whitelisted ids, at **user-configurable times**
  (`/digest add|remove HH:MM|off`, `/digest` sends now). APScheduler, tz Asia/Almaty,
  reschedulable at runtime. Times + KPI goal persist in `data/config.json` (docker volume).

**Architecture (`lead-bot/app/`):** layered, one aiogram Router per feature, dependency
injection via aiogram contextual data.
- `config.py` Settings(env) + ConfigStore(JSON) · `twenty.py` TwentyClient + mappings ·
  `llm.py` LeadExtractor · `stats.py` StatsService · `scheduler.py` DigestScheduler ·
  `filters.py` Whitelist · `keyboards.py` · `timeutil.py` · `handlers/{common,capture,queries,kpi,digest}.py`.
- `main.py` builds deps once, injects them (`dp["twenty"]`, `dp["stats"]`, …), applies the
  whitelist to every router, starts the scheduler + polling.

**Secrets add:** `ANTHROPIC_API_KEY` (for Haiku). KPI goal/digest times are NOT secrets —
they live in `data/config.json` and are edited from the bot.
