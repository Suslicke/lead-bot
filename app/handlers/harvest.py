"""/harvest — find leads in bulk from OpenStreetMap (self-hosted Overpass).

Pick a niche → send a city/district → Overpass returns matching businesses, which flow
through the SAME draft → dedup → confirm path as a captured batch (capture._present_drafts):
a 'Create all' summary, per-lead ✏️ editing, dups skipped. OSM has no reviews/rating —
those stay empty and are filled later from 2GIS. Gated on OVERPASS_URL (the /harvest
command is only listed when it's set; see main).
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from ..keyboards import harvest_niche_kb
from ..osm import OverpassClient
from ..osm_tags import harvestable_niches
from ..reference import OptionsRegistry
from ..twenty import TwentyClient, to_payload
from .capture import _dedupe_within, _present_drafts

log = logging.getLogger(__name__)
router = Router()

HARVEST_LIMIT = 50  # hard cap per run — keeps the pipeline and Overpass sane


class Harvest(StatesGroup):
    city = State()


def _niche_choices(options: OptionsRegistry) -> list[str]:
    """Live niches we also know how to map to OSM tags (fall back to all mappable)."""
    live = set(options.labels("niche"))
    return [n for n in harvestable_niches() if n in live] or harvestable_niches()


HARVEST_BTN = "🌍 Harvest"  # bottom-panel button (keyboards.main_kb) → same as /harvest


async def _open(message: Message, overpass: OverpassClient | None,
                options: OptionsRegistry, state: FSMContext) -> None:
    if overpass is None:
        await message.answer("🌍 OSM harvest is off (OVERPASS_URL not set).")
        return
    await state.clear()
    await message.answer(
        "🌍 <b>Harvest leads from OpenStreetMap</b>\nPick a niche:",
        reply_markup=harvest_niche_kb(_niche_choices(options)),
    )


@router.message(Command("harvest"))
async def harvest_command(message: Message, overpass: OverpassClient | None,
                          options: OptionsRegistry, state: FSMContext) -> None:
    await _open(message, overpass, options, state)


# Bottom-panel tap arrives as plain text; this router runs before capture's catch-all,
# and the button label isn't in menu.NAV, so menu doesn't intercept it.
@router.message(F.text == HARVEST_BTN)
async def harvest_button(message: Message, overpass: OverpassClient | None,
                         options: OptionsRegistry, state: FSMContext) -> None:
    await _open(message, overpass, options, state)


@router.callback_query(F.data == "hvcancel")
async def harvest_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("✖️ Cancelled.")
    await callback.answer()


@router.callback_query(F.data.startswith("hvn:"))
async def harvest_pick_niche(callback: CallbackQuery, state: FSMContext) -> None:
    niche = callback.data.split(":", 1)[1]
    await state.set_state(Harvest.city)
    await state.update_data(niche=niche)
    await callback.message.edit_text(
        f"🌍 Niche: <b>{niche}</b>\nSend a city or district "
        f"(e.g. <code>Алматы</code>), or /cancel."
    )
    await callback.answer()


# /cancel must beat the catch-all below (both gated on the city state)
@router.message(StateFilter(Harvest.city), Command("cancel"))
async def harvest_cancel_city(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("✖️ Cancelled.")


@router.message(StateFilter(Harvest.city), F.text & ~F.text.startswith("/"))
async def harvest_run(message: Message, state: FSMContext, overpass: OverpassClient,
                      options: OptionsRegistry, twenty: TwentyClient) -> None:
    data = await state.get_data()
    await state.clear()
    niche, area = (data.get("niche") or ""), message.text.strip()
    note = await message.answer(f"⏳ Overpass: {niche} in {area}…")
    try:
        places = await overpass.harvest(niche, area, HARVEST_LIMIT)
    except Exception as e:  # noqa: BLE001
        log.exception("overpass harvest failed")
        await note.edit_text(f"⚠️ Overpass unavailable ({e}). Try again later.")
        return
    if not places:
        await note.edit_text(
            f"🤷 Nothing found for <b>{niche}</b> in <b>{area}</b>. "
            f"Check the city name — OSM uses the local name (e.g. Алматы)."
        )
        return
    nm, sm = options.value_map("niche"), options.value_map("source")
    payloads = _dedupe_within([to_payload(p.to_fields(niche), nm, sm) for p in places])
    await _present_drafts(note, payloads, twenty)
