"""Merchant setup, live stream, case status and page routes.  Owner: Pile 1 (Platform)."""

import asyncio
import base64
import io
import json

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session

from app import events
from app.config import STATIC_DIR, settings
from app.db import get_session
from app.models import Case, Merchant

router = APIRouter()

SSE_KEEPALIVE_S = 15


class MerchantIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    upi_id: str = Field(default="", max_length=80)


def _pay_url(merchant_id: str) -> str:
    return f"{settings.BASE_URL}/pay/{merchant_id}"


def _qr_png(url: str) -> bytes:
    buf = io.BytesIO()
    qrcode.make(url, box_size=10, border=2).save(buf)
    return buf.getvalue()


def _get_merchant(session: Session, merchant_id: str) -> Merchant:
    merchant = session.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(404, "Merchant not found")
    return merchant


@router.get("/health")
def health():
    return {"status": "ok", "version": settings.APP_VERSION}


@router.post("/api/merchants", status_code=201)
def create_merchant(body: MerchantIn, session: Session = Depends(get_session)):
    merchant = Merchant(name=body.name.strip(), upi_id=body.upi_id.strip())
    session.add(merchant)
    session.commit()
    session.refresh(merchant)
    pay_url = _pay_url(merchant.id)
    return {
        "id": merchant.id,
        "name": merchant.name,
        "api_token": merchant.api_token,  # shown once: goes into the SMS forwarder
        "pay_url": pay_url,
        "merchant_url": f"{settings.BASE_URL}/merchant?m={merchant.id}",
        "qr_png_base64": base64.b64encode(_qr_png(pay_url)).decode(),
    }


@router.get("/api/merchants/{merchant_id}/qr.png")
def merchant_qr(merchant_id: str, session: Session = Depends(get_session)):
    _get_merchant(session, merchant_id)
    return Response(_qr_png(_pay_url(merchant_id)), media_type="image/png")


@router.get("/api/merchants/{merchant_id}/stream")
async def stream_cases(merchant_id: str, request: Request, session: Session = Depends(get_session)):
    """Server-Sent Events: one `case` event per status change for this merchant."""
    _get_merchant(session, merchant_id)
    queue = events.subscribe(merchant_id)

    async def event_source():
        try:
            yield "retry: 3000\n\n"
            while not await request.is_disconnected():
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=SSE_KEEPALIVE_S)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield f"event: case\ndata: {json.dumps(payload)}\n\n"
        finally:
            events.unsubscribe(merchant_id, queue)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/api/cases/{case_id}")
def get_case(case_id: str, session: Session = Depends(get_session)):
    """Polling fallback for the merchant screen and the customer page."""
    case = session.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    return events.case_payload(case)


@router.get("/pay/{merchant_id}", include_in_schema=False)
def pay_page(merchant_id: str, session: Session = Depends(get_session)):
    """What the printed QR opens. The page itself belongs to Pile 2 (static/pay.html)."""
    _get_merchant(session, merchant_id)
    return FileResponse(STATIC_DIR / "pay.html")


@router.get("/merchant", include_in_schema=False)
def merchant_page():
    return FileResponse(STATIC_DIR / "merchant.html")
