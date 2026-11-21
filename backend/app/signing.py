"""Ed25519 signed, write-once case records. (Filled in at Step 5.)"""
from app.models import Record


def canonical_json(d) -> bytes:
    raise NotImplementedError


def sign_case(session, case) -> Record:
    raise NotImplementedError


def verify_record(record_json, signature_b64) -> bool:
    raise NotImplementedError


def public_key_b64() -> str:
    raise NotImplementedError
