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
from app import privacy
from app.db import get_session
from app.models import Merchant

router = APIRouter()


class ConsentIn(BaseModel):
    given: bool


class MockSmsIn(BaseModel):
    merchant_id: str
    utr: str
    amount: float


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
    """DEMO BACKUP: build the agreed demo SMS and call ingest.ingest_sms. Returns {"accepted": bool}."""
    raise HTTPException(501, "Not implemented yet (Pile 2: Mock bank)")
