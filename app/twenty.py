"""Twenty CRM REST client + the Lead field/value mappings."""
from __future__ import annotations

import httpx

# LLM label -> Twenty Select option VALUE. Keep in sync with the Lead object (CLAUDE.md).
NICHE = {"Cafe": "CAFE", "Beauty": "BEAUTY", "Gaming club": "GAMING_CLUB",
         "Dental": "DENTAL", "Detailing": "DETAILING", "Other": "OTHER"}
HAS_WEBSITE = {"No": "NO", "Weak": "WEAK", "Yes": "YES"}
SOURCE = {"2GIS": "TWO_GIS", "Site": "SITE", "Instagram": "INSTAGRAM",
          "Referral": "REFERRAL", "Event": "EVENT", "Shirt": "SHIRT"}

STAGE_ORDER = ["TO_CONTACT", "CONTACTED", "REPLIED", "QUALIFIED", "PROPOSAL", "WON", "LOST"]
STAGE_LABEL = {"TO_CONTACT": "To contact", "CONTACTED": "Contacted", "REPLIED": "Replied",
               "QUALIFIED": "Qualified", "PROPOSAL": "Proposal", "WON": "Won", "LOST": "Lost"}
CLOSED = {"WON", "LOST"}


def to_payload(fields: dict) -> dict:
    """Map an extracted-fields dict to a Twenty /rest/leads body (drop empty values)."""
    payload = {
        "name": fields.get("name") or "Unnamed lead",
        "stage": "TO_CONTACT",
        "city": fields.get("city") or "Almaty",
        "niche": NICHE.get(fields.get("niche"), "OTHER"),
        "hasWebsite": HAS_WEBSITE.get(fields.get("hasWebsite"), "NO"),
        "source": SOURCE.get(fields.get("source"), "TWO_GIS"),
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
