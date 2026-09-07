"""A firm's SIDEBAR in the left margin of a pleading page is not content.

One firm prints its name up the side of every page, set bottom-to-top and
unusually close to the line-number gutter; scanned upside down it reads
top-to-bottom. Step 7 of `_detect_line_anchors` — written to keep the e-filing
stamp and the service list, which are real text outside the numbered band —
read the sidebar as a left-margin label and emitted it as an unnumbered row,
so the export carried the firm's name on every page. An OCR'd copy arrives as
a scatter of debris words down the margin instead.

The exclusion is measured off the GUTTER ITSELF (`_sidebar_spans`): the
numbers are the leftmost thing a pleading prints, so what stands wholly left of
their column is the margin outside the pleading.

Run:  cd PDF-Linker && python3 -m pytest tests/test_firm_sidebar.py -v
"""

import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P


STAMP = "ELECTRONICALLY FILED 03/14/2025 Sherri R. Carter, Clerk"
SIDEBAR = "OGLETREE, DEAKINS, NASH, SMOAK & STEWART, P.C."
SERVICE = "Ryan Kay, Esq. rkay@example.com Erskine Law Group, PC"
GUTTER_X = 72.0


def _build(tmp_path, extra):
    doc = fitz.open()
    pg = doc.new_page()
    pg.insert_text((40, 40), STAMP, fontsize=9)
    y = 90
    for i in range(1, 29):
        pg.insert_text((GUTTER_X, y), f"{i:>2}", fontsize=10)
        pg.insert_text((110, y), f"Body line {i} of the memorandum.", fontsize=10)
        y += 24
    extra(pg)
    path = tmp_path / "pleading.pdf"
    doc.save(path)
    doc.close()
    return fitz.open(path)[0]


def _text(page):
    return "\n".join(a["body_text"] for a in P._detect_line_anchors(page))


def test_a_bottom_to_top_sidebar_hard_against_the_gutter_is_dropped(tmp_path):
    # x=62 puts the sidebar's glyph box within ten points of the gutter's
    # left edge — "unusually close to the numbered margin".
    page = _build(tmp_path, lambda pg: pg.insert_text(
        (62, 700), SIDEBAR, fontsize=8, rotate=90))
    out = _text(page)
    assert "OGLETREE" not in out and "STEWART" not in out, out


def test_the_same_sidebar_scanned_upside_down_is_dropped(tmp_path):
    page = _build(tmp_path, lambda pg: pg.insert_text(
        (50, 120), SIDEBAR, fontsize=8, rotate=270))
    assert "OGLETREE" not in _text(page)


def test_an_ocr_layer_reads_the_sidebar_as_horizontal_debris(tmp_path):
    # A scan's OCR lays the sidebar down as ordinary horizontal words, one box
    # per word, standing beside the numbered band and wholly left of the
    # gutter. Positional, since the direction says nothing there.
    def words(pg):
        for k, w in enumerate(["OGLE", "TREE", "DEAK", "INS"]):
            pg.insert_text((40, 200 + 30 * k), w, fontsize=7)
    page = _build(tmp_path, words)
    out = _text(page)
    for w in ("OGLE", "TREE", "DEAK", "INS"):
        assert w not in out.split(), out


def test_the_numbered_band_and_the_stamp_still_read(tmp_path):
    page = _build(tmp_path, lambda pg: pg.insert_text(
        (62, 700), SIDEBAR, fontsize=8, rotate=90))
    out = _text(page)
    assert "Sherri R. Carter" in out
    for i in range(1, 29):
        assert f"Body line {i} of the memorandum." in out


def test_an_ocr_split_stamp_overlapping_the_band_is_kept_whole(tmp_path):
    # A tall stamp's per-word OCR boxes reach into the band; "FILED" alone
    # ends left of the gutter, but shares its baseline with words that run
    # into the page, and is kept with them.
    def stamp(pg):
        pg.insert_text((36, 92), "FILED", fontsize=7)
        pg.insert_text((58, 92), "by Superior Court of California", fontsize=7)
    page = _build(tmp_path, stamp)
    assert "FILED" in _text(page).split()


def test_a_service_block_below_the_band_survives(tmp_path):
    page = _build(tmp_path, lambda pg: pg.insert_text(
        (90, 90 + 28 * 24 + 6), SERVICE, fontsize=9))
    assert "rkay@example.com" in _text(page)


def test_a_sidebar_never_reaches_the_export_text(tmp_path):
    page = _build(tmp_path, lambda pg: pg.insert_text(
        (62, 700), SIDEBAR, fontsize=8, rotate=90))
    # Both renderings a pleading page reaches the export through: the lined
    # rows the writer prints, and the column-ordered text detection reads.
    assert "OGLETREE" not in P._page_detect_text(page)
    rows = P._page_lined_rows(page)
    assert rows and not any("OGLETREE" in t for _n, segs in rows for _x, t in segs)


def test_a_page_with_no_sidebar_does_not_move(tmp_path):
    before = [
        (a["line_num"], a["body_text"])
        for a in P._detect_line_anchors(_build(tmp_path, lambda pg: None))]
    assert (None, STAMP) in before
    assert sum(1 for n, _t in before if n is not None) == 28
