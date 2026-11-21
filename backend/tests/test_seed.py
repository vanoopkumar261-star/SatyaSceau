"""scripts/seed_demo.py: idempotent demo shop + printable QR poster.  Owner: Pile 1."""

import qrcode
from PIL import Image

from scripts.seed_demo import seed_merchant, write_qr_poster


def test_first_run_creates_an_opted_in_shop(session):
    m, action = seed_merchant(session, "Raju Tea Stall", "raju@okaxis")
    assert action == "created"
    assert m.consent_given and m.consent_at is not None
    assert m.screen_key and m.api_token and m.screen_key != m.api_token


def test_rerun_reuses_the_same_shop_and_token(session):
    first, _ = seed_merchant(session, "Raju Tea Stall", "raju@okaxis")
    again, action = seed_merchant(session, "Raju Tea Stall", "raju@okaxis")
    assert action == "reused"
    assert (again.id, again.api_token, again.screen_key) == (first.id, first.api_token, first.screen_key)


def test_rotate_keeps_the_shop_but_replaces_both_keys(session):
    first, _ = seed_merchant(session, "Raju Tea Stall", "raju@okaxis")
    old_token, old_key = first.api_token, first.screen_key
    rotated, action = seed_merchant(session, "Raju Tea Stall", "raju@okaxis", rotate=True)
    assert action == "rotated" and rotated.id == first.id
    assert rotated.api_token != old_token and rotated.screen_key != old_key


def test_new_creates_a_second_shop(session):
    first, _ = seed_merchant(session, "Raju Tea Stall", "raju@okaxis")
    other, action = seed_merchant(session, "Raju Tea Stall", "raju@okaxis", new=True)
    assert action == "created" and other.id != first.id


def test_qr_poster_is_a_png_larger_than_the_bare_qr(tmp_path):
    url = "https://example.test/pay/abc12345"
    bare = qrcode.make(url, box_size=12, border=2).get_image()
    path = write_qr_poster(url, "Raju Tea Stall", tmp_path / "qr.png")
    with Image.open(path) as img:
        assert img.format == "PNG"
        assert img.width > bare.width and img.height > bare.height + 100  # heading + shop name + footer
