# Roadmap / TODO — lead-bot

State + remaining work, so a fresh session can resume without re-deriving context.
See `CLAUDE.md` (architecture) and `DESIGN.md` (capture pipeline).

## Next up

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
  live (query + add + restore) with the bot's own key.
- Pluggable LLM (Strategy registry): `cloudflare`(default, Llama, no key) · `aigateway`
  (Claude/GPT/Gemini via CF AI Gateway) · `anthropic` · `ollama`.
- Bot uses its **own** Twenty API key. CI/CD: push → GitHub Actions build → `ghcr.io/suslicke/lead-bot`
  (private) → SSH deploy (restricted forced-command key). Private repo `Suslicke/lead-bot`.
