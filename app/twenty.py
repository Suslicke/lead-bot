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
# language is a MULTI_SELECT on the Lead object — a lead can speak several (RU + KK).
LANGUAGES = ("RU", "KK", "EN")
# Opportunity.amount is multi-currency (currencyCode stored per record; amount * 1_000_000).
# The bot picks a default at convert time (runtime-configurable, /currency); any single deal's
# currency can still be changed in the CRM.
DEFAULT_CURRENCY = "KZT"
CURRENCIES = ("KZT", "RUB", "USD", "EUR", "GBP")

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


def _languages(value) -> list[str]:
    """Sanitise the LLM's language guess into a valid MULTI_SELECT list (default ['RU']).

    Tolerates a bare string ('RU'), lowercase ('ru'), and unknown values; keeps order,
    de-dupes, and always returns at least ['RU'] so the field is never empty.
    """
    raw = [value] if isinstance(value, str) else list(value or [])
    out: list[str] = []
    for v in raw:
        up = str(v).strip().upper()
        if up in LANGUAGES and up not in out:
            out.append(up)
    return out or ["RU"]


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
        "language": _languages(fields.get("language")),
    }
    for key in ("contact", "prospectLink", "addressText", "notes", "nextStep"):
        if fields.get(key):
            payload[key] = fields[key]
    for key in ("reviewsCount", "rating"):  # numbers: include 0 too, skip only when absent
        if fields.get(key) is not None:
            payload[key] = fields[key]
    return payload


# --- Lead -> relational layer (Company / Opportunity) -------------------------------------
# A Lead record (as stored in Twenty) carries VALUE-form selects already; we only have to
# re-shape the composite fields: Lead.prospectLink (TEXT) -> Company.prospectLink (LINKS),
# Lead.city + addressText (TEXT) -> Company.address (ADDRESS), Lead.dealValue (NUMBER) ->
# Opportunity.amount (CURRENCY). Selects/multiselect carry over verbatim (same option values).

def to_company_payload(lead: dict) -> dict:
    """Firmographics from a Lead record → a /rest/companies body."""
    p: dict = {"name": lead.get("name") or "Unnamed company"}
    for key in ("niche", "source", "hasWebsite", "contact"):
        if lead.get(key):
            p[key] = lead[key]
    for key in ("reviewsCount", "rating"):
        if lead.get(key) is not None:
            p[key] = lead[key]
    if lead.get("language"):
        p["language"] = lead["language"]
    if lead.get("prospectLink"):
        p["prospectLink"] = {"primaryLinkUrl": lead["prospectLink"], "primaryLinkLabel": "2GIS"}
    address = {}
    if lead.get("addressText"):
        address["addressStreet1"] = lead["addressText"]
    if lead.get("city"):
        address["addressCity"] = lead["city"]
    if address:
        address.setdefault("addressCountry", "Kazakhstan")
        p["address"] = address
    return p


def to_opportunity_payload(lead: dict, company_id: str, currency: str = DEFAULT_CURRENCY) -> dict:
    """The deal from a Lead record → a /rest/opportunities body (starts at QUALIFIED)."""
    p: dict = {"name": lead.get("name") or "Opportunity", "stage": "QUALIFIED", "companyId": company_id}
    deal = lead.get("dealValue")
    if deal:
        p["amount"] = {"amountMicros": int(float(deal) * 1_000_000), "currencyCode": currency}
    if lead.get("nextStep"):
        p["nextStep"] = lead["nextStep"]
    return p


def _link_url(value) -> str:
    """Normalise a link for dedup — handles both TEXT and LINKS-composite shapes."""
    if isinstance(value, dict):
        value = value.get("primaryLinkUrl")
    return (value or "").strip().rstrip("/").lower()


def find_company(companies: list[dict], link: str | None, name: str | None) -> dict | None:
    """Dedup a Company by 2GIS link (the natural key), then exact name."""
    nlink = _link_url(link)
    if nlink:
        for c in companies:
            if _link_url(c.get("prospectLink")) == nlink:
                return c
    nname = (name or "").strip().lower()
    if nname:
        for c in companies:
            if (c.get("name") or "").strip().lower() == nname:
                return c
    return None


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

    async def get_lead(self, lead_id: str) -> dict:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{self._base}/rest/leads/{lead_id}", headers=self._headers)
        r.raise_for_status()
        return r.json().get("data", {}).get("lead", {})

    # --- relational layer (Company / Opportunity) -------------------------------------------
    async def all_companies(self, limit: int = 200) -> list[dict]:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{self._base}/rest/companies?limit={limit}", headers=self._headers)
        r.raise_for_status()
        return r.json().get("data", {}).get("companies", [])

    async def create_company(self, payload: dict) -> str:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"{self._base}/rest/companies", headers=self._headers, json=payload)
        if r.status_code != 201:
            raise RuntimeError(f"Twenty {r.status_code}: {r.text[:200]}")
        return r.json()["data"]["createCompany"]["id"]

    async def create_opportunity(self, payload: dict) -> str:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"{self._base}/rest/opportunities", headers=self._headers, json=payload)
        if r.status_code != 201:
            raise RuntimeError(f"Twenty {r.status_code}: {r.text[:200]}")
        return r.json()["data"]["createOpportunity"]["id"]

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

    async def add_select_option(self, field_id: str, current: list[dict], label: str,
                                value: str | None = None) -> str:
        """Append one option to a Select field (updateOneField replaces the whole array).

        We round-trip the existing options verbatim (keeping their ids) and append the new
        one — dropping any of the existing options would delete it from the schema. `value`
        can be forced (to mirror the same option onto another object, e.g. Company.niche,
        with an identical VALUE) instead of deriving it from the label.
        """
        if any(not o.get("id") for o in current):
            # Options without ids means we're working off the un-synced seed fallback, not the
            # live schema; sending them would regenerate every option's id. Refuse instead.
            raise RuntimeError("options not synced from Twenty — cannot safely add (try again)")
        taken = {o.get("value") for o in current}
        positions = [o.get("position", 0) for o in current]
        new = {"id": str(uuid.uuid4()), "label": label, "value": value or _option_value(label, taken),
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
