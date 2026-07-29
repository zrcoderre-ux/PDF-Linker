"""
PREVENT the weld rather than cure it: the normalize-before-detect rebuild.

`_page_lined_rows` can rebuild a page's body spans from CHARACTER geometry
(`_detect_line_anchors(page, desplice=True)`), splitting each welded span at its
column jumps. That is the only stage that stops a weld from ever reaching the
scrubber; `scrub_welded` and the hard-seam pass merely clean up after one.

It used to be gated on `_page_looks_spliced`, which misses the very shape that
motivated this work — a caps run welded to a paragraph number ("MICHAEL14.") —
and which cannot be taught to see it without swallowing every case number and
Bates stamp (~90% false positives, measured; see test_hard_seam_weld.py).

So the gate is the weld SCORE, which is only ever read COMPARATIVELY. A verdict
has to be right in absolute terms; "did the rebuild help?" only has to be right
relatively, so the score can count shapes the verdict cannot afford — whatever a
signal misfires on, it misfires on identically in both scores. Adoption requires
a STRICT reduction, so a rebuild that doesn't help is discarded.

Run:  cd PDF-Linker && python3 -m pytest tests/test_desplice_gate.py -v
"""
import logging

import fitz
import pdf_linker as P

log = logging.getLogger("test")


def _rows(text):
    return [(1, [(50.0, text)])]


def _pleading(body, nlines=28):
    """A synthetic pleading page: gutter line numbers plus body text."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for i in range(1, nlines + 1):
        y = 90 + i * 23.0
        page.insert_text((45, y), str(i), fontsize=11)
        page.insert_text((95, y), body(i), fontsize=11)
    return doc, page


def test_score_sees_the_shape_the_verdict_misses():
    welded = _rows("MICHAEL14. While LAPD responded")
    assert not P._page_looks_spliced(welded)     # the gap that let it through
    assert P._page_weld_score(welded) > 0        # the score catches it


def test_verdict_signals_still_score():
    assert P._page_weld_score(_rows("SERVICEoffices of the firm")) > 0
    assert P._page_looks_spliced(_rows("SERVICEoffices of the firm"))


def test_clean_text_scores_zero():
    assert P._page_weld_score(_rows("Plaintiff alleges negligence.")) == 0
    assert P._page_weld_score([]) == 0


def test_a_case_number_never_scores():
    # The digit-seam pattern is anchored to a word start, so a California case
    # number's leading year keeps it out entirely — backtracking must not be
    # able to rescue "TCV37838" from "25STCV37838".
    assert P._page_weld_score(_rows("Case No. 26STCV00400 filed")) == 0
    assert P._page_weld_score(_rows("See 25STCV37838 and 20EDCV221896MWFJC")) == 0


def test_an_unchanged_shape_cancels_between_the_two_scores():
    # A Bates stamp DOES score, and that is harmless: it contributes the same
    # to both sides, so it can never tip the adoption decision on its own.
    bates = P._page_weld_score(_rows("RAM000013"))
    assert bates > 0
    before = P._page_weld_score(_rows("MICHAEL14. See RAM000013"))
    after = P._page_weld_score(_rows("MICHAEL 14. See RAM000013"))
    assert after < before                    # only the repaired weld moved it
    assert after == bates                    # the stamp is all that is left


def test_a_rebuild_that_does_not_help_is_discarded():
    # The safety property that makes a loose gate cheap: this page's text really
    # is one run (no column jump for the rebuild to split), so the score does
    # not drop and the ORIGINAL rows must stand.
    doc, page = _pleading(lambda i: f"MICHAEL{i}. Plaintiff alleges the defendant "
                                    f"failed to act reasonably.")
    rows = P._page_lined_rows(page)
    assert rows                                        # rows still returned
    text = " ".join(t for _n, segs in rows for _x, t in segs)
    assert "MICHAEL" in text                           # unchanged, not mangled
    doc.close()


def test_a_clean_page_is_unaffected():
    doc, page = _pleading(lambda i: f"{i}. Plaintiff alleges the defendant failed "
                                    f"to act. Case No. 26STCV00400.")
    rows = P._page_lined_rows(page)
    assert rows
    assert P._page_weld_score(rows) == 0               # no retry was needed
    doc.close()
