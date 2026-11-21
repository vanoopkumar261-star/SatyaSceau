from sqlmodel import select

from app import matcher
from app.models import BankCredit, Merchant

DEMO = "Rs.120.00 credited to A/c XX1234 on 22-11-26 by UPI Ref No 618656730702. -HDFC Bank"


# Only the shared `session` + `client` fixtures (same DB) are used, per WORK_SPLIT §4.
def _merchant(session, consent=True):
    m = Merchant(name="Ramu Tea", upi_id="ramu@okaxis", consent_given=consent)
    session.add(m)
    session.commit()
    session.refresh(m)
    return m.id, m.api_token


def _credits(session):
    session.expire_all()
    return session.exec(select(BankCredit)).all()


# ---- /api/sms ----

def test_sms_missing_or_wrong_token_is_401(client, session):
    _merchant(session)
    assert client.post("/api/sms", json={"sender": "AX-HDFCBK", "body": DEMO}).status_code == 401
    assert client.post("/api/sms", json={"sender": "AX-HDFCBK", "body": DEMO}, headers={"X-Token": "nope"}).status_code == 401


def test_sms_consent_off_is_403(client, session):
    _, token = _merchant(session, consent=False)
    r = client.post("/api/sms", json={"sender": "AX-HDFCBK", "body": DEMO}, headers={"X-Token": token})
    assert r.status_code == 403 and r.json() == {"detail": "consent required"}
    assert _credits(session) == []


def test_sms_otp_is_200_but_stores_nothing(client, session):
    _, token = _merchant(session)
    r = client.post("/api/sms", json={"sender": "AX-HDFCBK", "body": "Your OTP is 123456"}, headers={"X-Token": token})
    assert r.status_code == 200 and r.json() == {"accepted": False}
    assert _credits(session) == []


def test_sms_credit_accepted_with_received_at(client, session, monkeypatch):
    monkeypatch.setattr(matcher, "on_new_credit", lambda s, c: [])
    _, token = _merchant(session)
    r = client.post("/api/sms", json={"sender": "AX-HDFCBK", "body": DEMO, "received_at": "2026-11-22T01:00:00"},
                    headers={"X-Token": token})
    assert r.json() == {"accepted": True}
    (c,) = _credits(session)
    assert (c.utr, c.amount) == ("618656730702", 120.0)


def test_sms_oversized_body_rejected(client, session):
    _, token = _merchant(session)
    assert client.post("/api/sms", json={"sender": "AX-HDFCBK", "body": "x" * 5000},
                       headers={"X-Token": token}).status_code == 422
