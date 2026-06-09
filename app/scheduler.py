"""Digest scheduler — pushes the daily status to whitelisted ids at configured times."""
from __future__ import annotations

import logging
from zoneinfo import ZoneInfo

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import ConfigStore
from .stats import StatsService

log = logging.getLogger(__name__)


class DigestScheduler:
    def __init__(self, tz: ZoneInfo, config: ConfigStore, stats: StatsService,
                 bot: Bot, allowed_ids: frozenset[int]):
        self._config = config
        self._stats = stats
        self._bot = bot
        self._allowed = allowed_ids
        self._sched = AsyncIOScheduler(timezone=tz)

    def start(self) -> None:
        self._sched.start()
        self.reschedule()

    def reschedule(self) -> None:
        """Rebuild jobs from config — called at startup and whenever times change."""
        self._sched.remove_all_jobs()
        for t in self._config.digest_times:
            hour, minute = t.split(":")
            self._sched.add_job(self._send, CronTrigger(hour=int(hour), minute=int(minute)))
        log.info("digests scheduled at %s", self._config.digest_times)

    async def _send(self) -> None:
        text = await self._stats.status_text("📊 Daily digest")
        for uid in self._allowed:
            try:
                await self._bot.send_message(uid, text)
            except Exception:  # noqa: BLE001
                log.exception("digest send failed for %s", uid)
