"""Consent endpoint + mock bank (demo backup).  Owner: Pile 2 (Vision, Customer & Privacy).

STUB from the scaffold. Keep the paths and parameters; replace the bodies.
Spec: docs/WORK_SPLIT.md -> Pile 2, Steps 5-6.
"""

import secrets

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session

from app.config import STATIC_DIR
from app import ingest, privacy
from app.db import get_session, utcnow
from app.models import Merchant
from app.routes_merchant import authorize_screen

router = APIRouter()


class ConsentIn(BaseModel):
    given: bool


class MockSmsIn(BaseModel):
    merchant_id: str
    utr: str
    amount: float
    k: str = ""  # the shop's screen key (the merchant id alone is public: it's on the QR)


@router.post("/api/merchants/{merchant_id}/consent")
def update_consent(
    merchant_id: str,
    body: ConsentIn,
    x_token: str | None = Header(default=None),
    session: Session = Depends(get_session),
):
    """X-Token must be this merchant's api_token. Returns {"consent_given": bool}."""
    merchant = session.get(Merchant, merchant_id)
    if merchant is None:
        raise HTTPException(404, "merchant not found")
    if not x_token or not secrets.compare_digest(x_token, merchant.api_token):
        raise HTTPException(401, "invalid token")
    merchant = privacy.set_consent(session, merchant_id, body.given)
    return {"consent_given": merchant.consent_given}


@router.get("/mock-bank", include_in_schema=False)
def mock_bank_page():
    return FileResponse(STATIC_DIR / "mock-bank.html")


@router.post("/api/mock-bank")
def mock_bank_credit(body: MockSmsIn, session: Session = Depends(get_session)):
    """DEMO BACKUP: build the agreed demo SMS and call ingest.ingest_sms. Returns {"accepted": bool}.

    Requires the shop's screen key: without it, a customer could inject a fake bank credit for
    their own UTR and then get an edited screenshot VERIFIED.
    """
    merchant = authorize_screen(session, body.merchant_id, body.k)  # 404 unknown shop, 403 bad key
    sender = "AX-HDFCBK"
    now = utcnow()
    sms = (
        f"Rs.{body.amount:.2f} credited to A/c XX1234 on {now:%d-%m-%y} "
        f"by UPI Ref No {body.utr}. -HDFC Bank"
    )
    credit = ingest.ingest_sms(session, merchant, sender, sms, now)
    return {"accepted": credit is not None}
