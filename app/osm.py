"""OpenStreetMap (Overpass) lead source — harvest businesses by niche+area, enrich by name.

Gated on OVERPASS_URL (the full /api/interpreter endpoint of the self-hosted instance);
unset → /harvest and OSM enrichment are off. Produces the same LLM/2GIS-shaped fields dict
(labels, not option VALUEs) as twogis.item_to_fields, so it reuses to_payload + the whole
draft → dedup → confirm flow. OSM has no reviews/rating — those stay empty (filled later
from 2GIS); the stable `osm_type/id` becomes Lead.osmId, the dedup key that survives the
prospectLink being swapped to a 2GIS URL.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

from .osm_tags import build_name_query, build_query, tags_for

log = logging.getLogger(__name__)

# only-empty contact facts an OSM match may fill on an LLM draft (never overrides the LLM).
_ENRICH_KEYS = ("addressText", "contact", "prospectLink")


@dataclass
class OsmPlace:
    osm_type: str       # node | way | relation
    osm_id: int
    tags: dict
    lat: float | None = None
    lon: float | None = None

    @property
    def ref(self) -> str:
        """Stable OSM id like 'node/123' — the dedup key (Twenty Lead.osmId)."""
        return f"{self.osm_type}/{self.osm_id}"

    @property
    def url(self) -> str:
        return f"https://www.openstreetmap.org/{self.osm_type}/{self.osm_id}"

    @property
    def name(self) -> str:
        t = self.tags
        return (t.get("name:ru") or t.get("name") or t.get("name:en")
                or t.get("name:kk") or "").strip()

    def _languages(self) -> list[str]:
        langs = [code for tag, code in (("name:ru", "RU"), ("name:kk", "KK"), ("name:en", "EN"))
                 if self.tags.get(tag)]
        return langs or ["RU"]

    def _address(self) -> str:
        t = self.tags
        street = " ".join(p for p in (t.get("addr:street"), t.get("addr:housenumber")) if p)
        return street or t.get("addr:full") or ""

    def _phone(self) -> str | None:
        t = self.tags
        return t.get("contact:phone") or t.get("phone") or None

    def _has_site(self) -> bool:
        t = self.tags
        return bool(t.get("website") or t.get("contact:website") or t.get("url"))

    def to_fields(self, niche_label: str) -> dict:
        """An LLM/2GIS-shaped fields dict (labels, not VALUEs). The niche is carried in by
        the caller — we queried by niche, so OSM's own category tag is redundant."""
        fields: dict = {
            "name": self.name or "Unnamed",
            "source": "OSM",
            "niche": niche_label,
            "language": self._languages(),
            "osmId": self.ref,
            "prospectLink": self.url,
            "hasWebsite": "Yes" if self._has_site() else "No",
        }
        if (addr := self._address()):
            fields["addressText"] = addr
        if (phone := self._phone()):
            fields["contact"] = phone
        return fields


def parse_elements(payload: dict) -> list[OsmPlace]:
    """Overpass JSON → [OsmPlace], skipping unnamed elements (unusable as a lead)."""
    out: list[OsmPlace] = []
    for el in (payload or {}).get("elements", []):
        tags = el.get("tags") or {}
        if not any(tags.get(k) for k in ("name", "name:ru", "name:en", "name:kk")):
            continue
        center = el.get("center") or {}
        out.append(OsmPlace(
            osm_type=el.get("type", "node"),
            osm_id=int(el.get("id", 0)),
            tags=tags,
            lat=el.get("lat", center.get("lat")),
            lon=el.get("lon", center.get("lon")),
        ))
    return out


def enrich(fields: dict, place: OsmPlace) -> dict:
    """Fill only-empty contact facts on an extracted-fields dict from an OSM match.

    Never overrides what the LLM already produced; always stamps osmId for dedup, and
    upgrades a missing/'No' website to 'Yes' when OSM knows a site. Mutates and returns.
    """
    src = place.to_fields(fields.get("niche") or "Other")
    for k in _ENRICH_KEYS:
        if not fields.get(k) and src.get(k):
            fields[k] = src[k]
    fields.setdefault("osmId", src["osmId"])
    if src.get("hasWebsite") == "Yes" and fields.get("hasWebsite") in (None, "", "No"):
        fields["hasWebsite"] = "Yes"
    return fields


class OverpassClient:
    def __init__(self, base_url: str, timeout: int = 30):
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    async def _post(self, query: str) -> dict:
        """One Overpass request with a single retry (a cold/self-hosted instance is slow)."""
        last: Exception | None = None
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as c:
                    r = await c.post(self._base, data={"data": query})
                if r.status_code == 200:
                    return r.json()
                last = RuntimeError(f"Overpass {r.status_code}: {r.text[:160]}")
            except (httpx.HTTPError, ValueError) as e:
                last = e
            if attempt == 0:
                await asyncio.sleep(1.0)
        raise last or RuntimeError("Overpass request failed")

    async def harvest(self, niche_label: str, area: str, limit: int = 50) -> list[OsmPlace]:
        tags = tags_for(niche_label)
        if not tags:
            return []
        data = await self._post(build_query(area, tags, limit))
        return parse_elements(data)[:limit]

    async def find_by_name(self, name: str, area: str, limit: int = 5) -> list[OsmPlace]:
        if not (name or "").strip():
            return []
        data = await self._post(build_name_query(name, area, limit))
        return parse_elements(data)
