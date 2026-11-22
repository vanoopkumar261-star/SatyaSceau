"""Merchant setup, live stream, case status and page routes.  Owner: Pile 1 (Platform)."""

import asyncio
import base64
import io
import json
import re
import secrets
from datetime import timedelta

import qrcode
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response, StreamingResponse
from PIL import Image
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import events, ingest, matcher, ocr
from app.config import STATIC_DIR, settings
from app.db import get_session, utcnow
from app.models import BankCredit, Case, CaseStatus, Merchant, Record, UsedUTR
from app.schemas import ParsedCredit
from app.sms_parser import BANK_CODES

# How a bank credit reached us, kept in BankCredit.sender_id so the evidence trail shows it:
#   "AX-HDFCBK" forwarded automatically from the bank's SMS
#   "MP-HDFCBK" the merchant pasted the SMS text by hand
#   "MI-HDFCBK" the merchant uploaded an image (screenshot of the SMS / bank app), read by OCR
PASTED_SENDER_PREFIX = "MP"
IMAGE_SENDER_PREFIX = "MI"
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

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


@router.get("/api/merchants/{merchant_id}/public")
def merchant_public(merchant_id: str, session: Session = Depends(get_session)):
    """What a customer may see: the shop's name (already printed on the QR poster). Nothing else."""
    return {"name": _get_merchant(session, merchant_id).name}


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


@router.post("/api/merchants/{merchant_id}/bank-image")
async def add_bank_image(
    merchant_id: str,
    k: str = Form(default=""),
    bank: str = Form(...),
    image: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """The merchant uploads an IMAGE of their bank credit (SMS screenshot or bank-app notification).

    OCR reads it in memory, then it goes through the same SMS parser and matcher as a pasted or
    forwarded SMS. The image and its text are never stored; only the parsed credit is.
    """
    try:
        merchant = authorize_screen(session, merchant_id, k)
        bank = bank.upper()
        if bank not in BANK_CODES:
            raise HTTPException(422, "Unknown bank")
        if image.content_type not in ALLOWED_IMAGE_TYPES:
            raise HTTPException(415, "Image must be JPEG, PNG or WebP")
        limit = settings.MAX_UPLOAD_MB * 1024 * 1024
        data = await image.read(limit + 1)
    finally:
        await image.close()
    if len(data) > limit:
        raise HTTPException(413, f"Image larger than {settings.MAX_UPLOAD_MB} MB")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
    except Exception:
        raise HTTPException(400, "Could not read image")

    sender = f"{IMAGE_SENDER_PREFIX}-{bank}"
    text = await run_in_threadpool(ocr.extract_text, data)
    # 1) A screenshot of the bank's credit SMS: same strict parser as a forwarded SMS.
    credit = await run_in_threadpool(ingest.ingest_sms, session, merchant, sender, text, utcnow())
    # 2) Otherwise a UPI app's "Received" receipt (e.g. PhonePe "Received from ... Credited to ... UTR").
    #    The strict parser wants Rs/INR/₹, but OCR often reads a large ₹ as "2" or "z", so use the
    #    screenshot reader (handles those misreads, gates on OCR confidence). Only RECEIVE-side
    #    receipts count: the customer's "Paid to / Debited from" screen is the claim, never the proof.
    if credit is None and _is_receive_side(text):
        receipt = await run_in_threadpool(ocr.analyze_screenshot, data)
        if receipt.utr and receipt.amount is not None:
            credit = await run_in_threadpool(
                ingest.save_credit, session, merchant,
                ParsedCredit(utr=receipt.utr, amount=receipt.amount, sender_id=sender), utcnow(),
            )
    del data, text
    if credit is None:
        return {
            "accepted": False,
            "reason": "Couldn't read a bank credit in that image. Use ONE credit SMS, or your UPI app's "
                      "'Received from … UTR' receipt, showing the amount and the 12-digit UTR, "
                      "or paste the SMS text instead.",
        }
    return {"accepted": True, "utr": credit.utr, "amount": credit.amount}


_RECEIVE_SIDE = re.compile(r"\b(received\s+from|credited\s+to|money\s+received|received)\b", re.I)
_PAYER_SIDE = re.compile(r"\b(paid\s+to|debited|sent\s+to|payment\s+to)\b", re.I)


def _is_receive_side(text: str) -> bool:
    """A receiver's receipt ("Received from", "Credited to"), not the payer's screen ("Paid to")."""
    return bool(_RECEIVE_SIDE.search(text)) and not _PAYER_SIDE.search(text)


# --- "Show detection details": how a verdict was reached --------------------------------------

def _credit_source(sender_id: str) -> str:
    prefix, _, bank = sender_id.partition("-")
    if prefix == PASTED_SENDER_PREFIX:
        return f"SMS pasted by merchant ({bank})"
    if prefix == IMAGE_SENDER_PREFIX:
        return f"bank screenshot uploaded by merchant ({bank})"
    return f"SMS forwarded from {sender_id}"


@router.get("/api/cases/{case_id}/details")
def case_details(case_id: str, k: str = Query(default=""), session: Session = Depends(get_session)):
    """Each check the verdict engine makes, with what it saw. Merchant only (screen key).

    Read-only: it shows the evidence as it stands now, in the matcher's order.
    States: pass | fail | wait | skip | info.
    """
    case = session.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    authorize_screen(session, case.merchant_id, k)
    window = timedelta(minutes=settings.MATCH_WINDOW_MIN)
    final = case.status in CaseStatus.FINAL
    checks = []

    def add(key, label, state, detail=""):
        checks.append({"key": key, "label": label, "state": state, "detail": detail})

    readable = case.utr is not None
    ocr_amount = None if case.amount_from_bank else case.amount   # what OCR itself read
    add("ocr", "UPI reference (UTR) read from screenshot",
        "pass" if readable else "fail",
        f"{case.utr} · OCR confidence {case.ocr_confidence:.0f} (needs {settings.OCR_MIN_CONF:.0f})" if readable
        else "Not readable with enough confidence → customer asked to retake")
    add("amount_read", "Amount read from screenshot",
        "pass" if ocr_amount is not None else "info",
        f"₹{ocr_amount:,.2f}" if ocr_amount is not None else "Not read → the bank's amount is used")

    if not readable:
        for key, label in (("replay", "UTR not used before"), ("duplicate", "Screenshot not seen before"),
                           ("bank", "Bank credit for this UTR"), ("window", "Credit within time window"),
                           ("amount", "Amount matches the bank")):
            add(key, label, "skip", "Skipped: no UTR")
    else:
        used = session.get(UsedUTR, case.utr)
        if used is None:
            add("replay", "UTR not used before", "pass", "No earlier payment claimed this UTR")
        elif used.case_id == case.id:
            add("replay", "UTR not used before", "pass", "This payment claimed the UTR")
        else:
            add("replay", "UTR not used before", "fail", f"Already used by another payment at {used.used_at.isoformat()}")

        dup = matcher._is_duplicate_image(session, case)
        add("duplicate", "Screenshot not seen before", "fail" if dup else "pass",
            "Same image (or a re-saved copy with the same UTR) was uploaded earlier" if dup
            else f"Fingerprint {case.image_sha256[:12]}… is new")

        credits = session.exec(
            select(BankCredit).where(BankCredit.merchant_id == case.merchant_id, BankCredit.utr == case.utr)
        ).all()
        if not credits:
            add("bank", "Bank credit for this UTR", "fail" if final else "wait",
                "None received" + ("" if final else " yet: forwarded SMS, pasted SMS or bank image will arrive here"))
            add("window", f"Credit within {settings.MATCH_WINDOW_MIN} min of upload", "skip" if final else "wait", "")
            add("amount", "Amount matches the bank", "skip" if final else "wait", "")
        else:
            best = min(credits, key=lambda c: abs(c.credited_at - case.created_at))
            gap = abs(best.credited_at - case.created_at)
            add("bank", "Bank credit for this UTR", "pass",
                f"₹{best.amount:,.2f} at {best.credited_at.isoformat()} · {_credit_source(best.sender_id)}")
            add("window", f"Credit within {settings.MATCH_WINDOW_MIN} min of upload",
                "pass" if gap <= window else "fail", f"{int(gap.total_seconds())} s apart")
            if ocr_amount is None:
                add("amount", "Amount matches the bank", "info",
                    f"Screenshot amount unreadable → bank amount ₹{best.amount:,.2f} used")
            else:
                same = abs(best.amount - ocr_amount) <= 0.01
                add("amount", "Amount matches the bank", "pass" if same else "fail",
                    f"Screen ₹{ocr_amount:,.2f} vs bank ₹{best.amount:,.2f}")

    record = session.get(Record, case.id)
    add("signed", "Signed, tamper-proof record",
        "pass" if record else ("fail" if final else "wait"),
        f"SHA-256 {record.record_sha256[:12]}… · Ed25519" if record else ("" if final else "Created when decided"))

    return {
        "case_id": case.id,
        "status": case.status,
        "reason": case.reason,
        "checks": checks,
        "params": {
            "match_window_min": settings.MATCH_WINDOW_MIN,
            "ocr_min_conf": settings.OCR_MIN_CONF,
            "phash_max_distance": matcher.PHASH_MAX_DISTANCE,
            "image_sha256": case.image_sha256[:16],
            "image_phash": case.image_phash,
            "risk_score": case.risk_score,
        },
    }


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
