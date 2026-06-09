"""Inline keyboards."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


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
