"""A page whose text layer is drawn TWICE must export once.

A page can carry its text twice and look perfectly normal to a reader, because
the two copies land on top of each other: an e-filing stamp that redraws the
content, a faux-bold double strike, or an OCR overlay laid over a text layer the
redaction failed to remove.

`page.get_text("text")` survives that — the duplicate comes back as its own
line, which is ugly and harmless. The SPAN path does not, because it joins a
row's pieces left to right and the two copies of each piece sort adjacent:

    BOWMAN BOWMAN AND BROOKE LLP AND BROOKE LLP Michael Michael Chung (SBN
    243204) Chung (SBN 243204)

That is not cosmetic. A whole-word term cannot match "Michael Michael Chung", so
the party is left standing; the harvester reads the doubled run as a name and
mints it — a delivered key carried `Michael Michael Chung`, `Justin Justin
Carpenter` and `SeeSee` as party rows, each with its own stand-in; and
`_pn_context` quotes the wreckage into the triage worksheet, where it reads as
an unrelated extraction failure.

Run:  cd PDF-Linker && python3 -m pytest tests/test_overdrawn_text_layer.py -v
"""
import pytest

import pdf_linker as P

fitz = pytest.importorskip("fitz")

# Shapes taken from the delivered key and worksheet that exposed this.
LINES = [
    ("BOWMAN", "AND BROOKE LLP", "Michael Chung (SBN 243204)"),
    ("For", "its part, Sunlight merely facilitated", "the financing"),
    ("see", "AT&T Mobility LLC", "v. Concepcion (2011)"),
    ("Attn:", "Jesus", "Email: clark@hbalaw.com"),
    ("Dept:", "515", "8:30 a.m."),
    ("Filed", "concurrently with Declaration of", "Justin Carpenter"),
]


def _page(times, dx=0.0, dy=0.0):
    """A pleading-paper page whose whole text layer is drawn `times` times, each
    copy offset by (dx, dy) — an exact overdraw at 0, a second layer set in its
    own metrics at a point or two."""
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    for i in range(times):
        y = 100
        for n, (a, b, c) in enumerate(LINES, start=1):
            pg.insert_text((40, y), str(n), fontsize=10)
            pg.insert_text((90 + dx * i, y + dy * i), a, fontsize=10)
            pg.insert_text((150 + dx * i, y + dy * i), b, fontsize=10)
            pg.insert_text((330 + dx * i, y + dy * i), c, fontsize=10)
            y += 26
    return doc[0]


def _rows(page):
    return [(n, [t for _x, t in segs])
            for n, segs in (P._page_lined_rows(page) or [])]


# ── the page reads as though it were drawn once ─────────────────────────────

@pytest.mark.parametrize("times,dx,dy", [
    (2, 0.0, 0.0),      # exact overdraw
    (2, 1.5, 0.0),      # a second layer nudged right
    (2, 2.0, 1.0),      # …and down
    (3, 0.8, 0.4),      # three layers (a re-run that overlaid twice)
])
def test_an_overdrawn_page_renders_like_a_single_draw(times, dx, dy):
    assert _rows(_page(times, dx, dy)) == _rows(_page(1))


def test_the_welded_shapes_from_the_delivered_key_are_gone():
    flat = " ".join(t for _n, segs in _rows(_page(2, 1.5)) for t in segs)
    for welded in ("Michael Michael", "BOWMAN BOWMAN", "see see",
                   "Justin Justin", "Dept: Dept:", "For For"):
        assert welded not in flat, flat


def test_a_party_name_matches_again_after_the_dedupe():
    """The point of the fix: a whole-word term cannot match a doubled run, so
    the party rode through the scrub untouched."""
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Michael Chung"], [], [], registry=reg)
    z = P.Pseudonymizer(terms, list(P._PN_DEFAULT_DETECTORS), registry=reg)
    flat = " ".join(t for _n, segs in _rows(_page(2, 1.5)) for t in segs)
    assert "Michael Chung" in flat
    assert "Michael Chung" not in z.apply(flat)


# ── and a page that is NOT overdrawn is untouched ───────────────────────────

def test_a_single_draw_page_is_unchanged():
    page = _page(1)
    assert _rows(page) == [
        (1, ["BOWMAN AND BROOKE LLP", "Michael Chung (SBN 243204)"]),
        (2, ["For", "its part, Sunlight merely facilitated", "the financing"]),
        (3, ["see", "AT&T Mobility LLC", "v. Concepcion (2011)"]),
        (4, ["Attn:", "Jesus", "Email: clark@hbalaw.com"]),
        (5, ["Dept:", "515", "8:30 a.m."]),
        (6, ["Filed", "concurrently with Declaration of",
             "Justin Carpenter"]),
    ]


def test_two_copies_side_by_side_are_both_kept():
    """A second copy far enough away is a real second column, not a re-draw —
    the boxes do not overlap, so nothing is dropped."""
    flat = " ".join(t for _n, segs in _rows(_page(2, 30.0)) for t in segs)
    assert flat.count("BOWMAN") == 2, flat


# ── the primitive ───────────────────────────────────────────────────────────

def _sp(text, x0, y0, x1, y1):
    return {"text": text, "bbox": (x0, y0, x1, y1)}


def test_overdrawn_is_overlap_not_proximity():
    a = _sp("Chung", 100, 50, 140, 62)
    assert P._spans_overdrawn(a, _sp("Chung", 100, 50, 140, 62))     # exact
    assert P._spans_overdrawn(a, _sp("Chung", 101.5, 50.5, 141.5, 62.5))
    # Adjacent, not overlapping: two real words that happen to be the same.
    assert not P._spans_overdrawn(a, _sp("Chung", 141, 50, 181, 62))
    # Same place, different text: never a re-draw.
    assert P._drop_overdrawn_spans(
        [a, _sp("Cheung", 100, 50, 140, 62)]) == [a, _sp("Cheung", 100, 50,
                                                         140, 62)]


def test_dedupe_keeps_the_first_and_preserves_order():
    a, b = _sp("A", 0, 0, 10, 10), _sp("B", 20, 0, 30, 10)
    dup = _sp("A", 0.5, 0.5, 10.5, 10.5)
    assert P._drop_overdrawn_spans([a, dup, b]) == [a, b]
