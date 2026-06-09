"""Inline keyboards (per-message actions) + the persistent bottom nav (ReplyKeyboard)."""
from __future__ import annotations

from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, ReplyKeyboardMarkup)

# Bottom nav: label -> hub action. Tapping a reply button SENDS its label as text, so menu.py
# intercepts these exact labels (before capture's catch-all) and dispatches to the same render.
NAV = {
    "📅 Today": "today", "📊 Pipeline": "pipeline", "➡️ Convert": "convert",
    "💱 Currency": "currency", "🏷 Niches": "niches", "📈 Usage": "usage", "❔ Help": "help",
}


def main_kb() -> ReplyKeyboardMarkup:
    """Persistent bottom panel with the most-used actions (typing still adds a lead)."""
    rows = [["📅 Today", "📊 Pipeline"], ["➡️ Convert", "💱 Currency"],
            ["🏷 Niches", "📈 Usage"], ["❔ Help"]]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True, is_persistent=True,
        input_field_placeholder="Send a 2GIS link + facts to add a lead…",
    )


def confirm_kb(pending_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Create", callback_data=f"create:{pending_id}"),
        InlineKeyboardButton(text="✖️ Cancel", callback_data=f"cancel:{pending_id}"),
    ]])


def dup_kb(pending_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔄 Update", callback_data=f"update:{pending_id}"),
        InlineKeyboardButton(text="➕ Create new", callback_data=f"create:{pending_id}"),
        InlineKeyboardButton(text="✖️ Cancel", callback_data=f"cancel:{pending_id}"),
    ]])


def batch_kb(pending_id: str, n_new: int) -> InlineKeyboardMarkup:
    """Several leads parsed from one message → create all the new ones at once."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"✅ Create all ({n_new})", callback_data=f"createall:{pending_id}"),
        InlineKeyboardButton(text="✖️ Cancel", callback_data=f"cancel:{pending_id}"),
    ]])


def convert_kb(leads: list[dict]) -> InlineKeyboardMarkup:
    """One button per convertible lead → Company + Opportunity (callback conv:<leadId>)."""
    rows = [[InlineKeyboardButton(text=f"➡️ {l.get('name') or 'Unnamed'}",
                                  callback_data=f"conv:{l['id']}")] for l in leads]
    return InlineKeyboardMarkup(inline_keyboard=rows)
