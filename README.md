# SatyaSceau

> **Every payment gets a witness.**

SatyaSceau is a web platform that verifies UPI payment proofs for gig workers and small merchants. The merchant opens a case, the customer uploads the original payment screenshot through a unique QR link, and the system cross-checks it against the receiver's own record (bank SMS or payment gateway webhook) and issues a hash-locked, timestamped evidence record.

## Features

_Coming soon._

## Architecture

_Coming soon._

## Setup

**Requirements:** Python 3.11+, [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)
- Windows: `winget install UB-Mannheim.TesseractOCR`
- Mac: `brew install tesseract`
- Linux: `sudo apt install tesseract-ocr`

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Mac/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # optional: edit BASE_URL, TESSERACT_CMD, ...
pytest -q
uvicorn app.main:app --reload --host 0.0.0.0
```

Then open http://localhost:8000/docs.

**Windows note:** if `import sqlalchemy` fails with *"An Application Control policy has blocked this file"*, Smart App Control is blocking SQLAlchemy's compiled DLL. Reinstall it as pure Python (keep Smart App Control on):

```bash
set DISABLE_SQLALCHEMY_CEXT=1     # PowerShell: $env:DISABLE_SQLALCHEMY_CEXT=1
pip install --force-reinstall --no-deps --no-binary sqlalchemy "sqlalchemy==2.1.9"
```

## Team

_Coming soon._

---

Built for **Hacknovate 2026**, siNUsoid vX, NIIT University.
