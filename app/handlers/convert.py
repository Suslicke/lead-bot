"""/convert — promote a replied/qualified Lead into the relational layer.

A cold Lead is a prospect; once it engages you work it as a real deal. /convert turns a Lead
into **Company** (the account, deduped by 2GIS link) + **Opportunity** (the deal, starts at
QUALIFIED), links the Lead to the Company, and leaves the pipeline work to Opportunities.
Plus /currency to set the default deal currency.
"""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from ..config import ConfigStore, Settings
from ..keyboards import convert_kb
from ..twenty import (CURRENCIES, STAGE_ORDER, TwentyClient,
                      find_company, to_company_payload, to_opportunity_payload)

log = logging.getLogger(__name__)
router = Router()

# Leads ready to become deals (engaged but not yet closed / already converted).
_CONVERTIBLE = ("REPLIED", "QUALIFIED", "PROPOSAL")


def _lead_company_id(lead: dict) -> str | None:
    """The linked Company id, tolerating either the FK (companyId) or a nested object."""
    return lead.get("companyId") or (lead.get("company") or {}).get("id")


def convertible(leads: list[dict]) -> list[dict]:
    """Leads ready to become deals: engaged stage, not already linked to a company."""
    return [l for l in leads if l.get("stage") in _CONVERTIBLE and not _lead_company_id(l)]


@router.message(Command("convert"))
async def convert_list(message: Message, twenty: TwentyClient) -> None:
    try:
        leads = await twenty.all_leads()
    except Exception as e:  # noqa: BLE001
        await message.answer(f"⚠️ Couldn't load leads: {e}")
        return
    ready = convertible(leads)
    if not ready:
        await message.answer("No leads ready to convert (need stage Replied / Qualified / "
                             "Proposal and not yet linked to a company).")
        return
    await message.answer(
        "Pick a lead to convert into <b>Company + Opportunity</b>:",
        reply_markup=convert_kb(ready[:20]),
    )


@router.callback_query(F.data.startswith("conv:"))
async def convert_one(callback: CallbackQuery, twenty: TwentyClient,
                      settings: Settings, config: ConfigStore) -> None:
    lead_id = callback.data.split(":", 1)[1]
    base = settings.twenty_public_url
    try:
        lead = await twenty.get_lead(lead_id)
        if not lead:
            await callback.message.edit_text("⌛ Lead not found — it may have been deleted.")
            await callback.answer()
            return
        if _lead_company_id(lead):  # already converted — don't duplicate
            await callback.message.edit_text(
                f"ℹ️ <b>{lead.get('name')}</b> is already linked to a company.")
            await callback.answer()
            return

        # 1) Company — reuse an existing account (dedup by 2GIS link / name) or create one.
        companies = await twenty.all_companies()
        existing = find_company(companies, lead.get("prospectLink"), lead.get("name"))
        if existing:
            company_id, reused = existing["id"], True
        else:
            company_id, reused = await twenty.create_company(to_company_payload(lead)), False

        # 2) Opportunity — a new deal on that account, in the configured currency.
        opp_payload = to_opportunity_payload(lead, company_id, config.deal_currency)
        opp_id = await twenty.create_opportunity(opp_payload)

        # 3) Link the Lead to the Company and nudge its stage forward (never backward).
        patch = {"companyId": company_id}
        if STAGE_ORDER.index(lead.get("stage", "REPLIED")) < STAGE_ORDER.index("QUALIFIED"):
            patch["stage"] = "QUALIFIED"
        await twenty.update_lead(lead_id, patch)
    except Exception as e:  # noqa: BLE001
        log.exception("convert failed")
        await callback.message.edit_text(f"⚠️ Convert failed: {e}")
        await callback.answer()
        return

    company_line = ("🏢 Company (existing): " if reused else "🏢 Company: ") + \
        f"{base}/object/company/{company_id}"
    await callback.message.edit_text(
        f"✅ Converted <b>{lead.get('name')}</b>\n"
        f"{company_line}\n"
        f"💼 Opportunity: {base}/object/opportunity/{opp_id}",
        disable_web_page_preview=True,
    )
    await callback.answer("Converted ✓")


@router.message(Command("currency"))
async def currency(message: Message, command: CommandObject, config: ConfigStore) -> None:
    arg = (command.args or "").strip()
    if not arg:
        await message.answer(
            f"Default deal currency: <b>{config.deal_currency}</b>\n"
            f"Change: <code>/currency USD</code> · options: {', '.join(CURRENCIES)}")
        return
    try:
        config.set_deal_currency(arg)
        await message.answer(f"✅ Default deal currency → <b>{config.deal_currency}</b>")
    except ValueError as e:
        await message.answer(f"⚠️ {e}")
