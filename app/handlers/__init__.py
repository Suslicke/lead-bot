"""Feature routers. main wires these into the dispatcher (whitelist applied to each)."""
from aiogram import Router

from . import (capture, cards, common, convert, digest, edit, harvest, kpi,
               members, menu, queries, reference, usage)


def get_routers() -> list[Router]:
    # edit/harvest BEFORE capture: their StateFilter'd text handlers must win over
    # capture's catch-all so a typed value (field edit / harvest city) isn't parsed
    # as a new lead.
    return [menu.router, common.router, edit.router, harvest.router, capture.router,
            queries.router, kpi.router, digest.router, reference.router, usage.router,
            convert.router, cards.router, members.router]
