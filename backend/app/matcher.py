"""Verdict engine. The ONLY place that sets a case verdict. (Filled in at Step 4.)"""
from app.models import Case


def evaluate_case(session, case) -> Case:
    raise NotImplementedError


def on_new_credit(session, credit) -> list[Case]:
    raise NotImplementedError


def expire_waiting(session) -> int:
    raise NotImplementedError
