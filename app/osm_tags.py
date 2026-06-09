"""Niche → OSM tag vocabulary + Overpass-QL query builder.

`NICHE_TAG_MAP` maps our niche LABEL (the same labels twenty.NICHE / twogis use —
"Cafe", "Beauty", "Gaming club") to a list of (key, value) OSM tag filters. So a
harvested place's niche flows through the existing to_payload(label -> VALUE) path
just like an LLM/2GIS one. `build_query` turns a niche's tags + a named area into an
Overpass-QL request.

A product decision, not config — edit it as harvested-lead quality is observed:
- Cafe is deliberately narrow: `amenity=cafe` only (no restaurant/fast_food — a
  different ICP).
- Beauty spans salons + barbers + spa + massage.
- Gaming-club coverage in OSM is weak and inconsistently tagged, so expect few
  results there (kept as a best-effort draft).
"""
from __future__ import annotations

# niche LABEL -> [(osm_key, osm_value), ...]. The label MUST match the niche
# vocabulary in twenty.NICHE / OptionsRegistry, or to_payload collapses it to OTHER.
NICHE_TAG_MAP: dict[str, list[tuple[str, str]]] = {
    "Cafe": [("amenity", "cafe")],
    "Beauty": [("shop", "beauty"), ("shop", "hairdresser"),
               ("leisure", "spa"), ("shop", "massage")],
    "Gaming club": [("leisure", "adult_gaming_centre"), ("amenity", "internet_cafe")],
}


def harvestable_niches() -> list[str]:
    """Niche labels we know how to harvest (have an OSM tag mapping)."""
    return list(NICHE_TAG_MAP)


def tags_for(niche_label: str) -> list[tuple[str, str]]:
    return NICHE_TAG_MAP.get(niche_label, [])


def build_query(area: str, tags: list[tuple[str, str]], limit: int = 50, timeout: int = 25) -> str:
    """Overpass-QL: every node/way/relation matching any of `tags` inside `area`.

    `area["name"=...]` resolves the named admin boundary (city/district); `nwr(area)`
    collects places of each tag; `out center N` gives ways/relations a single lat/lon
    and hard-caps the result count so a big city can't return thousands.
    """
    safe_area = area.strip().replace("\\", "").replace('"', '\\"')
    selectors = "".join(f'  nwr["{k}"="{v}"](area.searchArea);\n' for k, v in tags)
    return (
        f"[out:json][timeout:{int(timeout)}];\n"
        f'area["name"="{safe_area}"]->.searchArea;\n'
        f"(\n{selectors});\n"
        f"out center {int(limit)};\n"
    )


def build_name_query(name: str, area: str, limit: int = 5, timeout: int = 25) -> str:
    """Overpass-QL for enrichment: places whose name matches `name` inside `area`.

    Case-insensitive substring match (`~`, `,i`) so "Coffee BOOM" finds
    "Coffee Boom" / "coffee boom №2". Restricted to named POIs (nwr with a name tag).
    """
    safe_area = area.strip().replace("\\", "").replace('"', '\\"')
    safe_name = name.strip().replace("\\", "").replace('"', '\\"')
    return (
        f"[out:json][timeout:{int(timeout)}];\n"
        f'area["name"="{safe_area}"]->.searchArea;\n'
        f'nwr["name"~"{safe_name}",i](area.searchArea);\n'
        f"out center {int(limit)};\n"
    )
