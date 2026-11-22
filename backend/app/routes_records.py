"""Signed record routes: the public shareable page plus JSON, public key and verify."""
import json

from fastapi import APIRouter, Depends, HTTPException, Path
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app import signing
from app.config import settings
from app.db import get_session
from app.models import Record

router = APIRouter()

CaseId = Path(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")

# The record URL is an unguessable bearer link: don't leak it via Referer, don't cache it,
# and only let the page talk to us (no third-party scripts).
PAGE_HEADERS = {
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    # Fonts: the shared design system loads Noto Sans / Source Code Pro / Material Symbols from Google Fonts
    # (stylesheets from fonts.googleapis.com, font files from fonts.gstatic.com). Nothing else external.
    "Content-Security-Policy": "default-src 'none'; script-src 'self' 'unsafe-inline'; "
                               "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; "
                               "connect-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
}


def _record_or_404(session, case_id) -> Record:
    rec = session.get(Record, case_id)
    if rec is None:
        raise HTTPException(404, "record not found")
    return rec


@router.get("/record/{case_id}", include_in_schema=False)
def record_page(case_id: str = CaseId, session=Depends(get_session)):
    _record_or_404(session, case_id)
    return FileResponse(settings.STATIC_DIR / "record.html", media_type="text/html", headers=PAGE_HEADERS)


@router.get("/api/records/{case_id}")
def get_record(case_id: str = CaseId, session=Depends(get_session)):
    rec = _record_or_404(session, case_id)
    return {
        "record": json.loads(rec.record_json),
        "record_json": rec.record_json,
        "record_sha256": rec.record_sha256,
        "signature": rec.signature,
        "public_key": signing.public_key_b64(),
    }


@router.get("/api/public-key")
def public_key():
    return {"algorithm": "Ed25519", "public_key": signing.public_key_b64()}


class VerifyIn(BaseModel):
    record_json: str | dict = Field(...)
    signature: str = Field(max_length=200)


@router.post("/api/records/verify")
def verify(payload: VerifyIn):
    if isinstance(payload.record_json, str) and len(payload.record_json) > 10_000:
        return {"valid": False}
    return {"valid": signing.verify_record(payload.record_json, payload.signature)}
