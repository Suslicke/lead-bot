"""Unit tests for the configurable KPI — resolver, config validation, name mapping.

Run with pytest, or directly: `python3 tests/test_kpi.py` (needs aiogram importable).
"""
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import ConfigStore  # noqa: E402
from app.handlers.kpi import _canonical_metric  # noqa: E402
from app.stats import resolve_kpi  # noqa: E402

_COUNTS = Counter({"TO_CONTACT": 6, "CONTACTED": 1, "QUALIFIED": 2, "WON": 3})


def test_resolve_created_default_and_unknown():
    assert resolve_kpi("created", created=2, worked=5, counts=_COUNTS) == (2, "new leads")
    assert resolve_kpi("bogus", created=2, worked=5, counts=_COUNTS) == (2, "new leads")


def test_resolve_worked_won_stage():
    assert resolve_kpi("worked", created=2, worked=5, counts=_COUNTS) == (5, "worked today")
    assert resolve_kpi("won", created=2, worked=5, counts=_COUNTS) == (3, "won")
    assert resolve_kpi("stage:QUALIFIED", created=2, worked=5, counts=_COUNTS) == (2, "qualified")
    assert resolve_kpi("stage:REPLIED", created=2, worked=5, counts=_COUNTS) == (0, "replied")


def test_config_set_kpi_metric_valid_and_invalid():
    c = ConfigStore(Path(tempfile.mkdtemp()) / "config.json")
    assert c.kpi_metric == "created"               # default
    c.set_kpi_metric("won")
    assert c.kpi_metric == "won"
    c.set_kpi_metric("stage:QUALIFIED")
    assert c.kpi_metric == "stage:QUALIFIED"
    for bad in ("nonsense", "stage:NOPE", "stage:"):
        try:
            c.set_kpi_metric(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {bad!r}")


def test_canonical_metric_mapping():
    assert _canonical_metric("new") == "created"
    assert _canonical_metric("worked today") == "worked"
    assert _canonical_metric("won") == "won"          # not stage:WON
    assert _canonical_metric("qualified") == "stage:QUALIFIED"
    assert _canonical_metric("To contact") == "stage:TO_CONTACT"
    assert _canonical_metric("stage:replied") == "stage:REPLIED"
    assert _canonical_metric("garbage") is None


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"ALL {len(tests)} PASSED ✅")


if __name__ == "__main__":
    _run_all()
