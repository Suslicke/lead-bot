"""Configuration: immutable Settings from env + a small persistent ConfigStore."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Settings:
    bot_token: str
    allowed_ids: frozenset[int]
    model: str
    twenty_api_url: str
    twenty_public_url: str
    twenty_api_key: str
    tz: ZoneInfo
    config_path: Path
    usage_path: Path                         # LLM usage counters (sits next to config_path)
    llm_provider: str = "anthropic"          # cloudflare | aigateway | anthropic
    anthropic_api_key: str | None = None     # required only if provider=anthropic
    cf_account_id: str | None = None         # cloudflare + aigateway
    cf_api_token: str | None = None          # cloudflare (Workers AI direct)
    aig_gateway_id: str | None = None        # aigateway: the AI Gateway id
    cf_aig_token: str | None = None          # aigateway: optional gateway auth token
    llm_api_key: str | None = None           # aigateway provider key / ollama bearer token (nginx)
    ollama_base_url: str | None = None       # ollama: self-hosted OpenAI-compat base, e.g. https://llm.suslicketeam.com/v1
    sentry_dsn: str | None = None            # optional — unset disables Sentry
    twogis_api_key: str | None = None        # optional — unset disables 2GIS link enrichment
    twogis_api_url: str = "https://catalog.api.2gis.com"
    overpass_url: str | None = None           # optional — unset disables OSM /harvest + enrichment

    @staticmethod
    def from_env() -> "Settings":
        ids = frozenset(
            int(x) for x in os.environ.get("ALLOWED_TELEGRAM_IDS", "").replace(" ", "").split(",") if x
        )
        provider = os.environ.get("LLM_PROVIDER", "anthropic").lower()
        defaults = {
            "cloudflare": "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
            "aigateway": "google-ai-studio/gemini-2.0-flash",
            "anthropic": "claude-haiku-4-5",
            "ollama": "qwen2.5:7b",
        }
        default_model = defaults.get(provider, "claude-haiku-4-5")
        model = os.environ.get("MODEL") or default_model
        if provider == "cloudflare" and not model.startswith("@cf/"):
            model = default_model  # ignore a stale non-CF MODEL when on Workers AI direct
        config_path = Path(os.environ.get("CONFIG_PATH", "/app/data/config.json"))
        return Settings(
            bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
            allowed_ids=ids,
            model=model,
            twenty_api_url=os.environ.get("TWENTY_API_URL", "http://127.0.0.1:4000").rstrip("/"),
            twenty_public_url=os.environ.get("TWENTY_PUBLIC_URL", "https://crm.suslicketeam.com").rstrip("/"),
            twenty_api_key=os.environ["TWENTY_API_KEY"],
            tz=ZoneInfo(os.environ.get("TZ", "Asia/Almaty")),
            config_path=config_path,
            usage_path=config_path.parent / "usage.json",
            llm_provider=provider,
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
            cf_account_id=os.environ.get("CLOUDFLARE_ACCOUNT_ID") or None,
            cf_api_token=os.environ.get("CLOUDFLARE_API_TOKEN") or None,
            aig_gateway_id=os.environ.get("AIG_GATEWAY_ID") or None,
            cf_aig_token=os.environ.get("CF_AIG_TOKEN") or None,
            llm_api_key=os.environ.get("LLM_API_KEY") or None,
            ollama_base_url=os.environ.get("OLLAMA_BASE_URL") or None,
            sentry_dsn=os.environ.get("SENTRY_DSN") or None,
            twogis_api_key=os.environ.get("TWOGIS_API_KEY") or None,
            twogis_api_url=os.environ.get("TWOGIS_API_URL", "https://catalog.api.2gis.com").rstrip("/"),
            overpass_url=(os.environ.get("OVERPASS_URL") or "").rstrip("/") or None,
        )


# llm_max_* are per-user, per-day caps (0 = unlimited). Defaults are generous
# backstops against runaway loops/abuse — the Workers AI free tier (~10k Neurons/day)
# is far above normal manual capture, so these rarely bite in practice.
_DEFAULTS = {
    "kpi_goal": 10,
    "digest_times": ["09:00", "19:00"],
    "llm_max_requests": 200,
    "llm_max_tokens": 300_000,
    "deal_currency": "KZT",  # default currency for opportunities created by /convert
}


class ConfigStore:
    """Runtime, user-editable config (KPI goal + digest times) persisted as JSON."""

    def __init__(self, path: Path):
        self._path = path
        self._data = {**_DEFAULTS, **self._read()}

    def _read(self) -> dict:
        try:
            return json.loads(self._path.read_text())
        except (FileNotFoundError, ValueError):
            return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2))

    @property
    def kpi_goal(self) -> int:
        return int(self._data["kpi_goal"])

    def set_kpi_goal(self, value: int) -> None:
        self._data["kpi_goal"] = int(value)
        self._save()

    @property
    def digest_times(self) -> list[str]:
        return list(self._data["digest_times"])

    def add_digest(self, hhmm: str) -> None:
        self._data["digest_times"] = sorted(set(self._data["digest_times"]) | {hhmm})
        self._save()

    def remove_digest(self, hhmm: str) -> None:
        self._data["digest_times"] = sorted(set(self._data["digest_times"]) - {hhmm})
        self._save()

    def clear_digests(self) -> None:
        self._data["digest_times"] = []
        self._save()

    @property
    def llm_max_requests(self) -> int:
        return int(self._data["llm_max_requests"])

    def set_llm_max_requests(self, value: int) -> None:
        self._data["llm_max_requests"] = max(0, int(value))
        self._save()

    @property
    def llm_max_tokens(self) -> int:
        return int(self._data["llm_max_tokens"])

    def set_llm_max_tokens(self, value: int) -> None:
        self._data["llm_max_tokens"] = max(0, int(value))
        self._save()

    @property
    def deal_currency(self) -> str:
        return str(self._data["deal_currency"])

    def set_deal_currency(self, code: str) -> None:
        from .twenty import CURRENCIES
        code = code.strip().upper()
        if code not in CURRENCIES:
            raise ValueError(f"unsupported currency {code!r}; pick one of {', '.join(CURRENCIES)}")
        self._data["deal_currency"] = code
        self._save()
