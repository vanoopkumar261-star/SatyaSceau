"""Bank SMS ingest: parse, keep only {utr, amount, time, sender}, then re-check waiting cases.
The raw SMS body is never stored, logged or printed."""
from app import matcher
from app.db import as_utc, utcnow
from app.models import BankCredit
from app.sms_parser import parse_bank_sms


def ingest_sms(session, merchant, sender, body, received_at) -> BankCredit | None:
    parsed = parse_bank_sms(sender, body)
    if parsed is None:
        return None                                   # OTP / debit / promo / untrusted sender: store nothing
    credit = BankCredit(
        merchant_id=merchant.id,
        utr=parsed.utr,
        amount=parsed.amount,
        credited_at=as_utc(received_at) or utcnow(),
        sender_id=parsed.sender_id,
    )
    session.add(credit)
    session.commit()
    session.refresh(credit)
    matcher.on_new_credit(session, credit)
    return credit
