"""
A Context quote never OPENS with the value it is about — at the owner's
direction. What came BEFORE the value is half the evidence a row's question
needs (the label, the role word, the sentence that introduced it), so where a
value opens its sentence the quote reaches back one sentence, inside the
paragraph where the paragraph has one and across the run boundary — the
caption above it, even on another line — where the value opens the run.
Capped: the whole previous sentence when the width allows, else its tail cut
at a word boundary behind an ellipsis, and at least `_PN_CONTEXT_LEAD` of it.

Run:  cd PDF-Linker && python3 -m pytest tests/test_context_lead.py -v
"""
import pdf_linker as P


def _parsed(lines):
    return [(1, None, l) for l in lines]


def _quote(lines, value):
    return P._pn_context_hit(_parsed(lines), value)[0]


def test_a_value_opening_a_sentence_is_shown_the_sentence_before_it():
    q = _quote(["SUPERIOR COURT OF CALIFORNIA", "COUNTY OF LOS ANGELES",
                "Helen Rasho signed the lease on April 2, 2024 and paid the "
                "deposit that day.",
                "Marcus Delacroix witnessed the signing at the branch office "
                "in Pasadena."], "Marcus Delacroix")
    assert q.startswith("Helen Rasho signed"), q
    # …and not the caption above the paragraph: one sentence back, inside
    # the run where the run holds one.
    assert "COUNTY OF LOS ANGELES" not in q


def test_a_value_opening_its_run_reaches_across_the_line_above():
    q = _quote(["SUPERIOR COURT OF CALIFORNIA", "COUNTY OF LOS ANGELES",
                "Rasho moved to compel arbitration of every claim in the "
                "complaint."], "Rasho")
    assert q.startswith("SUPERIOR COURT"), q
    assert "COUNTY OF LOS ANGELES Rasho moved" in q


def test_a_long_previous_sentence_is_cut_to_a_tail_behind_an_ellipsis():
    q = _quote(["word " * 60 + "ended here.",
                "Rasho then moved to compel arbitration of the whole action, "
                "every claim included."], "Rasho")
    assert q.startswith("…word"), q
    assert "ended here. Rasho then moved" in q
    assert len(q) <= P._PN_CONTEXT_MAX + 1
    assert not q.startswith("…ord")          # cut on a word boundary


def test_the_value_still_never_opens_the_quote_when_nothing_grows():
    q = _quote(["Defendant answered the complaint on March 3, 2025, and "
                "served it.",
                "Rasho then moved to compel arbitration of the whole action."],
               "Rasho")
    assert q.startswith("Defendant answered"), q


def test_the_document_start_has_nothing_before_it():
    q = _quote(["Rasho moved to compel arbitration of every claim in the "
                "complaint."], "Rasho")
    assert q.startswith("Rasho")


def test_a_value_mid_sentence_is_quoted_as_before():
    lines = ["On Tuesday Rasho served the notice on every party of record."]
    assert _quote(lines, "Rasho") == lines[0]


def test_the_export_half_reaches_back_the_same_way():
    """Both halves of a Context cell describe one passage: the export half is
    held to the original's site and reaches back to the same sentence."""
    orig = ["Defendant answered the complaint on March 3, 2025, and served "
            "it.", "Rasho then moved to compel arbitration of the whole "
            "action."]
    scrub = ["Defendant answered the complaint on March 3, 2025, and served "
             "it.", "Strangeways then moved to compel arbitration of the whole "
             "action."]
    q1, site = P._pn_context_hit(_parsed(orig), "Rasho")
    q2, _ = P._pn_context_hit(_parsed(scrub), "Strangeways", within=site)
    assert q1.startswith("Defendant answered") and q2.startswith("Defendant answered")
    assert q1.replace("Rasho", "Strangeways") == q2
