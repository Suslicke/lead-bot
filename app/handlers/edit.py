"""Interactive draft editor: tap a field → edit it → re-render, then Create.

Works for a single draft (ref="pid") and a batch item (ref="pid#idx") via the
ref-addressed helpers in `app/draft.py`. Free-text/number fields use an FSM text
prompt; selects/language use inline pickers (no typing).

Wiring note: the text handler is gated on `EditLead.awaiting_value`, and `capture`
is gated on `StateFilter(None)` — so a reply that is a *field value* is never mistaken
for a new lead. This router is registered BEFORE capture.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from .. import draft
from ..keyboards import batch_kb, edit_kb, enum_kb, lang_kb
from ..reference import OptionsRegistry
from ..twenty import HAS_WEBSITE

log = logging.getLogger(__name__)
router = Router()

_EXPIRED = "⌛ Session expired — please resend the lead."


class EditLead(StatesGroup):
    awaiting_value = State()


def _enum_choices(field: str, options: OptionsRegistry) -> tuple[list[str], dict[str, str]]:
    """(labels, label→VALUE) for a select field. hasWebsite is fixed; niche/source are live."""
    if field == "hasWebsite":
        return list(HAS_WEBSITE), HAS_WEBSITE
    return options.labels(field), options.value_map(field)


async def _show_editor(bot, chat_id: int, ref: str) -> None:
    """(Re)render the draft message as the field editor."""
    payload = draft.get_payload(ref)
    msg_id = draft.msg_id_of(ref)
    if payload is None or msg_id is None:
        return
    head = ""
    pid, idx = draft.parse_ref(ref)
    if idx is None:
        entry = draft.PENDING.get(pid)
        if entry and entry.get("dup"):
            head = f"⚠️ Already in CRM: {entry['dup']}\n\n"
    await bot.edit_message_text(
        chat_id=chat_id, message_id=msg_id,
        text=head + "Draft lead:\n\n" + draft.preview(payload),
        reply_markup=edit_kb(ref, payload),
    )


# --- open a field ------------------------------------------------------------
@router.callback_query(F.data.startswith("ef:"))
async def open_field(callback: CallbackQuery, state: FSMContext, options: OptionsRegistry) -> None:
    _, ref, field = callback.data.split(":", 2)
    payload = draft.get_payload(ref)
    if payload is None:
        await callback.message.edit_text(_EXPIRED)
        await callback.answer()
        return

    if field in draft.SELECT:
        labels, _ = _enum_choices(field, options)
        await callback.message.edit_reply_markup(reply_markup=enum_kb(ref, field, labels))
    elif field in draft.MULTI:
        await callback.message.edit_reply_markup(reply_markup=lang_kb(ref, payload))
    else:  # free text / number → ask for a typed value
        await state.set_state(EditLead.awaiting_value)
        await state.update_data(ref=ref, field=field)
        hint = " (a number)" if field in draft.NUMERIC else ""
        await callback.message.edit_text(
            f"✏️ Send the new value for <b>{draft.LABEL[field]}</b>{hint}, "
            f"or /cancel to keep it."
        )
    await callback.answer()


# --- set a select value ------------------------------------------------------
@router.callback_query(F.data.startswith("es:"))
async def set_enum(callback: CallbackQuery, options: OptionsRegistry) -> None:
    _, ref, field, i = callback.data.split(":", 3)
    payload = draft.get_payload(ref)
    if payload is None:
        await callback.message.edit_text(_EXPIRED)
        await callback.answer()
        return
    labels, vmap = _enum_choices(field, options)
    try:
        draft.set_select(payload, field, vmap[labels[int(i)]])
    except (IndexError, KeyError, ValueError):
        log.warning("stale enum pick %s", callback.data)
    await _show_editor(callback.bot, callback.message.chat.id, ref)
    await callback.answer()


# --- toggle a language -------------------------------------------------------
@router.callback_query(F.data.startswith("el:"))
async def toggle_lang(callback: CallbackQuery) -> None:
    _, ref, code = callback.data.split(":", 2)
    payload = draft.get_payload(ref)
    if payload is None:
        await callback.message.edit_text(_EXPIRED)
        await callback.answer()
        return
    draft.toggle_language(payload, code)
    await callback.message.edit_reply_markup(reply_markup=lang_kb(ref, payload))
    await callback.answer()


# --- back to the editor (from a picker) --------------------------------------
@router.callback_query(F.data.startswith("ed:"))
async def back_to_editor(callback: CallbackQuery) -> None:
    ref = callback.data.split(":", 1)[1]
    await _show_editor(callback.bot, callback.message.chat.id, ref)
    await callback.answer()


# --- batch: open an item / back to the list ----------------------------------
@router.callback_query(F.data.startswith("eopen:"))
async def open_item(callback: CallbackQuery) -> None:
    _, pid, idx = callback.data.split(":", 2)
    ref = draft.make_ref(pid, int(idx))
    if draft.get_payload(ref) is None:
        await callback.message.edit_text(_EXPIRED)
        await callback.answer()
        return
    await _show_editor(callback.bot, callback.message.chat.id, ref)
    await callback.answer()


@router.callback_query(F.data.startswith("eback:"))
async def back_to_list(callback: CallbackQuery) -> None:
    pid = callback.data.split(":", 1)[1]
    batch = draft.BATCH.get(pid)
    if not batch:
        await callback.message.edit_text(_EXPIRED)
        await callback.answer()
        return
    await callback.message.edit_text(draft.batch_summary(batch["items"]),
                                     reply_markup=batch_kb(pid, batch["items"]))
    await callback.answer()


# --- /cancel an in-progress field edit (registered BEFORE the text catch-all) --
@router.message(StateFilter(EditLead.awaiting_value), Command("cancel"))
async def cancel_edit(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    ref = data.get("ref")
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass
    if ref:
        await _show_editor(message.bot, message.chat.id, ref)


# --- the typed value (free text / number; "/" commands excluded) -------------
@router.message(StateFilter(EditLead.awaiting_value), F.text & ~F.text.startswith("/"))
async def receive_value(message: Message, state: FSMContext) -> None:
    from ..keyboards import NAV  # avoid editing a field with a nav-button tap

    if message.text in NAV:
        await message.reply("⌛ Finish the field (or /cancel) first.")
        return

    data = await state.get_data()
    ref, field = data.get("ref"), data.get("field")
    payload = draft.get_payload(ref) if ref else None
    if payload is None:
        await state.clear()
        await message.answer(_EXPIRED)
        return
    try:
        draft.set_text(payload, field, message.text)
    except ValueError:  # bad number → stay in the state and re-prompt
        await message.reply(f"⚠️ <b>{draft.LABEL[field]}</b> must be a number — try again, or /cancel.")
        return

    await state.clear()
    try:  # keep the chat anchored on the one draft message
        await message.delete()
    except Exception:  # noqa: BLE001
        pass
    await _show_editor(message.bot, message.chat.id, ref)
