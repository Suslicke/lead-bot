"""/start and /menu — an inline button hub that fronts the most-used commands.

The hub is a thin convenience layer: each button re-runs the same read it would from the
typed command (no duplicated business logic beyond a few render lines). Telegram's blue
"Menu" button (set in main via set_my_commands) covers the full command list.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)

from ..config import ConfigStore
from ..keyboards import convert_kb
from ..reference import OptionsRegistry
from ..stats import StatsService
from ..twenty import CURRENCIES, STAGE_LABEL, STAGE_ORDER, TwentyClient
from ..usage import UsageStore
from .common import HELP
from .convert import convertible

router = Router()

HUB = ("<b>Lead-bot</b> — command center\n\n"
       "➕ <b>Add a lead:</b> just send a 2GIS link + facts.")


def _hub_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardButton
    return InlineKeyboardMarkup(inline_keyboard=[
        [b(text="📅 Today", callback_data="menu:today"), b(text="📊 Pipeline", callback_data="menu:pipeline")],
        [b(text="➡️ Convert", callback_data="menu:convert"), b(text="💱 Currency", callback_data="menu:currency")],
        [b(text="🏷 Niches", callback_data="menu:niches"), b(text="📈 Usage", callback_data="menu:usage")],
        [b(text="❔ Help", callback_data="menu:help")],
    ])


@router.message(CommandStart())
@router.message(Command("menu"))
async def menu(message: Message) -> None:
    await message.answer(HUB, reply_markup=_hub_kb())


@router.callback_query(F.data.startswith("menu:"))
async def hub_dispatch(callback: CallbackQuery, stats: StatsService, twenty: TwentyClient,
                       config: ConfigStore, options: OptionsRegistry, usage: UsageStore) -> None:
    action = callback.data.split(":", 1)[1]
    await callback.answer()
    send = callback.message.answer  # post a fresh message; leaves the hub intact

    if action == "today":
        await send(await stats.status_text("📅 Today"))
    elif action == "pipeline":
        counts, total = await stats.pipeline_counts()
        lines = ["<b>Pipeline</b>", ""] + [f"  {STAGE_LABEL[s]}: {counts.get(s, 0)}" for s in STAGE_ORDER]
        await send("\n".join(lines) + f"\n\nTotal: {total}")
    elif action == "convert":
        ready = convertible(await twenty.all_leads())
        if ready:
            await send("Pick a lead to convert into <b>Company + Opportunity</b>:",
                       reply_markup=convert_kb(ready[:20]))
        else:
            await send("No leads ready to convert (need Replied / Qualified / Proposal).")
    elif action == "currency":
        await send(f"Default deal currency: <b>{config.deal_currency}</b>\n"
                   f"Change: <code>/currency USD</code> · options: {', '.join(CURRENCIES)}")
    elif action == "niches":
        labels = options.labels("niche")
        await send(f"<b>Niches</b> ({len(labels)}):\n" + "\n".join(f"• {x}" for x in labels) +
                   "\n\nAdd: <code>/niche add &lt;name&gt;</code>")
    elif action == "usage":
        t = usage.today(callback.from_user.id)
        await send(f"📊 <b>Usage today</b>\nRequests: <b>{t['requests']}</b>   "
                   f"Tokens: <b>{t['total_tokens']}</b>  ·  see /usage")
    elif action == "help":
        await send(HELP)
