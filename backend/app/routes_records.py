"""Signed record pages + verification API.  Owner: Pile 3 (Verification & Trust).

STUB from the scaffold. Keep the paths and parameters; replace the bodies.
Spec: docs/WORK_SPLIT.md -> Pile 3, Steps 6-7.
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.db import get_session

router = APIRouter()


class VerifyIn(BaseModel):
    record_json: Any  # str or object
    signature: str


@router.get("/record/{case_id}", include_in_schema=False)
def record_page(case_id: str, session: Session = Depends(get_session)):
    """Serves static/record.html (404 if no Record)."""
    raise HTTPException(501, "Not implemented yet (Pile 3: records)")


@router.get("/api/records/{case_id}")
def get_record(case_id: str, session: Session = Depends(get_session)):
    """{record, record_json, record_sha256, signature, public_key}"""
    raise HTTPException(501, "Not implemented yet (Pile 3: records)")


@router.get("/api/public-key")
def public_key():
    """{"algorithm": "Ed25519", "public_key": ...}"""
    raise HTTPException(501, "Not implemented yet (Pile 3: signing)")


@router.post("/api/records/verify")
def verify(body: VerifyIn):
    """{"valid": bool}"""
    raise HTTPException(501, "Not implemented yet (Pile 3: signing)")
