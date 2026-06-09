"""Unit tests for app/osm_tags.py + app/osm.py — pure parsing/mapping (no network).

Run with pytest, or directly: `python3 tests/test_osm.py`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import osm, osm_tags  # noqa: E402


# --- osm_tags ----------------------------------------------------------------
def test_tags_for_known_and_unknown():
    assert osm_tags.tags_for("Cafe") == [("amenity", "cafe")]
    assert ("shop", "hairdresser") in osm_tags.tags_for("Beauty")
    assert osm_tags.tags_for("Nope") == []


def test_harvestable_niches():
    n = osm_tags.harvestable_niches()
    assert "Cafe" in n and "Beauty" in n and "Gaming club" in n


def test_build_query_shape():
    q = osm_tags.build_query("Алматы", [("amenity", "cafe")], limit=30)
    assert '[out:json]' in q
    assert 'area["name"="Алматы"]->.searchArea;' in q
    assert 'nwr["amenity"="cafe"](area.searchArea);' in q
    assert "out center 30;" in q


def test_build_query_escapes_quotes():
    q = osm_tags.build_query('Bad"name', [("shop", "beauty")], limit=5)
    assert 'Bad\\"name' in q  # injected quote is escaped, not raw


def test_build_name_query():
    q = osm_tags.build_name_query("Coffee BOOM", "Алматы", limit=5)
    assert 'nwr["name"~"Coffee BOOM",i](area.searchArea);' in q
    assert "out center 5;" in q


# --- osm.parse_elements ------------------------------------------------------
def _overpass_payload():
    return {"elements": [
        {"type": "node", "id": 1, "lat": 43.2, "lon": 76.9,
         "tags": {"name": "Coffee Boom", "name:ru": "Кофе Бум", "amenity": "cafe",
                  "addr:street": "пр. Абая", "addr:housenumber": "10",
                  "contact:phone": "+7 700 111 22 33", "website": "https://cb.kz"}},
        {"type": "way", "id": 2, "center": {"lat": 43.3, "lon": 77.0},
         "tags": {"name": "Beauty Bar", "shop": "beauty"}},
        {"type": "node", "id": 3, "tags": {"amenity": "cafe"}},  # no name → skipped
    ]}


def test_parse_skips_unnamed_and_reads_center():
    places = osm.parse_elements(_overpass_payload())
    assert [p.osm_id for p in places] == [1, 2]      # node 3 (unnamed) dropped
    assert places[1].lat == 43.3 and places[1].lon == 77.0  # way center used


def test_place_ref_and_url():
    p = osm.parse_elements(_overpass_payload())[0]
    assert p.ref == "node/1"
    assert p.url == "https://www.openstreetmap.org/node/1"


def test_to_fields_full():
    p = osm.parse_elements(_overpass_payload())[0]
    f = p.to_fields("Cafe")
    assert f["name"] == "Кофе Бум"            # name:ru preferred
    assert f["source"] == "OSM" and f["niche"] == "Cafe"
    assert f["osmId"] == "node/1"
    assert f["prospectLink"].endswith("/node/1")
    assert f["language"] == ["RU"]            # has name:ru
    assert f["hasWebsite"] == "Yes"
    assert f["addressText"] == "пр. Абая 10"
    assert f["contact"] == "+7 700 111 22 33"


def test_to_fields_minimal_no_site_no_addr():
    p = osm.parse_elements(_overpass_payload())[1]   # Beauty Bar (way)
    f = p.to_fields("Beauty")
    assert f["hasWebsite"] == "No"
    assert "addressText" not in f and "contact" not in f
    assert f["language"] == ["RU"]            # default when no name:* lang tags


# --- osm.enrich --------------------------------------------------------------
def test_enrich_fills_only_empty_and_stamps_osmid():
    place = osm.parse_elements(_overpass_payload())[0]
    fields = {"name": "Coffee Boom", "niche": "Cafe", "contact": "existing-phone"}
    osm.enrich(fields, place)
    assert fields["contact"] == "existing-phone"   # NOT overridden
    assert fields["addressText"] == "пр. Абая 10"  # filled (was empty)
    assert fields["osmId"] == "node/1"             # stamped
    assert fields["hasWebsite"] == "Yes"           # upgraded from absent


def test_enrich_does_not_downgrade_website():
    place = osm.parse_elements(_overpass_payload())[1]  # no site
    fields = {"name": "X", "niche": "Beauty", "hasWebsite": "Yes"}
    osm.enrich(fields, place)
    assert fields["hasWebsite"] == "Yes"           # OSM 'No' must not clobber a known Yes


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"ALL {len(tests)} PASSED ✅")


if __name__ == "__main__":
    _run_all()
