"""Feature routers. main wires these into the dispatcher (whitelist applied to each)."""
from aiogram import Router

from . import capture, common, convert, digest, kpi, menu, queries, reference, usage


def get_routers() -> list[Router]:
    return [menu.router, common.router, capture.router, queries.router, kpi.router,
            digest.router, reference.router, usage.router, convert.router]
