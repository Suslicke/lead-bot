"""/help and the shared HELP text (/start + /menu live in menu.py as the button hub)."""
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

router = Router()

HELP = (
    "<b>Lead-bot</b> — your sales command center.\n\n"
    "📝 <b>Add a lead</b> — send free text (RU/KK/EN), no strict format. Useful to include:\n"
    "  • name + niche (cafe / beauty / dental…)\n"
    "  • the 2GIS (or other) link\n"
    "  • ~reviews, rating, has a site or not\n"
    "  • contact (wa.me / instagram / phone)\n"
    "<i>e.g. https://2gis.kz/almaty/firm/… Барбершоп Chop, ~250 отзывов 4.8, без сайта, wa.me/7707…</i>\n"
    "The bot fills the fields → you confirm. <b>Several at once:</b> paste each business on its own "
    "line / link — it parses them all and offers <i>Create all</i>.\n\n"
    "📊 <b>Commands</b>\n"
    "/today — due follow-ups + KPI\n"
    "/pipeline — counts per stage\n"
    "/leads &lt;stage&gt; — list (e.g. /leads replied)\n"
    "/kpi — progress · /kpi set 10 — goal · /kpi metric won — what it counts\n"
    "/digest — send now · /digest list · /digest add 09:00 · /digest remove 19:00 · /digest off\n"
    "/niche — list niches · /niche add &lt;name&gt; — new niche (LLM picks it up)\n"
    "/source — list sources · /source add &lt;name&gt;\n"
    "/usage — LLM tokens/requests today · /llm set req|tok &lt;n&gt; — daily caps\n"
    "/convert — turn a replied/qualified lead into Company + Opportunity\n"
    "/harvest — find leads from OpenStreetMap (pick a niche → a city)\n"
    "/currency — default deal currency (e.g. /currency USD)\n"
    "/members — who can use the bot · /members add &lt;id&gt; (admins only)\n"
    "/settings — show config"
)


@router.message(Command("help"))
async def help_cmd(message: Message) -> None:
    await message.answer(HELP)
