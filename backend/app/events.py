"""In-memory pub/sub that feeds the merchant's live SSE stream.  Owner: Pile 1 (Platform).

The matcher calls publish() on every status change, often from a worker thread,
so delivery is handed to the event loop with call_soon_threadsafe.
"""

import asyncio
from collections import defaultdict
from typing import Optional

from app.models import Case, CaseStatus

_loop: Optional[asyncio.AbstractEventLoop] = None
_subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)


def set_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _loop
    _loop = loop


def case_payload(case: Case) -> dict:
    """Public view of a case (used by the SSE stream and GET /api/cases/{id})."""
    final = case.status in CaseStatus.FINAL
    return {
        "case_id": case.id,
        "merchant_id": case.merchant_id,
        "status": case.status,
        "reason": case.reason,
        "utr": case.utr,
        "amount": case.amount,
        "risk_score": case.risk_score,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "decided_at": case.decided_at.isoformat() if case.decided_at else None,
        "record_url": f"/record/{case.id}" if final else None,
    }


def subscribe(merchant_id: str) -> asyncio.Queue:
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    _subscribers[merchant_id].add(queue)
    return queue


def unsubscribe(merchant_id: str, queue: asyncio.Queue) -> None:
    subs = _subscribers.get(merchant_id)
    if subs is not None:
        subs.discard(queue)
        if not subs:
            _subscribers.pop(merchant_id, None)


def publish(merchant_id: str, case: Case) -> None:
    queues = list(_subscribers.get(merchant_id, ()))
    if not queues:
        return
    payload = case_payload(case)
    for queue in queues:
        if _loop is not None and _loop.is_running():
            _loop.call_soon_threadsafe(_put, queue, payload)
        else:
            _put(queue, payload)


def _put(queue: asyncio.Queue, payload: dict) -> None:
    try:
        queue.put_nowait(payload)
    except asyncio.QueueFull:
        pass  # a stuck browser tab must never block verdicts
