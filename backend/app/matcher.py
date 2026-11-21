"""Verdict engine. The ONLY place that sets a case verdict.

Order (BUILD_PLAN / WORK_SPLIT §6 step 4): unreadable -> UTR replay -> duplicate image ->
bank credit in window (amount ok = VERIFIED, else edited) -> WAITING.
"""
from datetime import timedelta, timezone

import imagehash
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app import events, signing
from app.config import settings
from app.db import utcnow
from app.models import BankCredit, Case, CaseStatus, UsedUTR

UNREADABLE = "Could not read the UPI reference clearly — ask the customer to retake"
SAME_IMAGE = "Same screenshot seen before"
VERIFIED_OK = "Payment received in bank"
WAITING_MSG = "Looks fine, waiting for bank SMS"
TIMED_OUT = "No bank credit within 5 minutes"
PHASH_MAX_DISTANCE = 6
IST = timezone(timedelta(hours=5, minutes=30))


def _rupees(x):
    return f"₹{x:,.2f}".replace(".00", "")


def _replay_reason(used_at):
    return f"This UTR was already used on {used_at.astimezone(IST):%d %b %H:%M} IST (replay)"


def _window():
    return timedelta(minutes=settings.MATCH_WINDOW_MIN)


def _find_used(session, utr):
    return session.get(UsedUTR, utr)


def _is_duplicate_image(session, case):
    """Same bytes or near-identical pHash as an EARLIER readable case.

    Earlier only: otherwise, when the bank SMS arrives, re-evaluating the genuine first case would
    find the later replay upload's identical hash and wrongly fail the genuine payment.
    Unreadable earlier cases (utr None) don't count, so a customer can resend after "retake".
    """
    earlier = session.exec(
        select(Case).where(Case.id != case.id, Case.created_at < case.created_at, Case.utr.is_not(None))
    ).all()  # ponytail: linear pHash scan; index/BK-tree if case volume grows
    mine = imagehash.hex_to_hash(case.image_phash) if case.image_phash else None
    for other in earlier:
        if case.image_sha256 and other.image_sha256 == case.image_sha256:
            return True
        if mine is not None and other.image_phash:
            try:
                if mine - imagehash.hex_to_hash(other.image_phash) <= PHASH_MAX_DISTANCE:
                    return True
            except ValueError:
                continue
    return False


def _credit_in_window(session, case):
    credits = session.exec(
        select(BankCredit).where(BankCredit.merchant_id == case.merchant_id, BankCredit.utr == case.utr)
    ).all()
    in_window = [c for c in credits if abs(c.credited_at - case.created_at) <= _window()]
    return min(in_window, key=lambda c: abs(c.credited_at - case.created_at)) if in_window else None


def _finalize(session, case, status, reason):
    case.status, case.reason, case.decided_at = status, reason, utcnow()
    session.add(case)
    session.commit()
    session.refresh(case)
    signing.sign_case(session, case)
    events.publish(case.merchant_id, case)
    return case


def evaluate_case(session, case) -> Case:
    if case.status in CaseStatus.FINAL:
        return case                                   # verdicts and records are write-once
    if case.utr is None:
        return _finalize(session, case, CaseStatus.NOT_VERIFIED, UNREADABLE)
    used = _find_used(session, case.utr)
    if used is not None and used.case_id != case.id:
        return _finalize(session, case, CaseStatus.NOT_VERIFIED, _replay_reason(used.used_at))
    if _is_duplicate_image(session, case):
        return _finalize(session, case, CaseStatus.NOT_VERIFIED, SAME_IMAGE)

    credit = _credit_in_window(session, case)
    if credit is not None:
        if case.amount is not None and abs(credit.amount - case.amount) > 0.01:
            return _finalize(session, case, CaseStatus.NOT_VERIFIED,
                             f"Amount on screen {_rupees(case.amount)}, bank credited {_rupees(credit.amount)} (edited amount)")
        # One transaction: claim the UTR (PK = race-safe replay guard) and set the verdict together.
        now = utcnow()
        if case.amount is None:
            case.amount = credit.amount              # OCR missed it; the bank's amount is the truth
        case.status, case.reason = CaseStatus.VERIFIED, VERIFIED_OK
        case.bank_credited_at, case.decided_at = credit.credited_at, now
        session.add(UsedUTR(utr=case.utr, case_id=case.id, used_at=now))
        session.add(case)
        try:
            session.commit()
        except IntegrityError:
            session.rollback()                        # another case claimed this UTR first
            session.refresh(case)
            used = _find_used(session, case.utr)
            return _finalize(session, case, CaseStatus.NOT_VERIFIED,
                             _replay_reason(used.used_at if used else utcnow()))
        session.refresh(case)
        signing.sign_case(session, case)
        events.publish(case.merchant_id, case)
        return case

    case.status, case.reason = CaseStatus.WAITING, WAITING_MSG
    session.add(case)
    session.commit()
    session.refresh(case)
    events.publish(case.merchant_id, case)
    return case


def on_new_credit(session, credit) -> list[Case]:
    waiting = session.exec(
        select(Case).where(Case.merchant_id == credit.merchant_id, Case.utr == credit.utr,
                           Case.status == CaseStatus.WAITING).order_by(Case.created_at)
    ).all()                                           # oldest first: the genuine case wins the UTR
    return [evaluate_case(session, c) for c in waiting]


def expire_waiting(session) -> int:
    cutoff = utcnow() - _window()
    stale = session.exec(
        select(Case).where(Case.status == CaseStatus.WAITING, Case.created_at < cutoff)
    ).all()
    for c in stale:
        _finalize(session, c, CaseStatus.NOT_VERIFIED, TIMED_OUT)
    return len(stale)
