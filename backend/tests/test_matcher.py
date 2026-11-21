from datetime import datetime, timezone

from sqlmodel import select

from app import ingest, matcher
from app.models import BankCredit, Merchant

DEMO = "Rs.120.00 credited to A/c XX1234 on 22-11-26 by UPI Ref No 618656730702. -HDFC Bank"


def _merchant(session):
    m = Merchant(name="Ramu Tea", upi_id="ramu@okaxis", consent_given=True)
    session.add(m)
    session.commit()
    return m


# ---- ingest ----

def test_ingest_stores_minimal_credit_and_triggers_matcher(session, monkeypatch):
    seen = []
    monkeypatch.setattr(matcher, "on_new_credit", lambda s, c: seen.append(c.utr) or [])
    m = _merchant(session)
    when = datetime(2026, 11, 22, 1, 0)                       # naive from the forwarder -> treated as UTC
    credit = ingest.ingest_sms(session, m, "AX-HDFCBK", DEMO, when)
    assert (credit.utr, credit.amount, credit.sender_id) == ("618656730702", 120.0, "AX-HDFCBK")
    assert credit.credited_at == when.replace(tzinfo=timezone.utc)
    assert seen == ["618656730702"]
    assert not hasattr(credit, "body") and "credited to" not in repr(credit)   # no raw SMS kept


def test_ingest_drops_otp_and_stores_nothing(session, monkeypatch):
    monkeypatch.setattr(matcher, "on_new_credit", lambda s, c: (_ for _ in ()).throw(AssertionError("called")))
    m = _merchant(session)
    assert ingest.ingest_sms(session, m, "AX-HDFCBK", "123456 is your OTP. Rs.1 credited UPI Ref No 618656730702", None) is None
    assert session.exec(select(BankCredit)).all() == []


def test_ingest_without_received_at_uses_now(session, monkeypatch):
    monkeypatch.setattr(matcher, "on_new_credit", lambda s, c: [])
    credit = ingest.ingest_sms(session, _merchant(session), "AX-HDFCBK", DEMO, None)
    assert credit.credited_at.tzinfo is not None
