"""/kpi — an interactive settings panel (pick metric, nudge the goal), plus text shortcuts
`/kpi set <n>` and `/kpi metric <x>` for power users."""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from ..config import ConfigStore
from ..keyboards import kpi_kb, kpi_stage_kb
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


def panel_text(d: dict) -> str:
    """Header for the KPI panel — built from StatsService.today_data()."""
    return (f"🎯 <b>KPI</b> · {d['kpi_label']}: <b>{d['kpi_value']}/{d['goal']}</b>  "
            f"{progress_bar(d['kpi_value'], d['goal'])}\n"
            f"<i>Tap a metric · adjust the goal with ±.</i>")


async def _show_panel(message: Message, stats: StatsService, config: ConfigStore) -> None:
    d = await stats.today_data()
    await message.answer(panel_text(d), reply_markup=kpi_kb(d["kpi_metric"], d["goal"]))


async def _rerender(callback: CallbackQuery, stats: StatsService) -> None:
    d = await stats.today_data()
    try:
        await callback.message.edit_text(panel_text(d), reply_markup=kpi_kb(d["kpi_metric"], d["goal"]))
    except TelegramBadRequest:
        pass  # "message is not modified" (e.g. goal already at the clamp) — ignore


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
        canonical = _canonical_metric(name) if name else None
        if name and not canonical:
            await message.answer(f"⚠️ Unknown metric <code>{name}</code>.\n\n{_METRIC_HELP}")
            return
        if canonical:
            config.set_kpi_metric(canonical)
        await _show_panel(message, stats, config)
        return
    await _show_panel(message, stats, config)  # no arg → interactive panel


# --- panel callbacks ---------------------------------------------------------
@router.callback_query(F.data == "kpi:noop")
async def kpi_noop(callback: CallbackQuery) -> None:
    await callback.answer("Use ± to change the goal")


@router.callback_query(F.data.startswith("kpi:m:"))
async def kpi_pick_metric(callback: CallbackQuery, config: ConfigStore, stats: StatsService) -> None:
    config.set_kpi_metric(callback.data.split(":", 2)[2])
    await _rerender(callback, stats)
    await callback.answer("Metric set ✓")


@router.callback_query(F.data == "kpi:stage")
async def kpi_open_stage(callback: CallbackQuery, config: ConfigStore) -> None:
    await callback.message.edit_reply_markup(reply_markup=kpi_stage_kb(config.kpi_metric))
    await callback.answer()


@router.callback_query(F.data.startswith("kpi:s:"))
async def kpi_pick_stage(callback: CallbackQuery, config: ConfigStore, stats: StatsService) -> None:
    v = callback.data.split(":", 2)[2]
    config.set_kpi_metric("won" if v == "WON" else f"stage:{v}")
    await _rerender(callback, stats)
    await callback.answer("Stage set ✓")


@router.callback_query(F.data == "kpi:back")
async def kpi_back(callback: CallbackQuery, config: ConfigStore, stats: StatsService) -> None:
    await _rerender(callback, stats)
    await callback.answer()


@router.callback_query(F.data.startswith("kpi:g:"))
async def kpi_goal(callback: CallbackQuery, config: ConfigStore, stats: StatsService) -> None:
    delta = int(callback.data.split(":", 2)[2])
    config.set_kpi_goal(max(1, config.kpi_goal + delta))
    await _rerender(callback, stats)
    await callback.answer(f"Goal {config.kpi_goal}")
