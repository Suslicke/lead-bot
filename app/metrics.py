"""Lightweight daily counters for outbound API calls (2GIS, OSM/Overpass, …).

A process-global singleton (the bot is single-process) persisted to data/api.json, keyed by
local-tz day → per-API count. Deliberately separate from UsageStore: that's per-*user* LLM
tokens; this is per-*API* call volume, to watch external quotas (the 2GIS demo key, the
Overpass rate limit). Call `init()` once at startup; `hit()` from anywhere; `today()` to read.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_KEEP_DAYS = 30
_path: Path | None = None
_tz: ZoneInfo | None = None
_data: dict = {}


def init(path: Path, tz: ZoneInfo) -> None:
    global _path, _tz, _data
    _path, _tz = path, tz
    try:
        _data = json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        _data = {}


def _day() -> str:
    return datetime.now(_tz).strftime("%Y-%m-%d")


def hit(api: str) -> None:
    """Count one call to `api` today. No-op until init() (e.g. in unit tests)."""
    if _path is None or _tz is None:
        return
    bucket = _data.setdefault(_day(), {})
    bucket[api] = bucket.get(api, 0) + 1
    if len(_data) > _KEEP_DAYS:
        for d in sorted(_data)[:-_KEEP_DAYS]:
            _data.pop(d, None)
    try:
        _path.parent.mkdir(parents=True, exist_ok=True)
        _path.write_text(json.dumps(_data, indent=2))
    except OSError:
        pass  # counters are best-effort — never break a capture over a write hiccup


def today() -> dict:
    """Today's per-API call counts, e.g. {'2gis': 8, 'osm': 3}."""
    return dict(_data.get(_day(), {})) if _tz else {}
