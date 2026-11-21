"""Consent + data retention.  Owner: Pile 2 (Vision, Customer & Privacy).

STUB from the scaffold. Keep both signatures exactly; replace the bodies.
Spec: docs/WORK_SPLIT.md -> Pile 2, Step 5.
"""

from datetime import timedelta

from sqlmodel import Session, delete, or_

from app.config import settings
from app.db import utcnow
from app.models import BankCredit, Merchant


def set_consent(session: Session, merchant_id: str, given: bool) -> Merchant:
    """Opt in/out of SMS forwarding. Withdrawing (given=False) DELETES this merchant's BankCredit rows."""
    merchant = session.get(Merchant, merchant_id)
    if merchant is None:
        raise ValueError("merchant not found")
    if not given:
        session.exec(delete(BankCredit).where(BankCredit.merchant_id == merchant_id))
    merchant.consent_given = given
    merchant.consent_at = utcnow()
    session.add(merchant)
    session.commit()
    session.refresh(merchant)
    return merchant


def purge_expired_credits(session: Session) -> int:
    """Delete BankCredit rows older than settings.RETENTION_DAYS; return how many.

    Called by main.py at startup and hourly. A row counts as old if either the bank credit time
    or the time we stored it is past the cutoff (matching only needs minutes, so this is safe).
    """
    cutoff = utcnow() - timedelta(days=settings.RETENTION_DAYS)
    result = session.exec(
        delete(BankCredit).where(
            or_(BankCredit.credited_at < cutoff, BankCredit.created_at < cutoff)
        )
    )
    session.commit()
    return result.rowcount or 0
