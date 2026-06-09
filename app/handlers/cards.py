"""🖼 Card button on /today → a branded PNG stats card (rendered off the event loop)."""
from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.types import (BufferedInputFile, CallbackQuery,
                           InlineKeyboardButton, InlineKeyboardMarkup)

from .. import card as card_render
from ..stats import StatsService

log = logging.getLogger(__name__)
router = Router()


def card_kb() -> InlineKeyboardMarkup:
    """Attached to the /today text reply — taps render the image card on demand."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🖼 Card", callback_data="today_card")]])


@router.callback_query(F.data == "today_card")
async def today_card(callback: CallbackQuery, stats: StatsService) -> None:
    await callback.answer("Rendering…")
    try:
        data = await stats.today_data()
        png = await asyncio.to_thread(card_render.render_today, data)  # Pillow is CPU-bound
        await callback.message.answer_photo(
            BufferedInputFile(png, filename="today.png"), caption="📊 Today · suslicketeam")
    except Exception:  # noqa: BLE001
        log.exception("card render failed")
        await callback.message.answer("⚠️ Couldn't render the card (the text /today still works).")
