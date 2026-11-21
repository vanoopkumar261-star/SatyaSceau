"""Shared data passed between piles (frozen contract).  Owner: Pile 1 (Platform)."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class OcrResult:
    """Output of ocr.analyze_screenshot (Pile 2). Raw OCR text is never included."""

    utr: Optional[str]
    amount: Optional[float]
    confidence: float  # Tesseract confidence of the UTR token, 0-100 (0 if none)
    raw_text_len: int
    image_sha256: str
    image_phash: str  # str(imagehash.phash(...))


@dataclass
class ParsedCredit:
    """Output of sms_parser.parse_bank_sms (Pile 3)."""

    utr: str
    amount: float
    sender_id: str
