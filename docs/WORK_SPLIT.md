# SatyaSceau — Work split (3 piles, parallel, one PR each)

Spec: `docs/BUILD_PLAN.md`. Project rules: `CLAUDE.md`. **This file wins on who-owns-what and on the contracts.**
Repo lock **07:30** · code freeze **07:00** · final push **07:20**.

| Pile | Owner | Branch | BUILD_PLAN phases |
|---|---|---|---|
| 1 — Platform & Merchant | Anoop (`vanoopkumar261-star`), lead / reviewer | `feat/platform` | 0, 3 (merchant side), 6 |
| 2 — Vision, Customer & Privacy | Teammate B | `feat/vision` | 1, 3 (pay page), 5, stretch forensics |
| 3 — Verification & Trust | Teammate C (cybersecurity) | `feat/trust` | 2, 4 |

The scaffold on `main` already contains **every file as a stub** with its final signature, and `main.py` already includes every router. You only fill in your own files. You never touch `main.py`.

---

## 1. Setup (each teammate, once)

```bash
git clone https://github.com/vanoopkumar261-star/SatyaSceau.git && cd SatyaSceau
git config user.name "Your Name" && git config user.email "your-github-email"   # commits must show YOU
git checkout -b feat/vision            # or feat/trust
cd backend
python -m venv .venv
.venv\Scripts\activate                 # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
pytest -q                              # 7 smoke tests should pass
uvicorn app.main:app --reload --host 0.0.0.0     # http://localhost:8000/docs
```

- **Python 3.11+.** **Pile 2 also needs Tesseract:**
  - Windows: `winget install UB-Mannheim.TesseractOCR`, then `TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe` in `backend/.env`
  - Mac: `brew install tesseract`
  - Linux: `sudo apt install tesseract-ocr`
- **Windows "An Application Control policy has blocked this file" on `import sqlalchemy`:** Smart App Control blocks SQLAlchemy's compiled DLL. Rebuild it as pure Python. Do **not** turn Smart App Control off; it can't be turned back on.
  ```bash
  set DISABLE_SQLALCHEMY_CEXT=1    # PowerShell: $env:DISABLE_SQLALCHEMY_CEXT=1   bash: export DISABLE_SQLALCHEMY_CEXT=1
  pip install --force-reinstall --no-deps --no-binary sqlalchemy "sqlalchemy==2.1.9"
  ```
- Copy `backend/.env.example` to `backend/.env` if you need to change a setting. Never commit `.env`.

## 2. Kickoff prompt for your Claude Code (paste it as-is, then change the pile number)

```
Read CLAUDE.md, docs/BUILD_PLAN.md and docs/WORK_SPLIT.md fully. I am building PILE 2 only
(the "Pile 2" section of docs/WORK_SPLIT.md). Edit ONLY the files listed under "My files" for
that pile. The stubs already exist: keep every signature, path and parameter exactly and
replace the bodies. Never run git commit/push or change the author: at the end of each step,
give me the exact `git add <files>` and `git commit -m` lines. Work one step at a time; after
each step run `pytest -q` from backend/, show me what changed, and wait for me to say `next`.
If a shared file (models, schemas, main, db, config, events, conftest) seems to need a change,
STOP and tell me what to ask Anoop.
```

## 3. Git loop (every 20–30 min)

```bash
git add <only your files>                 # never `git add -A` / `git add .`
git commit -m "feat(ocr): UTR anchor extraction"
git fetch origin && git rebase origin/main   # at least every ~45 min
git push -u origin feat/vision            # after a rebase: git push --force-with-lease
gh pr create --base main --fill           # when your pile is done and pytest -q is green (target T+2:00)
```

- Anoop merges with a **merge commit** (no squash), so everyone's commits stay visible.
- Commit prefixes: `feat(...)`, `fix(...)`, `test(...)`, `docs(...)`.
- Never commit `.env`, `*.pem`, `backend/data/` or `*.db`.

---

## 4. Contracts (frozen; changes go through Anoop)

Layout: `backend/app/*.py`, `backend/static/*.html`, `backend/tests/*.py`. Run everything from `backend/`. Imports look like `from app.models import Case`.

**`app/config.py`**: `settings`
- `MATCH_WINDOW_MIN=5`, `RETENTION_DAYS=7`
- `SIGNING_KEY_PATH` (a `Path`), `BASE_URL`
- `TESSERACT_CMD` (empty = on PATH), `OCR_MIN_CONF=60`, `MAX_UPLOAD_MB=8`
- `ENABLE_EXTERNAL_AI=False`, `APP_VERSION="0.1.0"`
- Also `STATIC_DIR` and `DATA_DIR`.

**`app/db.py`**
- `engine`
- `get_session()`: FastAPI dependency yielding a sqlmodel `Session`
- `utcnow()`: **timezone-aware UTC**. Use it for every timestamp. Values read back from the DB are also aware UTC, so you can compare them directly.
- `as_utc(dt)`: normalise incoming datetimes. Naive input is treated as UTC. Use it on `received_at` from the SMS forwarder.

**`app/models.py`** (SQLModel tables)
```
Merchant   id (8-char random PK), name, upi_id, api_token (unique), consent_given=False, consent_at, created_at
Case       id (12-char random PK), merchant_id, status, reason, utr|None, amount|None, image_sha256, image_phash,
           ocr_confidence, risk_score|None, bank_credited_at|None, created_at, decided_at|None
BankCredit id (int PK), merchant_id, utr (indexed), amount, credited_at, sender_id, created_at   # never raw SMS text
UsedUTR    utr (PK = replay protection), case_id, used_at
Record     case_id (PK), record_json, record_sha256, signature (base64), created_at             # write-once
CaseStatus.WAITING / .VERIFIED / .NOT_VERIFIED / .FINAL (VERIFIED, NOT_VERIFIED)
```

**`app/schemas.py`** (dataclasses)
```
OcrResult(utr: str|None, amount: float|None, confidence: float, raw_text_len: int, image_sha256: str, image_phash: str)
ParsedCredit(utr: str, amount: float, sender_id: str)
```

**Functions**
```
Pile 2  ocr.extract_fields(text) -> {"utr": str|None, "amount": float|None}      (pure)
        ocr.analyze_screenshot(image_bytes) -> OcrResult
        privacy.set_consent(session, merchant_id, given) -> Merchant
        privacy.purge_expired_credits(session) -> int                             (main.py: startup + hourly)
Pile 3  sms_parser.parse_bank_sms(sender, body) -> ParsedCredit | None
        ingest.ingest_sms(session, merchant, sender, body, received_at) -> BankCredit | None
        matcher.evaluate_case(session, case) -> Case
        matcher.on_new_credit(session, credit) -> list[Case]
        matcher.expire_waiting(session) -> int                                    (main.py: every 15 s)
        signing.canonical_json(d) -> bytes
        signing.sign_case(session, case) -> Record
        signing.verify_record(record_json, signature_b64) -> bool
        signing.public_key_b64() -> str
Pile 1  events.publish(merchant_id, case)          (thread-safe; the matcher calls it on every status change)
        events.case_payload(case) -> dict          (public view used by SSE and GET /api/cases/{id})
```

**Endpoints**
- **Pile 1:**
  - `POST /api/merchants {name, upi_id}` returns `{id, name, api_token, pay_url, merchant_url, qr_png_base64}`
  - `GET /api/merchants/{id}/qr.png`
  - `GET /api/merchants/{id}/stream` (SSE `event: case`)
  - `GET /api/cases/{id}`
  - `GET /pay/{id}` (serves Pile 2's `pay.html`)
  - `GET /merchant?m=<id>`
  - `GET /health`
- **Pile 2:**
  - `POST /api/proof` (multipart `merchant_id`, `image`)
  - `POST /api/merchants/{id}/consent {given}` (with `X-Token`)
  - `GET /mock-bank`
  - `POST /api/mock-bank {merchant_id, utr, amount}`
- **Pile 3:**
  - `POST /api/sms {sender, body, received_at?}` (with `X-Token`)
  - `GET /record/{id}`
  - `GET /api/records/{id}`
  - `GET /api/public-key`
  - `POST /api/records/verify {record_json, signature}`

**Shared agreements**
- **The matcher is the only place that sets a verdict.** Pile 2 passes the `OcrResult` through. If `utr` is None, the matcher sets NOT_VERIFIED with `"Could not read the UPI reference clearly — ask the customer to retake"`.
- On VERIFIED or NOT_VERIFIED, the matcher sets `decided_at`, commits, then calls `signing.sign_case` and `events.publish`. On WAITING, it calls `events.publish`.
- **Demo bank SMS format** (the mock bank generates it, and the parser MUST accept it):
  sender `AX-HDFCBK`, body `Rs.{amount:.2f} credited to A/c XX1234 on {dd-mm-yy} by UPI Ref No {utr}. -HDFC Bank`
- Test fixtures (`tests/conftest.py`): `session` (fresh in-memory SQLite per test) and `client` (TestClient on the same DB, with no background loop). Put extra fixtures in your own test files.

---

## 5. Pile 2 — Vision, Customer & Privacy (`feat/vision`)

**My files:** `app/ocr.py`, `app/privacy.py`, `app/forensics.py` (stretch), `app/routes_proof.py`, `app/routes_privacy.py`, `static/pay.html`, `static/mock-bank.html`, `tests/test_ocr_fields.py`, `tests/test_privacy.py`

**Step 1: `ocr.extract_fields(text)`** (pure, no image)
- **UTR:**
  - Prefer a 12-digit number near `UPI Ref`, `UPI Reference`, `UPI Ref No`, `UTR`, `RRN`, `Ref No`, or `Transaction ID`. Use `Transaction ID` only when it is exactly 12 digits.
  - Fallback: any standalone `\b\d{12}\b`.
  - Reject tokens starting with `T` (PhonePe IDs) and numbers longer than 12 digits.
- **OCR fixes:** `O→0 o→0 I→1 l→1 S→5 B→8`, applied **only inside candidate number tokens**, never to normal words. Example: `UPI Ref No 12345678901O` gives `123456789010`.
- **Amount:**
  - The number after `₹`, `Rs`, `Rs.` or `INR`. If none, a standalone amount near "paid", "successful" or "sent".
  - `1,000.00` parses as `1000.0`.
  - Tesseract often misreads `₹` as `%`, `X` or `2`, so handle that defensively.
- Return None when unsure. Never guess.

**Step 2: `ocr.analyze_screenshot(image_bytes)`**
- Decode **in memory** (`np.frombuffer` + `cv2.imdecode`). Never write the image to disk. No temp files.
- If width < 1000, upscale 2x. Then greyscale, a light sharpen, and an adaptive threshold.
- If `settings.TESSERACT_CMD` is set, assign it to `pytesseract.pytesseract.tesseract_cmd`.
- Run `pytesseract.image_to_data(..., config="--psm 6", lang="eng")` to get the text plus word confidences, then call `extract_fields`.
- `confidence` is the Tesseract confidence of the UTR token (0 if none). Below `OCR_MIN_CONF`, set `utr=None`.
- `image_sha256` is the sha256 of the original bytes. `image_phash = str(imagehash.phash(Image.open(BytesIO(...))))`. `raw_text_len = len(text)`.
- Never return or store the raw text.

**Step 3: `POST /api/proof`**
- Error checks:
  - The merchant must exist (404).
  - `content_type` in `image/jpeg|png|webp` (415).
  - Size ≤ `MAX_UPLOAD_MB` (413).
  - Pillow must be able to open it (400).
- Read the bytes, then call `await image.close()` immediately. Starlette may spool uploads over 1 MB to a temp file that is deleted on close. Note this in the README limitations.
- Call `analyze_screenshot`, then create `Case(status=WAITING, reason="Checking…", <OcrResult fields>, ocr_confidence=confidence)`.
- Commit, then call `matcher.evaluate_case(session, case)`.
- Return `{case_id, status, reason}`.

**Step 4: `static/pay.html`** (served at `/pay/<merchant_id>`)
- Mobile-first. One big button "Upload payment screenshot" using `<input type="file" accept="image/*">`. Do **not** add the `capture` attribute, so both gallery and camera work.
- Read the merchant id from `location.pathname`. POST `FormData` to `/api/proof`.
- Show a spinner, then "Sent ✓ — show this to the shopkeeper" plus a coloured status. Optionally poll `/api/cases/{id}` every 3 s while WAITING.
- No login, no analytics, no external scripts or CDNs.

**Step 5: privacy**
- `set_consent`:
  - Set `consent_given` and `consent_at`.
  - Withdrawing (`given=False`) **deletes** that merchant's BankCredit rows.
- `purge_expired_credits`: delete BankCredit rows older than `RETENTION_DAYS` and return the count.
- `POST /api/merchants/{id}/consent {given}`:
  - `X-Token` must equal that merchant's `api_token` (401 if missing or wrong, 404 if there is no merchant).
  - Returns `{consent_given}`.

**Step 6: mock bank (demo backup)**
- `static/mock-bank.html`:
  - Red banner **"DEMO BACKUP — simulated bank SMS"**.
  - Form fields: merchant_id, UTR, amount.
- `POST /api/mock-bank`:
  - Build the agreed demo SMS with sender `AX-HDFCBK`.
  - Call `ingest.ingest_sms(session, merchant, sender, body, utcnow())`.
  - Return `{accepted: credit is not None}`.

**Step 7: tests**
- `test_ocr_fields.py` (text strings only):
  - GPay-style
  - PhonePe-style with a `T2311221234567890` ID that must be ignored
  - Paytm-style
  - O/0 confusion inside the UTR
  - `₹1,000.00` gives 1000.0
  - A 13-digit number is rejected
  - No UTR gives None
- `test_privacy.py`:
  - Withdrawing consent deletes only that merchant's credits.
  - The purge removes only rows older than 7 days.
  - The consent endpoint rejects a wrong `X-Token`.

**Done when:**
- `pytest -q` is green.
- `curl -F merchant_id=<id> -F image=@shot.jpg http://localhost:8000/api/proof` reads the right UTR and amount from a real screenshot.
- The pay page works from a phone.

**Stretch** (only after the PR is merged, everything is green, and Anoop says go): `forensics.assess` returns `risk_score` 0–1 plus reasons, using colour-uniformity patch detection around the amount and basic layout sanity. It **never** decides the verdict. No external AI APIs.

---

## 6. Pile 3 — Verification & Trust (`feat/trust`)

**My files:** `app/sms_parser.py`, `app/ingest.py`, `app/matcher.py`, `app/signing.py`, `app/routes_sms.py`, `app/routes_records.py`, `static/record.html`, `tests/test_sms_parser.py`, `tests/test_matcher.py`, `tests/test_signing.py`

**Step 1: `sms_parser.parse_bank_sms(sender, body)`**
- **Sender:**
  - Must match `^[A-Z]{2}-[A-Z0-9]{6}(-[A-Z])?$`.
  - The 6-char code must be in `BANK_CODES = {HDFCBK, SBIUPI, SBIINB, ICICIB, AXISBK, KOTAKB, PNBSMS, BOIIND, UNIONB, CANBNK, IDFCFB, YESBNK, PAYTMB, AIRBNK, INDBNK}`.
  - Phone numbers return None.
- **Drop (return None):**
  - OTP: `OTP`, `one time password`
  - Debits: `debited`, `\bDR\b`, `withdrawn`, `spent`
  - Anything without a credit word (`credited`, `received`, `deposited`, `\bCR\b`)
- **UTR:** exactly 12 digits, from `UPI Ref No`, `Ref No`, `UTR`, `RRN`, or `UPI/CR/<12 digits>`. Reject longer numbers.
- **Amount:** after `Rs.`, `Rs`, `INR` or `₹`, with commas allowed.
- If the UTR or amount is missing, return None.
- **Must parse the demo format.**

**Step 2: `ingest.ingest_sms(...)`**
- Parse. If the result is None, return None and store nothing.
- Save `BankCredit(merchant_id, utr, amount, credited_at=as_utc(received_at) or utcnow(), sender_id)`, then commit.
- Call `matcher.on_new_credit(session, credit)` and return the credit.
- Never store, log or print the raw body.

**Step 3: `POST /api/sms`**
- `X-Token` identifies the merchant (401 if unknown).
- If `consent_given` is False, return **403 `{"detail": "consent required"}`**.
- Call `ingest`.
- Always return 200 `{accepted: bool}` when auth is valid, so the forwarder doesn't retry dropped OTPs.

**Step 4: `matcher.py`** — `evaluate_case` checks in this exact order:
1. `utr is None` → NOT_VERIFIED (unreadable reason above).
2. The UTR is in `UsedUTR` → NOT_VERIFIED `"This UTR was already used on <time> (replay)"`.
3. Another case (`id != this`) has the same `image_sha256`, or a pHash distance ≤ 6 (`imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)`, skipping empty hashes) → NOT_VERIFIED `"Same screenshot seen before"`.
4. Look for a BankCredit with the same merchant and the same UTR, and `|credited_at − case.created_at| ≤ MATCH_WINDOW_MIN`:
   - Amount equal within ±0.01 → in **one transaction**, insert `UsedUTR` and set VERIFIED `"Payment received in bank"`, with `bank_credited_at`. On `IntegrityError`: rollback → NOT_VERIFIED replay. This makes it race-safe.
   - Amount different → NOT_VERIFIED `"Amount on screen ₹X, bank credited ₹Y (edited amount)"`.
5. Otherwise → WAITING `"Looks fine, waiting for bank SMS"`.

After the verdict:
- Final verdict: set `decided_at=utcnow()`, commit, `signing.sign_case`, `events.publish`.
- WAITING: commit, `events.publish`.

Other matcher functions:
- `on_new_credit`: run `evaluate_case` on every WAITING case with the same merchant and the same UTR, and return them.
- `expire_waiting`: every WAITING case older than `MATCH_WINDOW_MIN` becomes NOT_VERIFIED `"No bank credit within 5 minutes"` (sign + publish). Return the count.

**Step 5: `signing.py`** (Ed25519 via `cryptography`)
- **Keys:** load or generate the PEM private key at `settings.SIGNING_KEY_PATH`, creating the parent dir if needed. It is gitignored. **Never commit it.**
- **`sign_case`:**
  - If a Record already exists, return it. Records are write-once.
  - Build `{app_version, case_id, merchant_id, verdict, reason, utr, amount, image_sha256, proof_time, bank_credit_time, decided_time}` with ISO strings (None allowed).
  - `record_sha256` is the sha256 of `canonical_json`. `signature = base64(sign(canonical bytes))`.
  - Insert the Record.
- **`verify_record`:** accepts a str or dict. `json.loads`, re-canonicalise, then verify. Return False on any exception.
- **`public_key_b64`:** base64 of the raw public key.

**Step 6: record routes**
- `GET /record/{id}` serves `static/record.html` (404 if there is no Record).
- `GET /api/records/{id}` returns `{record, record_json, record_sha256, signature, public_key}`.
- `GET /api/public-key` returns `{algorithm: "Ed25519", public_key}`.
- `POST /api/records/verify` returns `{valid}`.

**Step 7: `static/record.html`**
- Read the id from the path and fetch `/api/records/{id}`.
- Show: a big verdict badge (green or red), amount, UTR, proof/bank/decided times, the reason, and the sha256 and signature (wrapping monospace).
- A **"Verify this record"** button shows ✅ Valid or ❌ Invalid.
- Add print CSS. No external scripts.

**Step 8: tests** (monkeypatch `settings.SIGNING_KEY_PATH` to `tmp_path / "key.pem"`)
- `test_sms_parser.py`:
  - The demo format parses.
  - `UPI/CR/` parses.
  - A phone-number sender is rejected.
  - An unknown bank code is rejected.
  - OTP, debit and promo messages are dropped.
  - A 13-digit ref is rejected.
- `test_matcher.py`:
  - Genuine → VERIFIED.
  - Late SMS: WAITING, then `on_new_credit` → VERIFIED.
  - Replay UTR → NOT_VERIFIED.
  - Duplicate image → NOT_VERIFIED.
  - Edited amount: both amounts appear in the reason.
  - A credit outside the window does not match.
  - `expire_waiting` timeout.
  - `utr=None` → NOT_VERIFIED.
- `test_signing.py`:
  - Sign, then verify → True.
  - One field changed → False.
  - A second `sign_case` returns the same Record.
  - `/api/sms` with consent off → 403.
  - An OTP via `/api/sms` stores no BankCredit.

**Done when:**
- The 3 demo scenarios work with curl only:
  1. Proof, then SMS → VERIFIED
  2. Proof first gives WAITING, then the SMS → VERIFIED
  3. The same screenshot or UTR again → NOT_VERIFIED (replay)
- `/record/<id>` opens on a phone, and Verify says Valid.

---

## 7. Pile 1 — Platform & Merchant (`feat/platform`, Anoop)

Done on `main`: scaffold, contracts, stubs, SSE event bus, background loop, merchant creation + QR, case status, page routes, smoke tests.
Next on `feat/platform`:
- `merchant.html`: live card per latest case (green/amber/red), reason, amount, time, record link. SSE plus a 3 s polling fallback.
- Hindi/English voice (`speechSynthesis`) behind a "Start listening" tap.
- `scripts/seed_demo.py`.
- Then Phase 6: cloudflared tunnel + `BASE_URL`, SMS-forwarder setup notes, README, rehearsal.
- Review and merge PRs.

## 8. Timeline

| When | What |
|---|---|
| T+0:00–0:25 | Scaffold on main (done). B and C: setup, accept the invite, read the docs |
| T+0:25–2:00 | All three build in parallel and commit every 20–30 min. **T+1:15**: 5-min sync |
| T+2:00–2:30 | PRs opened, reviewed, merged. `pytest -q` on main |
| T+2:30–3:30 | Integration: 3 scenarios with curl, then with phones |
| T+3:30–4:30 | Demo readiness + rehearsal. Stretch only if green |
| 07:00 / 07:20 | Code freeze / final push (lock 07:30) |
