"""/start and /help."""
from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

router = Router()

HELP = (
    "<b>Lead-bot</b> — your sales command center.\n\n"
    "📝 <b>Add a lead:</b> just send a 2GIS link + facts:\n"
    "<i>https://2gis.kz/... барбершоп на Абая, ~250 отзывов, без сайта</i>\n\n"
    "📊 <b>Commands</b>\n"
    "/today — due follow-ups + KPI\n"
    "/pipeline — counts per stage\n"
    "/leads &lt;stage&gt; — list (e.g. /leads replied)\n"
    "/kpi — progress · /kpi set 10 — daily goal\n"
    "/digest — send now · /digest list · /digest add 09:00 · /digest remove 19:00 · /digest off\n"
    "/niche — list niches · /niche add &lt;name&gt; — new niche (LLM picks it up)\n"
    "/source — list sources · /source add &lt;name&gt;\n"
    "/settings — show config"
)


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(HELP)


@router.message(Command("help"))
async def help_cmd(message: Message) -> None:
    await message.answer(HELP)
