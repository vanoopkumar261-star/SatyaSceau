"""Consent endpoint + mock bank (demo backup).  Owner: Pile 2 (Vision, Customer & Privacy).

STUB from the scaffold. Keep the paths and parameters; replace the bodies.
Spec: docs/WORK_SPLIT.md -> Pile 2, Steps 5-6.
"""

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import Session

from app.config import STATIC_DIR
from app.db import get_session

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
    raise HTTPException(501, "Not implemented yet (Pile 2: Privacy)")


@router.get("/mock-bank", include_in_schema=False)
def mock_bank_page():
    return FileResponse(STATIC_DIR / "mock-bank.html")


@router.post("/api/mock-bank")
def mock_bank_credit(body: MockSmsIn, session: Session = Depends(get_session)):
    """DEMO BACKUP: build the agreed demo SMS and call ingest.ingest_sms. Returns {"accepted": bool}."""
    raise HTTPException(501, "Not implemented yet (Pile 2: Mock bank)")
