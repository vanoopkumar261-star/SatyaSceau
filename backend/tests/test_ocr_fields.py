"""OCR field-extraction tests (text strings only, no images).  Owner: Pile 2 (Vision).

Spec: docs/WORK_SPLIT.md -> Pile 2, Step 7.
"""

from app.ocr import extract_fields

GPAY = """Google Pay
Payment successful
₹500
Paid to Ramesh Kirana
UPI transaction ID
412345678901
"""

PHONEPE = """PhonePe
Payment Successful
₹1,250.00
Paid to Sharma Stores
Transaction ID T2311221234567890
UTR: 345678901234
"""

PAYTM = """Paytm
Money sent successfully
Rs. 75.50
UPI Ref No: 298765432109
"""


def test_gpay_style():
    assert extract_fields(GPAY) == {"utr": "412345678901", "amount": 500.0}


def test_phonepe_ignores_t_id():
    r = extract_fields(PHONEPE)
    assert r["utr"] == "345678901234"
    assert r["amount"] == 1250.0


def test_paytm_style():
    assert extract_fields(PAYTM) == {"utr": "298765432109", "amount": 75.5}


def test_ocr_letter_confusion_inside_utr():
    assert extract_fields("UPI Ref No 12345678901O  ₹10")["utr"] == "123456789010"
    assert extract_fields("RRN: 4I2345678S01")["utr"] == "412345678501"


def test_confusion_fix_never_touches_words():
    # 12 letters from the confusable set must not become a number
    assert extract_fields("UPI Ref No: OOIlSBOOIlSB")["utr"] is None


def test_amount_with_commas():
    assert extract_fields("₹1,000.00\nUTR 123456789012")["amount"] == 1000.0
    assert extract_fields("INR 12,50,000\nUTR 123456789012")["amount"] == 1250000.0


def test_rupee_symbol_misread():
    assert extract_fields("%500\nUTR 123456789012")["amount"] == 500.0
    assert extract_fields("X 250.00\nUTR 123456789012")["amount"] == 250.0


def test_amount_near_keyword_without_symbol():
    assert extract_fields("Payment successful\n 350\n12:30 PM\nUTR 123456789012")["amount"] == 350.0


def test_thirteen_digit_number_rejected():
    assert extract_fields("UPI Ref No 1234567890123")["utr"] is None
    assert extract_fields("some id 1234567890123")["utr"] is None


def test_transaction_id_only_when_12_digits():
    assert extract_fields("Transaction ID 123456789012")["utr"] == "123456789012"
    assert extract_fields("Transaction ID T123456789012")["utr"] is None


def test_fallback_standalone_12_digits():
    assert extract_fields("Paid ₹20\nref 123456789012 done")["utr"] == "123456789012"


def test_spaced_utr():
    assert extract_fields("UPI Ref No 1234 5678 9012")["utr"] == "123456789012"


def test_no_utr_gives_none():
    r = extract_fields("Payment successful ₹99\nThank you")
    assert r["utr"] is None
    assert r["amount"] == 99.0
    assert extract_fields("") == {"utr": None, "amount": None}


# --- Patterns seen in REAL screenshots (structure only; numbers are made up) ----

# PhonePe dark mode: the rupee sign was read as £, the T-id must be ignored, UTR is labelled "UTR:",
# and the header date line must not be mistaken for the amount.
REAL_PHONEPE = """pe Transaction Successful
01:31 am on 22 Nov 2026
Paid to
The Waffle Busters £150
Q049100471@ybl
Payment Details
PhonePe Transaction ID
T261122013108669098781
Debited from
XXXXXXXXXXX1599 £150
UTR: 094974384030
"""

# GPay dark mode: the rupee sign was read as %, the 12-digit "UPI transaction ID" has no UTR label,
# and the "Google transaction ID" (14 letters/digits) must not be taken.
REAL_GPAY = """To SMOOTHIE ZONE CAFE AND BAKERY
%50 Completed
3 Nov 2026, 1:24 pm
Payment of 50 completed
UPI transaction ID
630748200742
To: SMOOTHIE ZONE CAFE AND BAKERY
Google transaction ID
CICAgPiFwJTnVg
"""


def test_real_phonepe_pattern():
    assert extract_fields(REAL_PHONEPE) == {"utr": "094974384030", "amount": 150.0}


def test_real_gpay_pattern():
    assert extract_fields(REAL_GPAY) == {"utr": "630748200742", "amount": 50.0}


def test_leading_zero_utr_kept_as_text():
    assert extract_fields("UTR: 094974384030")["utr"] == "094974384030"


def test_date_line_is_never_the_amount():
    assert extract_fields("Transaction Successful\n01:31 am on 22 Nov 2026")["amount"] is None
    # but an amount on its own line near "successful" is still found
    assert extract_fields("Transaction Successful\n01:31 am on 22 Nov 2026\n150")["amount"] == 150.0


# --- POST /api/proof (validation + happy path) --------------------------------

from io import BytesIO  # noqa: E402

from PIL import Image  # noqa: E402

from app.models import Case, Merchant  # noqa: E402


def _png(size=(200, 120), color="white") -> bytes:
    buf = BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


def _post(client, merchant_id, data, ctype="image/png"):
    return client.post(
        "/api/proof", data={"merchant_id": merchant_id}, files={"image": ("s.png", data, ctype)}
    )


def test_proof_errors(client, session):
    m = Merchant(name="Shop")
    session.add(m)
    session.commit()
    assert _post(client, "nope", _png()).status_code == 404
    assert _post(client, m.id, _png(), "text/plain").status_code == 415
    assert _post(client, m.id, b"not an image").status_code == 400


def test_proof_too_large(client, session, monkeypatch):
    from app.config import settings

    m = Merchant(name="Shop")
    session.add(m)
    session.commit()
    monkeypatch.setattr(settings, "MAX_UPLOAD_MB", 0)
    assert _post(client, m.id, _png()).status_code == 413


def test_proof_creates_case_and_never_stores_image(client, session):
    m = Merchant(name="Shop")
    session.add(m)
    session.commit()
    r = _post(client, m.id, _png())  # blank image: no UTR readable
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"case_id", "status", "reason"}
    case = session.get(Case, body["case_id"])
    assert case.merchant_id == m.id and len(case.image_sha256) == 64 and case.image_phash
    assert case.utr is None
