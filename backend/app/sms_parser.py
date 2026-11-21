"""Bank credit-SMS parser. Trust only official DLT bank sender IDs; keep only credits with a UTR."""
import re

from app.schemas import ParsedCredit

BANK_CODES = {
    "HDFCBK", "SBIUPI", "SBIINB", "ICICIB", "AXISBK", "KOTAKB", "PNBSMS", "BOIIND",
    "UNIONB", "CANBNK", "IDFCFB", "YESBNK", "PAYTMB", "AIRBNK", "INDBNK",
}

# DLT sender: 2-letter operator/circle prefix, 6-char header, optional TRAI suffix (-S, -T, -P, -G).
_SENDER = re.compile(r"^[A-Z]{2}-([A-Z0-9]{6})(-[A-Z])?$")
_OTP = re.compile(r"\bOTP\b|one\s*time\s*password", re.I)
_DEBIT = re.compile(r"\b(debited|withdrawn|spent)\b", re.I)
_DEBIT_DR = re.compile(r"\bDR\b")                      # uppercase only: don't trip on "Dr." in names
_CREDIT = re.compile(r"\b(credited|received|deposited)\b", re.I)
_CREDIT_CR = re.compile(r"\bCR\b")
_UTR = re.compile(
    r"(?:\b(?:UPI\s*)?Ref(?:erence)?\.?\s*(?:No\.?)?|\bUTR|\bRRN)\s*[:#.-]?\s*(\d{12})(?!\d)"
    r"|UPI/CR/(\d{12})(?!\d)", re.I)
_AMOUNT = re.compile(r"(?:\bRs\.?|\bINR|₹)\s*([0-9][0-9,]*(?:\.\d{1,2})?)", re.I)


def parse_bank_sms(sender: str, body: str) -> ParsedCredit | None:
    """Return the credit (utr, amount, sender) or None. None means: store nothing."""
    sender = (sender or "").strip().upper()
    m = _SENDER.match(sender)
    if not m or m.group(1) not in BANK_CODES:
        return None                                    # phone numbers, unknown or spoofed headers
    body = body or ""
    if _OTP.search(body) or _DEBIT.search(body) or _DEBIT_DR.search(body):
        return None
    if not (_CREDIT.search(body) or _CREDIT_CR.search(body)):
        return None                                    # promos, balance alerts, anything not a credit
    u = _UTR.search(body)
    a = _AMOUNT.search(body)
    if not u or not a:
        return None
    try:
        amount = float(a.group(1).replace(",", ""))
    except ValueError:
        return None
    return ParsedCredit(utr=u.group(1) or u.group(2), amount=amount, sender_id=sender)
