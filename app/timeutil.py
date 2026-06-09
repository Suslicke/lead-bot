"""Time helpers: 'today' bounds in the configured tz, ISO parsing, a progress bar."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

MIN_UTC = datetime.min.replace(tzinfo=timezone.utc)
MAX_UTC = datetime.max.replace(tzinfo=timezone.utc)


def day_bounds_utc(tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Start and end of 'today' (local tz), expressed in UTC for comparing timestamps."""
    start_local = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def progress_bar(done: int, goal: int, width: int = 10) -> str:
    if goal <= 0:
        return ""
    filled = min(width, round(width * done / goal))
    return "▰" * filled + "▱" * (width - filled)


_PARTIAL = "▏▎▍▌▋▊▉"  # 1/8 .. 7/8 block fills, for a smooth proportional bar


def bar(value: int, peak: int, width: int = 12) -> str:
    """A proportional block bar (value/peak), padded to `width` for monospace alignment."""
    if peak <= 0 or value <= 0:
        return " " * width
    units = width * value / peak
    full = int(units)
    rem = units - full
    out = "█" * full
    if full < width and rem > 0:
        out += _PARTIAL[min(len(_PARTIAL) - 1, int(rem * 8))]
    return out[:width].ljust(width)


def valid_hhmm(s: str) -> bool:
    try:
        h, m = s.split(":")
        return 0 <= int(h) < 24 and 0 <= int(m) < 60
    except ValueError:
        return False
