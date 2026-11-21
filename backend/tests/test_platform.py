"""Merchant screen API: screen-key auth, recent cases, additive DB migration.  Owner: Pile 1."""

from datetime import timedelta
from urllib.parse import parse_qs, urlparse

from sqlalchemy import inspect
from sqlmodel import create_engine
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
