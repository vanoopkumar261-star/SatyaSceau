# CLAUDE.md — SatyaSceau project context

Context for future Claude Code sessions working on this repo. Read this first.

## Team

- **Team name:** Billi meows
- **Event:** Hacknovate 2026, siNUsoid vX, NIIT University

## Problem

Fake, edited, reused, or "pending" UPI payment screenshots cheat delivery riders and shopkeepers. A screenshot proves nothing on its own — anyone can fake one. **The receiver's own bank record is the only source of truth.** SatyaSceau verifies a customer's claimed payment against what the receiver actually received.

## Core rule

The **12-digit UPI Reference Number (RRN / UTR)** is the same on both the sender's and the receiver's side — it is the anchor for matching. App-specific transaction IDs (like PhonePe's "T..." ID) differ per side and are **ignored**.

## Two account modes

- **Personal** — verify against the worker's own bank SMS. Only **official sender IDs** are trusted.
- **Company** — Razorpay **test-mode** dynamic QR plus **signed webhooks** as the receiver record.

## Doorstep flow

1. Merchant opens a **case** with a random (unguessable) ID.
2. Case generates a **QR** link.
3. Customer uploads the **original** payment screenshot via the link — **no login required**.
4. System **verifies** the screenshot against the receiver record.
5. Merchant's screen updates **live**: green / amber / red.
6. Result is written to a **locked record** at `/record/<id>`.

## Verdict engine

- **Layer 1 — decides (hard match):** RRN, payee, exact amount, time window, plus **replay protection**. This layer determines the pass/fail outcome.
- **Layer 2 — warns (risk score):** layout-template check, brand-colour and colour-uniformity patch detection, text-logic checks, ELA (error-level analysis), metadata / C2PA inspection, duplicate fingerprinting. Produces a risk score; does not override Layer 1 on its own.
- **Layer 3 — combines + locks:** merges Layer 1 and Layer 2 into a final verdict — **Verified / Suspicious / Mismatch** — and **hash-locks** the record.

## Stack

- **Frontend:** Next.js
- **Backend (OCR + forensics):** Python FastAPI
- **Data + realtime:** Supabase / Postgres plus Realtime
- **Payments:** Razorpay (test mode)

## Security

- Unguessable, **expiring, single-use** links.
- **Webhook signature** verification.
- **Rate limiting**.
- **Upload validation** (type/size/content).
- **Immutable SHA-256** records.

## Out of scope

- Our own wallet or UPI IDs — needs RBI / NPCI licensing.
- Direct bank access — Account Aggregator is **future scope**.

## Hackathon rules (operational constraints)

- **All code must be written during the event window.**
- **Every team member must commit.**
- The GitHub repo **locks at 7:30** — keep commits small and frequent.
