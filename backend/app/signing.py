"""Ed25519 signed, write-once evidence records.  Owner: Pile 3 (Verification & Trust).

STUB from the scaffold. Keep all four signatures exactly; replace the bodies.
Spec: docs/WORK_SPLIT.md -> Pile 3, Step 5.
The private key lives at settings.SIGNING_KEY_PATH (backend/data/, gitignored). NEVER commit it.
"""

import json

from sqlmodel import Session

from app.models import Case, Record


def canonical_json(d: dict) -> bytes:
    """The exact bytes that get hashed and signed."""
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def sign_case(session: Session, case: Case) -> Record:
    """Create the Record for a decided case (return the existing one if present).  TODO(Pile 3)."""
    raise NotImplementedError("Pile 3: signing")


def verify_record(record_json, signature_b64: str) -> bool:
    """record_json may be a str or a dict. True only if the signature matches.  TODO(Pile 3)."""
    return False


def public_key_b64() -> str:
    """Raw Ed25519 public key, base64.  TODO(Pile 3)."""
    return ""
