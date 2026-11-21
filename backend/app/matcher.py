"""Verdict engine: the ONLY place that sets a case verdict.  Owner: Pile 3 (Verification & Trust).

STUB from the scaffold. Keep all three signatures exactly; replace the bodies.
Spec: docs/WORK_SPLIT.md -> Pile 3, Step 4.
Order: unreadable -> replay (UsedUTR) -> duplicate image -> bank credit match / amount mismatch -> WAITING.
On a final verdict: set decided_at, commit, signing.sign_case, events.publish.
"""

from sqlmodel import Session

from app import events
from app.db import utcnow
from app.models import BankCredit, Case, CaseStatus

UNREADABLE_REASON = "Could not read the UPI reference clearly — ask the customer to retake"
WAITING_REASON = "Looks fine, waiting for bank SMS"


def evaluate_case(session: Session, case: Case) -> Case:
    """Decide (or re-decide) one case.  TODO(Pile 3): replay, duplicate image, match, mismatch, signing."""
    if case.utr is None:
        case.status = CaseStatus.NOT_VERIFIED
        case.reason = UNREADABLE_REASON
        case.decided_at = utcnow()
    else:
        case.status = CaseStatus.WAITING
        case.reason = WAITING_REASON
    session.add(case)
    session.commit()
    session.refresh(case)
    events.publish(case.merchant_id, case)
    return case


def on_new_credit(session: Session, credit: BankCredit) -> list[Case]:
    """Re-check WAITING cases with the same merchant + UTR. Returns the cases re-evaluated.  TODO(Pile 3)."""
    return []


def expire_waiting(session: Session) -> int:
    """WAITING older than MATCH_WINDOW_MIN -> NOT_VERIFIED. Returns the count. Called every 15 s.  TODO(Pile 3)."""
    return 0
