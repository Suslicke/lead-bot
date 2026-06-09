"""Twenty CRM client: Core API (/rest records) + Metadata API (/metadata schema).

The Lead field/value mappings below are the *fallback* vocabulary. The live source of
truth for the niche/source Select options is Twenty itself — read/extended via the
Metadata-API methods here and cached by app.reference.OptionsRegistry.
"""
from __future__ import annotations

import uuid

import httpx

# LLM label -> Twenty Select option VALUE. Fallback only (used when a metadata fetch fails);
# the live options come from OptionsRegistry. Keep roughly in sync with the Lead object.
NICHE = {"Cafe": "CAFE", "Beauty": "BEAUTY", "Gaming club": "GAMING_CLUB",
         "Dental": "DENTAL", "Detailing": "DETAILING", "Other": "OTHER"}
HAS_WEBSITE = {"No": "NO", "Weak": "WEAK", "Yes": "YES"}
SOURCE = {"2GIS": "TWO_GIS", "Site": "SITE", "Instagram": "INSTAGRAM",
          "Referral": "REFERRAL", "Event": "EVENT", "Shirt": "SHIRT"}

STAGE_ORDER = ["TO_CONTACT", "CONTACTED", "REPLIED", "QUALIFIED", "PROPOSAL", "WON", "LOST"]
STAGE_LABEL = {"TO_CONTACT": "To contact", "CONTACTED": "Contacted", "REPLIED": "Replied",
               "QUALIFIED": "Qualified", "PROPOSAL": "Proposal", "WON": "Won", "LOST": "Lost"}
CLOSED = {"WON", "LOST"}

# Twenty's Select-option color palette (used round-robin for new options).
_PALETTE = ["green", "turquoise", "sky", "blue", "purple", "pink",
            "red", "orange", "yellow", "gray"]
# Keys Twenty expects on each option; we round-trip only these so an existing option's
# extra keys can't make updateOneField reject the array.
_OPTION_KEYS = ("id", "label", "value", "color", "position")

# RU -> latin, so a Cyrillic niche label still yields an ASCII UPPER_SNAKE option value.
_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def _option_value(label: str, taken: set[str]) -> str:
    """Derive a stable UPPER_SNAKE option VALUE from a (possibly Cyrillic) label.

    Twenty Select values are the stable keys stored on records; convention is ASCII
    UPPER_SNAKE (CAFE, GAMING_CLUB). We transliterate RU so 'Барбершоп' -> BARBERSHOP
    rather than an empty value, fall back to OPTION if nothing usable remains, and
    de-dupe against values already on the field. (Policy lives here — see TODO.md.)
    """
    out: list[str] = []
    for ch in label.lower():
        if ch.isascii() and ch.isalnum():
            out.append(ch)
        elif ch in _TRANSLIT:
            out.append(_TRANSLIT[ch])
        elif ch in " -_/":
            out.append("_")
        # everything else (punctuation, other scripts) is dropped
    value = "_".join(p for p in "".join(out).upper().split("_") if p) or "OPTION"
    base, n = value, 2
    while value in taken:
        value, n = f"{base}_{n}", n + 1
    return value


def to_payload(fields: dict, niche_map: dict | None = None, source_map: dict | None = None) -> dict:
    """Map an extracted-fields dict to a Twenty /rest/leads body (drop empty values).

    niche_map/source_map are live label->VALUE maps from OptionsRegistry; they default to
    the hardcoded fallbacks so to_payload still works without a registry (e.g. in tests).
    """
    niche_map = niche_map or NICHE
    source_map = source_map or SOURCE
    payload = {
        "name": fields.get("name") or "Unnamed lead",
        "stage": "TO_CONTACT",
        "city": fields.get("city") or "Almaty",
        "niche": niche_map.get(fields.get("niche"), "OTHER"),
        "hasWebsite": HAS_WEBSITE.get(fields.get("hasWebsite"), "NO"),
        "source": source_map.get(fields.get("source"), "TWO_GIS"),
    }
    for key in ("contact", "prospectLink", "addressText", "notes", "nextStep"):
        if fields.get(key):
            payload[key] = fields[key]
    for key in ("reviewsCount", "rating"):  # numbers: include 0 too, skip only when absent
        if fields.get(key) is not None:
            payload[key] = fields[key]
    return payload


class TwentyClient:
    def __init__(self, base_url: str, api_key: str):
        self._base = base_url
        self._key = api_key

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._key}", "Content-Type": "application/json"}

    async def create_lead(self, payload: dict) -> str:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"{self._base}/rest/leads", headers=self._headers, json=payload)
        if r.status_code != 201:
            raise RuntimeError(f"Twenty {r.status_code}: {r.text[:200]}")
        return r.json()["data"]["createLead"]["id"]

    async def all_leads(self, limit: int = 200) -> list[dict]:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{self._base}/rest/leads?limit={limit}", headers=self._headers)
        r.raise_for_status()
        return r.json().get("data", {}).get("leads", [])

    async def update_lead(self, lead_id: str, patch: dict) -> None:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.patch(f"{self._base}/rest/leads/{lead_id}", headers=self._headers, json=patch)
        if r.status_code not in (200, 201):
            raise RuntimeError(f"Twenty {r.status_code}: {r.text[:200]}")

    # --- Metadata API (/metadata GraphQL): the Select-option schema, not records ----------
    # The two GraphQL documents live at the bottom of this module (_FIELDS_Q / _UPDATE_FIELD_M)
    # so they're easy to tweak if a Twenty upgrade changes the metadata schema.
    async def _metadata(self, query: str, variables: dict) -> dict:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(f"{self._base}/metadata", headers=self._headers,
                             json={"query": query, "variables": variables})
        r.raise_for_status()
        body = r.json()
        if body.get("errors"):
            raise RuntimeError(f"Twenty metadata: {body['errors'][0].get('message')}")
        return body["data"]

    async def field_options(self, object_id: str, field_name: str) -> tuple[str, list[dict]]:
        """Return (field_id, options[]) for a Select field on the given object."""
        data = await self._metadata(_FIELDS_Q, {"id": object_id})
        for f in data["object"]["fieldsList"]:
            if f["name"] == field_name:
                return f["id"], list(f.get("options") or [])
        raise RuntimeError(f"field {field_name!r} not found on object {object_id}")

    async def add_select_option(self, field_id: str, current: list[dict], label: str) -> str:
        """Append one option to a Select field (updateOneField replaces the whole array).

        We round-trip the existing options verbatim (keeping their ids) and append the new
        one — dropping any of the existing options would delete it from the schema.
        """
        if any(not o.get("id") for o in current):
            # Options without ids means we're working off the un-synced seed fallback, not the
            # live schema; sending them would regenerate every option's id. Refuse instead.
            raise RuntimeError("options not synced from Twenty — cannot safely add (try again)")
        taken = {o.get("value") for o in current}
        positions = [o.get("position", 0) for o in current]
        new = {"id": str(uuid.uuid4()), "label": label, "value": _option_value(label, taken),
               "color": _PALETTE[len(current) % len(_PALETTE)],
               "position": (max(positions) + 1) if positions else 0}
        options = [{k: o.get(k) for k in _OPTION_KEYS} for o in current] + [new]
        await self._metadata(_UPDATE_FIELD_M, {"input": {"id": field_id, "update": {"options": options}}})
        return new["value"]


_FIELDS_Q = "query Obj($id: UUID!) { object(id: $id) { fieldsList { id name options } } }"
_UPDATE_FIELD_M = (
    "mutation UpdField($input: UpdateOneFieldMetadataInput!) "
    "{ updateOneField(input: $input) { id name } }"
)
