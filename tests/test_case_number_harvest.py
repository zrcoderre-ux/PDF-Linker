"""
The case number a Judicial Council form prints, harvested from the DOCUMENT.

A California case number is the strongest re-identification key a filing
carries: one public-portal lookup on "24STCV24253" returns the caption, the
parties, counsel and the whole docket, so a surviving one inverts the entire
pseudonym map at a stroke. It was the one identifier with no document-side
harvest at all — case numbers reached the term list ONLY from the E-Court
template's "Case Number" column, and `reid_scan` reads the same table, so a
number that column never carried was neither faked NOR reported and the export
was certified clean while carrying it.

CIV-100 and JUD-100 are where that bites: a default-judgment packet prints the
number in a caption WIDGET typed by whoever filled the form, so it routinely
differs from — or is simply absent from — the spreadsheet.

Pinned here: the label anchor and every screen on it (a cited decision's
trial-court docket, a form id, a blank field, a separate statement's row
numbers), that a harvested number folds onto the SAME fake the template and a
reused key bind, the whitespace tolerance an opaque identifier gets, and the
output-side REID report.

Run:  cd PDF-Linker && python3 -m pytest tests/test_case_number_harvest.py -v
"""
import logging

import fitz
import pytest

import pdf_linker as P

log = logging.getLogger("test")
DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}

CASENO = "24STCV24253"


def _pz(names=(), casenos=()):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), list(casenos), [], registry=reg)
    return P.Pseudonymizer(terms, DET, registry=reg)


def _harvested(text):
    return [v for cls, v in P._pn_identifier_values(text)
            if cls == "case number"]


# ── the label, and what it must not read ────────────────────────────────────

@pytest.mark.parametrize("text, want", [
    # The Judicial Council caption box, as `_form_page_text` renders it.
    ("PLAINTIFF: ACME LENDING, LLC        CASE NUMBER: 24STCV24253", CASENO),
    # …and with the label printed above its own field, which is how the box is
    # actually laid out when the value does not fit beside it.
    ("CASE NUMBER:\n24STCV24253", CASENO),
    ("Case No. BC543295", "BC543295"),
    ("CASE NO.: 22STCP01234", "22STCP01234"),
    ("Case Number: 30-2024-01234567-CU-BC-CJC", "30-2024-01234567-CU-BC-CJC"),
    ("Case No.: 2:24-cv-01234", "2:24-cv-01234"),
    ("Case #123456", "123456"),
])
def test_a_labelled_case_number_is_harvested(text, want):
    assert _harvested(text) == [want]


@pytest.mark.parametrize("text, why", [
    # A brief gives an unreported decision's trial-court docket in exactly this
    # shape. That number belongs to the cited decision, not to this case, and
    # faking it renames an authority — the trade the whole method refuses.
    ("Krikorian Inv. Servs. v. Radmanesh, Case No. BC543295, 2015 WL 12751760",
     "a cited decision's docket"),
    ("Doe v. Roe, Case No. B123456 (2019) 12 Cal.App.5th 1", "a year tail"),
    # A blank caption field on a form, followed by the page's first numbered
    # item. Admitting more than one newline would reach straight into it.
    ("CASE NUMBER:\n1. TO THE CLERK: On the complaint filed", "a blank field"),
    # A separate statement numbers its own rows, and a page/exhibit counter is
    # the commonest short number in any filing.
    ("Response No. 101", "a row number"),
    ("Material Fact No. 110", "a row number"),
    ("in this case, number 3 of the exhibits", "prose"),
    # A form NUMBER is not a case number, and on a JC caption the two stand an
    # inch apart. Faked, a form id is a nonsense stamp.
    ("Case No. CIV-100", "a form id"),
])
def test_what_a_case_number_label_must_not_read(text, why):
    assert _harvested(text) == [], why


def test_a_form_id_behind_the_label_never_becomes_a_term():
    # The value screen refuses it; `register_identifiers` asks the same
    # never-fake gate the template's own case-number column is asked.
    pz = _pz()
    pz.register_identifiers("Case No. JUD-100")
    assert [t for t in pz.terms if t.category == "case_number"] == []


# ── the fallback: the shape, with no label anywhere ────────────────────────
# YY + a two-letter COURTHOUSE code + a two-letter DIVISION code + the
# zero-padded sequence. A caption box prints its label two inches away in
# another column, a proof of service prints the number bare, and a scan drops
# the label entirely — the label anchor sees none of those.

@pytest.mark.parametrize("text, want", [
    ("24STCV24253", "24STCV24253"),                  # Stanley Mosk, Civil
    ("Plaintiff, vs.        24STCV24253\nDEFENDANT.", "24STCV24253"),
    ("22STCP01234", "22STCP01234"),                  # …Probate
    ("24STLC12345", "24STLC12345"),                  # …Limited Civil
    # NOT restricted to this court's own STCV: a folder routinely carries
    # another courthouse's number (a related action, an exhibit from another
    # matter), and those are exactly the ones no template will ever name.
    ("23VECV01234", "23VECV01234"),                  # Van Nuys East
    ("24SMCV00987", "24SMCV00987"),                  # Santa Monica
])
def test_the_shape_alone_is_enough(text, want):
    assert _harvested(text) == [want]


@pytest.mark.parametrize("text, why", [
    ("RAM24STCV24253", "welded into a Bates stamp — no bare shape"),
    ("24STCV24253A", "a longer token that merely opens with the shape"),
    ("filed in 2024 by ACME Corp 12345", "the runs are not adjacent"),
    ("Exhibit 12 ABCD 345", "the sequence is too short"),
    # The one case that matters: an unreported decision cited by its
    # trial-court docket. `register_identifiers` masks the citation spans the
    # parser could read; this is the belt for one it was blinded on.
    ("Smith v. Jones, No. 19STCV12345, 2021 WL 1234567", "a cited docket"),
])
def test_what_the_shape_must_not_read(text, why):
    assert _harvested(text) == [], why


def test_a_spaced_spelling_is_the_same_number():
    """The registry memoizes on the string it is handed, so leaving the spaces
    in would draw a second stand-in and the filing would go out under two."""
    assert _harvested("24 STCV 24253") == [CASENO]
    pz = _pz()
    src = ("CASE NUMBER: 24 STCV 24253\n"
           "Proof of service in 24STCV24253 was filed.")
    pz.register_identifiers(src)
    numbers = [t for t in pz.terms if t.category == "case_number"]
    assert [t.real for t in numbers] == [CASENO]     # one value, one binding
    out = pz.apply(src)
    assert CASENO not in out and "24 STCV 24253" not in out
    assert out.count(numbers[0].fake) == 2           # both spellings scrubbed


def test_our_own_stand_in_is_never_read_back_as_a_real_value():
    """A minted case-number fake has the same shape as the real one by
    construction, so the unlabelled anchor is the one reader that could meet a
    stand-in and mint a second-generation fake over it — a chain
    `DeAnonymize` can never walk back."""
    pz = _pz(casenos=[CASENO])
    fake = next(t.fake for t in pz.terms if t.category == "case_number")
    before = len(pz.terms)
    pz.register_identifiers(f"CASE NUMBER: {fake}")
    assert len(pz.terms) == before


def test_the_shape_costs_nothing_on_this_repository_s_own_prose():
    """The project's own measurement convention: the shape most likely to
    throw up a coincidence is a corpus full of identifiers, and this one is."""
    import pathlib
    root = pathlib.Path(P.__file__).resolve().parent
    found, scanned = set(), 0
    for f in list(root.rglob("*.py")) + list(root.rglob("*.md")):
        text = f.read_text(errors="ignore")
        scanned += len(text)
        found.update(_harvested(text))
    assert scanned > 1_000_000, "the corpus moved — re-measure before trusting"
    # Every value is a case or docket number: YY+4 letters+sequence, an older
    # LASC number, a federal docket, or another county's hyphenated form.
    shapes = [r"(?i)\d{2}[a-z]{4}\d{4,6}", r"[A-Z]{2}\d{6}", r"\d{6}",
              r"\d:\d{2}-cv-\d{5}", r"30-\d{4}-\d{8}-CU-BC-CJC"]
    import re as _re
    for v in sorted(found):
        assert any(_re.fullmatch(sh, v) for sh in shapes), \
            f"not a case number: {v!r}"


# ── the fake, and the slot it is drawn from ─────────────────────────────────

def test_a_harvested_number_takes_the_fake_the_template_would_have_given_it():
    """Both paths draw through `_pn_fake_caseno`'s "caseno" slot, so a folder
    whose template names the number and a folder whose does not come out the
    same — and a re-run cannot mint a second stand-in for one case."""
    from_template = _pz(casenos=[CASENO])
    template_fake = next(t.fake for t in from_template.terms
                         if t.category == "case_number")
    from_document = _pz()
    from_document.register_identifiers(f"CASE NUMBER: {CASENO}")
    document_fake = next(t.fake for t in from_document.terms
                         if t.category == "case_number")
    assert document_fake == template_fake
    # The two-digit filing year is printed beside the number in every caption,
    # so randomising it hides nothing and only makes the fake impossible.
    assert document_fake.startswith("24") and document_fake != CASENO


def test_the_template_wins_and_the_harvest_does_not_double_register():
    pz = _pz(casenos=[CASENO])
    before = len(pz.terms)
    pz.register_identifiers(f"CASE NUMBER: {CASENO}")
    assert len(pz.terms) == before


def test_a_reused_key_pins_the_harvested_binding(tmp_path):
    """The incremental re-run: the documents already sent must come back byte
    for byte, so the key's binding outranks anything the harvest derives."""
    pz = _pz()
    text = f"CASE NUMBER: {CASENO}"
    pz.register_identifiers(text)
    first = pz.apply(text)
    path = tmp_path / "pseudonym_key.xlsx"
    pz.write_key(path, log)

    reg2 = P._PnFakeRegistry()
    terms, *_ = P._pn_load_key(path, reg2, log)
    pz2 = P.Pseudonymizer(terms, DET, registry=reg2)
    pz2.register_identifiers(text)        # the harvest runs on the re-run too
    assert pz2.apply(text) == first


def test_the_key_carries_the_row_that_reverses_it(tmp_path):
    pz = _pz()
    pz.register_identifiers(f"CASE NUMBER: {CASENO}")
    out = pz.apply(f"CASE NUMBER: {CASENO}")
    path = tmp_path / "pseudonym_key.xlsx"
    pz.write_key(path, log)
    import openpyxl
    rows = [r for ws in openpyxl.load_workbook(path).worksheets
            for r in ws.iter_rows(min_row=2, values_only=True) if r and r[0]]
    binding = {str(r[1]): str(r[2]) for r in rows}
    assert CASENO in binding
    # The row is what `DeAnonymize.bas` walks back: its Replacement is exactly
    # the stand-in the export carries.
    assert binding[CASENO] in out and binding[CASENO] != CASENO


# ── spelling: an opaque identifier's internal spacing carries no meaning ────

@pytest.mark.parametrize("printed", [
    "CASE NUMBER: 24STCV24253",
    "CASE NUMBER: 24 STCV 24253",       # typed into the form field with spaces
    "CASE NUMBER: 24STCV\n24253",       # a narrow caption column wrapped it
    "CASE NUMBER: 24 STCV24253",        # a scan spaced one seam, not the other
])
def test_every_spacing_of_one_number_is_one_number(printed):
    pz = _pz(casenos=[CASENO])
    assert CASENO not in pz.apply(printed)


@pytest.mark.parametrize("text", [
    "RAM24STCV24253",          # a Bates stamp around it — a weld, not this
    "24STCV24253A",            # a longer token that merely opens with it
    "in 2024 the plaintiff filed",
])
def test_the_word_boundaries_still_hold(text):
    pz = _pz(casenos=[CASENO])
    assert pz.apply(text) == text


def test_a_wrapped_number_keeps_the_line_it_was_printed_on():
    """`apply_lines` reflows, so a pinpoint cite keyed to a line number does
    not shift under a page whose caption column wrapped the case number."""
    pz = _pz(casenos=[CASENO])
    bodies = ["Plaintiff, vs.", "Case No. 24STCV", "24253", "Dept. 55"]
    assert len(pz.apply_lines(bodies)) == len(bodies)


# ── the output side: an export carrying one can never be certified clean ────

def test_a_surviving_case_number_is_reported_as_a_reidentification_key():
    pz = _pz()
    found = pz.reid_scan(f"CASE NUMBER: {CASENO}")
    assert ("REID case number", CASENO) in found


def test_our_own_stand_in_is_not_reported_back():
    pz = _pz(casenos=[CASENO])
    out = pz.apply(f"CASE NUMBER: {CASENO}")
    assert pz.reid_scan(out) == []


# ── end to end: the packet that reported this ───────────────────────────────

def _static(page, x, y, s, size=9):
    page.insert_text((x, y), s, fontsize=size, fontname="helv")


def _checkbox(page, name, x, y, on, size=10.0):
    w = fitz.Widget()
    w.field_name = name
    w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
    w.rect = fitz.Rect(x, y, x + size, y + size)
    w.field_value = on
    w.border_width = 0.7
    w.border_color = (0, 0, 0)
    page.add_widget(w)


def _text(page, name, x, y, value, w_=200.0):
    w = fitz.Widget()
    w.field_name = name
    w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
    w.rect = fitz.Rect(x, y, x + w_, y + 15.0)
    w.field_value = value
    w.text_fontsize = 8
    page.add_widget(w)


def _packet_form(form_id):
    """A CIV-100 / JUD-100 caption block: the case number lives in a WIDGET, so
    it reaches no pass at all unless the form rendering is harvested."""
    doc = fitz.open()
    p = doc.new_page(width=612, height=792)
    _static(p, 40, 150, "PLAINTIFF:", 7)
    _static(p, 40, 170, "DEFENDANT:", 7)
    _static(p, 400, 150, "CASE NUMBER:", 7)
    _static(p, 60, 230, "1. TO THE CLERK: On the complaint filed", 8)
    _static(p, 75, 250, "a. Enter default of defendant (names):", 8)
    _static(p, 75, 275, "b. Enter clerk's judgment", 8)
    _static(p, 40, 745, f"{form_id} [Rev. January 1, 2023]", 6)
    _text(p, "plaintiff", 95, 143, "ACME LENDING, LLC")
    _text(p, "defendant", 100, 163, "ERNEST N RAMIREZ")
    _text(p, "caseno", 460, 143, CASENO, 100.0)
    _checkbox(p, "cb_1a", 62, 244, True)
    _checkbox(p, "cb_1b", 62, 269, False)
    return doc


@pytest.mark.parametrize("form_id", ["CIV-100", "JUD-100"])
def test_the_packet_form_ships_no_case_number(tmp_path, form_id):
    """The template names this case's parties and never its case number — the
    ordinary shape of a prove-up packet dropped in a folder of its own."""
    src = tmp_path / f"{form_id}.pdf"
    _packet_form(form_id).save(src)
    pz = _pz(names=["Ernest N Ramirez"])
    with fitz.open(src) as doc:
        P._pn_learn_from_text(pz, "\n\f\n".join(P._page_detect_text(pg)
                                                for pg in doc))
    assert P._write_text_version(src, fitz.open(src), log, pseudonymizer=pz)
    # The export's own filename is pseudonymized too, so glob for it.
    body = next((tmp_path / "Text Files").glob("*.txt")).read_text("utf-8")
    assert CASENO not in body
    assert "ERNEST N RAMIREZ" not in body.upper()
    assert form_id in body            # the form id is boilerplate, never faked
    assert not pz.surviving_reals(body)
    assert not pz.reid_scan(body)
