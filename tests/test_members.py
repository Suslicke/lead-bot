"""Unit tests for the runtime allowlist — ConfigStore.members + dynamic Whitelist.

Run with pytest, or directly: `python3 tests/test_members.py` (needs aiogram importable).
"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import ConfigStore  # noqa: E402
from app.filters import Whitelist  # noqa: E402


def _store() -> ConfigStore:
    return ConfigStore(Path(tempfile.mkdtemp()) / "config.json")


class _Event:
    def __init__(self, uid: int | None):
        self.from_user = type("U", (), {"id": uid})() if uid is not None else None


def test_add_remove_member_idempotent():
    c = _store()
    assert c.members == []
    assert c.add_member(111) is True
    assert c.add_member(111) is False        # already present
    assert 111 in c.members
    assert c.remove_member(111) is True
    assert c.remove_member(111) is False     # not present
    assert c.members == []


def test_member_persists_across_reload():
    p = Path(tempfile.mkdtemp()) / "config.json"
    ConfigStore(p).add_member(222)
    assert 222 in ConfigStore(p).members     # read back from disk


def test_whitelist_admins_plus_members_live():
    c = _store()
    wl = Whitelist(frozenset({1}), c)
    assert wl.allowed() == {1}
    c.add_member(2)
    assert wl.allowed() == {1, 2}            # picked up live, not frozen at init


def test_whitelist_call_allows_admin_and_member_denies_other():
    c = _store()
    c.add_member(2)
    wl = Whitelist(frozenset({1}), c)
    assert asyncio.run(wl(_Event(1))) is True   # admin
    assert asyncio.run(wl(_Event(2))) is True   # member
    assert asyncio.run(wl(_Event(3))) is False  # neither
    assert asyncio.run(wl(_Event(None))) is False  # no user


def test_whitelist_empty_is_open():
    wl = Whitelist(frozenset(), _store())
    assert wl.allowed() == set()
    assert asyncio.run(wl(_Event(999))) is True  # empty allowlist = open


def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"  ✓ {t.__name__}")
    print(f"ALL {len(tests)} PASSED ✅")


if __name__ == "__main__":
    _run_all()
