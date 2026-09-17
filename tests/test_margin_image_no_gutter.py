"""A picture in the MARGIN is left unread on a page with no line-number gutter.

`_sidebar_image_rect` measures a pleading's margin off its line-number gutter,
which is that page's own statement of where the margin ends. A court FORM has
no gutter, so nothing measured it: the rotated e-filing stamp pasted up the
left edge of a scanned MC-350EX was rendered and read, and because the
recogniser did not detect the rotation it came back as a band of soup per
scanline — twenty words ("AEIUONIa/3", "PaNaray", "auodjIa|3") laid into the
form's own rows, each earning a column stop, so the form's own labels came out
ten columns in with "CASE NAME:" pushed to column 57.

`_margin_sideways_dropped` cannot catch those: it drops a margin span whose own
direction is crosswise, and a reading that came back UPRIGHT is ordinary
horizontal text to every renderer. So the words must not exist.

Run:  cd PDF-Linker && python3 -m pytest tests/test_margin_image_no_gutter.py -v
"""
import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P


def _form_page():
    """A court-form page: text from x=72 rightwards, no gutter numbers."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for y in range(80, 700, 20):
        page.insert_text((72, y), "ATTORNEY OR PARTY WITHOUT ATTORNEY",
                         fontsize=9, fontname="helv")
    return doc, page


STAMP = fitz.Rect(8, 100, 40, 500)        # rotated lines of type, up the side
# ...and never smaller than `_IMG_OCR_MIN_PT` in either direction, or the
# pass never offered it to be read in the first place.
assert STAMP.width >= P._IMG_OCR_MIN_PT and STAMP.height >= P._IMG_OCR_MIN_PT


def test_a_margin_stamp_is_left_unread(tmp_path):
    doc, page = _form_page()
    try:
        assert P._pleading_gutter(page) is None      # no gutter to measure by
        assert P._page_margin_images(page, [STAMP]) == [STAMP]
    finally:
        doc.close()


def test_a_picture_inside_the_text_is_read(tmp_path):
    """The judge's signature block this pass exists for."""
    doc, page = _form_page()
    try:
        sig = fitz.Rect(200, 300, 400, 380)
        assert P._page_margin_images(page, [sig]) == []
    finally:
        doc.close()


def test_a_picture_that_is_not_clearly_left_of_the_text_is_read(tmp_path):
    """The tolerance runs the conservative way: a picture wrongly refused is
    real words nothing recovers."""
    doc, page = _form_page()
    try:
        touching = fitz.Rect(40, 100, 72, 500)
        assert P._page_margin_images(page, [touching]) == []
    finally:
        doc.close()


def test_a_letterhead_logo_is_not_a_margin_stamp(tmp_path):
    """Wider than tall, so it is not set up the side of the page — and a
    logo's words may be the only place a firm is named."""
    doc, page = _form_page()
    try:
        logo = fitz.Rect(8, 200, 40, 226)
        assert P._page_margin_images(page, [logo]) == []
    finally:
        doc.close()


def test_a_picture_above_the_text_is_not_a_margin_stamp(tmp_path):
    doc, page = _form_page()
    try:
        above = fitz.Rect(8, 5, 40, 70)
        assert P._page_margin_images(page, [above]) == []
    finally:
        doc.close()


def test_a_page_that_is_all_picture_is_not_a_margin(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    try:
        assert P._page_margin_images(page, [STAMP]) == []
    finally:
        doc.close()


def test_a_pleading_page_still_measures_from_its_gutter(monkeypatch):
    """The gutter arm is unchanged and is preferred where there is one: it
    admits a stamp BESIDE the numbered band whatever its shape, which the
    no-gutter arm's shape test would refuse."""
    doc, page = _form_page()
    line_col = [{"num": n, "y_mid": 100.0 + n * 20, "x0": 55.0,
                 "y0": 94.0 + n * 20, "y1": 106.0 + n * 20}
                for n in range(1, 29)]
    monkeypatch.setattr(P, "_pleading_gutter", lambda pg, blocks=None: (55.0, line_col))
    try:
        wide = fitz.Rect(20, 200, 50, 215)       # wider than tall, left of 55
        assert P._page_margin_images(page, [wide]) == [wide]
        inside = fitz.Rect(200, 200, 300, 215)   # in the body
        assert P._page_margin_images(page, [inside]) == []
    finally:
        doc.close()


# ── the reading an EARLIER run already laid into the PDF ─────────────────────

def _overlay(page, rect, words):
    """Tesseract's own overlay, as `_ocr_image_regions` leaves it: invisible
    text (render mode 3) inside the picture's rect."""
    y = rect.y0 + 8
    for w in words:
        page.insert_text((rect.x0 + 1, y), w, fontsize=6, render_mode=3)
        y += 8


def test_a_margin_pictures_overlay_is_dropped(tmp_path):
    """`_page_margin_images` stops the picture being READ, and that protects
    only a PDF no run has met yet: the reading is laid INTO the text layer
    and the tool replaces the source file, so a folder an earlier run touched
    carries the soup for ever."""
    doc, page = _form_page()
    try:
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 32, 400))
        pix.clear_with(255)
        page.insert_image(STAMP, pixmap=pix)
        _overlay(page, STAMP, ["AEIUONIa/3", "PaNaray", "GZOZ/0Z80"])
        raw = P._page_text_spans(page)
        assert any("PaNaray" in sp["text"] for sp in raw), "fixture is wrong"
        kept = P._drop_overdrawn_spans(raw, page)
        text = " ".join(sp["text"] for sp in kept)
        assert "PaNaray" not in text and "AEIUONIa/3" not in text
        assert "ATTORNEY OR PARTY WITHOUT ATTORNEY" in text
    finally:
        doc.close()


def test_the_pages_own_visible_type_over_a_picture_stays(tmp_path):
    """Scoped to an INVISIBLE span: the visible text IS the document at that
    spot, whatever stands under it."""
    doc, page = _form_page()
    try:
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 32, 400))
        pix.clear_with(255)
        page.insert_image(STAMP, pixmap=pix)
        page.insert_text((STAMP.x0 + 1, STAMP.y0 + 8), "EXHIBIT A", fontsize=6)
        kept = P._drop_overdrawn_spans(P._page_text_spans(page), page)
        assert "EXHIBIT A" in " ".join(sp["text"] for sp in kept)
    finally:
        doc.close()


def test_a_page_wide_ocr_layer_loses_nothing(tmp_path):
    """The other scope: a picture that is not in a MARGIN holds no margin
    overlay, so a scanned page reads exactly as it did."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    try:
        pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 612, 792))
        pix.clear_with(255)
        page.insert_image(page.rect, pixmap=pix)
        y = 80
        for line in ("SUPERIOR COURT OF CALIFORNIA", "COUNTY OF LOS ANGELES",
                     "the whole page is a scan and its words are the layer"):
            page.insert_text((40, y), line, fontsize=10, render_mode=3)
            y += 20
        kept = P._drop_overdrawn_spans(P._page_text_spans(page), page)
        text = " ".join(sp["text"] for sp in kept)
        assert "SUPERIOR COURT OF CALIFORNIA" in text
        assert "the whole page is a scan" in text
    finally:
        doc.close()
