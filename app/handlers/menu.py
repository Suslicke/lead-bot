"""/start and /menu — a persistent bottom button panel (ReplyKeyboard) fronting the
most-used commands.

Reply-keyboard taps arrive as plain text (the button label), so the NAV handler must run
*before* capture's catch-all — `menu.router` is first in get_routers(), so it does. Each
action re-runs the same read as the typed command (no logic dupe — e.g. convert.convertible()).
Telegram's blue "Menu" button (set in main via set_my_commands) still lists every command.
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from ..config import ConfigStore
from ..keyboards import NAV, convert_kb, kpi_kb, main_kb
from ..reference import OptionsRegistry
from ..stats import StatsService
from ..twenty import CURRENCIES, STAGE_LABEL, STAGE_ORDER, TwentyClient
from ..usage import UsageStore
from .cards import card_kb
from .common import HELP
from .convert import convertible
from .kpi import panel_text

router = Router()

HUB = ("<b>Lead-bot</b> — command center.\n"
       "Use the buttons below, or just send a 2GIS link + facts to add a lead.")


@router.message(CommandStart())
@router.message(Command("menu"))
async def menu(message: Message) -> None:
    await message.answer(HUB, reply_markup=main_kb())


async def _run(action: str, send, stats: StatsService, twenty: TwentyClient,
               config: ConfigStore, options: OptionsRegistry, usage: UsageStore, uid: int) -> None:
    if action == "today":
        await send(await stats.status_text("📅 Today"), reply_markup=card_kb())
    elif action == "kpi":
        d = await stats.today_data()
        await send(panel_text(d), reply_markup=kpi_kb(d["kpi_metric"], d["goal"]))
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
        t = usage.today(uid)
        await send(f"📊 <b>Usage today</b>\nRequests: <b>{t['requests']}</b>   "
                   f"Tokens: <b>{t['total_tokens']}</b>  ·  see /usage")
    elif action == "help":
        await send(HELP)


@router.message(F.text.in_(NAV))
async def nav(message: Message, stats: StatsService, twenty: TwentyClient,
              config: ConfigStore, options: OptionsRegistry, usage: UsageStore) -> None:
    await _run(NAV[message.text], message.answer, stats, twenty, config, options, usage,
               message.from_user.id)
