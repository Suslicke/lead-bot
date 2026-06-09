"""2GIS Catalog API enrichment — paste a 2GIS link, get the lead facts (no LLM, no browser).

Gated on TWOGIS_API_KEY: unset → capture stays on the text+LLM path. `/3.0/items/byid` returns
name, rubrics (→ niche), reviews (rating + count), address, contacts. The reviews field may be
an on-demand (paid) add-on on your 2GIS plan — enrichment degrades gracefully if it's absent.

Keyless scraping is NOT viable: a raw fetch of a 2GIS firm page returns an anti-bot SPA shell
(no data, no usable key), so this path needs a real Catalog API key — a free demo key works.
"""
from __future__ import annotations

import logging
import re

import httpx

log = logging.getLogger(__name__)

# .../firm/<id>[/...] inside a 2gis link → the numeric branch id
_FIRM_RE = re.compile(r"firm/(\d+)")

# 2GIS rubric keyword (lowercased substring) -> our niche LABEL. to_payload maps label→VALUE,
# so unknown rubrics fall through to "Other". Extend as your niche vocabulary grows.
_RUBRIC_NICHE = {
    "кофейн": "Cafe", "кафе": "Cafe", "ресторан": "Cafe", "столов": "Cafe", "пиццер": "Cafe",
    "барбершоп": "Beauty", "парикмахер": "Beauty", "салон красоты": "Beauty", "ногт": "Beauty",
    "маникюр": "Beauty", "космет": "Beauty", "брови": "Beauty", "spa": "Beauty",
    "стоматолог": "Dental", "дентал": "Dental",
    "детейлинг": "Detailing", "автомойк": "Detailing",
    "компьютерный клуб": "Gaming club", "киберспорт": "Gaming club", "игровой клуб": "Gaming club",
}


def find_firms(text: str) -> list[tuple[str, str]]:
    """Return [(firm_id, original_url)] for each distinct 2GIS firm link in the text."""
    out, seen = [], set()
    for tok in (text or "").split():
        if "2gis." in tok.lower() and (m := _FIRM_RE.search(tok)):
            fid = m.group(1)
            if fid not in seen:
                seen.add(fid)
                out.append((fid, tok.rstrip(".,;)")))
    return out


def _niche(rubrics: list[dict] | None) -> str:
    names = " ".join((r.get("name") or "").lower() for r in (rubrics or []))
    for kw, label in _RUBRIC_NICHE.items():
        if kw in names:
            return label
    return "Other"


def item_to_fields(item: dict, link: str) -> dict:
    """Shape a /items/byid result like the LLM's output dict (labels, not option VALUEs)."""
    fields: dict = {"name": item.get("name") or "Unnamed", "source": "2GIS", "language": ["RU"],
                    "niche": _niche(item.get("rubrics")), "prospectLink": link}
    rev = item.get("reviews") or {}
    if rev.get("rating") is not None:
        fields["rating"] = rev["rating"]
    if rev.get("review_count") is not None:
        fields["reviewsCount"] = rev["review_count"]
    addr = item.get("full_address_name") or (item.get("address") or {}).get("name")
    if addr:
        fields["addressText"] = addr
    phone, has_site = None, False
    for group in (item.get("contact_groups") or []):
        for c in (group.get("contacts") or []):
            if c.get("type") == "phone" and not phone:
                phone = c.get("value")
            if c.get("type") == "website":
                has_site = True
    if phone:
        fields["contact"] = phone
    fields["hasWebsite"] = "Yes" if has_site else "No"
    return fields


class TwoGisClient:
    _FIELDS = ("items.reviews,items.rubrics,items.contact_groups,"
               "items.address,items.full_address_name")

    def __init__(self, api_key: str, base_url: str = "https://catalog.api.2gis.com"):
        self._key = api_key
        self._base = base_url.rstrip("/")

    async def fetch(self, firm_id: str, link: str) -> dict | None:
        """Enrich one firm → an LLM-shaped fields dict, or None if 2GIS has no such item."""
        params = {"id": firm_id, "fields": self._FIELDS, "key": self._key}
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"{self._base}/3.0/items/byid", params=params)
        if r.status_code != 200:
            raise RuntimeError(f"2GIS {r.status_code}: {r.text[:160]}")
        items = (r.json().get("result") or {}).get("items") or []
        return item_to_fields(items[0], link) if items else None
