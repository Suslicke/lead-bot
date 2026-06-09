"""/settings and /digest (send now, or manage the schedule live)."""
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..config import ConfigStore, Settings
from ..scheduler import DigestScheduler
from ..stats import StatsService
from ..timeutil import valid_hhmm

router = Router()


@router.message(Command("settings"))
async def settings_cmd(message: Message, config: ConfigStore, settings: Settings) -> None:
    await message.answer(
        f"<b>Settings</b>\n"
        f"KPI goal: {config.kpi_goal} new prospects/day\n"
        f"Digest times ({settings.tz.key}): {', '.join(config.digest_times) or 'off'}\n"
        f"LLM caps/user/day: {config.llm_max_requests or '∞'} req · {config.llm_max_tokens or '∞'} tokens"
    )


@router.message(Command("digest"))
async def digest_cmd(message: Message, command: CommandObject, config: ConfigStore,
                     stats: StatsService, scheduler: DigestScheduler, settings: Settings) -> None:
    parts = (command.args or "").split()
    if not parts:  # send the digest right now
        await message.answer(await stats.status_text("📊 Digest"))
        return
    action = parts[0].lower()
    if action == "list":
        await message.answer(f"Digest times ({settings.tz.key}): {', '.join(config.digest_times) or 'off'}")
    elif action in ("add", "remove") and len(parts) > 1 and valid_hhmm(parts[1]):
        (config.add_digest if action == "add" else config.remove_digest)(parts[1])
        scheduler.reschedule()
        await message.answer(f"✅ Digest times: {', '.join(config.digest_times) or 'off'}")
    elif action == "off":
        config.clear_digests()
        scheduler.reschedule()
        await message.answer("🔕 Digests off.")
    else:
        await message.answer("Usage: /digest [list|add HH:MM|remove HH:MM|off]")
