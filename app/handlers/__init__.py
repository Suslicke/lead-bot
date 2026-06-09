"""Feature routers. main wires these into the dispatcher (whitelist applied to each)."""
from aiogram import Router

from . import capture, common, digest, kpi, queries, reference


def get_routers() -> list[Router]:
    return [common.router, capture.router, queries.router, kpi.router,
            digest.router, reference.router]
