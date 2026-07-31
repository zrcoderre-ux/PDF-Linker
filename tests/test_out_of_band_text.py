"""
D9 — text outside the numbered band must still reach the export.

`_detect_line_anchors` collected body spans only to the RIGHT of the gutter
(Step 3) and kept only rows within half a lead of a line number (Step 4).
Both rules were written to stop such text being ADOPTED onto a numbered line —
a real bug, the running footer arriving as "28  ...OPPOSITION TO DEFENDANT'S
MOTION TO STRIKE". But the remedy was to DISCARD it, and a pleading page carries
real text outside its numbered band: an e-filing stamp above line 1, a
left-margin label, and — on the last page of a filing — the whole SERVICE LIST.

Measured on a real Song-Beverly costs memo, the export lost its service list
entire: the case caption naming the plaintiff, the case number, opposing
counsel, a street address and four e-mail addresses. Discarded text never
reaches the scrubber OR the leak scan, so the run certifies a file it never
read — the same reason `_page_detect_text` takes the DECIDED form text.

Run:  cd PDF-Linker && python3 -m pytest tests/test_out_of_band_text.py -v
"""

import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P


STAMP = "ELECTRONICALLY FILED 03/14/2025 Sherri R. Carter, Clerk"
SERVICE = "Ryan Kay, Esq. rkay@example.com Erskine Law Group, PC"


@pytest.fixture
def page(tmp_path):
    """A pleading page: a stamp above the numbered band, 19 numbered body
    lines, and a service block below the band but above the footer mask."""
    doc = fitz.open()
    pg = doc.new_page()
    pg.insert_text((40, 40), STAMP, fontsize=9)
    y = 90
    for i in range(1, 20):
        pg.insert_text((40, y), f"{i:>2}", fontsize=10)
        pg.insert_text((80, y), f"Body line {i} of the memorandum.", fontsize=10)
        y += 20
    pg.insert_text((90, y + 20), SERVICE, fontsize=9)
    path = tmp_path / "pleading.pdf"
    doc.save(path)
    doc.close()
    return fitz.open(path)[0]


def test_the_numbered_band_still_reads_the_same(page):
    out = P._page_detect_text(page)
    for i in range(1, 20):
        assert f"Body line {i} of the memorandum." in out


def test_a_stamp_above_line_one_survives(page):
    assert "Sherri R. Carter" in P._page_detect_text(page)


def test_a_block_below_the_last_line_survives(page):
    out = P._page_detect_text(page)
    assert "rkay@example.com" in out and "Erskine Law Group, PC" in out


def test_out_of_band_text_claims_no_line_number(page):
    # The original fix stays intact: furniture must not be ADOPTED onto a
    # numbered line, or a pinpoint "p.3:7" lands on it.
    rows = P._page_lined_rows(page)
    for num, segs in rows:
        body = " ".join(t for _x, t in segs)
        if "Sherri R. Carter" in body or "rkay@example.com" in body:
            assert num is None, f"furniture claimed line {num}: {body!r}"


def test_a_gutter_number_never_becomes_body_text(page):
    # Pleading paper right-aligns the gutter, so the single digits sit in their
    # own sub-column; a page whose 10-29 outnumber its 1-9 puts the dominant x
    # on the wider run and the singles fall outside it. They are still line
    # numbers, not content ("1 SERVICE LIST").
    for num, segs in P._page_lined_rows(page):
        for _x, text in segs:
            assert not text.strip().isdigit(), f"gutter number as body: {text!r}"


def test_out_of_band_text_reaches_the_scrubber(page):
    # The point of the fix. Text absent from the export is text no pass can
    # scrub and no scan can flag.
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Ryan Kay"], [], [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    z = P.Pseudonymizer(terms, det, registry=reg)
    out = z.apply(P._page_detect_text(page))
    assert "Ryan Kay" not in out, out
    assert "rkay@example.com" not in out, out


def test_the_running_footer_is_still_masked(tmp_path):
    # `_FOOTER_MASK_PT` is a separate, deliberate choice: the footer repeats the
    # document title on every page and carries nothing else.
    doc = fitz.open()
    pg = doc.new_page()
    y = 90
    for i in range(1, 20):
        pg.insert_text((40, y), f"{i:>2}", fontsize=10)
        pg.insert_text((80, y), f"Body line {i}.", fontsize=10)
        y += 20
    pg.insert_text((90, pg.rect.height - 20), "GM'S OPPOSITION TO MOTION",
                   fontsize=9)
    path = tmp_path / "footer.pdf"
    doc.save(path)
    doc.close()
    assert "GM'S OPPOSITION" not in P._page_detect_text(fitz.open(path)[0])
