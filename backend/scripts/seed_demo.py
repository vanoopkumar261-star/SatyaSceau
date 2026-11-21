"""Seed the demo shop and print everything needed to run the demo.  Owner: Pile 1 (Platform).

Run from backend/ (the server does not need to be running):
    python scripts/seed_demo.py                # create the demo shop, or reuse it (same token, same QR)
    python scripts/seed_demo.py --rotate       # same shop, new SMS token + screen key
    python scripts/seed_demo.py --new          # a brand-new shop
    python scripts/seed_demo.py --base-url https://xyz.trycloudflare.com

Re-running is safe: the token you typed into the phone's SMS forwarder keeps working.
Phones can't open "localhost": set BASE_URL in backend/.env to your tunnel URL, then re-run so the QR points there.
"""

import argparse
import sys
from datetime import timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # make `app` importable from anywhere

import qrcode  # noqa: E402
from PIL import Image, ImageDraw, ImageFont  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import engine, init_db, utcnow  # noqa: E402
from app.models import Merchant, new_id  # noqa: E402

DEFAULT_NAME = "Raju Tea Stall"
DEFAULT_UPI = "raju@okaxis"
DEMO_SENDER = "AX-HDFCBK"


def seed_merchant(session: Session, name: str, upi_id: str, *, new: bool = False, rotate: bool = False):
    """Return (merchant, action) with action in {"created", "reused", "rotated"}.

    The demo shop is opted in to SMS forwarding: in the demo, the shop owner has agreed to it.
    """
    merchant = None
    if not new:
        merchant = session.exec(
            select(Merchant).where(Merchant.name == name).order_by(Merchant.created_at.desc())
        ).first()

    if merchant is None:
        merchant = Merchant(name=name, upi_id=upi_id)
        action = "created"
    elif rotate:
        merchant.api_token, merchant.screen_key = new_id(24), new_id(16)
        action = "rotated"
    else:
        action = "reused"

    if not merchant.screen_key:  # shops created before screen keys existed
        merchant.screen_key = new_id(16)
    if not merchant.consent_given:
        merchant.consent_given, merchant.consent_at = True, utcnow()
    session.add(merchant)
    session.commit()
    session.refresh(merchant)
    return merchant, action


def _font(size: int):
    for name in ("arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def write_qr_poster(url: str, shop_name: str, path: Path) -> Path:
    """Printable counter poster: heading, shop name, QR, footer. PNG."""
    qr = qrcode.make(url, box_size=12, border=2).get_image().convert("RGB")
    pad, width = 40, max(qr.width + 80, 640)
    lines = [
        ("Paid by UPI? Scan to send your proof", _font(30)),
        (shop_name, _font(40)),
    ]
    footer = ("SatyaSceau - Every payment gets a witness", _font(20))

    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    def height(text, font):
        box = probe.textbbox((0, 0), text, font=font)
        return box[3] - box[1]

    top = pad + sum(height(t, f) + 16 for t, f in lines)
    total_h = top + qr.height + 24 + height(*footer) + pad
    poster = Image.new("RGB", (width, total_h), "white")
    draw = ImageDraw.Draw(poster)

    y = pad
    for text, font in lines:
        draw.text((width // 2, y), text, fill="black", font=font, anchor="mt")
        y += height(text, font) + 16
    poster.paste(qr, ((width - qr.width) // 2, top))
    draw.text((width // 2, top + qr.height + 24), footer[0], fill="#555555", font=footer[1], anchor="mt")

    path.parent.mkdir(parents=True, exist_ok=True)
    poster.save(path)
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Create or reuse the SatyaSceau demo shop.")
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument("--upi", default=DEFAULT_UPI)
    parser.add_argument("--base-url", default=settings.BASE_URL, help="public URL phones use (default: BASE_URL)")
    parser.add_argument("--port", type=int, default=8000, help="local server port (for the laptop link)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--new", action="store_true", help="create another shop instead of reusing")
    group.add_argument("--rotate", action="store_true", help="new SMS token + screen key for the same shop")
    args = parser.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows console + shop names

    base = args.base_url.rstrip("/")
    init_db()
    with Session(engine) as session:
        m, action = seed_merchant(session, args.name, args.upi, new=args.new, rotate=args.rotate)

    pay_url = f"{base}/pay/{m.id}"
    screen_path = f"/merchant?m={m.id}#k={m.screen_key}"
    screen_url = base + screen_path
    is_local = "localhost" in base or "127.0.0.1" in base
    if is_local:
        screen_lines = f"  Merchant screen  {screen_url}"
    else:  # quick tunnels buffer the live stream: the laptop gets instant updates over localhost
        screen_lines = (f"  Merchant screen  laptop (instant): http://localhost:{args.port}{screen_path}\n"
                        f"                   any phone (~3 s): {screen_url}")
    qr_path = write_qr_poster(pay_url, m.name, settings.DATA_DIR / f"demo_qr_{m.id}.png")
    today = utcnow().astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%d-%m-%y")  # banks write IST
    sms_body = f"Rs.1.00 credited to A/c XX1234 on {today} by UPI Ref No 123456789012. -HDFC Bank"

    print(f"""
SatyaSceau demo shop ({action})
  Shop             {m.name}   (id {m.id})
  Customer QR      {qr_path}
                   opens {pay_url}
{screen_lines}
  SMS forwarding   consent ON (demo opt-in)

Android SMS forwarder  (forward bank senders only, e.g. {DEMO_SENDER})
  POST    {base}/api/sms
  Header  X-Token: {m.api_token}
  JSON    {{"sender": "<SMS sender>", "body": "<SMS text>", "received_at": "<ISO time, optional>"}}

Test a bank SMS without a phone (PowerShell):
  Invoke-RestMethod -Method Post -Uri {base}/api/sms -Headers @{{"X-Token"="{m.api_token}"}} -ContentType "application/json" -Body '{{"sender":"{DEMO_SENDER}","body":"{sms_body}"}}'
""")
    if is_local:
        print("  NOTE: phones can't open localhost. Start a tunnel, put its URL in backend/.env as BASE_URL,")
        print("        then re-run this script so the QR points at it (the token stays the same).\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
