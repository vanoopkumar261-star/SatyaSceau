"""Supabase Auth: register, log in, and check who a token belongs to.  Owner: Pile 1 (Platform).

Only accounts live in Supabase; shops, payments, verdicts and records stay in our SQLite DB.
We call Supabase's Auth REST API (GoTrue) with the public anon/publishable key, so there are no
new dependencies. Passwords pass straight through to Supabase; we never store or log them.
"""

import time

import httpx

from app.config import settings

TIMEOUT_S = 10
_USER_CACHE_S = 60
_user_cache: dict[str, tuple[float, dict]] = {}  # access token -> (expires_at, user)


class AuthError(Exception):
    """A user-facing auth failure (wrong password, weak password, already registered...)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


class AuthNotConfigured(AuthError):
    def __init__(self):
        super().__init__("Login isn't set up yet: add SUPABASE_URL and SUPABASE_ANON_KEY to backend/.env.", 503)


def is_configured() -> bool:
    return bool(settings.SUPABASE_URL and settings.SUPABASE_ANON_KEY)


def _headers(access_token: str | None = None) -> dict:
    h = {"apikey": settings.SUPABASE_ANON_KEY, "Content-Type": "application/json"}
    if access_token:
        h["Authorization"] = f"Bearer {access_token}"
    return h


def _message(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return f"Supabase error ({resp.status_code})"
    return body.get("msg") or body.get("error_description") or body.get("message") or body.get("error") \
        or f"Supabase error ({resp.status_code})"


def _session(body: dict) -> dict:
    user = body.get("user") or {}
    return {"access_token": body["access_token"], "expires_in": body.get("expires_in"),
            "user": {"id": user.get("id"), "email": user.get("email")}}


def _post(path: str, payload: dict) -> httpx.Response:
    if not is_configured():
        raise AuthNotConfigured()
    try:
        return httpx.post(f"{settings.SUPABASE_URL}{path}", json=payload, headers=_headers(), timeout=TIMEOUT_S)
    except httpx.HTTPError:
        raise AuthError("Can't reach the login service. Check the internet connection.", 502)


def register(email: str, password: str) -> dict:
    """Create the account and return a session (needs 'Confirm email' OFF in Supabase)."""
    resp = _post("/auth/v1/signup", {"email": email, "password": password})
    if resp.status_code >= 400:
        raise AuthError(_message(resp), 400 if resp.status_code < 500 else 502)
    body = resp.json()
    if not body.get("access_token"):  # email confirmation is ON in the Supabase project
        raise AuthError("Account created. Confirm your email, then log in "
                        "(or turn off 'Confirm email' in Supabase for the demo).", 409)
    return _session(body)


def login(email: str, password: str) -> dict:
    resp = _post("/auth/v1/token?grant_type=password", {"email": email, "password": password})
    if resp.status_code >= 400:
        raise AuthError(_message(resp) if resp.status_code < 500 else "Login service error", 401 if resp.status_code < 500 else 502)
    return _session(resp.json())


def current_user(access_token: str) -> dict:
    """Validate a token with Supabase and return {"id", "email"}. Cached for a minute."""
    if not is_configured():
        raise AuthNotConfigured()
    now = time.time()
    hit = _user_cache.get(access_token)
    if hit and hit[0] > now:
        return hit[1]
    try:
        resp = httpx.get(f"{settings.SUPABASE_URL}/auth/v1/user", headers=_headers(access_token), timeout=TIMEOUT_S)
    except httpx.HTTPError:
        raise AuthError("Can't reach the login service. Check the internet connection.", 502)
    if resp.status_code != 200:
        _user_cache.pop(access_token, None)
        raise AuthError("Please log in again.", 401)
    body = resp.json()
    user = {"id": body.get("id"), "email": body.get("email")}
    if len(_user_cache) > 500:  # tiny demo cache; never grows unbounded
        _user_cache.clear()
    _user_cache[access_token] = (now + _USER_CACHE_S, user)
    return user
