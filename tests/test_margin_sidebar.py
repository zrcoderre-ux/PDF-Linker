"""
A law firm's MARGIN SIDEBAR must not reach the export.

Many California firms print their own name and address SIDEWAYS down the
margin outside the numbered gutter, on every page of every filing. A rotated
run is its own text block whose box spans a dozen printed rows, so
`_cluster_rows` lands the whole thing on ONE arbitrary baseline and Step 7 of
`_detect_line_anchors` emitted it as a row in the middle of the page's prose —
the firm's street address arriving between two sentences of an argument, at a
different point on every page.

It is furniture, the sideways twin of the running footer `_FOOTER_MASK_PT`
already masks: repeated identically on every page, saying nothing the attorney
block above the caption on page 1 does not already say. So it is dropped, from
the deliverable AND from the do-not-share original.

What must NOT be dropped is the rest of Step 7's out-of-band text — the
e-filing stamp, the service list, and in particular the one thing that shares a
sidebar's geometry: a rotated EXHIBIT LABEL, which is real content.

Run:  cd PDF-Linker && python3 -m pytest tests/test_margin_sidebar.py -v
"""

import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P


FIRM = "LAW OFFICES OF SEDGWICK & LINFORD, LLP"
ADDR = "1200 Wilshire Boulevard, Los Angeles, CA 90017"
STAMP = "ELECTRONICALLY FILED 03/14/2025 Dana Whitaker, Clerk"
LABEL = 'EXHIBIT "A"'


def _pleading(tmp_path, name, margin=()):
    """A pleading page: 19 numbered body lines, an e-filing stamp above the
    band, and whatever `margin` puts sideways in the left margin. `margin` is
    a list of (x, text) drawn bottom-to-top at 90 degrees."""
    doc = fitz.open()
    pg = doc.new_page()
    pg.insert_text((60, 40), STAMP, fontsize=9)
    y = 90
    for i in range(1, 20):
        pg.insert_text((48, y), f"{i:>2}", fontsize=10)
        pg.insert_text((80, y), f"Body line {i} of the memorandum.", fontsize=10)
        y += 20
    for x, text in margin:
        pg.insert_text((x, 470), text, fontsize=8, rotate=90)
    path = tmp_path / name
    doc.save(path)
    doc.close()
    return fitz.open(path)[0]


@pytest.fixture
def with_sidebar(tmp_path):
    return _pleading(tmp_path, "sidebar.pdf",
                     margin=[(22, FIRM), (34, ADDR)])


@pytest.fixture
def with_label(tmp_path):
    return _pleading(tmp_path, "label.pdf", margin=[(28, LABEL)])


# ── the fixture itself ──────────────────────────────────────────────────────

def test_the_sidebar_really_is_on_the_page(with_sidebar):
    # Guard the fixture: if the margin text stopped being drawn, every
    # assertion below would pass for the wrong reason.
    assert FIRM in with_sidebar.get_text("text")


# ── the sidebar goes ────────────────────────────────────────────────────────

def test_the_sidebar_is_not_in_the_pleading_rows(with_sidebar):
    body = "\n".join(" ".join(t for _x, t in segs)
                     for _num, segs in P._page_lined_rows(with_sidebar))
    assert FIRM not in body
    assert "Wilshire" not in body


def test_the_sidebar_is_not_in_the_detect_rendering(with_sidebar):
    # Detection reads what the export writes — so the leak scan is never asked
    # about a value the export does not carry, and the pre-scan harvest and the
    # export cannot disagree about what the page said.
    out = P._page_detect_text(with_sidebar)
    assert FIRM not in out and "Wilshire" not in out


def test_the_page_still_reads_the_same(with_sidebar):
    out = P._page_detect_text(with_sidebar)
    for i in range(1, 20):
        assert f"Body line {i} of the memorandum." in out
    assert "Dana Whitaker" in out          # Step 7 out-of-band text survives


# ── and nothing else does ───────────────────────────────────────────────────

def test_a_rotated_exhibit_label_survives(with_label):
    # The one thing that shares a sidebar's geometry. It carries no firm word,
    # no phone and no address, so `_reads_as_letterhead` refuses it and Step 7
    # restores it exactly as before.
    assert "EXHIBIT" in P._page_detect_text(with_label)


def test_a_page_with_no_margin_text_is_untouched(tmp_path):
    plain = _pleading(tmp_path, "plain.pdf")
    out = P._page_detect_text(plain)
    for i in range(1, 20):
        assert f"Body line {i} of the memorandum." in out
    assert "Dana Whitaker" in out


# ── the unit rule ───────────────────────────────────────────────────────────

def _blocks(*lines):
    return [{"lines": list(lines)}]


def _sp(text, bbox):
    return {"text": text, "bbox": bbox, "size": 10.0, "origin": (bbox[0], bbox[3])}


def _body():
    return {"lines": [{"dir": (1.0, 0.0),
                       "spans": [_sp("Plaintiff moves to compel further "
                                     "responses.", (80, 100 + 8 * i,
                                                    400, 110 + 8 * i))]}
                      for i in range(20)]}


def _ids(margin_line, band=68.0):
    return P._margin_sidebar_ids([{"lines": [margin_line]}, _body()], band)


VERT, HORZ = (0.0, -1.0), (1.0, 0.0)


def test_letterhead_evidence_is_required():
    assert _ids({"dir": VERT, "spans": [_sp(FIRM, (30, 200, 42, 520))]})
    assert _ids({"dir": VERT, "spans": [_sp(ADDR, (30, 200, 42, 520))]})
    assert _ids({"dir": VERT, "spans": [_sp("(213) 555-1212", (30, 200, 42, 320))]})
    # ...and without it, nothing is taken.
    assert not _ids({"dir": VERT, "spans": [_sp(LABEL, (30, 300, 42, 380))]})
    assert not _ids({"dir": VERT,
                     "spans": [_sp("DEPOSITION OF JANE DOE", (30, 200, 42, 420))]})


def test_upright_letterhead_is_never_taken():
    # A firm block set the ordinary way is the attorney block above the
    # caption, or a service list. It is content and every harvest pass reads it.
    assert not _ids({"dir": HORZ, "spans": [_sp(FIRM, (30, 60, 300, 70))]})


def test_text_reaching_into_the_body_column_is_never_taken():
    assert not _ids({"dir": VERT, "spans": [_sp(FIRM, (30, 200, 120, 520))]})


def test_a_page_set_sideways_is_not_a_sidebar():
    # A rotated scan or a landscape exhibit: the vertical text IS the page, so
    # the minority guard refuses the whole thing.
    rot = {"lines": [{"dir": VERT,
                      "spans": [_sp(f"{FIRM} line {i}", (10, 20 * i, 22, 20 * i + 18))]}
                     for i in range(40)]}
    assert not P._margin_sidebar_ids([rot], 68.0)


def test_the_geometry_fallback_needs_two_characters():
    # A PDF that stacks its sidebar glyph by glyph reports no rotation, so the
    # box's aspect has to carry it. One character has no aspect worth reading.
    assert P._margin_sidebar_ids(
        [{"lines": [{"spans": [_sp("SEDGWICK & LINFORD LLP", (30, 200, 40, 520))]}]},
         _body()], 68.0)
    assert not P._margin_sidebar_ids(
        [{"lines": [{"spans": [_sp("L", (30, 200, 34, 214))]}]}, _body()], 68.0)
