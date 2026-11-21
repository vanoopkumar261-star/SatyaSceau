# CLAUDE.md — SatyaSceau

Read this first, then `docs/BUILD_PLAN.md` (full spec) and `docs/WORK_SPLIT.md` (who owns which files).

**Team:** Billi meows · **Event:** Hacknovate 2026, siNUsoid vX, NIIT University · **Repo lock:** 07:30

## Product
"Every payment gets a witness." A customer shows a UPI "payment successful" screenshot. We read the UTR and the amount from it, match them against the receiver's own bank credit SMS, give a verdict in seconds, and issue a signed, shareable record.

- **The screenshot is a claim. The receiver's bank credit SMS is the truth.**
- The **12-digit UPI reference (UTR/RRN)** is identical on both sides and is the join key. App IDs (e.g. PhonePe `T…`) differ per side and are **ignored**.

## Verdicts
- **VERIFIED**: the UTR and amount match a bank credit within 5 min, and the UTR was never used before.
- **WAITING**: looks fine, but no bank credit yet. Re-checked for up to 5 min.
- **NOT_VERIFIED**: replayed UTR, same image seen before, amount mismatch, unreadable screenshot, or 5 min with no credit.

## Stack (authoritative; no Next.js, Supabase or Razorpay)
- One **Python FastAPI** app that also serves **plain HTML** pages (`backend/static/`). No React and no build step.
- **SQLite** via SQLModel. **Tesseract** OCR (pytesseract + OpenCV). **Ed25519** signatures (`cryptography`).
- Bank credits arrive from an **Android SMS forwarder** (`POST /api/sms`). `/mock-bank` is a labelled demo backup.
- Run from `backend/`: `uvicorn app.main:app --reload --host 0.0.0.0`, tests: `pytest -q`.

## Ownership (3 piles; see docs/WORK_SPLIT.md)
- **Pile 1, Platform & Merchant (Anoop):** `main.py config.py db.py models.py schemas.py events.py routes_merchant.py static/merchant.html tests/conftest.py scripts/ requirements.txt`
- **Pile 2, Vision, Customer & Privacy:** `ocr.py privacy.py forensics.py routes_proof.py routes_privacy.py static/pay.html static/mock-bank.html tests/test_ocr_fields.py tests/test_privacy.py`
- **Pile 3, Verification & Trust:** `sms_parser.py ingest.py matcher.py signing.py routes_sms.py routes_records.py static/record.html tests/test_sms_parser.py tests/test_matcher.py tests/test_signing.py`

Only edit files in your pile. Shared contracts (models, schemas, function signatures) change **only through Anoop**.

## Rules for Claude Code
- **Never `git commit`, `git push`, or set authors.** Humans commit their own work. At the end of each step, give the exact `git add <files>` and `git commit -m` lines.
- Work one step at a time. After each step: `pytest -q`, show the changes, and wait for `next`.
- The **matcher is the only place that sets a verdict.**
- Never write customer images to disk. Never store raw SMS or OCR text. Keep only UTR, amount, times and sender ID.
- Never commit `.env`, keys (`*.pem`, `backend/data/`) or `*.db`.
- If something is blocked (Tesseract missing, port busy), stop and say so. Don't change the architecture.
- A simple working version beats a clever unfinished one.

## Out of scope
Our own wallet or UPI IDs (needs RBI/NPCI licensing). Direct bank access (Account Aggregator is future scope). External AI APIs stay off by default (`ENABLE_EXTERNAL_AI=false`); ask mentors first.
