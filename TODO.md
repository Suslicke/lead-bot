# Roadmap / TODO — lead-bot

State + remaining work, so a fresh session can resume without re-deriving context.
See `CLAUDE.md` (architecture) and `DESIGN.md` (capture pipeline).

## Next up

### 1. `/niche add` — dynamic Select options (niche + source)
**Why:** niches are hardcoded in `app/twenty.py` (`NICHE`/`SOURCE`) → anything off-list
falls to `OTHER`. Want a single source of truth (Twenty) + add new options from the phone.

**Build:**
- `app/twenty.py` — add Metadata-API methods:
  - `select_options(field_name) -> list[dict]`: query `objects → fieldsList → options`
    (format `[{id,label,value,color,position}]`).
  - `add_select_option(field_name, label)`: `updateOneField` with the **full** options
    array (existing — keep their `id` — + new `{label, value, color, position}`). `value` =
    UPPER_SNAKE from label; `position` = next; pick a palette color. **Test empirically**
    (server can't be reached from the dev sandbox over HTTPS — run via `ssh netcup` curl,
    key piped via stdin; one resolver per metadata document).
- `app/reference.py` (new) — `OptionsRegistry`: fetch+cache niche/source options at
  startup, refresh after an add; expose current labels + `label→value` map.
- `app/llm.py` — make `SCHEMA` niche/source **enums dynamic** (inject from registry per
  extract, not the hardcoded `NICHE`/`SOURCE`).
- `app/twenty.py` `to_payload` — map niche/source via the registry, not hardcoded dicts.
- `app/handlers/reference.py` (new) — `/niche`, `/niche list`, `/niche add <name>`
  (optionally `/source ...`). Register in `handlers/__init__.py` + apply Whitelist.
- `app/main.py` — build `OptionsRegistry`, inject (`dp["options"]`), refresh at startup.

**Known ids (Lead object on Twenty):** object `52b9769d-73ef-4d71-a99c-78f6ed3098f8`;
`niche` field `5577b72c-0439-4e42-8ac4-66f133986369`; `source` `27af265a-decf-4c34-b868-d639fe9609d3`.
Reserved field names rename internally (`link`→`prospectLink`, `address`→`addressText`).

### 2. Ollama server (provider already coded — `@provider("ollama")`)
Stand up Ollama behind nginx at `https://llm.suslicketeam.com/v1` (OpenAI-compat), optional
bearer. Candidate host: **netcup-observ** (62 GB / 16 cores, no GPU → CPU inference, pick a
small model like `qwen2.5:7b`). Then set `.env`: `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL`,
`MODEL`, optional `LLM_API_KEY` (bearer). Default stays `cloudflare`/Llama until then.

## Later
3. **Observability** — OTel → Alloy on netcup-observ (logs/traces/metrics in Grafana).
   Sentry already wired (`SENTRY_DSN`).
4. **Edit-before-create** — ✏️ inline buttons to fix niche/stage in the draft pre-save.
5. **2GIS enrichment** — auto-fill name/reviews/rating from the link (Catalog API or scrape;
   fragile, anti-bot). MVP keeps manual.

## Done (reference)
- Twenty CRM live (`crm.suslicketeam.com`, netcup VPS); custom `Lead` object (15 fields:
  +Reviews/Rating/Address) + Kanban; signup disabled.
- lead-bot: capture → LLM → Twenty; **dedup** by `prospectLink` (Update refreshes facts,
  keeps stage/nextStep/notes); commands `/today /pipeline /leads /kpi /digest /settings`;
  configurable digests (APScheduler, Asia/Almaty); Sentry; 60s timeout + 1 retry.
- Pluggable LLM (Strategy registry): `cloudflare`(default, Llama, no key) · `aigateway`
  (Claude/GPT/Gemini via CF AI Gateway) · `anthropic` · `ollama`.
- Bot uses its **own** Twenty API key. CI/CD: push → GitHub Actions build → `ghcr.io/suslicke/lead-bot`
  (private) → SSH deploy (restricted forced-command key). Private repo `Suslicke/lead-bot`.
