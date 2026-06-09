"""Business logic: pipeline counts, KPI (new prospects today), digest text."""
from __future__ import annotations

from collections import Counter
from zoneinfo import ZoneInfo

from .config import ConfigStore
from .timeutil import MAX_UTC, MIN_UTC, day_bounds_utc, parse_dt, progress_bar
from .twenty import CLOSED, STAGE_LABEL, STAGE_ORDER, TwentyClient


class StatsService:
    def __init__(self, twenty: TwentyClient, config: ConfigStore, tz: ZoneInfo):
        self._twenty = twenty
        self._config = config
        self._tz = tz

    async def pipeline_counts(self) -> tuple[Counter, int]:
        leads = await self._twenty.all_leads()
        return Counter(l.get("stage") for l in leads), len(leads)

    async def created_today(self) -> int:
        start, _ = day_bounds_utc(self._tz)
        leads = await self._twenty.all_leads()
        return sum(1 for l in leads if (parse_dt(l.get("createdAt")) or MIN_UTC) >= start)

    async def leads_in_stage(self, stage: str) -> list[dict]:
        return [l for l in await self._twenty.all_leads() if l.get("stage") == stage]

    async def status_text(self, header: str) -> str:
        leads = await self._twenty.all_leads()
        start, end = day_bounds_utc(self._tz)
        counts = Counter(l.get("stage") for l in leads)
        due = [
            l for l in leads
            if l.get("stage") not in CLOSED
            and (parse_dt(l.get("nextStepDate")) or MAX_UTC) <= end
        ]
        created = sum(1 for l in leads if (parse_dt(l.get("createdAt")) or MIN_UTC) >= start)
        goal = self._config.kpi_goal

        lines = [f"<b>{header}</b>", "", "<b>Pipeline</b>"]
        for s in STAGE_ORDER:
            if counts.get(s):
                lines.append(f"  {STAGE_LABEL[s]}: {counts[s]}")
        lines += ["", f"⏰ <b>Due today: {len(due)}</b>"]
        for l in due[:10]:
            lines.append(f"  • {l.get('name')} — {l.get('nextStep') or '—'}")
        if len(due) > 10:
            lines.append(f"  …and {len(due) - 10} more")
        lines += ["", f"🎯 <b>KPI: {created}/{goal}</b> new prospects today  {progress_bar(created, goal)}"]
        return "\n".join(lines)
