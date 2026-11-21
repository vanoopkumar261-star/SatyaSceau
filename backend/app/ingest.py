"""Shared bank-credit ingest used by POST /api/sms and the mock bank.  Owner: Pile 3 (Trust).

STUB from the scaffold. Keep the signature exactly; replace the body.
Spec: docs/WORK_SPLIT.md -> Pile 3, Step 2.
"""

from datetime import datetime
from typing import Optional

from sqlmodel import Session

from app.models import BankCredit, Merchant


def ingest_sms(
    session: Session,
    merchant: Merchant,
    sender: str,
    body: str,
    received_at: Optional[datetime],
) -> Optional[BankCredit]:
    """Parse -> save only {utr, amount, credited_at, sender_id} -> matcher.on_new_credit -> return the credit.

    Returns None (and stores nothing) when the SMS is not a genuine bank credit.
    Never store, log or print the raw SMS body.  TODO(Pile 3).
    """
    return None
