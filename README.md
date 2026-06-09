# lead-bot

A Telegram **sales command center** for Twenty CRM. Capture leads from your phone,
check the pipeline, track a daily KPI, and get scheduled digests.

Design: `../docs/plans/2026-06-09-lead-bot-design.md`. CRM context: `../CLAUDE.md` → CRM & sales ops.

## What it does

- **Capture:** send a 2GIS link + facts → Claude Haiku drafts a Lead → confirm → created in Twenty.
- **Read:** `/today`, `/pipeline`, `/leads <stage>`.
- **KPI:** `/kpi` (progress), `/kpi set 10` (daily goal = new prospects added today, auto from `createdAt`).
- **Digests:** push the daily status at custom times — `/digest`, `/digest add 09:00`, `/digest remove 19:00`, `/digest off`.

Whitelisted Telegram ids only. Long-polling (no public webhook). Co-located with Twenty
(calls `127.0.0.1:4000`, so the CRM API is never exposed).

## Architecture

```
app/
  main.py        entrypoint — builds deps, injects them, wires routers, starts polling
  config.py      Settings (env) + ConfigStore (runtime JSON: KPI goal, digest times)
  twenty.py      TwentyClient (REST) + Lead field/value mappings
  llm.py         LeadExtractor — Claude Haiku forced tool call → structured fields
  stats.py       StatsService — pipeline counts, KPI, digest text
  scheduler.py   DigestScheduler — APScheduler, reschedulable at runtime
  filters.py     Whitelist (applied per router)
  keyboards.py   inline confirm keyboard
  timeutil.py    today-bounds (Asia/Almaty), ISO parse, progress bar
  handlers/      one Router per feature: common · capture · queries · kpi · digest
```

Dependencies are created once in `main.py` and injected into handlers by parameter name
(aiogram contextual data: `dp["twenty"]`, `dp["stats"]`, …).

## Setup

1. **Bot:** Telegram → @BotFather → `/newbot` → token.
2. **Your id:** @userinfobot → numeric id.
3. **Keys:** Anthropic API key (console.anthropic.com); Twenty API key (Settings → API & Webhooks).
4. `cp .env.example .env` and fill it in (`.env` is gitignored).

## Run (on netcup, next to Twenty)

```bash
cd /opt/lead-bot
docker compose up -d --build
docker compose logs -f          # expect "lead-bot up (whitelist=[...])"
```

`network_mode: host` → reaches Twenty at `127.0.0.1:4000`. `./data` volume persists
`config.json` (KPI goal + digest times). `restart: always` survives reboots.

## Local dev

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
set -a; . ./.env; set +a
CONFIG_PATH=./data/config.json python -m app.main
```

## Notes

- Field/value maps (niche, hasWebsite, source → Twenty option values) live in `app/twenty.py` —
  keep in sync with the `Lead` object.
- KPI metric = **new prospects today** (auto, honest). Manual-only metrics (messages sent)
  are intentionally not tracked.
- Phase-2 ideas (2GIS enrichment, edit-before-create, voice notes) in the design doc.
