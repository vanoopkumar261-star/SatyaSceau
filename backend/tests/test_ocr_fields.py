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
