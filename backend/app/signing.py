"""Ed25519 signed, write-once case records. Anyone can verify with /api/public-key.

The private key lives at settings.SIGNING_KEY_PATH (gitignored, generated on first use). Never commit it.
"""
import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models import CaseStatus, Record

_keys: dict[str, Ed25519PrivateKey] = {}   # cache per path (tests point SIGNING_KEY_PATH at tmp dirs)


def _private_key() -> Ed25519PrivateKey:
    path = Path(settings.SIGNING_KEY_PATH)
    cached = _keys.get(str(path))
    if cached is not None:
        return cached
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        pem = Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
        try:
            with open(path, "xb") as f:            # exclusive create: two workers can't make two keys
                f.write(pem)
            os.chmod(path, 0o600)                   # best effort (no-op on Windows)
        except FileExistsError:
            pass                                    # someone else created it first: load theirs
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError(f"{path} is not an Ed25519 private key")
    _keys[str(path)] = key
    return key


def canonical_json(d) -> bytes:
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _iso(dt):
    return dt.isoformat() if dt is not None else None


def sign_case(session, case) -> Record:
    existing = session.get(Record, case.id)
    if existing is not None:
        return existing                              # write-once
    if case.status not in CaseStatus.FINAL:
        raise ValueError("only final verdicts get a signed record")
    body = canonical_json({
        "app_version": settings.APP_VERSION,
        "case_id": case.id,
        "merchant_id": case.merchant_id,
        "verdict": case.status,
        "reason": case.reason,
        "utr": case.utr,
        "amount": case.amount,
        "image_sha256": case.image_sha256,
        "proof_time": _iso(case.created_at),
        "bank_credit_time": _iso(case.bank_credited_at),
        "decided_time": _iso(case.decided_at),
    })
    record = Record(
        case_id=case.id,
        record_json=body.decode("utf-8"),
        record_sha256=hashlib.sha256(body).hexdigest(),
        signature=base64.b64encode(_private_key().sign(body)).decode("ascii"),
    )
    session.add(record)
    try:
        session.commit()
    except IntegrityError:                           # concurrent signer won: return the stored record
        session.rollback()
        return session.get(Record, case.id)
    session.refresh(record)
    return record


def verify_record(record_json, signature_b64) -> bool:
    try:
        data = json.loads(record_json) if isinstance(record_json, (str, bytes)) else record_json
        if not isinstance(data, dict):
            return False
        sig = base64.b64decode(signature_b64, validate=True)
        _private_key().public_key().verify(sig, canonical_json(data))
        return True
    except Exception:                    # bad JSON, bad base64, wrong signature...: invalid, never a 500
        return False


def public_key_b64() -> str:
    raw = _private_key().public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")
