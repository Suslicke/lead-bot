"""/kpi — show progress, set the daily goal (/kpi set <n>) or the metric (/kpi metric <x>)."""
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..config import ConfigStore
from ..stats import StatsService
from ..timeutil import progress_bar
from ..twenty import STAGE_LABEL, STAGE_ORDER

router = Router()

_METRIC_HELP = (
    "Pick what the KPI counts:\n"
    "• <code>/kpi metric created</code> — new leads / day\n"
    "• <code>/kpi metric worked</code> — leads touched today\n"
    "• <code>/kpi metric won</code> — deals won\n"
    "• <code>/kpi metric qualified</code> (or any stage) — current count in that stage"
)


def _canonical_metric(name: str) -> str | None:
    """Friendly name → canonical config value ('created'|'worked'|'won'|'stage:<STAGE>')."""
    n = name.strip().lower().removeprefix("stage:")
    if n in ("created", "new", "new leads", "leads"):
        return "created"
    if n in ("worked", "worked today", "updated", "touched"):
        return "worked"
    if n in ("won", "deal", "deals", "sales"):
        return "won"
    for val in STAGE_ORDER:
        if n in (val.lower(), STAGE_LABEL[val].lower()):
            return "won" if val == "WON" else f"stage:{val}"
    return None


@router.message(Command("kpi"))
async def kpi(message: Message, command: CommandObject,
              config: ConfigStore, stats: StatsService) -> None:
    arg = (command.args or "").strip()

    if arg.startswith("set"):
        try:
            config.set_kpi_goal(int(arg.split()[1]))
            await message.answer(f"🎯 Daily goal set to <b>{config.kpi_goal}</b>.")
        except (IndexError, ValueError):
            await message.answer("Usage: <code>/kpi set 10</code>")
        return

    if arg.startswith("metric"):
        name = arg[len("metric"):].strip()
        if not name:
            await message.answer(_METRIC_HELP + f"\n\nNow: <b>{config.kpi_metric}</b>")
            return
        canonical = _canonical_metric(name)
        if not canonical:
            await message.answer(f"⚠️ Unknown metric <code>{name}</code>.\n\n{_METRIC_HELP}")
            return
        config.set_kpi_metric(canonical)
        await message.answer(f"🎯 KPI metric → <b>{config.kpi_metric}</b>.")
        return

    d = await stats.today_data()
    await message.answer(
        f"🎯 <b>{d['kpi_label']}: {d['kpi_value']}/{d['goal']}</b>  "
        f"{progress_bar(d['kpi_value'], d['goal'])}\n"
        f"<i>metric: {d['kpi_metric']} · change: /kpi metric &lt;x&gt; · goal: /kpi set &lt;n&gt;</i>"
    )
