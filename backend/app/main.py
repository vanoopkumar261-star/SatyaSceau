"""FastAPI app: wires every pile's router, static files and background jobs.  Owner: Pile 1 (Platform).

Run from backend/:  uvicorn app.main:app --reload --host 0.0.0.0
"""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import Session

from app import (
    events,
    matcher,
    privacy,
    routes_auth,
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


class RevalidatePages:
    """Pure ASGI middleware: HTML pages and our CSS get `Cache-Control: no-cache` (browser re-checks via ETag).

    Without it, browsers reuse stale pages after an update (seen during the redesign). Pure ASGI
    rather than @app.middleware so the SSE stream is never buffered. Responses that already set
    Cache-Control (the record page's no-store) keep theirs.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                names = {k.lower() for k, _ in headers}
                ctype = next((v for k, v in headers if k.lower() == b"content-type"), b"")
                if b"cache-control" not in names and (ctype.startswith(b"text/html") or ctype.startswith(b"text/css")):
                    headers.append((b"cache-control", b"no-cache"))
            await send(message)

        await self.app(scope, receive, send_wrapper)


app = FastAPI(title="SatyaSceau", version=settings.APP_VERSION, lifespan=lifespan)
app.add_middleware(RevalidatePages)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

for module in (routes_merchant, routes_auth, routes_proof, routes_privacy, routes_sms, routes_records):
    app.include_router(module.router)


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(STATIC_DIR / "index.html")  # home page; API docs stay at /docs
