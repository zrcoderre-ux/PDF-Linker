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


# ── the same page seen the other way: the FLOWING-text path ─────────────────
#
# `_drop_overdrawn_spans` fixes the row path. `get_text` returns the duplicate
# as its own LINE, which looked merely ugly — until a weld-cure pass matched a
# party's reduced core ACROSS the seam between the two copies and rewrote the
# text. One export came back:
#
#   4 Defendant Defendant Best Best FonnuFalcon lations LLC is a tenant ...
#
# for "Defendant Best Formulations LLC is a tenant at the Property." A doubled
# page is also the page most likely to defeat the gutter-number detection, so it
# falls to this rendering rather than the row path.

REAL = "Defendant Best Formulations LLC is a tenant at the Property."


def _flat(page):
    return [l for l in P._page_flowing_text(page).split("\n") if l.strip()]


def _flow_page(times, dx=0.0, dy=0.0):
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    for i in range(times):
        y = 100
        for txt in (REAL, "The lease was signed in 2021.",
                    "Plaintiff seeks possession of the premises."):
            pg.insert_text((72 + dx * i, y + dy * i), txt, fontsize=11)
            y += 22
    return doc[0]


@pytest.mark.parametrize("times,dx,dy", [(2, 0, 0), (2, 1.5, 0.4), (3, 0.8, 0.4)])
def test_a_doubled_page_reads_once_on_the_flowing_path(times, dx, dy):
    assert _flat(_flow_page(times, dx, dy)) == _flat(_flow_page(1))


def test_a_clean_page_is_returned_untouched():
    page = _flow_page(1)
    assert P._page_flowing_text(page) == page.get_text("text")
    assert not P._page_is_overdrawn(page)


def test_a_document_that_repeats_a_line_on_purpose_is_untouched():
    """The gate is POSITIVE evidence: nothing on this page is over-drawn, so
    the repeated row stays. Collapsing it would delete content."""
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    y = 100
    for txt in ("Item      100.00", "Item      100.00", "Total     200.00"):
        pg.insert_text((72, y), txt, fontsize=11)
        y += 22
    assert not P._page_is_overdrawn(doc[0])
    assert _flat(doc[0]) == ["Item      100.00", "Item      100.00",
                             "Total     200.00"]


# ── …and the copies that do NOT split their row the same way ────────────────
# The dedupe above compares on exact TEXT, so it collapses two copies only when
# both split their row identically. They routinely do not: an OCR layer emits
# one span per WORD while the layer underneath has one span per styled run. A
# delivered fee motion carried
#
#   EDGECOMBE EDGECOMBE N. DENHOLM, ESQ. (SBN 584673) N. DENHOLM, ESQ. (SBN 584673)
#
# on 26 of its pages — which is why the operator sees the duplication as
# "always the first word on the line": both copies start at the same left edge,
# so their first pieces sort adjacent and the word-by-word copy trails after the
# long span.

RUN = "EDGECOMBE N. DENHOLM, ESQ. (SBN 584673)"


def _word_copy_over_a_run():
    """One span for the printed run, one per word of a second reading of it."""
    spans = [_sp(RUN, 72, 100, 400, 112)]
    x = 72.0
    for w in RUN.split():
        spans.append(_sp(w, x, 101, x + 6 * len(w), 111))
        x += 6 * len(w) + 3
    return spans


def test_a_word_by_word_re_draw_collapses_to_the_printed_run():
    kept = P._drop_overdrawn_spans(_word_copy_over_a_run())
    joined = " ".join(s["text"] for s in sorted(kept, key=lambda s: s["bbox"][0]))
    assert joined == RUN, joined


def test_the_first_word_is_not_doubled():
    """The symptom as the operator described it."""
    kept = P._drop_overdrawn_spans(_word_copy_over_a_run())
    words = " ".join(s["text"] for s in
                     sorted(kept, key=lambda s: s["bbox"][0])).split()
    assert words[0] != words[1], words[:4]


@pytest.mark.parametrize("piece", RUN.split())
def test_every_piece_survives_inside_the_run_it_came_from(piece):
    """Dropping one can lose nothing: its text is on the page, in that same
    place, as part of the span it sits inside."""
    kept = P._drop_overdrawn_spans(_word_copy_over_a_run())
    assert any(piece in s["text"] for s in kept)


def test_a_clean_line_of_separate_words_is_untouched():
    """Ordinary typesetting never nests one span's box inside another's — spans
    on a line abut, they do not overlap."""
    spans = [_sp("Plaintiff", 72, 100, 120, 112),
             _sp("moved", 124, 100, 160, 112),
             _sp("to strike the answer", 164, 100, 280, 112)]
    assert P._drop_overdrawn_spans(spans) == spans


def test_a_watermark_and_the_text_under_it_both_survive():
    """Its box is not inside a body span's, and the body span's text is not
    inside "COPY"."""
    spans = [_sp("COPY", 60, 95, 500, 140),
             _sp("a COPY of the lease", 72, 110, 300, 122)]
    assert P._drop_overdrawn_spans(spans) == spans


def test_a_repeated_word_elsewhere_on_the_line_is_kept():
    """Containment is not enough on its own — the box has to be inside too."""
    spans = [_sp("the lease and the rent", 72, 100, 240, 112),
             _sp("the", 260, 100, 275, 112)]
    assert P._drop_overdrawn_spans(spans) == spans


def test_a_fragment_is_never_dropped_for_a_fragment():
    """Two pieces of one copy do not remove each other, or a row would erode
    down to its longest span."""
    spans = [_sp("DENHOLM", 100, 100, 160, 112),
             _sp("HOLM", 100, 101, 130, 111)]
    kept = P._drop_overdrawn_spans(spans)
    assert [s["text"] for s in kept] == ["DENHOLM"]


# ---- two copies that agree on the words and not on the bytes -----------------

def _twice(a_text, b_text, dx=0.0):
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    pg.insert_text((90, 100), a_text, fontsize=10)
    pg.insert_text((90 + dx, 100), b_text, fontsize=10)
    return pg


def _spans(page):
    return [sp for blk in page.get_text("dict")["blocks"]
            for ln in blk.get("lines", []) for sp in ln.get("spans", [])
            if sp["text"].strip()]


class TestCopiesThatDifferOnlyInTheirBytes:
    """A flattened form carries each value twice — the field's appearance
    burned into the content over the value the builder printed — and the two
    fonts set the same words differently: a typographic apostrophe against a
    straight one, a trailing space on one run. Compared byte for byte they
    were two texts and both copies shipped."""

    def test_a_curly_and_a_straight_apostrophe_are_one_text(self):
        # As span dicts: the base-14 font a test page is set in has no
        # typographic apostrophe, where the delivered PDF's fonts do.
        a = {"text": "Plaintiffs\u2019 vehicle.", "bbox": (90.0, 89.2, 167.2, 103.0)}
        b = {"text": "Plaintiffs' vehicle.", "bbox": (90.0, 89.2, 166.4, 103.0)}
        assert len(P._drop_overdrawn_spans([a, b])) == 1

    def test_a_trailing_space_is_one_text(self):
        pg = _twice("Detroit St. near ", "Detroit St. near")
        assert len(P._drop_overdrawn_spans(_spans(pg), pg)) == 1

    def test_different_words_at_one_place_still_both_stand(self):
        pg = _twice("Plaintiffs", "Defendants")
        assert len(P._drop_overdrawn_spans(_spans(pg), pg)) == 2

    def test_the_key_folds_only_what_two_fonts_disagree_on(self):
        assert P._span_text_key(" It\u2019s  \u201cso\u201d ") == "It's \"so\""
        assert P._span_text_key("90013") != P._span_text_key("90014")


class TestAFormPageReadsEachValueOnce:
    """The ink-form path read the page's spans raw, so a flattened form's
    doubled values were laid out twice ("ZIP CODE: 90013 90013",
    "1 1 to 50 50") where the rows path beside it collapsed them."""

    def _form(self, twice):
        doc = fitz.open()
        pg = doc.new_page(width=612, height=792)
        sh = pg.new_shape()
        for k in range(4):                    # checkbox-sized squares: the ink gate
            sh.draw_rect(fitz.Rect(40, 200 + 20 * k, 50, 210 + 20 * k))
        sh.finish(width=0.6)
        sh.commit()
        for k, cap in enumerate(("MOTOR VEHICLE", "OTHER", "Property Damage", "Wrongful Death")):
            pg.insert_text((56, 209 + 20 * k), cap, fontsize=9)
        pg.insert_text((40, 120), "ZIP CODE:", fontsize=7)
        for _ in range(2 if twice else 1):
            pg.insert_text((90, 120), "90013", fontsize=9)
        pg.insert_text((40, 760), "PLD-PI-001 [Rev. January 1, 2024]", fontsize=6)
        return pg

    def test_a_value_drawn_twice_is_written_once(self):
        once = P._form_page_text(self._form(False))
        twice = P._form_page_text(self._form(True))
        assert once is not None and "90013" in once
        assert twice.count("90013") == 1, twice
        assert "90013 90013" not in twice


class TestABoxDrawnAsAQuadIsABox:
    def test_page_rules_reads_a_quad(self):
        doc = fitz.open()
        pg = doc.new_page(width=612, height=792)
        sh = pg.new_shape()
        sh.draw_quad(fitz.Quad(fitz.Point(36, 47), fitz.Point(576, 47),
                               fitz.Point(36, 120), fitz.Point(576, 120)))
        sh.finish(width=0.6)
        sh.commit()
        vert, horiz = P._page_rules(pg, P._FORM_RULE_MIN)
        assert len(vert) == 2 and len(horiz) == 2, (vert, horiz)
