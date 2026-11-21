from datetime import datetime, timezone

from sqlmodel import select

from app import ingest, matcher
from app.models import BankCredit, Merchant

DEMO = "Rs.120.00 credited to A/c XX1234 on 22-11-26 by UPI Ref No 618656730702. -HDFC Bank"


def _merchant(session):
    m = Merchant(name="Ramu Tea", upi_id="ramu@okaxis", consent_given=True)
    session.add(m)
    session.commit()
    return m


# ---- ingest ----

def test_ingest_stores_minimal_credit_and_triggers_matcher(session, monkeypatch):
    seen = []
    monkeypatch.setattr(matcher, "on_new_credit", lambda s, c: seen.append(c.utr) or [])
    m = _merchant(session)
    when = datetime(2026, 11, 22, 1, 0)                       # naive from the forwarder -> treated as UTC
    credit = ingest.ingest_sms(session, m, "AX-HDFCBK", DEMO, when)
    assert (credit.utr, credit.amount, credit.sender_id) == ("618656730702", 120.0, "AX-HDFCBK")
    assert credit.credited_at == when.replace(tzinfo=timezone.utc)
    assert seen == ["618656730702"]
    assert not hasattr(credit, "body") and "credited to" not in repr(credit)   # no raw SMS kept


def test_ingest_drops_otp_and_stores_nothing(session, monkeypatch):
    monkeypatch.setattr(matcher, "on_new_credit", lambda s, c: (_ for _ in ()).throw(AssertionError("called")))
    m = _merchant(session)
    assert ingest.ingest_sms(session, m, "AX-HDFCBK", "123456 is your OTP. Rs.1 credited UPI Ref No 618656730702", None) is None
    assert session.exec(select(BankCredit)).all() == []


def test_ingest_without_received_at_uses_now(session, monkeypatch):
    monkeypatch.setattr(matcher, "on_new_credit", lambda s, c: [])
    credit = ingest.ingest_sms(session, _merchant(session), "AX-HDFCBK", DEMO, None)
    assert credit.credited_at.tzinfo is not None


# ---- matcher ----
from datetime import timedelta  # noqa: E402

import pytest  # noqa: E402

from app import events, signing  # noqa: E402
from app.db import utcnow  # noqa: E402
from app.models import Case, CaseStatus, UsedUTR  # noqa: E402

UTR = "618656730702"


@pytest.fixture
def signed(monkeypatch):
    """Record sign_case + publish calls (real signing is tested in test_signing.py)."""
    calls = {"signed": [], "published": []}
    monkeypatch.setattr(signing, "sign_case", lambda s, c: calls["signed"].append(c.id))
    monkeypatch.setattr(events, "publish", lambda mid, c: calls["published"].append((c.id, c.status)))
    return calls


def _case(session, m, utr=UTR, amount=120.0, sha="a" * 64, phash="", ago=timedelta(0)):
    c = Case(merchant_id=m.id, status=CaseStatus.WAITING, reason="Checking…", utr=utr, amount=amount,
             image_sha256=sha, image_phash=phash, ocr_confidence=90, created_at=utcnow() - ago)
    session.add(c)
    session.commit()
    session.refresh(c)
    return c


def _credit(session, m, utr=UTR, amount=120.0, ago=timedelta(0)):
    session.add(BankCredit(merchant_id=m.id, utr=utr, amount=amount, credited_at=utcnow() - ago, sender_id="AX-HDFCBK"))
    session.commit()


def test_genuine_payment_verified_signed_and_published(session, signed):
    m = _merchant(session)
    _credit(session, m)
    c = matcher.evaluate_case(session, _case(session, m))
    assert (c.status, c.reason) == (CaseStatus.VERIFIED, matcher.VERIFIED_OK)
    assert c.bank_credited_at is not None and c.decided_at is not None
    assert session.get(UsedUTR, UTR).case_id == c.id
    assert signed["signed"] == [c.id] and signed["published"] == [(c.id, CaseStatus.VERIFIED)]


def test_late_sms_waiting_then_verified_via_ingest(session, signed):
    m = _merchant(session)
    c = matcher.evaluate_case(session, _case(session, m))
    assert (c.status, c.reason) == (CaseStatus.WAITING, matcher.WAITING_MSG)
    assert signed["signed"] == []                           # no record while waiting
    ingest.ingest_sms(session, m, "AX-HDFCBK", DEMO, None)  # real on_new_credit
    session.refresh(c)
    assert c.status == CaseStatus.VERIFIED and signed["signed"] == [c.id]


def test_replay_utr_rejected(session, signed):
    m = _merchant(session)
    _credit(session, m)
    first = matcher.evaluate_case(session, _case(session, m, sha="a" * 64))
    second = matcher.evaluate_case(session, _case(session, m, sha="b" * 64))
    assert first.status == CaseStatus.VERIFIED
    assert second.status == CaseStatus.NOT_VERIFIED and "already used" in second.reason and "(replay)" in second.reason


def test_duplicate_image_rejected_but_genuine_first_case_still_verifies(session, signed):
    m = _merchant(session)
    first = matcher.evaluate_case(session, _case(session, m, ago=timedelta(seconds=30)))
    dup = matcher.evaluate_case(session, _case(session, m))            # same sha, later
    assert first.status == CaseStatus.WAITING
    assert (dup.status, dup.reason) == (CaseStatus.NOT_VERIFIED, matcher.SAME_IMAGE)
    _credit(session, m)
    matcher.on_new_credit(session, session.exec(select(BankCredit)).first())
    session.refresh(first)
    assert first.status == CaseStatus.VERIFIED                        # regression: later dup must not fail it


def test_near_duplicate_phash_with_same_utr_rejected(session, signed):
    m = _merchant(session)
    matcher.evaluate_case(session, _case(session, m, sha="a" * 64, phash="ffffffffffffffff", ago=timedelta(seconds=5)))
    c = matcher.evaluate_case(session, _case(session, m, sha="b" * 64, phash="fffffffffffffff0"))   # re-photographed copy
    assert c.reason == matcher.SAME_IMAGE


def test_same_template_different_utr_is_not_a_duplicate(session, signed):
    """Regression: two customers' success screens from one app are 4-6 pHash bits apart."""
    m = _merchant(session)
    matcher.evaluate_case(session, _case(session, m, utr="111111111111", sha="a" * 64,
                                         phash="ffffffffffffffff", ago=timedelta(seconds=5)))
    c = matcher.evaluate_case(session, _case(session, m, utr="222222222222", sha="b" * 64, phash="fffffffffffffff0"))
    assert (c.status, c.reason) == (CaseStatus.WAITING, matcher.WAITING_MSG)


def test_resend_after_unreadable_is_not_a_duplicate(session, signed):
    m = _merchant(session)
    bad = matcher.evaluate_case(session, _case(session, m, utr=None, ago=timedelta(seconds=5)))
    assert (bad.status, bad.reason) == (CaseStatus.NOT_VERIFIED, matcher.UNREADABLE)
    _credit(session, m)
    assert matcher.evaluate_case(session, _case(session, m)).status == CaseStatus.VERIFIED


def test_edited_amount_names_both_amounts(session, signed):
    m = _merchant(session)
    _credit(session, m, amount=100.0)
    c = matcher.evaluate_case(session, _case(session, m, amount=1000.0))
    assert c.status == CaseStatus.NOT_VERIFIED
    assert "₹1,000" in c.reason and "₹100" in c.reason and "edited amount" in c.reason


def test_credit_outside_window_does_not_match(session, signed):
    m = _merchant(session)
    _credit(session, m, ago=timedelta(minutes=10))
    assert matcher.evaluate_case(session, _case(session, m)).status == CaseStatus.WAITING


def test_expire_waiting_times_out_only_old_cases(session, signed):
    m = _merchant(session)
    old = _case(session, m, utr="333333333333", sha="c" * 64, ago=timedelta(minutes=6))
    fresh = _case(session, m, utr="444444444444", sha="d" * 64)
    assert matcher.expire_waiting(session) == 1
    session.refresh(old)
    session.refresh(fresh)
    assert (old.status, old.reason) == (CaseStatus.NOT_VERIFIED, matcher.TIMED_OUT)
    assert fresh.status == CaseStatus.WAITING and signed["signed"] == [old.id]


def test_utr_none_not_verified(session, signed):
    c = matcher.evaluate_case(session, _case(session, _merchant(session), utr=None))
    assert (c.status, c.reason) == (CaseStatus.NOT_VERIFIED, matcher.UNREADABLE)


def test_missing_ocr_amount_filled_from_bank(session, signed):
    m = _merchant(session)
    _credit(session, m, amount=120.0)
    c = matcher.evaluate_case(session, _case(session, m, amount=None))
    assert (c.status, c.amount) == (CaseStatus.VERIFIED, 120.0)


def test_final_case_is_never_re_decided(session, signed):
    m = _merchant(session)
    c = matcher.evaluate_case(session, _case(session, m, utr=None))
    _credit(session, m)
    assert matcher.evaluate_case(session, c).reason == matcher.UNREADABLE and signed["signed"] == [c.id]


def test_race_on_utr_claim_becomes_replay(session, signed, monkeypatch):
    m = _merchant(session)
    _credit(session, m)
    other = _case(session, m, sha="e" * 64)
    session.add(UsedUTR(utr=UTR, case_id=other.id, used_at=utcnow()))
    session.commit()
    real, lookups = matcher._find_used, {"n": 0}

    def first_lookup_misses(s, u):                     # as if the other transaction hadn't committed yet
        lookups["n"] += 1
        return None if lookups["n"] == 1 else real(s, u)

    monkeypatch.setattr(matcher, "_find_used", first_lookup_misses)
    c = matcher.evaluate_case(session, _case(session, m, sha="f" * 64))
    assert c.status == CaseStatus.NOT_VERIFIED and "(replay)" in c.reason
