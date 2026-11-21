"""Screenshot OCR: preprocessing + Tesseract + UTR/amount extraction.  Owner: Pile 2 (Vision).

STUB from the scaffold. Keep both signatures exactly; replace the bodies.
Spec: docs/WORK_SPLIT.md -> Pile 2, Steps 1-2.  Never write the image to disk; never return raw text.
"""

import hashlib
import re
from io import BytesIO

import cv2
import imagehash
import numpy as np
import pytesseract
from PIL import Image

from app.config import settings
from app.schemas import OcrResult

# --- UTR -------------------------------------------------------------------

# Tesseract confusions, applied ONLY inside a candidate 12-char number token.
_OCR_FIX = str.maketrans("OoIlSB", "001158")
_TOKEN = r"([A-Za-z0-9]{4}[ ][A-Za-z0-9]{4}[ ][A-Za-z0-9]{4}(?![A-Za-z0-9])|[A-Za-z0-9]+)"
# Preferred anchors first; "Transaction ID" is a weaker anchor (only if exactly 12 digits).
_UTR_ANCHOR = re.compile(
    r"(?<![A-Za-z])(?:UPI\s*Ref(?:erence)?(?:\s*(?:No|Number|ID))?|UTR(?:\s*(?:No|Number))?"
    r"|RRN|Ref(?:erence)?\s*(?:No|Number))\.?\s*[:#\-]?\s*" + _TOKEN,
    re.I,
)
_TXN_ANCHOR = re.compile(r"(?<![A-Za-z])Transaction\s*ID\s*[:#\-]?\s*" + _TOKEN, re.I)
_FALLBACK = re.compile(r"(?<![A-Za-z0-9])[0-9OoIlSB]{12}(?![A-Za-z0-9])")
_DIGITS12 = re.compile(r"[0-9]{12}")


def _as_utr(token: str, min_real_digits: int = 8) -> str | None:
    """Return a clean 12-digit UTR from a candidate token, else None."""
    token = token.replace(" ", "")
    if len(token) != 12 or token[0] in "Tt":  # >12 chars / PhonePe 'T...' ids are not UTRs
        return None
    if sum(c in "0123456789" for c in token) < min_real_digits:  # a word, not a number
        return None
    fixed = token.translate(_OCR_FIX)
    return fixed if _DIGITS12.fullmatch(fixed) else None


def _find_utr(text: str) -> str | None:
    for m in _UTR_ANCHOR.finditer(text):
        utr = _as_utr(m.group(1))
        if utr:
            return utr
    for m in _TXN_ANCHOR.finditer(text):
        tok = m.group(1).replace(" ", "")
        if _DIGITS12.fullmatch(tok):  # no OCR fixes here: only a clean 12-digit id counts
            return tok
    for m in _FALLBACK.finditer(text):
        utr = _as_utr(m.group(0), min_real_digits=10)
        if utr:
            return utr
    return None


# --- Amount ----------------------------------------------------------------

_NUM = r"(\d[\d,]*(?:\.\d{1,2})?)"
# ₹ / Rs / Rs. / INR, and the usual Tesseract misreads of ₹ (% X x € ¥ £) glued to the number.
_AMT_SYMBOL = re.compile(r"(?:(?<![A-Za-z])(?:Rs\.?|INR)\s*|₹\s*|(?<![\w.,])[%Xx€¥£]\s?)" + _NUM, re.I)
_AMT_KEYWORD = re.compile(r"paid|successful|sent|paying", re.I)
# Lines with a time or a month name are dates ("01:31 am on 22 Nov 2026"), never the amount.
_DATE_LINE = re.compile(
    r"\b\d{1,2}:\d{2}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\b", re.I
)
# Standalone number: not part of a date/time/id ("12:30", "22/11/2026", "AB123").
_AMT_STANDALONE = re.compile(r"(?<![\w.,:/\-])(\d{1,7}(?:,\d{2,3})*(?:\.\d{1,2})?)(?![\w:/\-]|\.\d)")


def _to_amount(s: str) -> float | None:
    try:
        value = float(s.replace(",", ""))
    except ValueError:
        return None
    return value if 0 < value < 10_000_000 else None


def _find_amount(text: str, utr: str | None) -> float | None:
    for m in _AMT_SYMBOL.finditer(text):
        amount = _to_amount(m.group(1))
        if amount is not None and len(m.group(1).replace(",", "").split(".")[0]) <= 8:
            return amount
    # No currency symbol survived OCR: look for a lone number next to "paid/successful/sent".
    # (A leading '₹' misread as '2' cannot be told apart from a real digit; the matcher then
    # sees a different amount than the bank and fails safe.)
    lines = text.replace(utr, "").splitlines() if utr else text.splitlines()
    for i, line in enumerate(lines):
        if _AMT_KEYWORD.search(line):
            for near in lines[max(0, i - 2) : i + 3]:
                if _DATE_LINE.search(near):
                    continue
                for m in _AMT_STANDALONE.finditer(near):
                    amount = _to_amount(m.group(1))
                    if amount is not None:
                        return amount
    return None


def extract_fields(text: str) -> dict:
    """Pure function: OCR text -> {"utr": str | None, "amount": float | None}.

    None means "not sure"; we never guess.
    """
    utr = _find_utr(text)
    return {"utr": utr, "amount": _find_amount(text, utr)}


def _preprocess(image_bytes: bytes) -> np.ndarray | None:
    """Decode in memory (nothing touches disk) and clean up for Tesseract.

    Tuned on real PhonePe/GPay screenshots: both are dark-mode, where an adaptive threshold
    destroyed the text. Plain greyscale (inverted when dark) + upscale reads them at 85-96 conf.
    """
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    width = img.shape[1]
    if width < 2000:  # phone screenshots are 700-1100 px wide; ~2000 px reads best
        scale = min(3, max(2, round(2000 / width)))
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    grey = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if grey.mean() < 127:  # dark-mode app (light text on dark): Tesseract wants dark text on light
        grey = 255 - grey
    return grey


def _utr_confidence(words: list[tuple[str, float]], utr: str) -> float:
    """Tesseract confidence (0-100) of the word(s) that make up the UTR; 0 if not found."""
    # Word i of the UTR may be the whole number or a 4-digit group of it.
    for start in range(len(words)):
        joined = ""
        confs = []
        for text, conf in words[start : start + 3]:
            joined += text
            confs.append(conf)
            fixed = joined.translate(_OCR_FIX)
            if fixed == utr or fixed.endswith(utr):
                return sum(confs) / len(confs)
            if len(joined) > 16:
                break
    return 0.0


def analyze_screenshot(image_bytes: bytes) -> OcrResult:
    """Image bytes (in memory only) -> OcrResult. Never returns or stores the raw text."""
    sha = hashlib.sha256(image_bytes).hexdigest()
    try:
        phash = str(imagehash.phash(Image.open(BytesIO(image_bytes))))
    except Exception:
        phash = ""
    processed = _preprocess(image_bytes)
    if processed is None:
        return OcrResult(None, None, 0.0, 0, sha, phash)

    if settings.TESSERACT_CMD:
        pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
    data = pytesseract.image_to_data(
        processed, lang="eng", config="--psm 6", output_type=pytesseract.Output.DICT
    )

    # Rebuild text line by line and keep (word, confidence) pairs.
    lines: dict[tuple, list[str]] = {}
    words: list[tuple[str, float]] = []
    for text, conf, *key in zip(
        data["text"], data["conf"], data["block_num"], data["par_num"], data["line_num"]
    ):
        text = text.strip()
        if not text or float(conf) < 0:
            continue
        lines.setdefault(tuple(key), []).append(text)
        words.append((text, float(conf)))
    text = "\n".join(" ".join(ws) for ws in lines.values())

    fields = extract_fields(text)
    utr, confidence = fields["utr"], 0.0
    if utr:
        confidence = _utr_confidence(words, utr)
        if confidence < settings.OCR_MIN_CONF:
            utr = None  # not sure -> don't guess; the matcher asks for a retake
    return OcrResult(
        utr=utr,
        amount=fields["amount"],
        confidence=confidence,
        raw_text_len=len(text),
        image_sha256=sha,
        image_phash=phash,
    )
