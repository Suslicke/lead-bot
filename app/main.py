"""Entrypoint: build dependencies, inject them, wire routers, start polling."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import BotCommand

# Shown in Telegram's blue "Menu" button (tap to run). Order = display order.
_COMMANDS = [
    ("menu", "Command hub (buttons)"),
    ("today", "Due follow-ups + KPI"),
    ("pipeline", "Counts per stage"),
    ("leads", "List leads in a stage"),
    ("convert", "Lead → Company + Opportunity"),
    ("kpi", "Daily goal progress"),
    ("digest", "Digest schedule"),
    ("niche", "Niches (add new)"),
    ("source", "Sources (add new)"),
    ("currency", "Default deal currency"),
    ("usage", "LLM usage today"),
    ("settings", "Show config"),
    ("help", "Help"),
]

from .config import ConfigStore, Settings
from .filters import Whitelist
from .handlers import get_routers
from .llm import build_extractor
from .osm import OverpassClient
from .reference import OptionsRegistry
from .scheduler import DigestScheduler
from .stats import StatsService
from .twenty import TwentyClient
from .twogis import TwoGisClient
from .usage import UsageStore

log = logging.getLogger("lead-bot")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = Settings.from_env()

    # --- error tracking (optional) ---
    if settings.sentry_dsn:
        import sentry_sdk

        # default LoggingIntegration turns our log.exception(...) calls into Sentry events.
        sentry_sdk.init(dsn=settings.sentry_dsn, environment="prod", traces_sample_rate=0.0)
        log.info("sentry enabled")

    # --- build dependencies ---
    config = ConfigStore(settings.config_path)
    usage = UsageStore(settings.usage_path, settings.tz)
    twenty = TwentyClient(settings.twenty_api_url, settings.twenty_api_key)
    extractor = build_extractor(settings)
    stats = StatsService(twenty, config, settings.tz)
    options = OptionsRegistry(twenty)
    await options.refresh()  # seed niche/source from Twenty (best-effort; falls back to hardcoded)
    twogis = TwoGisClient(settings.twogis_api_key, settings.twogis_api_url) if settings.twogis_api_key else None
    overpass = OverpassClient(settings.overpass_url) if settings.overpass_url else None
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    scheduler = DigestScheduler(settings.tz, config, stats, bot, settings.allowed_ids)

    # --- dependency injection: handlers receive these by parameter name ---
    dp = Dispatcher()
    dp["settings"] = settings
    dp["config"] = config
    dp["usage"] = usage
    dp["twenty"] = twenty
    dp["extractor"] = extractor
    dp["stats"] = stats
    dp["scheduler"] = scheduler
    dp["options"] = options
    dp["twogis"] = twogis
    dp["overpass"] = overpass

    whitelist = Whitelist(settings.allowed_ids)
    for router in get_routers():
        router.message.filter(whitelist)
        router.callback_query.filter(whitelist)
        dp.include_router(router)

    scheduler.start()
    commands = list(_COMMANDS)
    if overpass:  # only advertise /harvest when OSM is wired up
        i = next((n for n, (c, _) in enumerate(commands) if c == "convert"), len(commands) - 1)
        commands.insert(i + 1, ("harvest", "Find leads via OpenStreetMap"))
    await bot.set_my_commands([BotCommand(command=c, description=d) for c, d in commands])
    log.info("lead-bot up (whitelist=%s, model=%s, twenty=%s, 2gis=%s, osm=%s)",
             sorted(settings.allowed_ids) or "OPEN(!)", settings.model, settings.twenty_api_url,
             "on" if twogis else "off", "on" if overpass else "off")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
