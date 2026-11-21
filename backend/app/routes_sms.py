"""POST /api/sms: bank SMS from the merchant's Android forwarder (header X-Token)."""
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlmodel import select

from app import ingest
from app.db import get_session
from app.models import Merchant

router = APIRouter()


class SmsIn(BaseModel):
    sender: str = Field(max_length=32)       # caps: a real SMS never needs more; cheap abuse guard
    body: str = Field(max_length=2000)
    received_at: datetime | None = None


@router.post("/api/sms")
def receive_sms(payload: SmsIn, x_token: str | None = Header(default=None), session=Depends(get_session)):
    merchant = session.exec(select(Merchant).where(Merchant.api_token == x_token)).first() if x_token else None
    if merchant is None:
        raise HTTPException(401, "invalid token")
    if not merchant.consent_given:
        raise HTTPException(403, "consent required")
    credit = ingest.ingest_sms(session, merchant, payload.sender, payload.body, payload.received_at)
    # Always 200 once authenticated, so the forwarder doesn't keep retrying dropped OTPs/debits.
    return {"accepted": credit is not None}
