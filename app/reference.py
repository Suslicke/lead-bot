"""Live Select-option vocabularies (niche, source), sourced from Twenty.

Hardcoding niches (twenty.NICHE/SOURCE) means the LLM can't pick a value you added in the
CRM, and any off-list niche silently collapses to OTHER. OptionsRegistry instead reads the
options straight off the Lead object at startup (and after each /niche add), and feeds them
to BOTH coupling points: the LLM enum (what it may pick) and to_payload (label -> VALUE).

It seeds from the hardcoded fallback so a metadata hiccup at startup degrades to today's
behaviour instead of mapping everything to OTHER.
"""
from __future__ import annotations

import logging

from .twenty import NICHE, SOURCE, TwentyClient

log = logging.getLogger(__name__)

# Lead object + its two Select fields (ids from the live CRM; see TODO.md).
LEAD_OBJECT_ID = "52b9769d-73ef-4d71-a99c-78f6ed3098f8"
FIELD_IDS = {"niche": "5577b72c-0439-4e42-8ac4-66f133986369",
             "source": "27af265a-decf-4c34-b868-d639fe9609d3"}

FIELDS = ("niche", "source")


def _seed(mapping: dict[str, str]) -> list[dict]:
    return [{"label": label, "value": value} for label, value in mapping.items()]


class OptionsRegistry:
    def __init__(self, twenty: TwentyClient, object_id: str = LEAD_OBJECT_ID):
        self._twenty = twenty
        self._object_id = object_id
        self._field_ids = dict(FIELD_IDS)  # refreshed from the API; FIELD_IDS is the fallback
        self._options: dict[str, list[dict]] = {"niche": _seed(NICHE), "source": _seed(SOURCE)}

    async def refresh(self) -> None:
        """Re-read options from Twenty. Per-field best-effort: a failure keeps the seed."""
        for field in FIELDS:
            try:
                field_id, opts = await self._twenty.field_options(self._object_id, field)
                self._field_ids[field] = field_id
                self._options[field] = sorted(opts, key=lambda o: o.get("position", 0))
            except Exception:  # noqa: BLE001 — keep the cached/seeded options on any error
                log.exception("options refresh failed for %s (keeping cached)", field)

    def labels(self, field: str) -> list[str]:
        return [o["label"] for o in self._options[field]]

    def value_map(self, field: str) -> dict[str, str]:
        return {o["label"]: o["value"] for o in self._options[field]}

    async def add(self, field: str, label: str) -> str:
        """Add a niche/source option (idempotent on label). Returns its VALUE."""
        if field not in FIELDS:
            raise ValueError(f"unknown field {field!r}")
        await self.refresh()  # mutate the *live* array (with real option ids), never a stale seed
        existing = self.value_map(field)
        if label in existing:
            return existing[label]
        value = await self._twenty.add_select_option(self._field_ids[field], self._options[field], label)
        await self.refresh()
        return value
