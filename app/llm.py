"""Lead extraction — pluggable LLM provider (Cloudflare Workers AI or Anthropic).

Both return the same structured dict. Selected by Settings.llm_provider.
"""
from __future__ import annotations

import json
from typing import Callable, Protocol

import httpx

from .twenty import HAS_WEBSITE, NICHE, SOURCE

SYSTEM = (
    "Extract a sales lead from the user's short note about a local business. "
    "Put each fact in its OWN field; default city to Almaty and source to 2GIS. "
    "'notes' is ONLY for extra context with no dedicated field (e.g. 'no site, all on "
    "Instagram', 'high foot traffic'). Never repeat reviews, rating, address, contact, "
    "or the link in 'notes' — leave 'notes' empty if there is nothing extra."
)

# Shared JSON schema for the extracted fields (used as Anthropic tool input_schema
# and as Cloudflare response_format json_schema).
SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Business name"},
        "niche": {"type": "string", "enum": list(NICHE)},
        "city": {"type": "string", "description": "City; default Almaty"},
        "hasWebsite": {"type": "string", "enum": list(HAS_WEBSITE),
                       "description": "No=no site, Weak=poor/outdated, Yes=good site"},
        "source": {"type": "string", "enum": list(SOURCE), "description": "Where found; default 2GIS"},
        "contact": {"type": "string", "description": "wa.me / instagram / phone, or empty"},
        "prospectLink": {"type": "string", "description": "The 2GIS or other URL from the message"},
        "addressText": {"type": "string", "description": "Approximate address / district, e.g. 'Микрорайон Аксай-5, 25'"},
        "notes": {"type": "string", "description": "Extra context ONLY (no field for it); empty if none. Never repeat reviews/rating/address/contact/link."},
        "nextStep": {"type": "string", "description": "Suggested first action"},
        "reviewsCount": {"type": "integer", "description": "Number of reviews, e.g. 1300 from '1300+ отзывов'"},
        "rating": {"type": "number", "description": "Average rating 0-5, e.g. 4.7"},
    },
    "required": ["name", "niche", "hasWebsite", "source"],
}


class Extractor(Protocol):
    def extract(self, text: str) -> dict: ...


def _loads(content) -> dict:
    """Coerce a chat 'content' to a dict.

    Providers vary: some return the structured object already as a dict (Workers AI
    with response_format), others as a JSON string (optionally wrapped in prose/fences).
    """
    if isinstance(content, dict):
        return content
    if not isinstance(content, str):
        raise ValueError(f"unexpected content type: {type(content).__name__}")
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        i, j = content.find("{"), content.rfind("}")
        if i >= 0 and j > i:
            return json.loads(content[i:j + 1])
        raise


class AnthropicExtractor:
    def __init__(self, api_key: str, model: str):
        from anthropic import Anthropic  # lazy: only needed for this provider
        self._client = Anthropic(api_key=api_key)
        self._model = model

    def extract(self, text: str) -> dict:
        tool = {"name": "save_lead", "description": SYSTEM, "input_schema": SCHEMA}
        resp = self._client.messages.create(
            model=self._model, max_tokens=600, tools=[tool],
            tool_choice={"type": "tool", "name": "save_lead"},
            messages=[{"role": "user", "content": text}],
        )
        for block in resp.content:
            if block.type == "tool_use" and block.name == "save_lead":
                return dict(block.input)
        raise ValueError("model did not return a save_lead tool call")


class OpenAICompatExtractor:
    """Any OpenAI-compatible chat endpoint with response_format json_schema.

    Covers Workers AI direct (base .../ai/v1) and AI Gateway (base .../{gw}/compat),
    where the model string picks the provider (e.g. google-ai-studio/gemini-2.0-flash).
    `api_key` is the provider key (Authorization); `aig_token` is the optional gateway
    auth (cf-aig-authorization).
    """

    def __init__(self, base_url: str, model: str, api_key: str | None = None,
                 aig_token: str | None = None, timeout: float = 60.0, retries: int = 1):
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._timeout = timeout
        self._retries = retries
        self._headers = {}
        if api_key:  # provider key — omitted when the gateway holds it (BYOK/stored keys)
            self._headers["Authorization"] = f"Bearer {api_key}"
        if aig_token:  # AI Gateway auth (required for stored-keys / authenticated gateway)
            self._headers["cf-aig-authorization"] = f"Bearer {aig_token}"

    def extract(self, text: str) -> dict:
        body = {
            "model": self._model,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "lead", "schema": SCHEMA}},
            "max_tokens": 600,
        }
        last: Exception | None = None
        for _ in range(self._retries + 1):  # retry only transient timeouts/transport errors
            try:
                r = httpx.post(self._url, headers=self._headers, json=body, timeout=self._timeout)
                r.raise_for_status()
                return _loads(r.json()["choices"][0]["message"]["content"])
            except (httpx.TimeoutException, httpx.TransportError) as e:
                last = e
        raise last  # type: ignore[misc]


# --- provider strategies (registry) ------------------------------------------
# Add a provider = write a builder and decorate it with @provider("name").
# No central if/elif to edit. build_extractor() just looks it up.
ProviderBuilder = Callable[["object"], Extractor]
PROVIDERS: dict[str, ProviderBuilder] = {}


def provider(name: str):
    def register(fn: ProviderBuilder) -> ProviderBuilder:
        PROVIDERS[name] = fn
        return fn
    return register


def _require(settings, *fields: str) -> None:
    missing = [f for f in fields if not getattr(settings, f)]
    if missing:
        raise RuntimeError(f"LLM_PROVIDER={settings.llm_provider} needs: {', '.join(missing)}")


@provider("anthropic")
def _anthropic(s) -> Extractor:
    _require(s, "anthropic_api_key")
    return AnthropicExtractor(s.anthropic_api_key, s.model)


@provider("cloudflare")  # Workers AI direct (open models, CF token)
def _cloudflare(s) -> Extractor:
    _require(s, "cf_account_id", "cf_api_token")
    base = f"https://api.cloudflare.com/client/v4/accounts/{s.cf_account_id}/ai/v1"
    return OpenAICompatExtractor(base, s.model, s.cf_api_token)


@provider("aigateway")  # Claude/GPT/Gemini via AI Gateway (model = "provider/model")
def _aigateway(s) -> Extractor:
    _require(s, "cf_account_id", "aig_gateway_id")
    # auth: either send the provider key, OR rely on the gateway's stored key (BYOK)
    # via cf-aig-authorization. At least one must be present.
    if not (s.llm_api_key or s.cf_aig_token):
        raise RuntimeError(
            "LLM_PROVIDER=aigateway needs LLM_API_KEY (provider key) "
            "or CF_AIG_TOKEN (when the key is stored in the gateway / BYOK)"
        )
    base = f"https://gateway.ai.cloudflare.com/v1/{s.cf_account_id}/{s.aig_gateway_id}/compat"
    return OpenAICompatExtractor(base, s.model, s.llm_api_key, s.cf_aig_token)


@provider("ollama")  # self-hosted Ollama (OpenAI-compat), optional nginx bearer auth
def _ollama(s) -> Extractor:
    _require(s, "ollama_base_url")
    return OpenAICompatExtractor(s.ollama_base_url, s.model, s.llm_api_key)


def build_extractor(settings) -> Extractor:
    try:
        return PROVIDERS[settings.llm_provider](settings)
    except KeyError:
        raise RuntimeError(
            f"unknown LLM_PROVIDER={settings.llm_provider!r}; known: {', '.join(sorted(PROVIDERS))}"
        ) from None
