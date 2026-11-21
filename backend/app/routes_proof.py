"""POST /api/proof: the customer uploads the payment screenshot.  Owner: Pile 2 (Vision).

STUB from the scaffold. Keep the path and parameters; replace the body.
Spec: docs/WORK_SPLIT.md -> Pile 2, Step 3.
Flow: validate -> ocr.analyze_screenshot -> create Case(WAITING) -> matcher.evaluate_case -> respond.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlmodel import Session

from app.db import get_session

router = APIRouter()


@router.post("/api/proof")
async def submit_proof(
    merchant_id: str = Form(...),
    image: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Returns {"case_id", "status", "reason"}."""
    raise HTTPException(501, "Not implemented yet (Pile 2: Vision)")
