"""
A ROTATED page is rendered in its READING frame.

Extraction reports coordinates in the unrotated page space, and a scanned
exhibit is routinely a landscape image displayed through /Rotate with an OCR
layer laid so it reads upright — text running UP the unrotated page, one span
per word. Clustered on unrotated y, every word of a printed line became a row
of its own and the words of different lines at the same distance along their
line shared one: a Living Trust's numbered paragraphs came out as a scatter
of single words. `_reading_frame_spans` turns the spans into the frame the
row clustering assumes; an ordinary page is untouched.

Run:  cd PDF-Linker && python3 -m pytest tests/test_rotated_page_rendering.py -v
"""
import warnings

import fitz

import pdf_linker as P

warnings.filterwarnings("ignore", category=DeprecationWarning)

LINES = ["Trust Purpose",
         "1. This Living Trust is created for the benefit of the Beneficiaries",
         "provided for after the death of the Grantor; however during the",
         "Trustee",
         "2. During the lifetime of the Grantor, and while the Grantor is not"]


def _ocr_layer(page, lines, rotate, top=100, left=72.0, lead=14):
    """An OCR-style layer — one span per WORD — that reads upright in the
    DISPLAY of `page`, whatever its /Rotate says."""
    for i, ln in enumerate(lines):
        x = left
        for w in ln.split():
            disp = fitz.Point(x, top + lead * i)
            page.insert_text(disp * page.derotation_matrix, w, fontsize=9,
                             fontname="helv", rotate=rotate, render_mode=3)
            x += fitz.get_text_length(w, fontname="helv", fontsize=9) + 3


def _rotated_scan(rotation=90):
    doc = fitz.open()
    page = doc.new_page(width=792, height=612)
    page.set_rotation(rotation)
    _ocr_layer(page, LINES, rotation)
    return doc, page


def test_a_rotated_scans_ocr_layer_renders_in_reading_order():
    for rotation in (90, 270):
        _doc, page = _rotated_scan(rotation)
        assert P._page_visual_text(page).splitlines() == LINES
        # …and clustered AS IT LIES the same layer scatters: far more rows
        # than lines, which is what the fix is for.
        raw = P._cluster_rows(P._page_text_spans(page))
        assert len(raw) > 3 * len(LINES)


def test_vertical_text_on_an_unrotated_page_reads_the_same_way():
    # No /Rotate at all: the text itself runs up the page (a landscape scan
    # pasted into a portrait page and OCR'd upright).
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for i, ln in enumerate(LINES):
        # Reading direction (0, -1): the next line lies at +x.
        y = 700.0
        for w in ln.split():
            page.insert_text((72 + 14 * i, y), w, fontsize=9, fontname="helv",
                             rotate=90, render_mode=3)
            y -= fitz.get_text_length(w, fontname="helv", fontsize=9) + 3
    assert P._page_visual_text(page).splitlines() == LINES


def test_an_ordinary_page_is_untouched():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for i, ln in enumerate(LINES):
        page.insert_text((72, 100 + 14 * i), ln, fontsize=9, fontname="helv")
    spans = P._page_text_spans(page)
    assert P._reading_frame_spans(page, spans) is spans     # the same list
    assert P._page_visual_text(page).splitlines() == LINES


def test_a_rotated_margin_label_never_turns_the_page():
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for i, ln in enumerate(LINES):
        page.insert_text((72, 100 + 14 * i), ln, fontsize=9, fontname="helv")
    # The firm's sidebar, set up the left margin.
    page.insert_text((30, 700), "LAW OFFICES", fontsize=8, fontname="helv",
                     rotate=90)
    out = P._page_visual_text(page).splitlines()
    assert [l.strip() for l in out if l.strip() and "LAW" not in l] == LINES


def test_the_flowing_rebuild_uses_the_reading_frame_too():
    # A doubled layer on a rotated page takes `_page_flowing_text`'s span
    # rebuild; it must read in order as well.
    doc, page = _rotated_scan(90)
    _ocr_layer(page, LINES, 90)          # drawn twice, exactly over itself
    got = [l for l in P._page_flowing_text(page).splitlines() if l.strip()]
    assert got == LINES


def test_the_frame_is_shared_by_both_renderers():
    import inspect
    for fn in (P._page_visual_text, P._page_flowing_text):
        src = inspect.getsource(fn)
        assert "_reading_frame_spans(" in src and "_page_text_spans(" in src
