"""FastAPI app: wires every pile's router, static files and background jobs.  Owner: Pile 1 (Platform).

Run from backend/:  uvicorn app.main:app --reload --host 0.0.0.0
"""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app import (
    events,
    matcher,
    privacy,
    routes_merchant,
    routes_privacy,
    routes_proof,
    routes_records,
    routes_sms,
)
from app.config import STATIC_DIR, settings
from app.db import engine, init_db

log = logging.getLogger("satyasceau")

EXPIRE_EVERY_S = 15
PURGE_EVERY_S = 3600


def _expire_tick() -> None:
    with Session(engine) as session:
        matcher.expire_waiting(session)


def _purge_tick() -> None:
    with Session(engine) as session:
        privacy.purge_expired_credits(session)


async def _background_loop() -> None:
    """Every 15 s: time out stale WAITING cases. Every hour (and at startup): retention purge."""
    elapsed = PURGE_EVERY_S  # forces a purge on the first pass
    while True:
        for tick, due in ((_expire_tick, True), (_purge_tick, elapsed >= PURGE_EVERY_S)):
            if not due:
                continue
            try:
                await asyncio.to_thread(tick)
            except Exception:  # a bug in one pile must not kill the loop
                log.exception("background job %s failed", tick.__name__)
        if elapsed >= PURGE_EVERY_S:
            elapsed = 0
        await asyncio.sleep(EXPIRE_EVERY_S)
        elapsed += EXPIRE_EVERY_S


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    events.set_loop(asyncio.get_running_loop())
    task = asyncio.create_task(_background_loop()) if settings.BACKGROUND_TASKS else None
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="SatyaSceau", version=settings.APP_VERSION, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

for module in (routes_merchant, routes_proof, routes_privacy, routes_sms, routes_records):
    app.include_router(module.router)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/docs")
