"""POST /api/sms: bank credit SMS from the Android forwarder.  Owner: Pile 3 (Verification & Trust).

STUB from the scaffold. Keep the path and parameters; replace the body.
Spec: docs/WORK_SPLIT.md -> Pile 3, Step 3.
X-Token -> merchant (401) -> consent check (403 "consent required") -> ingest.ingest_sms -> 200 {"accepted": bool}
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.db import get_session

router = APIRouter()


class SmsIn(BaseModel):
    sender: str
    body: str
    received_at: Optional[datetime] = None


@router.post("/api/sms")
def receive_sms(
    sms: SmsIn,
    x_token: str | None = Header(default=None),
    session: Session = Depends(get_session),
):
    raise HTTPException(501, "Not implemented yet (Pile 3: SMS ingest)")
