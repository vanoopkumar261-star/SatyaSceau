"""Consent + retention tests.  Owner: Pile 2 (Vision, Customer & Privacy).

Spec: docs/WORK_SPLIT.md -> Pile 2, Step 7.
"""

from datetime import timedelta

from sqlmodel import select

from app import privacy
from app.db import utcnow
from app.models import BankCredit, Merchant


def _merchant(session, name="Shop"):
    m = Merchant(name=name)
    session.add(m)
    session.commit()
    session.refresh(m)
    return m


def _credit(session, merchant, utr, age_days=0):
    t = utcnow() - timedelta(days=age_days)
    session.add(BankCredit(merchant_id=merchant.id, utr=utr, amount=10.0, credited_at=t,
                           sender_id="AX-HDFCBK", created_at=t))
    session.commit()


def _utrs(session):
    return {c.utr for c in session.exec(select(BankCredit)).all()}


def test_withdraw_consent_deletes_only_that_merchants_credits(session):
    a, b = _merchant(session, "A"), _merchant(session, "B")
    _credit(session, a, "111111111111")
    _credit(session, b, "222222222222")
    privacy.set_consent(session, a.id, True)
    assert _utrs(session) == {"111111111111", "222222222222"}  # opting in deletes nothing
    m = privacy.set_consent(session, a.id, False)
    assert m.consent_given is False and m.consent_at is not None
    assert _utrs(session) == {"222222222222"}


def test_purge_removes_only_rows_older_than_retention(session):
    m = _merchant(session)
    _credit(session, m, "100000000001", age_days=8)
    _credit(session, m, "100000000002", age_days=6)
    _credit(session, m, "100000000003", age_days=0)
    assert privacy.purge_expired_credits(session) == 1
    assert _utrs(session) == {"100000000002", "100000000003"}
    assert privacy.purge_expired_credits(session) == 0


def test_consent_endpoint_auth(client, session):
    m = _merchant(session)
    url = f"/api/merchants/{m.id}/consent"
    assert client.post(url, json={"given": True}).status_code == 401
    assert client.post(url, json={"given": True}, headers={"X-Token": "wrong"}).status_code == 401
    assert client.post("/api/merchants/nope/consent", json={"given": True},
                       headers={"X-Token": m.api_token}).status_code == 404
    r = client.post(url, json={"given": True}, headers={"X-Token": m.api_token})
    assert r.status_code == 200 and r.json() == {"consent_given": True}
    r = client.post(url, json={"given": False}, headers={"X-Token": m.api_token})
    assert r.json() == {"consent_given": False}


# --- mock bank (demo backup) ---------------------------------------------------


def test_mock_bank_sends_the_agreed_demo_sms(client, session, monkeypatch):
    from app import ingest

    m = _merchant(session)
    seen = {}

    def fake_ingest(sess, merchant, sender, body, received_at):
        seen.update(merchant=merchant.id, sender=sender, body=body)
        return BankCredit(merchant_id=merchant.id, utr="x", amount=1, credited_at=received_at, sender_id=sender)

    monkeypatch.setattr(ingest, "ingest_sms", fake_ingest)
    r = client.post("/api/mock-bank", json={"merchant_id": m.id, "utr": "412345678901", "amount": 1250, "k": m.screen_key})
    assert r.status_code == 200 and r.json() == {"accepted": True}
    assert seen["sender"] == "AX-HDFCBK" and seen["merchant"] == m.id
    assert seen["body"].startswith("Rs.1250.00 credited to A/c XX1234 on ")
    assert seen["body"].endswith(" by UPI Ref No 412345678901. -HDFC Bank")


def test_mock_bank_not_accepted_and_unknown_merchant(client, session, monkeypatch):
    from app import ingest

    m = _merchant(session)
    monkeypatch.setattr(ingest, "ingest_sms", lambda *a, **k: None)
    r = client.post("/api/mock-bank", json={"merchant_id": m.id, "utr": "1", "amount": 5, "k": m.screen_key})
    assert r.json() == {"accepted": False}
    assert client.post("/api/mock-bank", json={"merchant_id": "nope", "utr": "1", "amount": 5}).status_code == 404
    assert client.get("/mock-bank").status_code == 200


def test_mock_bank_requires_the_shop_screen_key(client, session, monkeypatch):
    """The merchant id is public (QR). Without the key a customer could fake a credit for their own UTR."""
    from app import ingest

    m = _merchant(session)
    called = []
    monkeypatch.setattr(ingest, "ingest_sms", lambda *a, **k: called.append(1))
    body = {"merchant_id": m.id, "utr": "412345678901", "amount": 1}
    assert client.post("/api/mock-bank", json=body).status_code == 403
    assert client.post("/api/mock-bank", json=body | {"k": "wrong"}).status_code == 403
    assert client.post("/api/mock-bank", json=body | {"k": m.api_token}).status_code == 403
    assert called == []
