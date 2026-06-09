"""/niche and /source — view the live Select vocabularies and add to them from the phone.

  /niche            → list current niches
  /niche add <name> → add a niche option to the Lead object in Twenty (then the LLM can use it)
  /source [...]     → same, for the source field
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from ..reference import OptionsRegistry

router = Router()


def _label_case(name: str) -> str:
    """Capitalise the first letter, leave the rest (matches 'Gaming club', not 'Gaming Club')."""
    name = name.strip()
    return name[:1].upper() + name[1:] if name else name


def _listing(options: OptionsRegistry, field: str) -> str:
    labels = options.labels(field)
    body = "\n".join(f"• {label}" for label in labels) or "—"
    return (f"<b>{field.capitalize()} options</b> ({len(labels)}):\n{body}\n\n"
            f"Add one: <code>/{field} add &lt;name&gt;</code>")


async def _handle(message: Message, options: OptionsRegistry, field: str) -> None:
    # text is "/niche", "/niche list", or "/niche add <name>"
    parts = (message.text or "").split(maxsplit=2)
    sub = parts[1].lower() if len(parts) > 1 else ""
    if sub == "add":
        name = _label_case(parts[2]) if len(parts) > 2 else ""
        if not name:
            await message.answer(f"Usage: <code>/{field} add &lt;name&gt;</code>")
            return
        try:
            value = await options.add(field, name)
            await message.answer(f"✅ {field.capitalize()}: <b>{name}</b> → <code>{value}</code>")
        except Exception as e:  # noqa: BLE001
            await message.answer(f"⚠️ Couldn't add: {e}")
        return
    await message.answer(_listing(options, field))


@router.message(Command("niche"))
async def niche(message: Message, options: OptionsRegistry) -> None:
    await _handle(message, options, "niche")


@router.message(Command("source"))
async def source(message: Message, options: OptionsRegistry) -> None:
    await _handle(message, options, "source")
