"""A citation wraps wherever the margin falls, and the guards must read it
as the export prints it.

On pleading paper a cite breaks inside the plaintiff's name, around the
" v. ", between the defendant and the year — and the export keeps the gutter
number of the line it wraps onto, so the gap is "\\n13  " and not a space. At
the foot of a page it is a blank line, a page header and the next page's first
gutter number. The review mask's shape guard joined name words on horizontal
whitespace alone, so every tier that reads through it took the plaintiff for
an unscrubbed name: "Martine v. Chippewa Enterprises" was reported as a slip of
a party named Martinez, "Gavina v. Smith (1944) 25 Cal.2d 501" as one of a
party named Gavin. And a page is scrubbed on its own, so the defendant of a
cite that straddled the page break had a " v. " to its left and no year in
sight — "[Berryman v. Merit Prop. Mgmt., Inc." closed one page, "(2007) 152
Cal.App.4th 1544" opened the next, and the decision shipped as "Merit
Ravenwood. Kaldor., Inc."

Run:  cd PDF-Linker && python3 -m pytest tests/test_wrapped_citation.py -v
"""
import logging
from pathlib import Path

import pytest

import pdf_linker as P

log = logging.getLogger("test")
DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
NAMES = ["Helen Rasho", "Jose Martinez", "Ana Gavin", "Sunset Prop. Mgmt., Inc."]

CITES = {
    "Martine": ("The rule is settled. (Aubry v. Tri-City Hospital Dist. (2005) "
                "134 Cal.App.4th 118, 126; Martine v. Chippewa Enterprises, Ina "
                "(2004) 121 Ca1.App.4th 1179, 1184; Chance v. Lawry's, Inc. "
                "(1962) 58 Cal.2d 368, 372.)"),
    "Gavina": ("Whether the contract was formalized in a writing has no bearing "
               "on the validity of that contract. [Gavina v. Smith (1944) 25 "
               "Cal.2d 501, 504; Mitchell v. Gonzales (1991) 54 Cal.3d 1041.]"),
    "Berryman": ("Questions of fact cannot be decided on demurrer. [Berryman v. "
                 "Merit Prop. Mgmt., Inc. (2007) 152 Cal.App.4th 1544, 1556.]"),
}


def _pz():
    reg = P._PnFakeRegistry()
    return P.Pseudonymizer(P._pn_build_terms(NAMES, [], [], registry=reg), DET,
                           registry=reg)


def _rows(z, out):
    return [r[1] for fn in ("fuzzy_survivor_scan", "half_scrubbed_scan",
                            "unknown_name_scan")
            for r in getattr(z, fn)(out)]


def _every_wrap(text):
    """The export with the sentence wrapped at each word gap: onto the next
    numbered line, and across a page break."""
    words = text.split(" ")
    for k in range(1, len(words)):
        l1, l2 = " ".join(words[:k]), " ".join(words[k:])
        yield f"line {k}", f"====== Page 3 ======\n 7  {l1}\n 8  {l2}\n"
        yield f"page {k}", (f"====== Page 3 ======\n28  {l1}\n\n"
                            f"====== Page 4 ======\n 1  {l2}\n")


# ── the review mask ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("plaintiff", list(CITES))
def test_a_wrapped_cite_is_masked_wherever_it_wraps(plaintiff):
    bad = []
    for where, body in _every_wrap(CITES[plaintiff]):
        z = _pz()
        out = z.apply(body)
        if plaintiff in z._mask_protected_citations(out) or _rows(z, out):
            bad.append(where)
    assert bad == [], bad


def test_the_shape_guard_reads_the_gutter_number_and_the_page_header():
    spans = P._pn_cite_shape_spans(
        "See Gavina v.\n13  Smith (1944) 25 Cal.2d 501.")
    assert spans and "Gavina" in "See Gavina v.\n13  Smith"[spans[0][0]:]
    text = ("[Berryman v. Merit Prop. Mgmt.,\n\n====== Page 4 ======\n\n 1  "
            "Inc. (2007) 152 Cal.App.4th 1544")
    spans = P._pn_cite_shape_spans(text)
    assert spans and text[spans[0][0]:spans[0][1]].startswith("Berryman")


def test_a_comma_list_is_still_not_a_case_name():
    # The relaxed separator admits a wrap, not a new shape: prose with a
    # capitalised word before a " v. " and no year after still anchors nothing.
    assert P._pn_cite_shape_spans("Helen Rasho v. the world, she said.") == []


# ── the write guard across a page break ──────────────────────────────────────

def test_a_defendant_at_the_foot_of_a_page_keeps_its_name():
    z = _pz()
    z.set_page_context("", "(2007) 152 Cal.App.4th 1544, 1556.] Helen Rasho.")
    out = z.apply_lines(["Questions of fact cannot be decided on demurrer. "
                         "[Berryman v. Merit Prop. Mgmt., Inc."])
    assert out == ["Questions of fact cannot be decided on demurrer. "
                   "[Berryman v. Merit Prop. Mgmt., Inc."]


def test_a_defendant_at_the_head_of_a_page_keeps_its_name():
    z = _pz()
    z.set_page_context("Questions of fact cannot be decided. [Berryman v. Merit "
                       "Prop.", "")
    assert z.apply_lines(["Mgmt., Inc. (2007) 152 Cal.App.4th 1544, 1556.]"]) == [
        "Mgmt., Inc. (2007) 152 Cal.App.4th 1544, 1556.]"]


def test_a_party_name_cited_as_an_authority_across_the_break_is_kept():
    z = _pz()
    z.set_page_context("the rule. See Smith v.", "")
    assert z.apply_lines(["Martinez (2007) 152 Cal.App.4th 1544."]) == [
        "Martinez (2007) 152 Cal.App.4th 1544."]
    # …and without the context the page cannot know, which is the bug.
    z.set_page_context()
    assert "Martinez" not in z.apply_lines(
        ["Martinez (2007) 152 Cal.App.4th 1544."])[0]


def test_the_context_never_reaches_the_page_itself():
    z = _pz()
    z.set_page_context("Jose Martinez signed.", "Ana Gavin agreed.")
    out = z.apply_lines(["Helen Rasho appeared."])
    assert len(out) == 1 and "Rasho" not in out[0]
    assert "Martinez" not in out[0] and "Gavin" not in out[0]


# ── end to end: the export writer hands each page its neighbours ─────────────

def test_the_export_keeps_a_cite_that_straddles_the_page_break(tmp_path):
    fitz = pytest.importorskip("fitz")
    src = tmp_path / "Brief.pdf"
    doc = fitz.open()
    p1 = doc.new_page()
    p1.insert_text((72, 700), "Questions of fact cannot be decided on demurrer. "
                              "[Berryman v. Merit Prop. Mgmt., Inc.", fontsize=9)
    p2 = doc.new_page()
    p2.insert_text((72, 72), "(2007) 152 Cal.App.4th 1544, 1556.] Helen Rasho "
                             "so argues.", fontsize=9)
    doc.save(str(src)); doc.close()
    z = _pz()
    assert P._write_text_version(src, fitz.open(str(src)), log, pseudonymizer=z)
    out = (tmp_path / "Text Files").glob("*.txt")
    text = next(iter(out)).read_text(encoding="utf-8")
    assert "Merit Prop. Mgmt., Inc." in text
    assert "Rasho" not in text
