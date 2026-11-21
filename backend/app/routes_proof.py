"""POST /api/proof: the customer uploads the payment screenshot.  Owner: Pile 2 (Vision).

Spec: docs/WORK_SPLIT.md -> Pile 2, Step 3.
Flow: validate -> ocr.analyze_screenshot -> create Case(WAITING) -> matcher.evaluate_case -> respond.
The matcher (Pile 3) is the only place that sets a verdict; we just pass the OcrResult through.

Privacy note (README limitations): the image is held in memory only. Starlette may spool
uploads over 1 MB to a temp file; it is deleted when we close the upload right after reading.
"""

from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from PIL import Image
from sqlmodel import Session

from app import matcher, ocr
from app.config import settings
from app.db import get_session
from app.models import Case, CaseStatus, Merchant

router = APIRouter()

ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.post("/api/proof")
async def submit_proof(
    merchant_id: str = Form(...),
    image: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Returns {"case_id", "status", "reason"}."""
    if session.get(Merchant, merchant_id) is None:
        await image.close()
        raise HTTPException(404, "merchant not found")
    if image.content_type not in ALLOWED_TYPES:
        await image.close()
        raise HTTPException(415, "image must be JPEG, PNG or WebP")

    limit = settings.MAX_UPLOAD_MB * 1024 * 1024
    data = await image.read(limit + 1)  # never buffer more than limit+1 bytes
    await image.close()  # drops Starlette's temp spool file, if any
    if len(data) > limit:
        raise HTTPException(413, f"image larger than {settings.MAX_UPLOAD_MB} MB")
    try:
        with Image.open(BytesIO(data)) as probe:
            probe.verify()
    except Exception:
        raise HTTPException(400, "could not read image")

    result = await run_in_threadpool(ocr.analyze_screenshot, data)  # CPU-heavy: off the event loop
    del data

    case = Case(
        merchant_id=merchant_id,
        status=CaseStatus.WAITING,
        reason="Checking…",
        utr=result.utr,
        amount=result.amount,
        image_sha256=result.image_sha256,
        image_phash=result.image_phash,
        ocr_confidence=result.confidence,
    )
    session.add(case)
    session.commit()
    case = matcher.evaluate_case(session, case)
    return {"case_id": case.id, "status": case.status, "reason": case.reason}
