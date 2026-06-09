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
from ..keyboards import batch_kb, confirm_kb, dup_kb
from ..llm import Extractor, schema_with_options
from ..reference import OptionsRegistry
from ..twenty import TwentyClient, to_payload
from ..twogis import TwoGisClient, find_firms
from ..usage import UsageStore

log = logging.getLogger(__name__)
router = Router()

# in-memory drafts awaiting confirmation: pid -> {"payload": dict, "existing": id|None}
_pending: dict[str, dict] = {}
# in-memory batch drafts (several leads from one message): pid -> [{"payload", "existing"}]
_batch: dict[str, list[dict]] = {}

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


def _dedupe_within(payloads: list[dict]) -> list[dict]:
    """Drop repeats inside one message (same link, or same name) — keep first seen."""
    seen, out = set(), []
    for p in payloads:
        key = _norm(p.get("prospectLink")) or (p.get("name") or "").strip().lower()
        if key and key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


async def _present_drafts(note: Message, payloads: list[dict], twenty: TwentyClient) -> None:
    """Dedup against the CRM and present: one lead → rich draft; many → 'Create all'."""
    try:
        known = await twenty.all_leads()
    except Exception:  # noqa: BLE001 — dedup is best-effort; never block capture
        known = []
        log.exception("dedup fetch failed")

    if len(payloads) == 1:  # single lead → rich draft with Update/Create-new on a dup
        payload = payloads[0]
        existing = find_duplicate(known, payload)
        pid = uuid.uuid4().hex[:12]
        _pending[pid] = {"payload": payload, "existing": existing.get("id") if existing else None}
        if existing:
            head = (f"⚠️ Похоже, уже в CRM: <b>{existing.get('name')}</b> "
                    f"(stage: {existing.get('stage')})\n\n")
            kb = dup_kb(pid)
        else:
            head, kb = "", confirm_kb(pid)
        await note.edit_text(head + "Draft lead:\n\n" + _preview(payload), reply_markup=kb)
        return

    # several businesses → compact summary + "Create all" (dups skipped)
    entries = [{"payload": p, "existing": (e.get("id") if (e := find_duplicate(known, p)) else None)}
               for p in payloads]
    pid = uuid.uuid4().hex[:12]
    _batch[pid] = entries
    n_new = sum(1 for e in entries if not e["existing"])
    lines = [f"<b>{len(entries)} leads</b> parsed — {n_new} new, {len(entries) - n_new} already in CRM:", ""]
    for i, e in enumerate(entries, 1):
        p = e["payload"]
        lines.append(f"{i}. <b>{p['name']}</b> — {p['niche']}/{p['source']}"
                     + ("  ⚠️ dup" if e["existing"] else ""))
    await note.edit_text("\n".join(lines), reply_markup=batch_kb(pid, n_new))


@router.message(F.text & ~F.text.startswith("/"))
async def capture(message: Message, extractor: Extractor, twenty: TwentyClient,
                  options: OptionsRegistry, config: ConfigStore, usage: UsageStore,
                  twogis: TwoGisClient | None) -> None:
    nm, sm = options.value_map("niche"), options.value_map("source")

    # 2GIS link path (gated on TWOGIS_API_KEY): enrich each firm via the Catalog API, no LLM.
    firms = find_firms(message.text) if twogis else []
    if firms:
        note = await message.answer("⏳ 2GIS…")
        payloads = []
        for firm_id, link in firms:
            try:
                fields = await twogis.fetch(firm_id, link)
            except Exception:  # noqa: BLE001
                log.exception("2gis fetch failed (%s)", firm_id)
                fields = None
            if fields:
                payloads.append(to_payload(fields, nm, sm))
        payloads = _dedupe_within(payloads)
        if not payloads:
            await note.edit_text("⚠️ 2GIS lookup failed — send the facts as text instead.")
            return
        await _present_drafts(note, payloads, twenty)
        return

    # text → LLM path (token cap applies; one call may yield several leads)
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
        raw = result.fields
        # the model returns {"leads": [...]}; tolerate a flat single lead too (defensive)
        items = raw["leads"] if isinstance(raw.get("leads"), list) and raw["leads"] else [raw]
        payloads = _dedupe_within([to_payload(it, nm, sm) for it in items if isinstance(it, dict)])
    except Exception as e:  # noqa: BLE001
        log.exception("extract failed")
        await note.edit_text(f"⚠️ Couldn't parse that ({e}). Add the name + niche explicitly.")
        return
    if not payloads:
        await note.edit_text("⚠️ No business found in that. Add the name + niche.")
        return
    await _present_drafts(note, payloads, twenty)


@router.callback_query(F.data.startswith("cancel:"))
async def cancel(callback: CallbackQuery) -> None:
    pid = callback.data.split(":", 1)[1]
    _pending.pop(pid, None)
    _batch.pop(pid, None)
    await callback.message.edit_text("✖️ Cancelled.")
    await callback.answer()


@router.callback_query(F.data.startswith("createall:"))
async def create_all(callback: CallbackQuery, twenty: TwentyClient) -> None:
    entries = _batch.pop(callback.data.split(":", 1)[1], None)
    if not entries:
        await callback.message.edit_text("⌛ Session expired — please resend the leads.")
        await callback.answer()
        return
    created, skipped, failed, names = 0, 0, 0, []
    for e in entries:
        if e["existing"]:  # dups are skipped in batch (single-lead flow handles update)
            skipped += 1
            continue
        try:
            await twenty.create_lead(e["payload"])
            created += 1
            names.append(e["payload"]["name"])
        except Exception:  # noqa: BLE001
            log.exception("batch create failed")
            failed += 1
    summary = [f"✅ Created <b>{created}</b>"]
    if skipped:
        summary.append(f"skipped {skipped} dup")
    if failed:
        summary.append(f"⚠️ {failed} failed")
    text = " · ".join(summary)
    if names:
        text += "\n" + "\n".join(f"• {n}" for n in names[:15])
    await callback.message.edit_text(text)
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
