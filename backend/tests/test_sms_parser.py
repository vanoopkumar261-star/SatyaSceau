from app.sms_parser import parse_bank_sms

DEMO = "Rs.120.00 credited to A/c XX1234 on 22-11-26 by UPI Ref No 618656730702. -HDFC Bank"


def test_demo_format_parses():
    c = parse_bank_sms("AX-HDFCBK", DEMO)
    assert (c.utr, c.amount, c.sender_id) == ("618656730702", 120.0, "AX-HDFCBK")


def test_upi_cr_format_and_inr_with_commas():
    c = parse_bank_sms("VM-SBIUPI", "INR 1,000.00 credited to a/c XX99 UPI/CR/512345678912/RAHUL")
    assert (c.utr, c.amount) == ("512345678912", 1000.0)


def test_real_style_variants():
    assert parse_bank_sms("JD-KOTAKB-S", "Received Rs 50 in your Kotak A/c X1234 from x@ybl. UPI Ref: 412345678901").utr == "412345678901"
    assert parse_bank_sms("AD-ICICIB", "Acct XX1 CR with ₹75.50 on 22-Nov. RRN 398765432109").amount == 75.5


def test_phone_number_sender_rejected():
    assert parse_bank_sms("+919876543210", DEMO) is None
    assert parse_bank_sms("9876543210", DEMO) is None


def test_unknown_or_malformed_bank_code_rejected():
    assert parse_bank_sms("AX-FAKEBK", DEMO) is None
    assert parse_bank_sms("HDFCBK", DEMO) is None
    assert parse_bank_sms("AX-HDFCBK-XY", DEMO) is None


def test_otp_debit_and_promo_dropped():
    assert parse_bank_sms("AX-HDFCBK", "123456 is your OTP for UPI Ref No 618656730702 Rs.10 credited") is None
    assert parse_bank_sms("AX-HDFCBK", "Rs.200 debited from A/c XX1234 UPI Ref No 618656730702") is None
    assert parse_bank_sms("AX-HDFCBK", "A/c XX1234 DR Rs.200 UPI Ref No 618656730702 received") is None
    assert parse_bank_sms("AX-HDFCBK", "Rs.500 spent on card XX12. Ref No 618656730702") is None
    assert parse_bank_sms("AX-HDFCBK", "Congrats! Rs 500 cashback received on your card. T&C apply") is None
    assert parse_bank_sms("AX-HDFCBK", "Your A/c XX1234 balance is Rs.5,000 as of today") is None


def test_13_digit_ref_rejected():
    assert parse_bank_sms("AX-HDFCBK", "Rs.120.00 credited to A/c XX1234 by UPI Ref No 6186567307021") is None


def test_missing_utr_or_amount_returns_none():
    assert parse_bank_sms("AX-HDFCBK", "Rs.120.00 credited to A/c XX1234") is None
    assert parse_bank_sms("AX-HDFCBK", "Money credited to A/c XX1234 UPI Ref No 618656730702") is None


def test_name_with_dr_title_not_treated_as_debit():
    c = parse_bank_sms("AX-HDFCBK", "Rs.120.00 credited to A/c XX1234 from Dr. Mehta by UPI Ref No 618656730702")
    assert c is not None and c.utr == "618656730702"
