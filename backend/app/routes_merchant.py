"""Merchant setup, live stream, case status and page routes.  Owner: Pile 1 (Platform)."""

import asyncio
import base64
import io
import json
import secrets

import qrcode
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import events, ingest
from app.config import STATIC_DIR, settings
from app.db import get_session, utcnow
from app.models import Case, Merchant
from app.sms_parser import BANK_CODES

# Sender prefix for SMS the merchant pastes by hand. Kept in BankCredit.sender_id (e.g. "MP-HDFCBK"),
# so the evidence trail shows the credit was typed in, not forwarded automatically from the bank.
PASTED_SENDER_PREFIX = "MP"

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


def authorize_screen(session: Session, merchant_id: str, key: str) -> Merchant:
    """The merchant id is public (printed QR); acting as the merchant needs the screen key.

    Used to read payments, and to add bank credits by hand (pasted SMS, mock bank).
    Only the shop has the key, so a customer can't feed in a fake credit for their own UTR.
    """
    merchant = _get_merchant(session, merchant_id)
    expected = merchant.screen_key or ""
    if not expected or not secrets.compare_digest(key.encode(), expected.encode()):
        raise HTTPException(403, "Invalid screen key")
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
        # key in the #fragment: browsers never send it in the page request
        "merchant_url": f"{settings.BASE_URL}/merchant?m={merchant.id}#k={merchant.screen_key}",
        "qr_png_base64": base64.b64encode(_qr_png(pay_url)).decode(),
    }


@router.get("/api/merchants/{merchant_id}/qr.png")
def merchant_qr(merchant_id: str, session: Session = Depends(get_session)):
    _get_merchant(session, merchant_id)
    return Response(_qr_png(_pay_url(merchant_id)), media_type="image/png")


@router.get("/api/merchants/{merchant_id}/cases")
def list_cases(
    merchant_id: str,
    k: str = Query(default="", description="screen key"),
    limit: int = Query(default=10, ge=1, le=50),
    session: Session = Depends(get_session),
):
    """Newest cases first: the merchant screen's first load and its polling fallback."""
    merchant = authorize_screen(session, merchant_id, k)
    cases = session.exec(
        select(Case)
        .where(Case.merchant_id == merchant_id)
        .order_by(Case.created_at.desc())
        .limit(limit)
    ).all()
    return {
        "merchant": {"id": merchant.id, "name": merchant.name},
        "match_window_min": settings.MATCH_WINDOW_MIN,
        "cases": [events.case_payload(c) for c in cases],
    }


class BankSmsIn(BaseModel):
    k: str = ""  # screen key: in the body, never in the URL
    bank: str = Field(min_length=6, max_length=6)
    body: str = Field(min_length=1, max_length=2000)


@router.post("/api/merchants/{merchant_id}/bank-sms")
def add_bank_sms(merchant_id: str, payload: BankSmsIn, session: Session = Depends(get_session)):
    """The merchant pastes a bank credit SMS by hand (no forwarder app needed).

    It goes through the same parser and matcher as forwarded SMS. Pasting is an explicit action,
    so it isn't gated on the automatic-forwarding consent.
    """
    merchant = authorize_screen(session, merchant_id, payload.k)
    bank = payload.bank.upper()
    if bank not in BANK_CODES:
        raise HTTPException(422, "Unknown bank")
    credit = ingest.ingest_sms(session, merchant, f"{PASTED_SENDER_PREFIX}-{bank}", payload.body, utcnow())
    if credit is None:
        return {
            "accepted": False,
            "reason": "No bank credit found. The SMS needs the amount (Rs/INR/₹), the 12-digit "
                      "UPI reference and a word like 'credited' or 'received'.",
        }
    return {"accepted": True, "utr": credit.utr, "amount": credit.amount}


@router.get("/api/merchants/{merchant_id}/stream")
async def stream_cases(
    merchant_id: str,
    request: Request,
    k: str = Query(default="", description="screen key"),
    session: Session = Depends(get_session),
):
    """Server-Sent Events: one `case` event per status change for this merchant.

    EventSource can't send headers, so the screen key comes as ?k=.
    """
    authorize_screen(session, merchant_id, k)
    queue = events.subscribe(merchant_id)

    async def event_source():
        # `hello` / `ping` are real events (not SSE comments) so the page can tell a live stream
        # from one a proxy is silently buffering (Cloudflare quick tunnels do) and fall back to polling.
        try:
            yield "retry: 3000\n\n"
            yield "event: hello\ndata: {}\n\n"
            while not await request.is_disconnected():
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=SSE_KEEPALIVE_S)
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
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
