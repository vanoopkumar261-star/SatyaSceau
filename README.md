# SatyaSceau

> **Every payment gets a witness.**

Fake, edited, reused or "pending" UPI screenshots cheat delivery riders and small shopkeepers every day. A screenshot proves nothing on its own. **The receiver's own bank credit is the only source of truth.**

SatyaSceau ties the customer's screenshot to a real bank credit on the merchant's side. It gives a verdict in seconds, spoken aloud at the counter, plus a signed record anyone can check.

## How it works

1. The shop prints its **QR**. The customer scans it and uploads the original payment screenshot. No app, no login.
2. **OCR** reads the 12-digit **UPI reference (UTR)** and the amount. The UTR is identical on both sides of a UPI payment. App IDs like PhonePe's `T…` differ per side and are ignored.
3. The merchant's phone forwards **bank credit SMS** from official bank sender IDs only. Only the UTR, amount, time and sender are kept, never the SMS text.
4. The **verdict engine** decides:
   - 🟢 **VERIFIED**: UTR + amount match a bank credit within 5 minutes, and the UTR was never used before.
   - 🟡 **WAITING**: the screenshot looks fine, but there's no bank credit yet. It's re-checked for up to 5 minutes.
   - 🔴 **NOT VERIFIED**: replayed UTR, same screenshot seen before, edited amount, unreadable image, or no credit in time.
5. The merchant screen turns **green / amber / red** and **speaks the verdict** in Hindi or English.
6. Every final verdict becomes a **write-once record signed with Ed25519** at `/record/<id>`. Anyone can verify it with our public key, and changing any field breaks the signature.

## Features

- No-login customer upload from a printed QR
- OCR of UTR and amount with Tesseract and OpenCV. Images are processed in memory and never stored.
- Bank-SMS ingest with a DLT sender allowlist. OTP, debit and promo messages are dropped.
- Replay protection enforced by the database (a unique UTR claim, race-safe), plus duplicate-screenshot detection (SHA-256 + perceptual hash)
- Live merchant screen (SSE with automatic polling fallback) with Hindi/English voice verdicts
- Ed25519-signed, write-once evidence records with in-page verification
- Privacy by design: consent-gated SMS forwarding, 7-day retention for bank credits, no raw text stored

## Architecture

One **FastAPI** app serves both the API and plain HTML pages (no build step). It uses **SQLite** via SQLModel.

```
customer phone ──QR──▶ /pay/<shop>  ──upload──▶  OCR (Tesseract)  ─┐
merchant phone ──SMS forwarder──▶ /api/sms ──▶ SMS parser ──────────┤
                                                                    ▼
                         verdict engine (UTR, amount, window, replay, duplicate image)
                                   │                         │
                    live screen + voice (SSE)        Ed25519 signed record (/record/<id>)
```

| Area | Files (`backend/app/`) |
|---|---|
| Platform, merchant screen, voice | `main.py`, `routes_merchant.py`, `events.py`, `static/merchant.html` |
| OCR, customer page, privacy | `ocr.py`, `routes_proof.py`, `privacy.py`, `static/pay.html` |
| SMS, verdicts, signing | `sms_parser.py`, `ingest.py`, `matcher.py`, `signing.py`, `static/record.html` |

## Setup

**Requirements:** Python 3.11+, [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)
- Windows: the UB Mannheim installer, or `winget install UB-Mannheim.TesseractOCR`
- Mac: `brew install tesseract`
- Linux: `sudo apt install tesseract-ocr`

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # Windows: set TESSERACT_CMD=C:/Program Files/Tesseract-OCR/tesseract.exe
pytest -q
uvicorn app.main:app --reload --timeout-graceful-shutdown 3 --host 0.0.0.0
```

Then open http://localhost:8000/docs.

**Windows note:** if `import sqlalchemy` fails with *"An Application Control policy has blocked this file"*, Smart App Control is blocking SQLAlchemy's compiled DLL. Reinstall it as pure Python, and keep Smart App Control on:

```bash
set DISABLE_SQLALCHEMY_CEXT=1     # PowerShell: $env:DISABLE_SQLALCHEMY_CEXT=1
pip install --force-reinstall --no-deps --no-binary sqlalchemy "sqlalchemy==2.1.9"
```

## Demo

**1. Tunnel (phones can't open `localhost`).** Download the official [`cloudflared`](https://github.com/cloudflare/cloudflared/releases) binary into `tools/` (gitignored). Then, with the server running:

```bash
cd backend
python scripts/demo_tunnel.py
```

This starts a Cloudflare quick tunnel over HTTP/2 (many campus networks block QUIC). It writes the public `https://….trycloudflare.com` URL into `.env` as `BASE_URL` and prints the demo shop's details. The server reads `BASE_URL` live, so it doesn't need a restart. The URL changes every time the tunnel restarts; just re-run the script.

**2. Demo shop.** `python scripts/seed_demo.py` creates or reuses the demo shop and writes a printable **QR poster** to `backend/data/`. It also prints:
- the merchant-screen links: **laptop (instant)** via localhost, and **any phone (~3 s)** via the tunnel
- the SMS-forwarder settings
- a ready-to-paste test SMS

Re-running keeps the same token. `--rotate` issues new keys and `--new` creates another shop.

**3. SMS forwarder (merchant's Android phone).** Use any "SMS to webhook/URL" forwarder app:
- **POST** `<BASE_URL>/api/sms`
- **Header** `X-Token: <api_token from seed_demo.py>`
- **JSON body** `{"sender": "<SMS sender>", "body": "<SMS text>", "received_at": "<ISO time, optional>"}`
- Filter it to bank senders only (e.g. `AX-HDFCBK`). The server ignores everything else anyway, but OTPs shouldn't leave the phone.

No phone handy? `/mock-bank` is a clearly labelled **demo backup** that injects a simulated bank SMS.

**4. The three demo cases**
1. **Genuine:** a real ₹1 UPI payment, upload the screenshot → 🟢 *"Payment received in bank"*, spoken aloud.
2. **Screenshot before SMS:** upload first → 🟡 waiting, then the SMS arrives → 🟢.
3. **Replay:** upload the same screenshot again → 🔴 *"Same screenshot seen before"* / *"UTR already used (replay)"*.

Open the 🟢 case's record link and press **Verify this record** → ✅ Valid.

## Limitations

- **Not a bank integration.** We rely on the merchant's own bank SMS. Direct bank access (Account Aggregator) is future scope, and running our own wallet or UPI IDs would need RBI/NPCI licensing.
- **Bank SMS formats vary.** The parser covers common formats and official DLT sender IDs. A new format needs a parser rule.
- **OCR can misread** blurry or cropped screenshots. Low-confidence reads are rejected with "retake", never guessed.
- **Quick tunnels buffer live streams**, so phones on the tunnel URL update by polling (~3 s). The laptop on localhost is instant.
- **Uploads:** images are processed in memory and never saved. The web framework may briefly spool uploads over 1 MB to a temporary file, which is deleted immediately.
- Shop creation is open (demo build). Production would add merchant sign-up and authentication.

## Team — Billi meows

| Member | Built |
|---|---|
| Anoop | Platform, merchant live screen + voice, demo tooling, integration |
| Aarav | Bank-SMS ingest, verdict engine, Ed25519 signed records |
| Sahajta | OCR, customer upload page, consent & privacy, mock bank |

---

Built for **Hacknovate 2026**, siNUsoid vX, NIIT University.
