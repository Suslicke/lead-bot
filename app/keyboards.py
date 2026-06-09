"""Inline keyboards (per-message actions) + the persistent bottom nav (ReplyKeyboard)."""
from __future__ import annotations

from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup,
                           KeyboardButton, ReplyKeyboardMarkup)

from .draft import EDITABLE, action_mode, button_label, parse_ref
from .twenty import LANGUAGES

# Bottom nav: label -> hub action. Tapping a reply button SENDS its label as text, so menu.py
# intercepts these exact labels (before capture's catch-all) and dispatches to the same render.
NAV = {
    "📅 Today": "today", "📊 Pipeline": "pipeline", "➡️ Convert": "convert",
    "💱 Currency": "currency", "🏷 Niches": "niches", "📈 Usage": "usage", "❔ Help": "help",
}


def main_kb() -> ReplyKeyboardMarkup:
    """Persistent bottom panel with the most-used actions (typing still adds a lead)."""
    rows = [["📅 Today", "📊 Pipeline"], ["➡️ Convert", "💱 Currency"],
            ["🏷 Niches", "📈 Usage"], ["🌍 Harvest", "❔ Help"]]
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


def batch_kb(pending_id: str, entries: list[dict]) -> InlineKeyboardMarkup:
    """Several leads from one message: a ✏️ button per lead (open its editor) + Create all."""
    n_new = sum(1 for e in entries if not e["existing"])
    rows = []
    pair = []
    for i, e in enumerate(entries):
        name = e["payload"].get("name") or f"Lead {i + 1}"
        tag = " ⚠️" if e["existing"] else ""
        pair.append(InlineKeyboardButton(text=f"✏️ {i + 1}. {name}{tag}",
                                         callback_data=f"eopen:{pending_id}:{i}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([
        InlineKeyboardButton(text=f"✅ Create all ({n_new})", callback_data=f"createall:{pending_id}"),
        InlineKeyboardButton(text="✖️ Cancel", callback_data=f"cancel:{pending_id}"),
    ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def edit_kb(ref: str, payload: dict) -> InlineKeyboardMarkup:
    """The rich draft editor: a button per field (showing its value) + an action row.

    Action row depends on the draft kind (single new / single duplicate / batch item).
    """
    rows, pair = [], []
    for field in EDITABLE:
        pair.append(InlineKeyboardButton(text=button_label(payload, field),
                                         callback_data=f"ef:{ref}:{field}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)

    pid, _ = parse_ref(ref)
    mode = action_mode(ref)
    if mode == "batch_item":
        rows.append([InlineKeyboardButton(text="⬅️ Back to list", callback_data=f"eback:{pid}")])
    elif mode == "single_dup":
        rows.append([
            InlineKeyboardButton(text="🔄 Update", callback_data=f"update:{pid}"),
            InlineKeyboardButton(text="➕ Create new", callback_data=f"create:{pid}"),
            InlineKeyboardButton(text="✖️ Cancel", callback_data=f"cancel:{pid}"),
        ])
    else:  # single_new
        rows.append([
            InlineKeyboardButton(text="✅ Create", callback_data=f"create:{pid}"),
            InlineKeyboardButton(text="✖️ Cancel", callback_data=f"cancel:{pid}"),
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def enum_kb(ref: str, field: str, labels: list[str]) -> InlineKeyboardMarkup:
    """Pick-one keyboard for a select field; options carried by index (es:ref:field:i)."""
    rows, pair = [], []
    for i, label in enumerate(labels):
        pair.append(InlineKeyboardButton(text=label, callback_data=f"es:{ref}:{field}:{i}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton(text="⬅️ Back", callback_data=f"ed:{ref}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def lang_kb(ref: str, payload: dict) -> InlineKeyboardMarkup:
    """Multi-select language toggles (✓ = selected) + Done (back to editor)."""
    selected = set(payload.get("language") or [])
    row = [InlineKeyboardButton(text=("✓ " if code in selected else "") + code,
                                callback_data=f"el:{ref}:{code}") for code in LANGUAGES]
    return InlineKeyboardMarkup(inline_keyboard=[
        row,
        [InlineKeyboardButton(text="✅ Done", callback_data=f"ed:{ref}")],
    ])


def harvest_niche_kb(labels: list[str]) -> InlineKeyboardMarkup:
    """Pick a niche to harvest from OSM (callback hvn:<label>) + Cancel."""
    rows, pair = [], []
    for label in labels:
        pair.append(InlineKeyboardButton(text=label, callback_data=f"hvn:{label}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton(text="✖️ Cancel", callback_data="hvcancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def convert_kb(leads: list[dict]) -> InlineKeyboardMarkup:
    """One button per convertible lead → Company + Opportunity (callback conv:<leadId>)."""
    rows = [[InlineKeyboardButton(text=f"➡️ {l.get('name') or 'Unnamed'}",
                                  callback_data=f"conv:{l['id']}")] for l in leads]
    return InlineKeyboardMarkup(inline_keyboard=rows)
