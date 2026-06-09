"""Business logic: pipeline counts, KPI (new prospects today), digest text."""
from __future__ import annotations

from collections import Counter
from zoneinfo import ZoneInfo

from datetime import datetime

from .config import ConfigStore
from .timeutil import MAX_UTC, MIN_UTC, bar, day_bounds_utc, parse_dt, progress_bar
from .twenty import CLOSED, SOURCE, STAGE_LABEL, STAGE_ORDER, TwentyClient

# Lead.source VALUE -> short display label (inverse of twenty.SOURCE).
SOURCE_LABEL = {v: k for k, v in SOURCE.items()}


def resolve_kpi(metric: str, *, created: int, worked: int, counts) -> tuple[int, str]:
    """Map a KPI metric → (value, short label). Falls back to 'created' on anything unknown.

    created/worked are day-scoped flow counts; won + stage:<X> are point-in-time pipeline
    counts. Keeps the /today text and PNG cards reading from one definition.
    """
    if metric == "worked":
        return worked, "worked today"
    if metric == "won":
        return counts.get("WON", 0), "won"
    if metric.startswith("stage:"):
        st = metric.split(":", 1)[1]
        return counts.get(st, 0), STAGE_LABEL.get(st, st).lower()
    return created, "new leads"


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

    async def today_data(self) -> dict:
        """The numbers behind /today — one source for both the text and image cards."""
        leads = await self._twenty.all_leads()
        start, end = day_bounds_utc(self._tz)
        counts = Counter(l.get("stage") for l in leads)
        sources = Counter(l.get("source") for l in leads)
        due = [l for l in leads
               if l.get("stage") not in CLOSED
               and (parse_dt(l.get("nextStepDate")) or MAX_UTC) <= end]
        created = sum(1 for l in leads if (parse_dt(l.get("createdAt")) or MIN_UTC) >= start)
        worked = sum(1 for l in leads if (parse_dt(l.get("updatedAt")) or MIN_UTC) >= start)
        won, lost = counts.get("WON", 0), counts.get("LOST", 0)
        metric = self._config.kpi_metric
        kpi_value, kpi_label = resolve_kpi(metric, created=created, worked=worked, counts=counts)
        return {
            "date": datetime.now(self._tz).strftime("%d %b"),
            "counts": counts, "sources": sources, "due": due, "created": created,
            "worked": worked, "total": len(leads), "won": won, "lost": lost,
            "conv": (won / (won + lost)) if (won + lost) else None,
            "goal": self._config.kpi_goal,
            "kpi_metric": metric, "kpi_value": kpi_value, "kpi_label": kpi_label,
        }

    async def status_text(self, header: str) -> str:
        d = await self.today_data()
        counts, total, due = d["counts"], d["total"], d["due"]
        active = [(s, counts[s]) for s in STAGE_ORDER if counts.get(s)]
        peak = max((n for _, n in active), default=0)

        lines = [f"📊 <b>{header}</b> · {d['date']}", ""]
        if active:  # monospace funnel so the bars line up
            funnel = [f"Pipeline{total:>16}"]
            for s, n in active:
                funnel.append(f"  {STAGE_LABEL[s]:<11}{bar(n, peak, 10)} {n}")
            lines += [f"<pre>{chr(10).join(funnel)}</pre>"]
        conv = f"{round(d['conv'] * 100)}%" if d["conv"] is not None else "—"
        src = "  ".join(f"{SOURCE_LABEL.get(k, k or '—')} {v}"
                        for k, v in d["sources"].most_common(4))
        lines += [f"📈 Conv <b>{conv}</b>  ·  +<b>{d['created']}</b> today", f"   {src}" if src else ""]
        lines += ["", f"⏰ <b>Due today: {len(due)}</b>"]
        for l in due[:8]:
            lines.append(f"  • {l.get('name')} — {l.get('nextStep') or '—'}")
        if len(due) > 8:
            lines.append(f"  …and {len(due) - 8} more")
        lines += ["", f"🎯 <b>KPI · {d['kpi_label']} {d['kpi_value']}/{d['goal']}</b>  "
                  f"{progress_bar(d['kpi_value'], d['goal'])}"]
        return "\n".join(x for x in lines if x is not None)
