"""Capture flow: free text → Haiku/Llama draft → dedup check → confirm → Twenty.

On a duplicate (same prospectLink, or exact name) the draft offers Update / Create new.
Update refreshes the *facts* (niche, website, reviews, rating, contact, address) but keeps
the pipeline state (stage, next step) — a re-scan must not undo your work.
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from ..config import ConfigStore, Settings
from ..keyboards import confirm_kb, dup_kb
from ..llm import Extractor, schema_with_options
from ..reference import OptionsRegistry
from ..twenty import TwentyClient, to_payload
from ..usage import UsageStore

log = logging.getLogger(__name__)
router = Router()

# in-memory drafts awaiting confirmation: pid -> {"payload": dict, "existing": id|None}
_pending: dict[str, dict] = {}

# fields a re-scan may refresh on an existing lead (facts, not pipeline state)
_REFRESHABLE = ("niche", "hasWebsite", "city", "contact", "prospectLink",
                "addressText", "reviewsCount", "rating", "language")


def _preview(p: dict) -> str:
    return (
        f"<b>{p['name']}</b>\n"
        f"Niche: {p['niche']}   City: {p['city']}   Lang: {', '.join(p.get('language') or ['—'])}\n"
        f"Has website: {p['hasWebsite']}   Source: {p['source']}\n"
        f"Reviews: {p.get('reviewsCount', '—')}   Rating: {p.get('rating', '—')}\n"
        f"Address: {p.get('addressText', '—')}\n"
        f"Contact: {p.get('contact', '—')}\n"
        f"Link: {p.get('prospectLink', '—')}\n"
        f"Next step: {p.get('nextStep', '—')}\n"
        f"Notes: {p.get('notes', '—')}"
    )


def _norm(url: str | None) -> str:
    return (url or "").strip().rstrip("/").lower()


def find_duplicate(leads: list[dict], payload: dict) -> dict | None:
    """Match by prospectLink (the natural key), then by exact name as a fallback."""
    link = _norm(payload.get("prospectLink"))
    if link:
        for l in leads:
            if _norm(l.get("prospectLink")) == link:
                return l
    name = (payload.get("name") or "").strip().lower()
    if name:
        for l in leads:
            if (l.get("name") or "").strip().lower() == name:
                return l
    return None


@router.message(F.text & ~F.text.startswith("/"))
async def capture(message: Message, extractor: Extractor, twenty: TwentyClient,
                  options: OptionsRegistry, config: ConfigStore, usage: UsageStore) -> None:
    uid = message.from_user.id
    over = usage.over_limit(uid, config.llm_max_requests, config.llm_max_tokens)
    if over:  # hard stop before spending another LLM call
        await message.answer(
            f"🚫 Daily LLM limit reached ({over}). Resets at local midnight.\n"
            "See /usage · raise with /llm set req &lt;n&gt; or /llm set tok &lt;n&gt;."
        )
        return
    note = await message.answer("⏳ Reading…")
    try:
        schema = schema_with_options(options.labels("niche"), options.labels("source"))
        result = await asyncio.to_thread(extractor.extract, message.text, schema)
        usage.record(uid, result.usage.prompt_tokens, result.usage.completion_tokens)
        payload = to_payload(result.fields, options.value_map("niche"), options.value_map("source"))
    except Exception as e:  # noqa: BLE001
        log.exception("extract failed")
        await note.edit_text(f"⚠️ Couldn't parse that ({e}). Add the name + niche explicitly.")
        return

    existing = None
    try:
        existing = find_duplicate(await twenty.all_leads(), payload)
    except Exception:  # noqa: BLE001 — dedup is best-effort; never block capture
        log.exception("dedup check failed")

    pid = uuid.uuid4().hex[:12]
    _pending[pid] = {"payload": payload, "existing": existing.get("id") if existing else None}

    if existing:
        head = (f"⚠️ Похоже, уже в CRM: <b>{existing.get('name')}</b> "
                f"(stage: {existing.get('stage')})\n\n")
        kb = dup_kb(pid)
    else:
        head, kb = "", confirm_kb(pid)
    await note.edit_text(head + "Draft lead:\n\n" + _preview(payload), reply_markup=kb)


@router.callback_query(F.data.startswith("cancel:"))
async def cancel(callback: CallbackQuery) -> None:
    _pending.pop(callback.data.split(":", 1)[1], None)
    await callback.message.edit_text("✖️ Cancelled.")
    await callback.answer()


@router.callback_query(F.data.startswith("create:"))
async def create(callback: CallbackQuery, twenty: TwentyClient, settings: Settings) -> None:
    entry = _pending.pop(callback.data.split(":", 1)[1], None)
    if not entry:
        await callback.message.edit_text("⌛ Session expired — please resend the lead.")
        await callback.answer()
        return
    try:
        lead_id = await twenty.create_lead(entry["payload"])
        await callback.message.edit_text(
            f"✅ Created: <b>{entry['payload']['name']}</b>\n{settings.twenty_public_url}/object/lead/{lead_id}"
        )
    except Exception as e:  # noqa: BLE001
        log.exception("create failed")
        await callback.message.edit_text(f"⚠️ Failed to create: {e}")
    await callback.answer()


@router.callback_query(F.data.startswith("update:"))
async def update(callback: CallbackQuery, twenty: TwentyClient, settings: Settings) -> None:
    entry = _pending.pop(callback.data.split(":", 1)[1], None)
    if not entry or not entry.get("existing"):
        await callback.message.edit_text("⌛ Session expired — please resend the lead.")
        await callback.answer()
        return
    payload = entry["payload"]
    patch = {k: payload[k] for k in _REFRESHABLE if k in payload}
    try:
        await twenty.update_lead(entry["existing"], patch)
        await callback.message.edit_text(
            f"🔄 Updated: <b>{payload['name']}</b> (stage kept)\n"
            f"{settings.twenty_public_url}/object/lead/{entry['existing']}"
        )
    except Exception as e:  # noqa: BLE001
        log.exception("update failed")
        await callback.message.edit_text(f"⚠️ Failed to update: {e}")
    await callback.answer()
