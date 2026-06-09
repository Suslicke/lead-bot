# Roadmap / TODO — lead-bot

State + remaining work, so a fresh session can resume without re-deriving context.
See `CLAUDE.md` (architecture) and `DESIGN.md` (capture pipeline).

## Next up

### 0. OSM harvest — finish prod rollout (code on branch `feat/osm-harvest`)
Code done (`app/osm.py`, `app/osm_tags.py`, `app/handlers/harvest.py`, enrichment hook,
dedup by `osmId`, tests). **Before deploy, on the live CRM via Metadata API:** (a) add
`osmId` TEXT field to the Lead object; (b) add an `OSM` option to the `source` Select (mirror
to Company). Then on netcup: bring up the **Overpass** compose service (one-off Kazakhstan
import, tens of min) and set `OVERPASS_URL=http://127.0.0.1:12347/api/interpreter` in `.env`.
Verify `/harvest cafe → Алматы` and a text-capture enrichment. Tune `NICHE_TAG_MAP` from results.

### 1. Ollama server (provider already coded — `@provider("ollama")`)
Stand up Ollama behind nginx at `https://llm.suslicketeam.com/v1` (OpenAI-compat), optional
bearer. Candidate host: **netcup-observ** (62 GB / 16 cores, no GPU → CPU inference, pick a
small model like `qwen2.5:7b`). Then set `.env`: `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL`,
`MODEL`, optional `LLM_API_KEY` (bearer). Default stays `cloudflare`/Llama until then.

## Later
2. **Observability** — OTel → Alloy on netcup-observ (logs/traces/metrics in Grafana).
   Sentry already wired (`SENTRY_DSN`).
3. **Edit-before-create** — ✏️ inline buttons to fix niche/stage in the draft pre-save.
4. **2GIS enrichment** — auto-fill name/reviews/rating from the link (Catalog API or scrape;
   fragile, anti-bot). MVP keeps manual.
5. **Person on /convert** — currently skipped (2GIS = business, not a named human). Add when a
   real contact name is captured, linking Opportunity.pointOfContact.

## Done (reference)
- Twenty CRM live (`crm.suslicketeam.com`, netcup VPS); custom `Lead` object (15 fields:
  +Reviews/Rating/Address) + Kanban; signup disabled.
- lead-bot: capture → LLM → Twenty; **dedup** by `prospectLink` (Update refreshes facts,
  keeps stage/nextStep/notes); commands `/today /pipeline /leads /kpi /digest /settings`;
  configurable digests (APScheduler, Asia/Almaty); Sentry; 60s timeout + 1 retry.
- **`/niche add` + `/source add` — dynamic Select options** (`app/reference.py` OptionsRegistry):
  niche/source read live off Twenty via the Metadata API and fed to both the LLM enum
  (`schema_with_options`) and `to_payload`; new options added from the phone (RU labels
  transliterated to ASCII VALUEs). `twenty.NICHE/SOURCE` kept as a seed/fallback. Verified
  live (query + add + restore) with the bot's own key. Options mirror onto **Company** too.
- **Lead language** — `language` MULTI_SELECT (RU/KK/EN) on the Lead, LLM-detected, in the schema
  + `to_payload` (list, default `["RU"]`).
- **LLM usage accounting** — `Extraction(fields, usage)`; `UsageStore` per-user/day counters;
  `/usage`, `/llm set req|tok`, hard-stop on caps.
- **Relational layer + `/convert`** — Twenty Company/Opportunity standard objects; `/convert`
  promotes a replied/qualified Lead → Company (deduped) + Opportunity (deal), links the Lead,
  forward-only stage bump. Multi-currency via `/currency` (`config.deal_currency`, default KZT).
  Custom opp stages Qualified→Proposal→Negotiation→Won→Lost. Schema migrated via Metadata API.
- **Button hub** — `/start`+`/menu` inline hub + `set_my_commands` (Telegram command menu).
- Pluggable LLM (Strategy registry): `cloudflare`(default, Llama, no key) · `aigateway`
  (Claude/GPT/Gemini via CF AI Gateway) · `anthropic` · `ollama`.
- Bot uses its **own** Twenty API key. CI/CD: push → GitHub Actions build → `ghcr.io/suslicke/lead-bot`
  (private) → SSH deploy (restricted forced-command key). Private repo `Suslicke/lead-bot`.
