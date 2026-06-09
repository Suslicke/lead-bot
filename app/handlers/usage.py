"""/usage — today's LLM consumption (you); /llm set req|tok <n> — daily per-user caps."""
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from ..config import ConfigStore
from ..usage import UsageStore

router = Router()


def _cap(n: int) -> str:
    return str(n) if n else "∞"


@router.message(Command("usage"))
async def usage_cmd(message: Message, usage: UsageStore, config: ConfigStore) -> None:
    t = usage.today(message.from_user.id)
    rq, tk = config.llm_max_requests, config.llm_max_tokens
    await message.answer(
        "📊 <b>LLM usage today (you)</b>\n"
        f"Requests: <b>{t['requests']}</b> / {_cap(rq)}\n"
        f"Tokens: <b>{t['total_tokens']}</b> / {_cap(tk)}\n"
        f"  <i>prompt {t['prompt_tokens']} + completion {t['completion_tokens']}</i>\n\n"
        "Caps are per user, per day (reset at local midnight). 0 = unlimited.\n"
        "Change: <code>/llm set req 200</code> · <code>/llm set tok 300000</code>"
    )


@router.message(Command("llm"))
async def llm_cmd(message: Message, command: CommandObject, config: ConfigStore) -> None:
    parts = (command.args or "").split()
    if len(parts) == 3 and parts[0] == "set" and parts[1] in ("req", "tok"):
        try:
            n = int(parts[2])
        except ValueError:
            await message.answer("Usage: <code>/llm set req 200</code> | <code>/llm set tok 300000</code>")
            return
        if parts[1] == "req":
            config.set_llm_max_requests(n)
            await message.answer(f"✅ Daily request cap per user: <b>{_cap(config.llm_max_requests)}</b>.")
        else:
            config.set_llm_max_tokens(n)
            await message.answer(f"✅ Daily token cap per user: <b>{_cap(config.llm_max_tokens)}</b>.")
        return
    await message.answer(
        "Set per-user daily LLM caps (0 = unlimited):\n"
        "<code>/llm set req 200</code> — max requests/day\n"
        "<code>/llm set tok 300000</code> — max tokens/day\n"
        "See current usage with /usage."
    )
