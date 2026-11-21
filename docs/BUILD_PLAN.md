# SatyaSceau — Build Plan for Claude Code

> Save this file in the repo as `docs/BUILD_PLAN.md`, then tell Claude Code:
> **"Read docs/BUILD_PLAN.md and CLAUDE.md. Start with Phase 0. After each phase: run the tests, show me what changed, and STOP until I say `next`. Do not commit or push — we commit ourselves."**

---

## 0. Context (read first)

**Product:** SatyaSceau — "Every payment gets a witness."
A customer shows a UPI "payment successful" screen. We tie that screenshot to a real bank credit on the merchant's/rider's side and give a verdict in seconds, plus a signed, shareable record.

**Core rule:** the screenshot is only a *claim*. The receiver's bank credit SMS is the *truth*. The 12-digit UPI reference number (UTR/RRN) is the same on both sides — that's the join key. Ignore app-specific IDs (e.g. PhonePe "T…" IDs).

**Verdicts:**
- 🟢 **VERIFIED** — screenshot UTR + amount match a bank credit SMS within the time window, and the UTR was never used before.
- 🟡 **WAITING** — screenshot looks fine but no matching bank credit yet. Re-check for up to 5 minutes.
- 🔴 **NOT VERIFIED** — UTR already used (replay), same image seen before, amount mismatch, or 5 minutes passed with no credit.

**Hard constraints (hackathon):**
- ~5 hours to the GitHub lock at 07:30. Working demo beats feature count.
- Every team member must commit their own work. Claude Code must NOT commit, push, or set fake authors.
- Keep it simple: one FastAPI app that also serves plain HTML pages. No React/Next build step.
- Database: **SQLite** (via SQLModel). No external DB setup tonight.

---

## 1. Folder structure

```
satyasceau/
  backend/
    app/
      main.py            # FastAPI app, routes, static pages
      db.py              # SQLModel engine + session
      models.py          # tables
      ocr.py             # preprocessing + Tesseract + field extraction
      sms_parser.py      # bank SMS parsing + sender allowlist
      matcher.py         # verdict engine (match, window, replay)
      signing.py         # Ed25519 record signing + verify
      privacy.py         # consent, retention cleanup, data minimisation
      forensics.py       # OPTIONAL stretch: image risk signals
      config.py          # env settings
    static/
      pay.html           # customer page (camera/gallery upload, no login)
      merchant.html      # merchant live screen + voice verdict
      record.html        # public shareable signed record
      mock-bank.html     # backup panel to inject a fake bank SMS
    tests/
      test_sms_parser.py
      test_ocr_fields.py
      test_matcher.py
      test_privacy.py
      test_signing.py
    requirements.txt
  docs/BUILD_PLAN.md
  README.md
  CLAUDE.md
  .env.example
```

---

## 2. Data model (SQLite)

```
Merchant      id (short random), name, upi_id, api_token (random, for SMS forwarder),
              consent_given (bool), consent_at, created_at

Case          id (random 10+ chars, unguessable), merchant_id, status
              (WAITING | VERIFIED | NOT_VERIFIED), reason (plain words),
              utr, amount, image_sha256, image_phash, ocr_confidence,
              risk_score (nullable), created_at, decided_at

BankCredit    id, merchant_id, utr, amount, credited_at, sender_id, created_at
              # NO raw SMS text stored. Auto-delete after 7 days.

UsedUTR       utr (PRIMARY KEY / UNIQUE), case_id, used_at
              # replay protection enforced by the DB itself

Record        case_id (PK), record_json (canonical), record_sha256,
              signature (Ed25519, base64), created_at
              # write-once: never update/delete through the app
```

---

## 3. API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/merchants` | Create merchant → returns id, api_token, printable QR URL |
| POST | `/api/merchants/{id}/consent` | Opt in / opt out of SMS forwarding |
| GET  | `/pay/{merchant_id}` | Serves `pay.html` (what the printed QR opens) |
| POST | `/api/proof` | multipart: `merchant_id`, `image` → OCR → creates Case → runs matcher → returns case id + status |
| POST | `/api/sms` | From Android forwarder. Header `X-Token`. Body: `{sender, body, received_at}` |
| GET  | `/api/merchants/{id}/stream` | Server-Sent Events: pushes case status changes live |
| GET  | `/api/cases/{id}` | Case status (polling fallback) |
| GET  | `/record/{case_id}` | Public signed record page (the unique shareable link) |
| GET  | `/api/records/{case_id}` | Record JSON + hash + signature |
| GET  | `/api/public-key` | Ed25519 public key so anyone can verify |
| POST | `/api/records/verify` | Paste record JSON + signature → valid/invalid |
| GET  | `/mock-bank` | Backup panel to inject a credit SMS during demo |

---

## 4. Phases (do in order, stop after each)

### Phase 0 — Scaffold (15 min)  · owner: Anoop
1. Create the folder structure above, `requirements.txt`:
   `fastapi uvicorn[standard] sqlmodel python-multipart pytesseract pillow opencv-python-headless imagehash cryptography pytest httpx python-dotenv qrcode`
2. `config.py` reads `.env`: `SIGNING_KEY_PATH`, `MATCH_WINDOW_MIN=5`, `RETENTION_DAYS=7`, `BASE_URL`.
3. `db.py` creates tables on startup. `main.py` mounts `static/`, has `/health`.
4. Check Tesseract is installed (`tesseract --version`); if missing, print the install command for the OS and stop.
5. README "Run locally" section: create venv, install, `uvicorn app.main:app --reload --host 0.0.0.0`.
**Done when:** `/health` returns ok and `pytest` runs (0 tests is fine).

### Phase 1 — OCR: read UTR + amount from a screenshot (45 min)  · owner: Sahajta / Barsha
1. `ocr.py` preprocessing: load with OpenCV → if width < 1000 upscale 2x → greyscale → light sharpen → adaptive threshold. Run Tesseract (`--psm 6`, lang `eng`). Keep word-level confidences.
2. Field extraction from the text:
   - **UTR:** prefer a 12-digit number near anchors like `UPI Ref`, `UPI Reference`, `UTR`, `RRN`, `Ref No`, `Transaction ID` *only if 12 digits*. Fallback: any standalone `\b\d{12}\b`. Reject numbers starting with `T` or longer than 12.
   - Fix OCR confusions **only inside candidate number tokens**: O→0, o→0, I/l→1, S→5, B→8.
   - **Amount:** after `₹`, `Rs`, `INR` or a large standalone number near "paid"/"successful"; parse `1,000.00` → 1000.00.
   - Return `{utr, amount, confidence, raw_text_len}` — do NOT persist raw text.
3. If UTR confidence is low or missing → status NOT_VERIFIED with reason "Could not read the UPI reference clearly — ask the customer to retake" (don't guess).
4. Compute `image_sha256` and perceptual hash (`imagehash.phash`) here. **Discard the image after processing** (never write it to disk).
5. Tests in `test_ocr_fields.py` using text strings (not images): GPay-style, PhonePe-style (with a `T…` ID that must be ignored), Paytm-style, O/0 confusion, amount with commas.
**Done when:** tests pass and uploading a real screenshot via curl returns UTR + amount.

### Phase 2 — Bank SMS ingest + verdict engine (45 min)  · owner: cybersecurity teammate
1. `sms_parser.py`:
   - **Sender allowlist:** accept only DLT-style bank sender IDs matching `^[A-Z]{2}-[A-Z0-9]{6}(-[A-Z])?$` whose 6-char code is in a bank list (HDFCBK, SBIUPI, SBIINB, ICICIB, AXISBK, KOTAKB, PNBSMS, BOIIND, UNIONB, CANBNK, IDFCFB, YESBNK, PAYTMB, AIRBNK, INDBNK — extend as needed). Plain 10-digit numbers → rejected.
   - **Credits only:** must contain credit words (`credited`, `received`, `CR`, `deposited`). Drop debits, OTPs (`OTP`, `one time password`), promos → return `None`, store nothing.
   - Extract 12-digit UTR (`UPI Ref`, `Ref No`, `UPI/CR/<12 digits>` patterns) and amount.
2. `/api/sms`: check `X-Token` belongs to a merchant; reject if `consent_given` is false (HTTP 403 "consent required"). Save only `{utr, amount, credited_at, sender_id}`.
3. `matcher.py` — run on every new proof AND every new bank credit:
   - **Replay first:** if UTR exists in `UsedUTR` → NOT_VERIFIED "This UTR was already used on <time> (replay)". If `image_sha256` matches a previous case, or pHash distance ≤ 6 → NOT_VERIFIED "Same screenshot seen before".
   - **Match:** BankCredit for the same merchant with same UTR, amount equal (±0.01), credited within `MATCH_WINDOW_MIN` of the proof → VERIFIED; insert into `UsedUTR` in the same DB transaction (unique constraint = race-safe).
   - Same UTR but different amount → NOT_VERIFIED "Amount on screen ₹X, bank credited ₹Y (edited amount)".
   - No credit yet → WAITING "Looks fine, waiting for bank SMS".
   - Background task every 15 s: WAITING cases older than 5 min → NOT_VERIFIED "No bank credit within 5 minutes".
4. Tests `test_sms_parser.py` + `test_matcher.py`: genuine match, late SMS (WAITING then VERIFIED), replay UTR, duplicate image, edited amount, fake sender number rejected, OTP/debit dropped, timeout.
**Done when:** all three demo scenarios work using curl only.

### Phase 3 — Customer page + merchant live screen + voice (30 min)  · owner: Anoop
1. `pay.html`: mobile-first, one big button "Upload payment screenshot" (`<input type="file" accept="image/*">` — allows gallery AND camera). Shows "Sent ✓, show this to the shopkeeper". No login, no tracking.
2. `merchant.html?m=<id>`: big coloured card per latest case (green/amber/red), reason in words, amount, time, link to `/record/<id>`. Connect to SSE stream; fall back to polling `/api/cases/{id}` every 3 s.
3. **Voice:** Web Speech API `speechSynthesis`. Toggle Hindi/English. Hindi: VERIFIED "भुगतान सत्यापित हुआ", WAITING "बैंक का इंतज़ार है, ग्राहक को रोकें", NOT_VERIFIED "भुगतान सत्यापित नहीं हुआ". Needs one tap on the page first to unlock audio — add a "Start listening" button.
4. Printable QR: `/api/merchants` response includes a PNG QR (via `qrcode`) pointing to `BASE_URL/pay/<merchant_id>`.
**Done when:** phone uploads → laptop/merchant phone turns colour and speaks.

### Phase 4 — Signed shareable record (30 min)  · owner: cybersecurity teammate
1. `signing.py`: generate Ed25519 keypair on first run, save private key to `SIGNING_KEY_PATH` (gitignored!). Expose public key.
2. When a case reaches VERIFIED or NOT_VERIFIED: build canonical JSON (`json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)`) with case id, merchant id, verdict, reason, UTR, amount, image_sha256, proof time, bank credit time, decided time, app version. SHA-256 it, sign it, insert `Record`. Never update a Record.
3. `record.html`: printable certificate — verdict badge, timestamps, reasons, hashes, signature, "Verify this record" button that calls `/api/records/verify`.
4. Tests `test_signing.py`: verify passes; changing one field fails.
**Done when:** `/record/<id>` opens on any phone and the verify button says valid.

> Note: the current slides say HMAC-SHA256. Update the slide to **Ed25519 signature** — anyone can verify it with our public key; HMAC only lets *us* verify.

### Phase 5 — Privacy rules + mock bank (30 min)  · owner: Manan / any
1. `privacy.py`: on startup and hourly, delete BankCredit rows older than `RETENTION_DAYS`. Consent endpoint toggles forwarding; withdrawing consent deletes that merchant's stored credits.
2. Confirm in code: no image ever written to disk; no raw SMS text stored; only UTR/amount/time kept.
3. `mock-bank.html`: form (merchant, UTR, amount) → calls the same internal ingest as `/api/sms` with a valid bank sender. Label it clearly **"DEMO BACKUP — simulated bank SMS"**.
4. Tests `test_privacy.py`: consent off → 403; OTP not stored; retention deletes old rows.
**Done when:** all tests green.

### Phase 6 — Demo readiness (20 min)  · owner: Anoop
1. Public URL for phones: `cloudflared tunnel --url http://localhost:8000` (or ngrok). Set `BASE_URL`.
2. Android SMS forwarder app setup notes in README: POST to `BASE_URL/api/sms`, header `X-Token`, JSON `{sender, body, received_at}`, filter to bank senders only.
3. `scripts/seed_demo.py`: creates demo merchant, prints token + QR path.
4. Rehearse the 3 demo cases: real ₹1 payment (green), screenshot before SMS (amber → green), same screenshot again (red replay).
5. README: problem, how it works, run steps, team, limitations.

### Stretch only if everything above works — Forensics (adds risk, never decides)
- `forensics.py` own checks: colour-uniformity patch detection around the amount region, duplicate pHash, basic layout sanity. Output `risk_score` 0–1 + reasons shown in amber/red cards.
- Gemini/any external AI API: **off by default** behind `ENABLE_EXTERNAL_AI=false`. Ask mentors before enabling (rule: "no AI-generated thingy", and it sends customer images to a third party).

---

## 5. Rules for Claude Code while building
- Work one phase at a time. Small files, clear names, comments only where logic isn't obvious.
- After each phase: run `pytest -q`, list files changed, give each teammate the exact `git add`/`git commit -m` lines for their part. Do not run `git commit` or `git push` yourself.
- Never commit `.env`, keys, or `*.db`. Add them to `.gitignore` in Phase 0.
- If something is blocked (Tesseract missing, port busy), stop and say what's needed — don't invent workarounds that change the architecture.
- Prefer a working simple version over a clever unfinished one.
