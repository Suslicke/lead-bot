"""Whitelist filter — applied at router level so only allowed Telegram ids are served."""
from __future__ import annotations

from aiogram.filters import BaseFilter
from aiogram.types import TelegramObject


class Whitelist(BaseFilter):
    def __init__(self, allowed_ids: frozenset[int]):
        self._allowed = allowed_ids

    async def __call__(self, event: TelegramObject) -> bool:
        user = getattr(event, "from_user", None)
        # empty whitelist = open (logged loudly at startup); otherwise must match.
        return bool(user) and (not self._allowed or user.id in self._allowed)
