"""Merchant screen API: screen-key auth, recent cases, additive DB migration.  Owner: Pile 1."""

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from sqlalchemy import inspect
from sqlmodel import create_engine, select
from sqlmodel.pool import StaticPool

from app.db import init_db, utcnow
from app.models import Case


def _new_merchant(client):
    m = client.post("/api/merchants", json={"name": "Shop"}).json()
    url = urlparse(m["merchant_url"])
    key = parse_qs(url.fragment)["k"][0]
    assert parse_qs(url.query)["m"][0] == m["id"]
    return m, key


def test_merchant_url_carries_screen_key_in_fragment(client):
    m, key = _new_merchant(client)
    assert len(key) >= 16
    assert key != m["api_token"]  # read-only key, never the SMS-ingest token


def test_cases_list_requires_the_screen_key(client):
    m, key = _new_merchant(client)
    base = f"/api/merchants/{m['id']}/cases"
    assert client.get(base).status_code == 403
    assert client.get(base, params={"k": "wrong"}).status_code == 403
    assert client.get(base, params={"k": m["api_token"]}).status_code == 403
    assert client.get("/api/merchants/nope/cases", params={"k": key}).status_code == 404
    r = client.get(base, params={"k": key})
    assert r.status_code == 200
    assert r.json()["merchant"]["name"] == "Shop"
    assert r.json()["cases"] == []


def test_stream_requires_the_screen_key(client):
    m, _ = _new_merchant(client)
    r = client.get(f"/api/merchants/{m['id']}/stream", params={"k": "wrong"})
    assert r.status_code == 403
    assert client.get("/api/merchants/nope/stream", params={"k": "x"}).status_code == 404


def test_cases_list_is_newest_first_and_only_this_merchant(client, session):
    m, key = _new_merchant(client)
    other, _ = _new_merchant(client)
    now = utcnow()
    for i in range(3):
        session.add(Case(merchant_id=m["id"], utr=f"00000000000{i}", created_at=now + timedelta(seconds=i)))
    session.add(Case(merchant_id=other["id"], utr="999999999999"))
    session.commit()

    r = client.get(f"/api/merchants/{m['id']}/cases", params={"k": key, "limit": 2})
    utrs = [c["utr"] for c in r.json()["cases"]]
    assert utrs == ["000000000002", "000000000001"]


def test_init_db_adds_new_columns_to_an_old_database():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    with eng.begin() as conn:  # a 'merchants' table from before screen_key existed
        conn.exec_driver_sql(
            "CREATE TABLE merchants (id VARCHAR PRIMARY KEY, name VARCHAR, upi_id VARCHAR, "
            "api_token VARCHAR, consent_given BOOLEAN, consent_at DATETIME, created_at DATETIME)"
        )
    init_db(eng)
    columns = {c["name"] for c in inspect(eng).get_columns("merchants")}
    assert "screen_key" in columns
    eng.dispose()


def test_base_url_is_read_live_from_env_file(tmp_path, monkeypatch, client):
    """demo_tunnel.py rewrites .env while the server runs: new QR codes must follow without a restart."""
    from app import config

    env = tmp_path / ".env"
    monkeypatch.setattr(config, "ENV_FILE", env)
    monkeypatch.setattr(config, "_REAL_ENV_BASE_URL", None)
    env.write_text("BASE_URL=https://first.trycloudflare.com/\n", encoding="utf-8")
    first = client.post("/api/merchants", json={"name": "A"}).json()
    env.write_text("BASE_URL=https://second.trycloudflare.com\n", encoding="utf-8")
    second = client.post("/api/merchants", json={"name": "B"}).json()
    assert first["pay_url"].startswith("https://first.trycloudflare.com/pay/")
    assert second["pay_url"].startswith("https://second.trycloudflare.com/pay/")


# --- merchant pastes a bank SMS by hand ---------------------------------------------

def _paste(client, m, key, body, bank="HDFCBK"):
    return client.post(f"/api/merchants/{m['id']}/bank-sms", json={"k": key, "bank": bank, "body": body})


def test_pasted_bank_sms_verifies_a_waiting_case(client, session):
    from app.models import BankCredit

    m, key = _new_merchant(client)
    case = Case(merchant_id=m["id"], utr="431876509123", amount=150.0, image_sha256="img-paste")  # WAITING
    session.add(case)
    session.commit()
    case_id = case.id
    sms = "Rs.150.00 credited to A/c XX1234 on 22-11-26 by UPI Ref No 431876509123. -HDFC Bank"

    r = _paste(client, m, key, sms)
    assert r.status_code == 200 and r.json() == {"accepted": True, "utr": "431876509123", "amount": 150.0}
    assert client.get(f"/api/cases/{case_id}").json()["status"] == "VERIFIED"
    credit = session.exec(select(BankCredit).where(BankCredit.utr == "431876509123")).first()
    assert credit.sender_id == "MP-HDFCBK"  # evidence shows it was pasted by hand


def test_pasted_sms_needs_key_and_known_bank_and_a_real_credit(client):
    m, key = _new_merchant(client)
    sms = "Rs.1.00 credited to A/c XX1234 by UPI Ref No 111122223333. -HDFC Bank"
    assert _paste(client, m, "", sms).status_code == 403
    assert _paste(client, m, m["api_token"], sms).status_code == 403
    assert _paste(client, m, key, sms, bank="FAKEBK").status_code == 422
    r = _paste(client, m, key, "123456 is your OTP. Do not share. -HDFC")
    assert r.status_code == 200 and r.json()["accepted"] is False and "12-digit" in r.json()["reason"]


# --- merchant uploads an IMAGE of the bank credit -------------------------------------------

def _png_bytes():
    from io import BytesIO
    from PIL import Image as PILImage

    buf = BytesIO()
    PILImage.new("RGB", (40, 20), "white").save(buf, "PNG")
    return buf.getvalue()


def _upload(client, m, key, bank="HDFCBK", ctype="image/png", data=None):
    return client.post(f"/api/merchants/{m['id']}/bank-image", data={"k": key, "bank": bank},
                       files={"image": ("sms.png", data or _png_bytes(), ctype)})


def test_bank_image_verifies_a_waiting_case(client, session, monkeypatch):
    from app import ocr
    from app.models import BankCredit

    m, key = _new_merchant(client)
    case = Case(merchant_id=m["id"], utr="431876509123", amount=150.0, image_sha256="img-bankimg")
    session.add(case)
    session.commit()
    case_id = case.id
    monkeypatch.setattr(ocr, "extract_text", lambda b: "Rs.150.00 credited to A/c XX1234 on 22-11-26 by UPI Ref No 431876509123. -HDFC Bank")
    r = _upload(client, m, key)
    assert r.status_code == 200 and r.json() == {"accepted": True, "utr": "431876509123", "amount": 150.0}
    assert client.get(f"/api/cases/{case_id}").json()["status"] == "VERIFIED"
    credit = session.exec(select(BankCredit).where(BankCredit.utr == "431876509123")).first()
    assert credit.sender_id == "MI-HDFCBK"  # evidence shows it came from a merchant-uploaded image


def test_bank_image_rejects_non_credit_bad_key_and_bad_type(client, monkeypatch):
    from app import ocr

    m, key = _new_merchant(client)
    monkeypatch.setattr(ocr, "extract_text", lambda b: "Rs.150.00 debited from A/c XX1234 UPI Ref No 431876509123")
    r = _upload(client, m, key)
    assert r.status_code == 200 and r.json()["accepted"] is False and "12-digit" in r.json()["reason"]
    assert _upload(client, m, "wrong").status_code == 403
    assert _upload(client, m, key, bank="FAKEBK").status_code == 422
    assert _upload(client, m, key, ctype="application/pdf").status_code == 415
    assert _upload(client, m, key, data=b"not an image").status_code == 400


# --- "Show detection details" --------------------------------------------------------------

def _states(client, case_id, key):
    r = client.get(f"/api/cases/{case_id}/details", params={"k": key})
    assert r.status_code == 200
    return {c["key"]: c["state"] for c in r.json()["checks"]}, r.json()


def test_details_need_the_screen_key(client, session):
    m, key = _new_merchant(client)
    case = Case(merchant_id=m["id"], utr="431876509123", amount=1.0, image_sha256="x")
    session.add(case)
    session.commit()
    assert client.get(f"/api/cases/{case.id}/details").status_code == 403
    assert client.get(f"/api/cases/{case.id}/details", params={"k": "wrong"}).status_code == 403
    assert client.get("/api/cases/nope/details", params={"k": key}).status_code == 404


def test_details_explain_waiting_then_verified_then_replay(client, session):
    m, key = _new_merchant(client)
    first = Case(merchant_id=m["id"], utr="431876509123", amount=150.0, ocr_confidence=91, image_sha256="a" * 64)
    session.add(first)
    session.commit()
    states, body = _states(client, first.id, key)
    assert states["ocr"] == "pass" and states["replay"] == "pass" and states["duplicate"] == "pass"
    assert states["bank"] == "wait" and states["signed"] == "wait"
    assert body["params"]["match_window_min"] == 5

    sms = "Rs.150.00 credited to A/c XX1234 on 22-11-26 by UPI Ref No 431876509123. -HDFC Bank"
    _paste(client, m, key, sms)
    states, body = _states(client, first.id, key)
    assert body["status"] == "VERIFIED"
    assert all(states[k] == "pass" for k in ("ocr", "replay", "duplicate", "bank", "window", "amount", "signed"))
    bank = next(c for c in body["checks"] if c["key"] == "bank")
    assert "pasted by merchant" in bank["detail"]

    from app import matcher
    again = Case(merchant_id=m["id"], utr="431876509123", amount=150.0, ocr_confidence=90, image_sha256="b" * 64)
    session.add(again)
    session.commit()
    matcher.evaluate_case(session, again)
    states, _ = _states(client, again.id, key)
    assert states["replay"] == "fail"


def test_details_for_an_unreadable_screenshot(client, session):
    m, key = _new_merchant(client)
    case = Case(merchant_id=m["id"], utr=None, image_sha256="c" * 64)
    session.add(case)
    session.commit()
    states, _ = _states(client, case.id, key)
    assert states["ocr"] == "fail" and states["replay"] == "skip" and states["bank"] == "skip"


def test_details_never_claim_ocr_read_an_amount_the_bank_supplied(client, session):
    """OCR missed the amount; the matcher used the bank's. The panel must keep saying so after VERIFIED."""
    m, key = _new_merchant(client)
    case = Case(merchant_id=m["id"], utr="431876509123", amount=None, ocr_confidence=88, image_sha256="d" * 64)
    session.add(case)
    session.commit()
    _paste(client, m, key, "Rs.250.00 credited to A/c XX1234 on 22-11-26 by UPI Ref No 431876509123. -HDFC Bank")
    states, body = _states(client, case.id, key)
    assert body["status"] == "VERIFIED"
    assert states["amount_read"] == "info" and states["amount"] == "info"
    amount = next(c for c in body["checks"] if c["key"] == "amount")
    assert "unreadable" in amount["detail"] and "250" in amount["detail"]
