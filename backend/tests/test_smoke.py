"""Scaffold smoke tests: app boots, every BUILD_PLAN route exists, merchant basics work.  Owner: Pile 1."""

import base64

from app import events
from app.main import app
from app.models import Case, Merchant

SPEC_ROUTES = {
    ("POST", "/api/merchants"),
    ("POST", "/api/merchants/{merchant_id}/consent"),
    ("GET", "/pay/{merchant_id}"),
    ("POST", "/api/proof"),
    ("POST", "/api/sms"),
    ("GET", "/api/merchants/{merchant_id}/stream"),
    ("GET", "/api/cases/{case_id}"),
    ("GET", "/record/{case_id}"),
    ("GET", "/api/records/{case_id}"),
    ("GET", "/api/public-key"),
    ("POST", "/api/records/verify"),
    ("GET", "/mock-bank"),
    ("POST", "/api/mock-bank"),
    ("GET", "/merchant"),
    ("GET", "/health"),
}


def _walk(routes):
    """Flatten routes. Newer FastAPI nests included routers (route.original_router)."""
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _walk(inner.routes)
        else:
            yield route


def test_every_spec_route_is_registered():
    registered = {
        (method, route.path)
        for route in _walk(app.routes)
        for method in getattr(route, "methods", None) or ()
    }
    assert SPEC_ROUTES <= registered, SPEC_ROUTES - registered


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_merchant_returns_token_and_qr(client):
    r = client.post("/api/merchants", json={"name": "Raju Tea Stall", "upi_id": "raju@upi"})
    assert r.status_code == 201
    body = r.json()
    assert len(body["id"]) >= 8 and len(body["api_token"]) >= 24
    assert body["pay_url"].endswith(f"/pay/{body['id']}")
    assert base64.b64decode(body["qr_png_base64"]).startswith(b"\x89PNG")


def test_create_merchant_rejects_empty_name(client):
    assert client.post("/api/merchants", json={"name": ""}).status_code == 422


def test_pay_page_only_for_real_merchants(client):
    merchant_id = client.post("/api/merchants", json={"name": "Shop"}).json()["id"]
    assert client.get(f"/pay/{merchant_id}").status_code == 200
    assert client.get("/pay/does-not-exist").status_code == 404


def test_case_status_lookup(client, session):
    merchant = Merchant(name="Shop")
    session.add(merchant)
    session.commit()
    case = Case(merchant_id=merchant.id, utr="123456789012", amount=10.0, reason="Checking…")
    session.add(case)
    session.commit()

    r = client.get(f"/api/cases/{case.id}")
    assert r.status_code == 200
    assert r.json()["status"] == "WAITING"
    assert r.json()["record_url"] is None
    assert client.get("/api/cases/nope").status_code == 404


def test_publish_reaches_subscriber():
    queue = events.subscribe("m1")
    try:
        events.publish("m1", Case(id="c1", merchant_id="m1", status="VERIFIED", reason="ok"))
        payload = queue.get_nowait()
        assert payload["case_id"] == "c1"
        assert payload["record_url"] == "/record/c1"
    finally:
        events.unsubscribe("m1", queue)
