"""Bank credit SMS parsing + sender allowlist.  Owner: Pile 3 (Verification & Trust).

STUB from the scaffold. Keep the signature exactly; replace the body.
Spec: docs/WORK_SPLIT.md -> Pile 3, Step 1.
"""

from typing import Optional

from app.schemas import ParsedCredit


def parse_bank_sms(sender: str, body: str) -> Optional[ParsedCredit]:
    """Returns ParsedCredit for a genuine bank CREDIT SMS, else None (store nothing).

    TODO(Pile 3): DLT sender regex + BANK_CODES allowlist; credits only (drop OTP/debit/promo);
    exactly-12-digit UTR; amount. Must accept the agreed demo format:
      sender "AX-HDFCBK", "Rs.{amount:.2f} credited to A/c XX1234 on {dd-mm-yy} by UPI Ref No {utr}. -HDFC Bank"
    """
    return None
