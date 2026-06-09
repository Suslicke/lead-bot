"""Whitelist filter — applied at router level so only allowed Telegram ids are served.

The env `ALLOWED_TELEGRAM_IDS` are the **admins** (bootstrap). A ConfigStore may carry extra
runtime-added **members** (via /members add), so the effective allowlist is read live on each
event rather than frozen at startup."""
from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject


class Whitelist(BaseFilter):
    def __init__(self, admin_ids: frozenset[int], config=None):
        self._admins = frozenset(admin_ids)
        self._config = config  # ConfigStore | None — supplies extra runtime members

    def allowed(self) -> set[int]:
        extra = set(self._config.members) if self._config is not None else set()
        return set(self._admins) | extra

    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        allowed = self.allowed()
        # empty allowlist = open (logged loudly at startup); otherwise must match.
        return bool(user) and (not allowed or user.id in allowed)
