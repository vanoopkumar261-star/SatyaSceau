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
