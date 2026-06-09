"""/members — manage who may use the bot (runtime allowlist).

The env `ALLOWED_TELEGRAM_IDS` are **admins**; an admin can add/remove extra **members**
(persisted in config.json, read live by the Whitelist filter). Members may use the bot but
not manage the allowlist (no privilege escalation). The new user finds their id via @userinfobot.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..config import ConfigStore, Settings

router = Router()


def _is_admin(uid: int, settings: Settings) -> bool:
    # open mode (no env ids) → no admin gate to enforce
    return not settings.allowed_ids or uid in settings.allowed_ids


def _render(settings: Settings, config: ConfigStore) -> str:
    admins = ", ".join(f"<code>{i}</code>" for i in sorted(settings.allowed_ids)) or "— (open mode)"
    members = ", ".join(f"<code>{i}</code>" for i in config.members) or "—"
    return ("<b>Allowed users</b>\n\n"
            f"Admins (env): {admins}\n"
            f"Members: {members}\n\n"
            "Add: <code>/members add 123456789</code> · "
            "Remove: <code>/members remove 123456789</code>\n"
            "<i>The new user gets their id from @userinfobot.</i>")


@router.message(Command("members"))
async def members(message: Message, command: CommandObject,
                  settings: Settings, config: ConfigStore) -> None:
    args = (command.args or "").split()
    if not args:
        await message.answer(_render(settings, config))
        return

    action, rest = args[0].lower(), args[1:]
    if action not in ("add", "remove", "rm", "del"):
        await message.answer("Usage: <code>/members</code> · <code>/members add &lt;id&gt;</code> · "
                             "<code>/members remove &lt;id&gt;</code>")
        return
    if not _is_admin(message.from_user.id, settings):
        await message.answer("🚫 Only admins (in ALLOWED_TELEGRAM_IDS) can manage members.")
        return

    ids = []
    for tok in rest:
        try:
            ids.append(int(tok))
        except ValueError:
            await message.answer(f"⚠️ <code>{tok}</code> is not a numeric Telegram id.")
            return
    if not ids:
        await message.answer("Give at least one numeric id, e.g. <code>/members add 123456789</code>.")
        return

    lines = []
    for i in ids:
        if action == "add":
            if i in settings.allowed_ids:
                lines.append(f"<code>{i}</code> is already an admin")
            elif config.add_member(i):
                lines.append(f"➕ <code>{i}</code> added")
            else:
                lines.append(f"<code>{i}</code> already a member")
        else:  # remove / rm / del
            if i in settings.allowed_ids:
                lines.append(f"<code>{i}</code> is an env admin — remove it from ALLOWED_TELEGRAM_IDS")
            elif config.remove_member(i):
                lines.append(f"➖ <code>{i}</code> removed")
            else:
                lines.append(f"<code>{i}</code> wasn't a member")
    await message.answer("\n".join(lines) + "\n\n" + _render(settings, config))
