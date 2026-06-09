"""Unit tests for capture.find_duplicate / _dedupe_within — osmId + link + name dedup.

Run with pytest, or directly: `python3 tests/test_dedup.py` (needs aiogram importable).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.handlers import capture  # noqa: E402


def test_find_duplicate_by_osm_id():
    leads = [{"id": "1", "name": "Other", "osmId": "node/9"},
             {"id": "2", "name": "Mismatch name", "osmId": "node/42"}]
    # matches on osmId even though the name differs (a re-harvest after a rename)
    dup = capture.find_duplicate(leads, {"name": "Renamed", "osmId": "node/42"})
    assert dup and dup["id"] == "2"


def test_find_duplicate_osm_id_beats_prospect_link():
    leads = [{"id": "1", "osmId": "node/42", "prospectLink": "https://2gis.kz/firm/777"}]
    # prospectLink swapped to 2GIS, but osmId still finds the lead
    dup = capture.find_duplicate(leads, {"osmId": "node/42",
                                         "prospectLink": "https://www.openstreetmap.org/node/42"})
    assert dup and dup["id"] == "1"


def test_find_duplicate_by_link():
    leads = [{"id": "1", "prospectLink": "https://2gis.kz/firm/100/"}]
    dup = capture.find_duplicate(leads, {"name": "X", "prospectLink": "https://2gis.kz/firm/100"})
    assert dup and dup["id"] == "1"  # trailing-slash/case normalised


def test_find_duplicate_name_scoped_by_city():
    leads = [{"id": "1", "name": "Coffee Boom", "city": "Astana"},
             {"id": "2", "name": "Coffee Boom", "city": "Almaty"}]
    dup = capture.find_duplicate(leads, {"name": "coffee boom", "city": "Almaty"})
    assert dup and dup["id"] == "2"  # same-name in a different city is NOT a dup


def test_find_duplicate_none():
    leads = [{"id": "1", "name": "A", "osmId": "node/1"}]
    assert capture.find_duplicate(leads, {"name": "B", "osmId": "node/2"}) is None


def test_dedupe_within_prefers_osm_id():
    out = capture._dedupe_within([
        {"name": "A", "osmId": "node/1"},
        {"name": "A-renamed", "osmId": "node/1"},   # same osmId → dropped
        {"name": "B", "osmId": "node/2"},
    ])
    assert [p["name"] for p in out] == ["A", "B"]


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"ALL {len(tests)} PASSED ✅")


if __name__ == "__main__":
    _run_all()
