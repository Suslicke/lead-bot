"""Read commands: /today, /pipeline, /leads <stage>."""
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..stats import StatsService
from ..twenty import STAGE_LABEL, STAGE_ORDER

router = Router()


@router.message(Command("today"))
async def today(message: Message, stats: StatsService) -> None:
    await message.answer(await stats.status_text("📅 Today"))


@router.message(Command("pipeline"))
async def pipeline(message: Message, stats: StatsService) -> None:
    counts, total = await stats.pipeline_counts()
    lines = ["<b>Pipeline</b>", ""]
    for s in STAGE_ORDER:
        lines.append(f"  {STAGE_LABEL[s]}: {counts.get(s, 0)}")
    lines.append(f"\nTotal: {total}")
    await message.answer("\n".join(lines))


@router.message(Command("leads"))
async def leads(message: Message, command: CommandObject, stats: StatsService) -> None:
    arg = (command.args or "").strip().lower()
    stage = next((s for s, label in STAGE_LABEL.items() if arg in (s.lower(), label.lower())), None)
    if not stage:
        await message.answer("Usage: /leads &lt;stage&gt; — e.g. /leads replied")
        return
    items = await stats.leads_in_stage(stage)
    if not items:
        await message.answer(f"No leads in <b>{STAGE_LABEL[stage]}</b>.")
        return
    lines = [f"<b>{STAGE_LABEL[stage]}</b> ({len(items)})", ""]
    for l in items[:25]:
        lines.append(f"  • {l.get('name')} — {l.get('nextStep') or '—'}")
    await message.answer("\n".join(lines))
