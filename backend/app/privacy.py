"""Consent + data retention.  Owner: Pile 2 (Vision, Customer & Privacy).

STUB from the scaffold. Keep both signatures exactly; replace the bodies.
Spec: docs/WORK_SPLIT.md -> Pile 2, Step 5.
"""

from sqlmodel import Session

from app.db import utcnow
from app.models import Merchant


def set_consent(session: Session, merchant_id: str, given: bool) -> Merchant:
    """Opt in/out of SMS forwarding.

    TODO(Pile 2): withdrawing consent (given=False) must DELETE this merchant's BankCredit rows.
    """
    merchant = session.get(Merchant, merchant_id)
    if merchant is None:
        raise ValueError("merchant not found")
    merchant.consent_given = given
    merchant.consent_at = utcnow()
    session.add(merchant)
    session.commit()
    session.refresh(merchant)
    return merchant


def purge_expired_credits(session: Session) -> int:
    """Delete BankCredit rows older than settings.RETENTION_DAYS; return how many.

    Called by main.py at startup and hourly.  TODO(Pile 2).
    """
    return 0
