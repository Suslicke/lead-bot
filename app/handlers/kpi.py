"""/kpi — show progress, or `/kpi set <n>` to change the daily goal."""
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..config import ConfigStore
from ..stats import StatsService
from ..timeutil import progress_bar

router = Router()


@router.message(Command("kpi"))
async def kpi(message: Message, command: CommandObject, config: ConfigStore, stats: StatsService) -> None:
    arg = (command.args or "").strip()
    if arg.startswith("set"):
        try:
            config.set_kpi_goal(int(arg.split()[1]))
            await message.answer(f"🎯 Daily goal set to <b>{config.kpi_goal}</b> new prospects.")
        except (IndexError, ValueError):
            await message.answer("Usage: /kpi set 10")
        return
    created = await stats.created_today()
    goal = config.kpi_goal
    await message.answer(f"🎯 <b>{created}/{goal}</b> new prospects today  {progress_bar(created, goal)}")
