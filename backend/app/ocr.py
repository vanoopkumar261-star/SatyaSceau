"""Screenshot OCR: preprocessing + Tesseract + UTR/amount extraction.  Owner: Pile 2 (Vision).

STUB from the scaffold. Keep both signatures exactly; replace the bodies.
Spec: docs/WORK_SPLIT.md -> Pile 2, Steps 1-2.  Never write the image to disk; never return raw text.
"""

import hashlib

from app.schemas import OcrResult


def extract_fields(text: str) -> dict:
    """Pure function: OCR text -> {"utr": str | None, "amount": float | None}.

    TODO(Pile 2): UTR anchors + 12-digit fallback, reject 'T...' IDs and >12 digits,
    O/I/l/S/B fixes only inside number tokens, amount after ₹/Rs/INR.
    """
    return {"utr": None, "amount": None}


def analyze_screenshot(image_bytes: bytes) -> OcrResult:
    """Image bytes (in memory only) -> OcrResult.

    TODO(Pile 2): OpenCV preprocess, Tesseract --psm 6 with word confidences,
    extract_fields, utr=None below settings.OCR_MIN_CONF, real perceptual hash.
    """
    return OcrResult(
        utr=None,
        amount=None,
        confidence=0.0,
        raw_text_len=0,
        image_sha256=hashlib.sha256(image_bytes).hexdigest(),
        image_phash="",
    )
