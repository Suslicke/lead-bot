# Lead edit flow — design (2026-06-09)

## Goal

Make capturing a lead a *nice, forgiving* flow: after the draft is parsed (2GIS or LLM),
the operator can walk through it, **edit any field with buttons**, and only then send the
edited version to Twenty. Editing makes the flow tolerant of imperfect AI extraction —
fix a field and submit, instead of cancel + retype. Buttons only (no LLM re-edit).

Works for **both** the single-lead draft and the multi-lead batch.

## Interaction model

- **Per-field buttons + FSM.** The rich draft is shown already *with a field-edit keyboard*
  (`edit_kb`) — a button per editable field with its current value in the label
  (`Niche: барбершоп`), 1–2 per row, plus an action row.
- No separate "Edit mode": tapping a field edits it directly. "Walk through and fix" = tap
  the field.

### Field classes

1. **Free text** — `name, city, contact, prospectLink, addressText, nextStep, notes`:
   tap → FSM `EditLead.awaiting_value{ref, field}`, prompt "send new value (or /cancel)" →
   reply patches the payload → re-render. Empty reply clears optional fields.
2. **Numbers** — `reviewsCount` (int), `rating` (float, clamped 0–5): same, with numeric
   validation; bad input re-prompts without leaving the state.
3. **Enum buttons** (no text/FSM): `niche`/`source` → inline keyboard of **live options**
   from `OptionsRegistry`; `hasWebsite` → No/Weak/Yes; `language` (MULTI_SELECT) → RU/KK/EN
   toggle buttons with `✓` + Done.

After every edit: re-render the *same* draft message (`_preview` + `edit_kb`), labels show
new values. No new wall-of-text messages.

`required` fields (`name, niche, hasWebsite, source`) must be non-empty; Create is softly
blocked with a hint if one is empty.

## Batch navigation

Batch summary rows each get a `✏️ N` button (`eopen:<pid>:<idx>`) → opens that lead in the
same `edit_kb` with an extra **⬅️ Back to list**. Edits mutate `_batch[pid][idx]["payload"]`.
Back → re-render summary (updated names/niches). **Create all** unchanged.

### Unification — the `ref` address

`ref = pid` (single) or `ref = pid#idx` (batch item). One set of helpers
`get_payload(ref)` / `render(ref)` serves both — the editor doesn't know single vs batch,
it just patches by `ref` and re-renders. This collapses the single/batch split to one point:
the `ref` format + which action row to draw (Create vs Create-all vs ⬅️Back).

## Critical wiring

`capture` currently matches any non-`/` text. During a text edit, the reply is a *field
value*, not a new lead. So:
- edit text handler: `StateFilter(EditLead.awaiting_value)`
- `capture`: `StateFilter(None)` (only when no edit is in progress)

Register the **edit router before capture** in `handlers/__init__.py`.

## Files

- `app/draft.py` (new) — **pure logic**: `ref` parse, get/set payload, field patch with
  validation (int/float, rating clamp, enum check), `required` check. Extracted from handlers
  so it's unit-testable without Telegram.
- `app/handlers/edit.py` (new) — `EditLead` StatesGroup, callbacks (`ef/es/el/eopen/eback`),
  the `StateFilter(awaiting_value)` text handler.
- `app/keyboards.py` — `edit_kb(ref, mode)` (`mode` ∈ single_new/single_dup/batch_item),
  `enum_kb`, `lang_kb`; add `✏️ N` to `batch_kb`.
- `app/handlers/capture.py` — `capture` gets `StateFilter(None)`; draft uses `edit_kb`;
  store draft `msg_id`; render via the shared `render(ref)`.
- `app/handlers/__init__.py` — register `edit.router` before `capture.router`.
- `main.py` — Dispatcher already uses the default MemoryStorage (FSM-capable); no change
  expected.

## Edge cases

- Missing `pid` (bot restart / expiry) → "session expired, resend".
- `/cancel` while editing → clear state, back to draft.
- Edit text only caught in the FSM state; otherwise normal capture.
- Per-user FSM context + unique `pid` isolate concurrent edits.
- Stale button after Create → `callback.answer("already handled")`.

## Testing

- Unit tests on `app/draft.py` (patch/validation/required/ref parse) — pure, no aiogram.
  Introduce `tests/` (none today).
- `python -m compileall` + manual Telegram smoke (each field type, batch navigation).
- Commit gate: compile green.
