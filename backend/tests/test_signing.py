import base64
import json

import pytest
from sqlmodel import select

from app import ingest, matcher, signing
from app.config import settings
from app.db import utcnow
from app.models import BankCredit, Case, CaseStatus, Merchant, Record


@pytest.fixture(autouse=True)
def tmp_key(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SIGNING_KEY_PATH", tmp_path / "key.pem")
    return tmp_path / "key.pem"

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


# ---- signing ----

def _final_case(session, status=CaseStatus.VERIFIED):
    mid, _ = _merchant(session)
    now = utcnow()
    c = Case(merchant_id=mid, status=status, reason="Payment received in bank", utr="618656730702",
             amount=120.0, image_sha256="a" * 64, image_phash="", bank_credited_at=now, decided_at=now)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def test_sign_then_verify(session, tmp_key):
    rec = signing.sign_case(session, _final_case(session))
    assert tmp_key.exists()
    assert signing.verify_record(rec.record_json, rec.signature)
    assert signing.verify_record(json.loads(rec.record_json), rec.signature)          # dict form too
    body = json.loads(rec.record_json)
    assert body["verdict"] == "VERIFIED" and body["amount"] == 120.0 and body["utr"] == "618656730702"


def test_changing_one_field_fails(session):
    rec = signing.sign_case(session, _final_case(session))
    tampered = json.loads(rec.record_json) | {"amount": 1200.0}
    assert not signing.verify_record(tampered, rec.signature)


def test_bad_signature_or_garbage_is_false_not_error(session):
    rec = signing.sign_case(session, _final_case(session))
    flipped = base64.b64encode(bytes([base64.b64decode(rec.signature)[0] ^ 1]) + base64.b64decode(rec.signature)[1:]).decode()
    assert not signing.verify_record(rec.record_json, flipped)
    assert not signing.verify_record("not json", rec.signature)
    assert not signing.verify_record(rec.record_json, "%%%not-base64")
    assert not signing.verify_record("[1,2]", rec.signature)


def test_second_sign_returns_same_record(session):
    c = _final_case(session)
    first = signing.sign_case(session, c)
    c.reason = "changed after the fact"
    second = signing.sign_case(session, c)
    assert (second.signature, second.record_json) == (first.signature, first.record_json)
    assert len(session.exec(select(Record)).all()) == 1


def test_waiting_case_is_never_signed(session):
    with pytest.raises(ValueError):
        signing.sign_case(session, _final_case(session, status=CaseStatus.WAITING))


def test_key_persists_across_restarts(session, tmp_key):
    pk = signing.public_key_b64()
    assert len(base64.b64decode(pk)) == 32
    signing._keys.clear()                                       # simulate a restart
    assert signing.public_key_b64() == pk


def test_public_key_endpoint(client):
    r = client.get("/api/public-key").json()
    assert r == {"algorithm": "Ed25519", "public_key": signing.public_key_b64()}


def test_record_api_and_verify_endpoint(client, session):
    rec = signing.sign_case(session, _final_case(session))
    assert client.get("/api/records/nope123").status_code == 404
    got = client.get(f"/api/records/{rec.case_id}").json()
    assert got["record"] == json.loads(rec.record_json) and got["signature"] == rec.signature
    assert got["record_sha256"] == rec.record_sha256 and got["public_key"] == signing.public_key_b64()
    ok = client.post("/api/records/verify", json={"record_json": got["record_json"], "signature": got["signature"]})
    assert ok.json() == {"valid": True}
    tampered = got["record"] | {"verdict": "VERIFIED", "amount": 9999}
    assert client.post("/api/records/verify", json={"record_json": tampered, "signature": got["signature"]}).json() == {"valid": False}
    assert client.post("/api/records/verify", json={"record_json": "{}", "signature": "@@@"}).json() == {"valid": False}


def test_record_page_served_with_safe_headers(client, session):
    rec = signing.sign_case(session, _final_case(session))
    assert client.get("/record/nope123").status_code == 404
    assert client.get("/record/bad..id").status_code in (404, 422)
    r = client.get(f"/record/{rec.case_id}")
    assert r.status_code == 200 and "Verify this record" in r.text
    assert r.headers["referrer-policy"] == "no-referrer" and "default-src 'none'" in r.headers["content-security-policy"]


def test_full_flow_produces_a_valid_record(session):
    mid, _ = _merchant(session)
    m = session.get(Merchant, mid)
    c = Case(merchant_id=mid, status=CaseStatus.WAITING, reason="Checking…", utr="618656730702",
             amount=120.0, image_sha256="b" * 64, image_phash="")
    session.add(c)
    session.commit()
    matcher.evaluate_case(session, c)
    ingest.ingest_sms(session, m, "AX-HDFCBK", DEMO, None)
    rec = session.get(Record, c.id)
    assert rec is not None and json.loads(rec.record_json)["verdict"] == "VERIFIED"
    assert signing.verify_record(rec.record_json, rec.signature)


def test_record_page_csp_allows_only_google_fonts_as_external(client, session, signed=None):
    from app.routes_records import PAGE_HEADERS

    csp = PAGE_HEADERS["Content-Security-Policy"]
    assert "default-src 'none'" in csp and "frame-ancestors 'none'" in csp
    assert "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com;" in csp
    assert "font-src https://fonts.gstatic.com;" in csp
    assert "script-src 'self' 'unsafe-inline';" in csp  # no external scripts
