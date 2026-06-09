"""Per-user, per-day LLM usage accounting + daily caps.

Persisted as JSON in the data volume (next to config.json). Counters are keyed by
local (settings.tz) calendar day — so a "day" matches the operator's day, and the
cap resets at local midnight — and by Telegram user id. Old days are trimmed so the
file stays small.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

_KEEP_DAYS = 30  # history retained; older buckets are dropped on write


class UsageStore:
    def __init__(self, path: Path, tz: ZoneInfo):
        self._path = path
        self._tz = tz
        self._data: dict = self._read()

    def _read(self) -> dict:
        try:
            return json.loads(self._path.read_text())
        except (FileNotFoundError, ValueError):
            return {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(self._data, indent=2))

    def _today(self) -> str:
        return datetime.now(self._tz).strftime("%Y-%m-%d")

    def record(self, uid: int, prompt_tokens: int, completion_tokens: int) -> None:
        b = self._data.setdefault(self._today(), {}).setdefault(str(uid), {})
        b["requests"] = b.get("requests", 0) + 1
        b["prompt_tokens"] = b.get("prompt_tokens", 0) + int(prompt_tokens)
        b["completion_tokens"] = b.get("completion_tokens", 0) + int(completion_tokens)
        self._trim()
        self._save()

    def today(self, uid: int) -> dict:
        b = self._data.get(self._today(), {}).get(str(uid), {})
        p, c = b.get("prompt_tokens", 0), b.get("completion_tokens", 0)
        return {"requests": b.get("requests", 0),
                "prompt_tokens": p, "completion_tokens": c, "total_tokens": p + c}

    def over_limit(self, uid: int, max_requests: int, max_tokens: int) -> str | None:
        """Human reason if the user is at/over either cap *today*, else None.

        Checked BEFORE a call, so a cap of N lets exactly N requests through. A cap
        of 0 means 'unlimited' for that dimension.
        """
        t = self.today(uid)
        if max_requests and t["requests"] >= max_requests:
            return f"requests {t['requests']}/{max_requests}"
        if max_tokens and t["total_tokens"] >= max_tokens:
            return f"tokens {t['total_tokens']}/{max_tokens}"
        return None

    def _trim(self) -> None:
        if len(self._data) > _KEEP_DAYS:
            for day in sorted(self._data)[:-_KEEP_DAYS]:
                self._data.pop(day, None)
