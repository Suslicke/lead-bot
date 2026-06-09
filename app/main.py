"""Entrypoint: build dependencies, inject them, wire routers, start polling."""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from .config import ConfigStore, Settings
from .filters import Whitelist
from .handlers import get_routers
from .llm import build_extractor
from .reference import OptionsRegistry
from .scheduler import DigestScheduler
from .stats import StatsService
from .twenty import TwentyClient
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

    whitelist = Whitelist(settings.allowed_ids)
    for router in get_routers():
        router.message.filter(whitelist)
        router.callback_query.filter(whitelist)
        dp.include_router(router)

    scheduler.start()
    log.info("lead-bot up (whitelist=%s, model=%s, twenty=%s)",
             sorted(settings.allowed_ids) or "OPEN(!)", settings.model, settings.twenty_api_url)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
