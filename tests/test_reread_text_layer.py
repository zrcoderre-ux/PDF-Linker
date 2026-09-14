"""A page read TWICE must export once — even when the two readings disagree.

The operator's report: "PDF-Linker is doubling words, often with one spelled
right and the other spelled wrong."

    Customer Cuore reusr trust ise: is at the (He Hee heart fee of our
    brisiness business dnd and never bevel worth Werth pronrorminen

That is one printed line carrying two text layers. `_drop_overdrawn_spans`
compares on exact TEXT and `_span_is_redraw_fragment` on containment, so
neither can see it: the two engines read the same printed word differently, and
"Customer" never matches "Cuore". The row then joins left to right and every
word ships twice.

It is not cosmetic, and it is the `_drop_overdrawn_spans` harm exactly: a
whole-word term cannot match a doubled run, so the parties ride through the
scrub untouched; the harvester reads the welds as names and mints them; and
`_pn_context` quotes the wreckage into the triage worksheet.

TWO fixes, at the two ends.

CAUSE — `_ocr_image_regions` was laying the second layer itself.
`_image_ocr_already_read` refused a region the page had already read, measured
by WORD AGREEMENT at half. But the page worth re-reading is the page whose own
layer is bad, and a bad layer is one our reading will not agree with: a fax
generation scores a quarter where the guard wants half, so the overlay landed.
The guard now also asks the question disagreement cannot spoil — is the page
already carrying a comparable BODY of text in this rect? Both engines read the
same printed words, so the COUNT holds where the spellings do not.

BELT — `_drop_reread_spans`, for the folders already carrying doubled PDFs (the
tool writes its OCR into the source file) and for source PDFs that arrive that
way. Two spans over the same ink are two readings of one printed run, and one
of them has to go.

Run:  cd PDF-Linker && python3 -m pytest tests/test_reread_text_layer.py -v
"""
import pytest

import pdf_linker as P

fitz = pytest.importorskip("fitz")


# ── the CAUSE: the guard that let the second layer land ─────────────────────

# A fax generation's own text layer, and what a 300-dpi pass reads off the same
# printed page. They share a quarter of their words, which is the whole point.
THEIRS = ("Cuore reusr ise: the (He fee brisiness dnd bevel Werth pronrorminen "
          "Ensure oll groposdls Goores InvoloHs tesls Ser itatiany "
          "COmniunioations and any qgoverament requires documentation")
OURS = ("Customer trust is at the heart of our business and never worth "
        "compromising Ensure all proposals quotes invoices tests "
        "certifications communications and any other government required "
        "documentation")


def _scan_page(text, width=612, height=792):
    """A page whose whole area is a scanned image, carrying `text` as its own
    layer — the shape `_image_ocr_rects` hands to the guard."""
    doc = fitz.open()
    pg = doc.new_page(width=width, height=height)
    y = 80
    for line in text.split(" and "):
        pg.insert_text((72, y), line, fontsize=10)
        y += 16
    return pg


def test_the_two_engines_really_do_disagree():
    """The premise: the agreement arm cannot fire on this page, so it was not
    the arm that was mis-tuned — it was the only question being asked."""
    words = P._IMG_OCR_WORD_RE.findall(OURS)
    have = {w.lower() for w in P._IMG_OCR_WORD_RE.findall(THEIRS)}
    same = sum(1 for w in words if w.lower() in have)
    assert same < P._IMG_OCR_READ_MIN * len(words)


def test_a_re_read_page_is_refused_though_the_readings_disagree():
    pg = _scan_page(THEIRS)
    rect = fitz.Rect(0, 0, 612, 792)
    assert P._image_ocr_already_read(pg, rect, OURS)


def test_the_agreement_arm_still_fires():
    """Unchanged where it always worked: two engines that mostly agree."""
    pg = _scan_page(OURS)
    assert P._image_ocr_already_read(pg, fitz.Rect(0, 0, 612, 792), OURS)


def test_a_signature_block_on_a_blank_stretch_is_still_read():
    """What the pass exists for: a judge's signature image, with nothing
    underneath it. The page has text — elsewhere."""
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    pg.insert_text((72, 100), "IT IS SO ORDERED.", fontsize=11)
    sig = fitz.Rect(72, 300, 290, 391)
    assert not P._image_ocr_already_read(pg, sig, "Alison Mackenzie Judge")


def test_a_signature_block_clipping_a_line_of_body_text_is_still_read():
    """The coverage arm must not swallow the small region it exists beside: a
    couple of neighbouring words is not a body of text."""
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    pg.insert_text((72, 320), "Dated this day", fontsize=11)
    sig = fitz.Rect(72, 300, 290, 391)
    assert not P._image_ocr_already_read(pg, sig, "Alison Mackenzie Judge")


def test_an_empty_region_is_never_already_read():
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    assert not P._image_ocr_already_read(pg, fitz.Rect(0, 0, 612, 792), OURS)


def test_the_coverage_arm_needs_a_body_of_text_not_a_ratio():
    """Below the floor the arm says nothing, whatever the ratio. Two words
    against three is 0.67 and is not evidence of anything."""
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    pg.insert_text((100, 350), "the lease", fontsize=11)
    assert not P._image_ocr_already_read(pg, fitz.Rect(72, 300, 290, 391),
                                         "Alison Mackenzie Judge")


# ── the BELT: a page that already carries two readings ──────────────────────

# Word for word: what the page prints, and what a second reading made of it.
PAIRS = [
    ("Customer", "Cuore"), ("trust", "reusr"), ("is", "1s"), ("at", "at"),
    ("the", "the"), ("heart", "fee"), ("of", "of"), ("our", "our"),
    ("business", "brisiness"), ("and", "dnd"), ("never", "bevel"),
    ("worth", "Werth"), ("compromising", "pronrorminen"),
    ("Ensure", "Ensure"), ("all", "oll"), ("proposals", "groposdls"),
    ("quotes", "Goores"), ("invoices", "InvoloHs"), ("tests", "tesls"),
    ("communications", "COmniunioations"), ("government", "qgoverament"),
    ("documentation", "documentaticn"),
]


def _doubled(layers=2, dx=0.6, dy=0.4, pairs=None):
    """A page whose printed words each carry `layers` readings.

    The second reading sits in the PRINTED word's own place, which is what an
    OCR producer does — it draws what it recognised into the box it found the
    word in — so the two boxes land on each other whatever the spelling. The
    PAGE's reading is drawn first and the remedial one over it, the order
    `page.show_pdf_page(..., overlay=True)` produces.

    Each layer is set in its OWN font, which is what keeps them two spans: an
    OCR layer is a separate content object in a font of its own (Tesseract's
    GlyphLessFont), and drawing both in one font lets the extractor merge two
    short readings into a single run ("atat") that no span comparison can see.
    """
    pairs = PAIRS if pairs is None else pairs
    fonts = ("helv", "tiro", "cour")
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    x, y = 72.0, 100.0
    for printed, reread in pairs:
        for i, txt in enumerate((printed, reread)[:layers]):
            pg.insert_text((x + dx * i, y + dy * i), txt, fontsize=10,
                           fontname=fonts[i % len(fonts)])
        x += 6.2 * len(printed) + 6
        if x > 480:
            x, y = 72.0, y + 22
    return pg


def _flat(page):
    return " ".join(P._page_flowing_text(page).split())


def test_the_doubling_the_operator_reported_is_gone():
    """Side by side ("Customer Cuore") or run together ("CustomerCuore") — the
    row renderer spaces the two readings or welds them depending on how far
    apart the boxes fall, and neither may survive."""
    flat = _flat(_doubled())
    for printed, reread in PAIRS:
        if printed == reread:
            continue
        for welded in (printed + reread, reread + printed,
                       f"{printed} {reread}", f"{reread} {printed}"):
            assert welded not in flat, (welded, flat)


def test_each_printed_word_survives_as_exactly_one_reading():
    """The assertion the welded shape defeats: on the doubled page the token is
    "CustomerCuore", which is neither reading and matches no term."""
    flat = _flat(_doubled()).split()
    for printed, reread in PAIRS:
        got = [w for w in flat if w in (printed, reread)]
        assert len(got) == 1, (printed, reread, got, flat)


def test_the_later_reading_is_the_one_kept():
    """A second text layer exists because somebody judged the first
    inadequate — a filer's re-OCR, or this tool's own image pass, which lays
    its reading over the page with `overlay=True` and so comes second."""
    flat = _flat(_doubled())
    assert "Cuore" in flat and "Customer" not in flat, flat


def test_a_reading_under_half_the_printed_word_is_left_alone():
    """Residual, and stated. Mutual coverage is what refuses a stamp over a
    word, and it refuses this too: a reading that recovered less than half the
    printed run's ink is not demonstrably the same run. It costs a word left
    doubled where the alternative costs real text deleted."""
    short = [("documentation", "req")] * 12
    flat = _flat(_doubled(pairs=short))
    assert "documentationreq" in flat or "documentation req" in flat, flat


def test_a_single_layer_page_is_untouched():
    page = _doubled(layers=1)
    assert P._page_flowing_text(page) == page.get_text("text")
    assert not P._page_is_overdrawn(page)


def test_a_party_name_matches_again_after_the_collapse():
    """The point of the fix: a whole-word term cannot match a doubled run, so
    the party rode through the scrub untouched."""
    pairs = [("Sarkisyan", "Sarkisyau"), ("declares", "declaros")] + PAIRS
    flat = _flat(_doubled(pairs=pairs))
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Sarkisyau"], [], [], registry=reg)
    z = P.Pseudonymizer(terms, list(P._PN_DEFAULT_DETECTORS), registry=reg)
    assert "Sarkisyau" in flat
    assert "Sarkisyau" not in z.apply(flat)


def test_the_page_says_on_its_banner_that_it_had_to_choose():
    """Which spelling is right is not something any shape measure can settle,
    so the run says a choice was made rather than implying there was none."""
    page = _doubled()
    P._page_flowing_text(page)
    assert page.parent and getattr(page.parent, P._DOUBLED_ATTR, {}).get(0)


def test_a_clean_page_notes_nothing():
    page = _doubled(layers=1)
    P._page_flowing_text(page)
    assert not getattr(page.parent, P._DOUBLED_ATTR, {})


# ── the gates ───────────────────────────────────────────────────────────────

def _sp(text, x0, y0, x1, y1):
    return {"text": text, "bbox": (x0, y0, x1, y1)}


def test_a_reread_is_mutual_coverage_not_containment():
    word = _sp("Customer", 100, 50, 150, 62)
    assert P._spans_reread(word, _sp("Cuore", 100.6, 50.4, 145, 62.4))
    # A stamp whose box swallows the word covers almost none of its own.
    assert not P._spans_reread(word, _sp("FILED", 60, 45, 500, 70))
    # Adjacent words on a line abut; they do not sit on each other.
    assert not P._spans_reread(word, _sp("trust", 151, 50, 190, 62))


def test_two_readings_must_be_the_same_size_of_type():
    word = _sp("Customer", 100, 50, 150, 62)
    heading = _sp("CUSTOMERS", 100, 40, 150, 75)
    assert not P._spans_reread(word, heading)


def test_identical_text_is_not_this_tier():
    """That is the exact-text tier's, which keeps the FIRST and needs no floor."""
    a = _sp("Chung", 100, 50, 140, 62)
    assert not P._spans_reread(a, _sp("Chung", 100.5, 50.4, 140.5, 62.4))


def test_a_lone_coincidence_never_deletes_a_word():
    """Below the pair floor nothing is dropped, however the two boxes sit."""
    spans = [_sp("Customer", 100, 50, 150, 62),
             _sp("Cuore", 100.6, 50.4, 145, 62.4)]
    assert P._drop_reread_spans(spans)[0] == spans
    assert P._drop_overdrawn_spans(spans) == spans


def test_a_handful_of_coincidences_on_a_busy_page_never_delete_a_word():
    """The share gate: eight pairs among four hundred spans is not a page
    reading itself twice."""
    spans = []
    for i in range(P._SPAN_REREAD_MIN_PAIRS):
        y = 50 + 20 * i
        spans += [_sp("Customer", 100, y, 150, y + 12),
                  _sp("Cuore", 100.6, y + 0.4, 145, y + 12.4)]
    assert len(P._drop_reread_spans(spans)[0]) < len(spans)   # on its own: caught
    filler = [_sp(f"word{i}", 200 + 60 * (i % 5), 400 + 14 * (i // 5),
                  240 + 60 * (i % 5), 410 + 14 * (i // 5)) for i in range(400)]
    assert P._drop_reread_spans(spans + filler)[0] == spans + filler


def test_a_kept_span_is_never_eroded_for_one_already_dropped():
    """Three layers collapse to one, not to none."""
    spans = []
    for i in range(10):
        y = 50 + 20 * i
        spans += [_sp("Customer", 100, y, 150, y + 12),
                  _sp("Cuore", 100.6, y + 0.4, 148, y + 12.4),
                  _sp("Custorner", 101.2, y + 0.8, 149, y + 12.8)]
    kept = P._drop_reread_spans(spans)[0]
    assert [s["text"] for s in kept] == ["Custorner"] * 10


# ── the same page seen the other way: the PLEADING-ROW path ─────────────────

def _pleading(layers=2, dx=0.6, dy=0.4):
    """Pleading paper — a gutter of line numbers and a body — read `layers`
    times. This is the path the export takes for a filed document, and it welds
    the two readings exactly as the flowing one does."""
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    fonts = ("helv", "tiro")
    y = 90.0
    for n in range(1, 21):
        pg.insert_text((46, y), str(n), fontsize=10)
        x = 96.0
        for printed, reread in PAIRS[(n - 1) % 4::4]:
            for i, txt in enumerate((printed, reread)[:layers]):
                pg.insert_text((x + dx * i, y + dy * i), txt, fontsize=10,
                               fontname=fonts[i % len(fonts)])
            x += 6.2 * len(printed) + 8
        y += 24
    return pg


def _row_text(page):
    rows = P._page_lined_rows(page)
    return " ".join(t for _n, segs in (rows or []) for _x, t in segs)


def test_the_pleading_row_path_collapses_the_doubling_too():
    flat = _row_text(_pleading())
    assert flat.strip(), "the page produced no rows at all"
    for printed, reread in PAIRS:
        if printed == reread:
            continue
        for welded in (printed + reread, reread + printed,
                       f"{printed} {reread}", f"{reread} {printed}"):
            assert welded not in flat, (welded, flat)


def test_the_pleading_page_keeps_its_line_numbers():
    """Dropping spans must not cost the gutter, which a pinpoint cite lands on."""
    nums = [n for n, _segs in (P._page_lined_rows(_pleading()) or [])]
    assert nums == list(range(1, 21)), nums


def test_a_single_layer_pleading_page_keeps_every_word():
    """The other direction: a page drawn once must come through whole, or a
    tier that deletes text would pass the tests above by deleting all of it."""
    flat = _row_text(_pleading(layers=1)).split()
    for printed, _reread in PAIRS:
        assert printed in flat, (printed, flat)


# ── the banner ──────────────────────────────────────────────────────────────

def _header(pairs):
    return (f"====== Page 7 (printed p. 3)"
            f" — REVIEW: this page carried TWO text layers that disagree; "
            f"{pairs} piece(s) of the earlier reading were dropped and the "
            f"later one is shown ======")


def test_the_banner_still_reads_as_a_page_header():
    """A header `_PN_PAGE_HEADER_RE` cannot match does not merely lose its own
    page: the parser keeps the LAST page it did match, so every line after it
    is reported at that page's number."""
    assert P._PN_PAGE_HEADER_RE.search(_header(42))


def test_the_banner_stacks_with_the_others():
    h = ("====== Page 7 — REVIEW: the text layer was unreadable and was "
         "REBUILT by OCR; spellings, numbers and citations on this page are "
         "GUESSES" + _header(3).split("Page 7 (printed p. 3)")[1])
    assert P._PN_PAGE_HEADER_RE.search(h)


def test_the_note_records_the_largest_collapse_not_a_running_total():
    """The export, the detection copy and the citation parse each render a page
    through the dedupe; they describe ONE doubling, not three."""
    doc = fitz.open()
    pg = doc.new_page(width=612, height=792)
    P._note_doubled_page(pg, 12)
    P._note_doubled_page(pg, 12)
    P._note_doubled_page(pg, 5)
    assert getattr(doc, P._DOUBLED_ATTR) == {0: 12}
    doc.close()


def test_instrumentation_never_takes_a_run_down():
    """The text matters more than the note about it."""

    class _Hostile:
        number = 0

        @property
        def parent(self):
            raise RuntimeError("no parent")

    P._note_doubled_page(_Hostile(), 3)         # must not raise
