"""Unit tests for app/draft.py — the pure edit logic (no aiogram needed).

Run with pytest, or directly: `python3 tests/test_draft.py`.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import draft  # noqa: E402


def _lead():
    return {"name": "Чайхана", "stage": "TO_CONTACT", "city": "Almaty",
            "niche": "CAFE", "hasWebsite": "NO", "source": "TWO_GIS", "language": ["RU"]}


def test_ref_roundtrip():
    assert draft.parse_ref("abc") == ("abc", None)
    assert draft.parse_ref("abc#3") == ("abc", 3)
    assert draft.make_ref("abc") == "abc"
    assert draft.make_ref("abc", 3) == "abc#3"


def test_set_text_free_and_clear():
    p = _lead()
    draft.set_text(p, "contact", "  wa.me/77001112233 ")
    assert p["contact"] == "wa.me/77001112233"  # trimmed
    draft.set_text(p, "contact", "")  # optional → cleared
    assert "contact" not in p
    draft.set_text(p, "name", "")  # required → not cleared to empty
    assert p["name"] == "Чайхана"


def test_set_text_numbers():
    p = _lead()
    draft.set_text(p, "reviewsCount", "320")
    assert p["reviewsCount"] == 320 and isinstance(p["reviewsCount"], int)
    draft.set_text(p, "rating", "4,7")  # comma decimal tolerated
    assert p["rating"] == 4.7
    draft.set_text(p, "rating", "9")  # clamped to 0..5
    assert p["rating"] == 5.0
    draft.set_text(p, "reviewsCount", "-5")  # clamped to >= 0
    assert p["reviewsCount"] == 0


def test_set_text_bad_number_raises():
    p = _lead()
    try:
        draft.set_text(p, "rating", "good")
    except ValueError as e:
        assert str(e) == "number"
    else:
        raise AssertionError("expected ValueError for non-numeric rating")


def test_toggle_language():
    p = _lead()
    draft.toggle_language(p, "KK")
    assert p["language"] == ["RU", "KK"]
    draft.toggle_language(p, "RU")
    assert p["language"] == ["KK"]


def test_set_select_and_required_missing():
    p = _lead()
    draft.set_select(p, "niche", "BEAUTY")
    assert p["niche"] == "BEAUTY"
    assert draft.required_missing(p) == []
    p["name"] = "Unnamed lead"
    assert "name" in draft.required_missing(p)


def test_stores_and_action_mode():
    draft.PENDING.clear()
    draft.BATCH.clear()
    draft.PENDING["p1"] = {"payload": _lead(), "existing": None, "msg_id": 10}
    draft.PENDING["p2"] = {"payload": _lead(), "existing": "x", "msg_id": 11}
    draft.BATCH["b1"] = {"items": [{"payload": _lead(), "existing": None}], "msg_id": 20}

    assert draft.get_payload("p1")["name"] == "Чайхана"
    assert draft.action_mode("p1") == "single_new"
    assert draft.action_mode("p2") == "single_dup"
    assert draft.action_mode("b1#0") == "batch_item"
    assert draft.msg_id_of("p1") == 10
    assert draft.msg_id_of("b1#0") == 20
    assert draft.get_payload("b1#9") is None  # out-of-range idx
    assert draft.get_payload("nope") is None


def test_preview_and_batch_summary():
    p = _lead()
    text = draft.preview(p)
    assert "Чайхана" in text and "CAFE" in text and "RU" in text
    summary = draft.batch_summary([
        {"payload": _lead(), "existing": None},
        {"payload": {**_lead(), "name": "Barber"}, "existing": "x"},
    ])
    assert "2 leads" in summary and "1 new" in summary and "⚠️ dup" in summary


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"ALL {len(tests)} PASSED ✅")


if __name__ == "__main__":
    _run_all()
