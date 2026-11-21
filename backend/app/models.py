"""Database tables (frozen contract).  Owner: Pile 1 (Platform) — changes go through Anoop.

Privacy: no table stores raw SMS text, raw OCR text, or the customer image.
"""

import secrets
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from app.db import utcnow


def new_id(nbytes: int) -> str:
    """Unguessable URL-safe id (nbytes=6 -> 8 chars, nbytes=9 -> 12 chars)."""
    return secrets.token_urlsafe(nbytes)


class CaseStatus:
    WAITING = "WAITING"
    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"
    FINAL = (VERIFIED, NOT_VERIFIED)


class Merchant(SQLModel, table=True):
    __tablename__ = "merchants"

    id: str = Field(default_factory=lambda: new_id(6), primary_key=True)
    name: str
    upi_id: str = ""
    api_token: str = Field(default_factory=lambda: new_id(24), unique=True, index=True)
    # Read-only key for the merchant's live screen. Separate from api_token (which can inject SMS)
    # because it travels in a browser URL. The merchant id alone is public: it's on the printed QR.
    screen_key: Optional[str] = Field(default_factory=lambda: new_id(16))
    consent_given: bool = False
    consent_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow)


class Case(SQLModel, table=True):
    __tablename__ = "cases"

    id: str = Field(default_factory=lambda: new_id(9), primary_key=True)
    merchant_id: str = Field(foreign_key="merchants.id", index=True)
    status: str = Field(default=CaseStatus.WAITING, index=True)
    reason: str = ""
    utr: Optional[str] = Field(default=None, index=True)
    amount: Optional[float] = None
    image_sha256: str = Field(default="", index=True)
    image_phash: str = ""
    ocr_confidence: float = 0.0
    risk_score: Optional[float] = None
    bank_credited_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utcnow, index=True)
    decided_at: Optional[datetime] = None


class BankCredit(SQLModel, table=True):
    """Only the facts we need from a bank credit SMS. Auto-deleted after RETENTION_DAYS."""

    __tablename__ = "bank_credits"

    id: Optional[int] = Field(default=None, primary_key=True)
    merchant_id: str = Field(foreign_key="merchants.id", index=True)
    utr: str = Field(index=True)
    amount: float
    credited_at: datetime
    sender_id: str
    created_at: datetime = Field(default_factory=utcnow, index=True)


class UsedUTR(SQLModel, table=True):
    """Replay protection: the primary key makes a second use of a UTR impossible."""

    __tablename__ = "used_utrs"

    utr: str = Field(primary_key=True)
    case_id: str = Field(foreign_key="cases.id")
    used_at: datetime = Field(default_factory=utcnow)


class Record(SQLModel, table=True):
    """Signed evidence record. Write-once: the app never updates or deletes it."""

    __tablename__ = "records"

    case_id: str = Field(foreign_key="cases.id", primary_key=True)
    record_json: str
    record_sha256: str
    signature: str  # Ed25519, base64
    created_at: datetime = Field(default_factory=utcnow)
