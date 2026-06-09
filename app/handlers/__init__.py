"""Feature routers. main wires these into the dispatcher (whitelist applied to each)."""
from aiogram import Router

from . import (capture, common, convert, digest, edit, kpi, menu, queries,
               reference, usage)


def get_routers() -> list[Router]:
    # edit BEFORE capture: the in-edit text handler (StateFilter) must win over
    # capture's catch-all so a typed field value isn't parsed as a new lead.
    return [menu.router, common.router, edit.router, capture.router, queries.router,
            kpi.router, digest.router, reference.router, usage.router, convert.router]
