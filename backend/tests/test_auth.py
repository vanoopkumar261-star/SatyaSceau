"""Register / log in via Supabase Auth (faked: no network) and the logged-in user's shop.  Owner: Pile 1."""

import httpx
import pytest
from sqlmodel import select

from app import auth, config
from app.models import BankCredit, Merchant
from app.db import utcnow

USERS = {"tok-a": {"id": "user-a", "email": "a@example.com"}, "tok-b": {"id": "user-b", "email": "b@example.com"}}


@pytest.fixture
def fake_supabase(monkeypatch):
    """Configured, with two known tokens; no network."""
    monkeypatch.setattr(auth, "is_configured", lambda: True)

    def current_user(token):
        if token not in USERS:
            raise auth.AuthError("Please log in again.", 401)
        return USERS[token]

    monkeypatch.setattr(auth, "current_user", current_user)
    monkeypatch.setattr(auth, "register", lambda e, p: {"access_token": "tok-a", "user": {"id": "user-a", "email": e}})
    monkeypatch.setattr(auth, "login", lambda e, p: {"access_token": "tok-a", "user": {"id": "user-a", "email": e}})


def H(token):
    return {"Authorization": f"Bearer {token}"}


def _shop(client, token="tok-a", **kw):
    body = {"account_type": "personal", "name": "Raju Tea Stall", "upi_id": "raju@okaxis", "sms_consent": False} | kw
    return client.post("/api/me/shop", json=body, headers=H(token))


# --- pages + status ------------------------------------------------------------------

def test_home_page_and_login_page_are_served(client):
    home = client.get("/")
    assert home.status_code == 200 and "Every payment gets a witness" in home.text
    assert 'href="/login?mode=register"' in home.text
    assert client.get("/login").status_code == 200
    assert client.get("/static/site.css").status_code == 200


def test_status_reports_missing_keys(client, monkeypatch):
    monkeypatch.setattr(config, "_live_env", lambda name, default="": "")
    assert client.get("/api/auth/status").json() == {"configured": False}
    r = client.post("/api/auth/login", json={"email": "a@example.com", "password": "secret1"})
    assert r.status_code == 503 and "SUPABASE_URL" in r.json()["detail"]


# --- register / login ------------------------------------------------------------------

def test_register_and_login_return_a_session(client, fake_supabase):
    for path in ("/api/auth/register", "/api/auth/login"):
        r = client.post(path, json={"email": " A@Example.com ", "password": "secret1"})
        assert r.status_code == 200 and r.json()["access_token"] == "tok-a"
        assert r.json()["user"]["email"] == "a@example.com"  # trimmed + lower-cased


def test_bad_email_and_short_password_rejected(client, fake_supabase):
    assert client.post("/api/auth/login", json={"email": "not-an-email", "password": "secret1"}).status_code == 422
    assert client.post("/api/auth/login", json={"email": "a@example.com", "password": "123"}).status_code == 422


# --- the real Supabase client, with httpx faked ---------------------------------------------

@pytest.fixture
def supabase_env(monkeypatch):
    env = {"SUPABASE_URL": "https://demo.supabase.co/", "SUPABASE_ANON_KEY": "anon-key"}
    monkeypatch.setattr(config, "_live_env", lambda name, default="": env.get(name, default))
    auth._user_cache.clear()


def _resp(status, body):
    return httpx.Response(status, json=body, request=httpx.Request("POST", "https://demo.supabase.co"))


def test_supabase_login_success_and_wrong_password(monkeypatch, supabase_env):
    seen = {}

    def fake_post(url, json, headers, timeout):
        seen.update(url=url, apikey=headers["apikey"])
        if json["password"] == "right-pass":
            return _resp(200, {"access_token": "jwt", "expires_in": 3600, "user": {"id": "u1", "email": json["email"]}})
        return _resp(400, {"code": 400, "error_code": "invalid_credentials", "msg": "Invalid login credentials"})

    monkeypatch.setattr(auth.httpx, "post", fake_post)
    assert auth.login("a@example.com", "right-pass")["user"] == {"id": "u1", "email": "a@example.com"}
    assert seen == {"url": "https://demo.supabase.co/auth/v1/token?grant_type=password", "apikey": "anon-key"}
    with pytest.raises(auth.AuthError) as e:
        auth.login("a@example.com", "wrong-pass")
    assert e.value.status == 401 and e.value.message == "Invalid login credentials"


def test_supabase_register_with_email_confirmation_on(monkeypatch, supabase_env):
    monkeypatch.setattr(auth.httpx, "post", lambda *a, **k: _resp(200, {"id": "u1", "email": "a@example.com"}))
    with pytest.raises(auth.AuthError) as e:
        auth.register("a@example.com", "secret1")
    assert e.value.status == 409 and "Confirm email" in e.value.message


def test_supabase_unreachable(monkeypatch, supabase_env):
    def boom(*a, **k):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(auth.httpx, "post", boom)
    with pytest.raises(auth.AuthError) as e:
        auth.login("a@example.com", "secret1")
    assert e.value.status == 502


# --- the logged-in user's shop ---------------------------------------------------------------

def test_me_requires_a_valid_token(client, fake_supabase):
    assert client.get("/api/me").status_code == 401
    assert client.get("/api/me", headers=H("forged")).status_code == 401
    r = client.get("/api/me", headers=H("tok-a"))
    assert r.status_code == 200 and r.json() == {"user": USERS["tok-a"], "shop": None}


def test_first_save_creates_the_shop_then_updates_it(client, session, fake_supabase):
    shop = _shop(client).json()["shop"]
    assert shop["account_type"] == "personal" and shop["name"] == "Raju Tea Stall"
    assert shop["screen_path"].startswith(f"/merchant?m={shop['id']}#k=") and shop["qr_png_base64"]

    again = _shop(client, name="Raju Chai", account_type="company").json()["shop"]
    assert again["id"] == shop["id"] and again["name"] == "Raju Chai" and again["account_type"] == "company"
    assert client.get("/api/me", headers=H("tok-a")).json()["shop"]["id"] == shop["id"]
    m = session.get(Merchant, shop["id"])
    assert m.owner_user_id == "user-a"


def test_users_only_see_their_own_shop(client, fake_supabase):
    a = _shop(client, "tok-a").json()["shop"]
    assert client.get("/api/me", headers=H("tok-b")).json()["shop"] is None
    b = _shop(client, "tok-b", name="Other Shop").json()["shop"]
    assert b["id"] != a["id"] and b["api_token"] != a["api_token"]


def test_sms_consent_on_then_off_deletes_stored_credits(client, session, fake_supabase):
    shop = _shop(client, sms_consent=True).json()["shop"]
    assert shop["sms_consent"] is True
    session.add(BankCredit(merchant_id=shop["id"], utr="431876509123", amount=1.0, credited_at=utcnow(), sender_id="AX-HDFCBK"))
    session.commit()
    off = _shop(client, sms_consent=False).json()["shop"]
    assert off["sms_consent"] is False
    session.expire_all()
    assert session.exec(select(BankCredit).where(BankCredit.merchant_id == shop["id"])).all() == []
