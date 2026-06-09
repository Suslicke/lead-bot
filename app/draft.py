"""In-memory draft store + pure edit logic for the capture → edit → confirm flow.

A *draft* is a Twenty /rest/leads payload (VALUE-form selects, e.g. niche="CAFE",
language=["RU"]) awaiting confirmation. Single drafts live in `PENDING[pid]`; a batch
(several leads from one message) in `BATCH[pid]`.

The editor is **ref-addressed** so it doesn't care single-vs-batch:
  ref = "pid"        → single draft   (PENDING[pid])
  ref = "pid#<idx>"  → batch item     (BATCH[pid]["items"][idx])

Everything here is pure/aiogram-free so it can be unit-tested without Telegram.
"""
from __future__ import annotations

# pid -> {"payload": dict, "existing": id|None, "dup": str|None, "msg_id": int|None}
PENDING: dict[str, dict] = {}
# pid -> {"items": [{"payload": dict, "existing": id|None}, ...], "msg_id": int|None}
BATCH: dict[str, dict] = {}

# Order shown in the edit keyboard (stage is intentionally NOT editable here).
EDITABLE = ("name", "niche", "source", "city", "hasWebsite", "language",
            "contact", "prospectLink", "addressText", "reviewsCount", "rating",
            "nextStep", "notes")
REQUIRED = ("name", "niche", "hasWebsite", "source")

FREE_TEXT = ("name", "city", "contact", "prospectLink", "addressText", "nextStep", "notes")
NUMERIC = {"reviewsCount": "int", "rating": "float"}
SELECT = ("niche", "source", "hasWebsite")  # single-select enums
MULTI = ("language",)

LABEL = {
    "name": "Name", "niche": "Niche", "source": "Source", "city": "City",
    "hasWebsite": "Website", "language": "Lang", "contact": "Contact",
    "prospectLink": "Link", "addressText": "Address", "reviewsCount": "Reviews",
    "rating": "Rating", "nextStep": "Next step", "notes": "Notes",
}


# --- ref addressing ----------------------------------------------------------
def make_ref(pid: str, idx: int | None = None) -> str:
    return f"{pid}#{idx}" if idx is not None else pid


def parse_ref(ref: str) -> tuple[str, int | None]:
    if "#" in ref:
        pid, idx = ref.split("#", 1)
        return pid, int(idx)
    return ref, None


def get_entry(ref: str) -> dict | None:
    """The {'payload', 'existing'} entry for a ref, or None if the draft is gone."""
    pid, idx = parse_ref(ref)
    if idx is None:
        return PENDING.get(pid)
    batch = BATCH.get(pid)
    if not batch:
        return None
    items = batch["items"]
    return items[idx] if 0 <= idx < len(items) else None


def get_payload(ref: str) -> dict | None:
    entry = get_entry(ref)
    return entry["payload"] if entry else None


def msg_id_of(ref: str) -> int | None:
    """Telegram message id of the draft (single) / batch message — for re-rendering."""
    pid, idx = parse_ref(ref)
    holder = PENDING.get(pid) if idx is None else BATCH.get(pid)
    return holder.get("msg_id") if holder else None


def action_mode(ref: str) -> str:
    """Which action row the editor draws: single_new | single_dup | batch_item."""
    pid, idx = parse_ref(ref)
    if idx is not None:
        return "batch_item"
    entry = PENDING.get(pid)
    return "single_dup" if (entry and entry.get("existing")) else "single_new"


# --- field patching (validated) ----------------------------------------------
def set_text(payload: dict, field: str, raw: str) -> None:
    """Patch a free-text or numeric field from raw user input.

    Raises ValueError("number") if a numeric field gets non-numeric input (caller
    re-prompts). Empty input clears an optional field; required text fields keep
    their value (empty is rejected by required_missing at Create time anyway).
    """
    raw = (raw or "").strip()
    if field in NUMERIC:
        if raw == "":
            payload.pop(field, None)
            return
        try:
            value: float | int = (
                int(raw) if NUMERIC[field] == "int" else float(raw.replace(",", "."))
            )
        except ValueError:
            raise ValueError("number") from None
        if field == "rating":
            value = max(0.0, min(5.0, float(value)))
        elif field == "reviewsCount":
            value = max(0, int(value))
        payload[field] = value
        return
    # free text
    if raw == "":
        if field not in REQUIRED:
            payload.pop(field, None)  # optional → clear
        # required → ignore an empty value, keep the current one
    else:
        payload[field] = raw


def set_select(payload: dict, field: str, value: str) -> None:
    payload[field] = value


def toggle_language(payload: dict, value: str) -> None:
    langs = list(payload.get("language") or [])
    payload["language"] = [x for x in langs if x != value] if value in langs else [*langs, value]


def required_missing(payload: dict) -> list[str]:
    """Required fields that are empty (or name left as the placeholder)."""
    missing = [f for f in REQUIRED if not payload.get(f)]
    if payload.get("name") == "Unnamed lead":
        missing.append("name")
    return missing


# --- rendering helpers (pure strings) ----------------------------------------
def _fmt(payload: dict, field: str) -> str:
    val = payload.get(field)
    if field in MULTI:
        return ", ".join(val) if val else "—"
    return "—" if val in (None, "") else str(val)


def preview(p: dict) -> str:
    return (
        f"<b>{p.get('name', '—')}</b>\n"
        f"Niche: {_fmt(p, 'niche')}   City: {_fmt(p, 'city')}   Lang: {_fmt(p, 'language')}\n"
        f"Has website: {_fmt(p, 'hasWebsite')}   Source: {_fmt(p, 'source')}\n"
        f"Reviews: {_fmt(p, 'reviewsCount')}   Rating: {_fmt(p, 'rating')}\n"
        f"Address: {_fmt(p, 'addressText')}\n"
        f"Contact: {_fmt(p, 'contact')}\n"
        f"Link: {_fmt(p, 'prospectLink')}\n"
        f"Next step: {_fmt(p, 'nextStep')}\n"
        f"Notes: {_fmt(p, 'notes')}"
    )


def button_label(payload: dict, field: str, width: int = 16) -> str:
    """'Niche: барбершоп' for a field button, value truncated to keep the row compact."""
    val = _fmt(payload, field)
    if len(val) > width:
        val = val[: width - 1] + "…"
    return f"{LABEL[field]}: {val}"


def batch_summary(entries: list[dict]) -> str:
    n_new = sum(1 for e in entries if not e["existing"])
    lines = [f"<b>{len(entries)} leads</b> parsed — {n_new} new, "
             f"{len(entries) - n_new} already in CRM:", ""]
    for i, e in enumerate(entries, 1):
        p = e["payload"]
        lines.append(f"{i}. <b>{p.get('name')}</b> — {_fmt(p, 'niche')}/{_fmt(p, 'source')}"
                     + ("  ⚠️ dup" if e["existing"] else ""))
    return "\n".join(lines)
