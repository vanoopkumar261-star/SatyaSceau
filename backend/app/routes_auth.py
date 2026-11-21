"""Register / log in (Supabase Auth) and the logged-in user's shop.  Owner: Pile 1 (Platform).

Flow: /login -> register or log in -> pick Personal UPI or Company -> shop is created ->
the user opens the same live merchant screen as before (its screen-key link).
"""

import base64
import re
from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app import auth
from app.config import STATIC_DIR, settings
from app.db import get_session, utcnow
from app.models import Merchant
from app.routes_merchant import _pay_url, _qr_png

router = APIRouter()

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=6, max_length=72)


class ShopIn(BaseModel):
    account_type: Literal["personal", "company"]
    name: str = Field(min_length=1, max_length=80)
    upi_id: str = Field(default="", max_length=80)
    sms_consent: bool = False  # opt in to automatic bank-SMS forwarding (pasting by hand needs no opt-in)


def _call(fn, *args):
    try:
        return fn(*args)
    except auth.AuthError as e:
        raise HTTPException(e.status, e.message)


def _clean_email(email: str) -> str:
    email = email.strip().lower()
    if not _EMAIL.match(email):
        raise HTTPException(422, "Enter a valid email address")
    return email


def require_user(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI dependency: the Supabase user behind `Authorization: Bearer <token>`."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Please log in")
    return _call(auth.current_user, authorization[7:].strip())


def _shop_view(m: Merchant) -> dict:
    pay_url = _pay_url(m.id)
    return {
        "id": m.id,
        "name": m.name,
        "upi_id": m.upi_id,
        "account_type": m.account_type or "personal",
        "sms_consent": m.consent_given,
        "pay_url": pay_url,
        "screen_path": f"/merchant?m={m.id}#k={m.screen_key}",  # relative: works on localhost and the tunnel
        "api_token": m.api_token,  # for the SMS forwarder; only ever shown to the logged-in owner
        "qr_png_base64": base64.b64encode(_qr_png(pay_url)).decode(),
    }


def _my_shop(session: Session, user: dict) -> Merchant | None:
    return session.exec(select(Merchant).where(Merchant.owner_user_id == user["id"])).first()


@router.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(STATIC_DIR / "login.html")


@router.get("/api/auth/status")
def auth_status():
    return {"configured": auth.is_configured()}


@router.post("/api/auth/register")
def register(body: Credentials):
    return _call(auth.register, _clean_email(body.email), body.password)


@router.post("/api/auth/login")
def login(body: Credentials):
    return _call(auth.login, _clean_email(body.email), body.password)


@router.get("/api/me")
def me(user: dict = Depends(require_user), session: Session = Depends(get_session)):
    shop = _my_shop(session, user)
    return {"user": user, "shop": _shop_view(shop) if shop else None}


@router.post("/api/me/shop")
def save_shop(body: ShopIn, user: dict = Depends(require_user), session: Session = Depends(get_session)):
    """Create the user's shop (first time) or update its name / UPI ID / type / SMS consent."""
    shop = _my_shop(session, user)
    if shop is None:
        shop = Merchant(name=body.name.strip(), upi_id=body.upi_id.strip(), owner_user_id=user["id"])
    else:
        shop.name, shop.upi_id = body.name.strip(), body.upi_id.strip()
    shop.account_type = body.account_type
    if body.sms_consent != shop.consent_given:
        if not body.sms_consent:
            from app import privacy  # withdrawing consent also deletes stored credits (Pile 2 rule)
            session.add(shop)
            session.commit()
            privacy.set_consent(session, shop.id, False)
            session.refresh(shop)
        else:
            shop.consent_given, shop.consent_at = True, utcnow()
    session.add(shop)
    session.commit()
    session.refresh(shop)
    return {"shop": _shop_view(shop)}
