"""
An OCR fix (`*CORRECT TEXT`) corrects the PDF's own text layer, the ORIGINAL
text copy and the TEMP evidence cache — not only the export.

`*Smith` on "Smlth" says the page wrote "Smlth" and meant "Smith". The export
already read as Smith reads (the ocr-fix term); now the PDF's invisible OCR
layer is rewritten so the document itself says Smith, BEFORE the export is
extracted from it, and the reference copy and the evidence cache are corrected
at the text level wherever the PDF patch could not land (a garble in VISIBLE
type). `--fix-leaks` does the same for a worksheet `*`: it corrects the
original files on disk and patches the folder's PDFs — the one thing that
pass does to a PDF, a text-layer patch with no extraction and no OCR.

Run:  cd PDF-Linker && python3 -m pytest tests/test_ocr_fix_everywhere.py -v
"""
import inspect
import logging
import types
import warnings

import fitz
import openpyxl

import pdf_linker as P

warnings.filterwarnings("ignore", category=DeprecationWarning)
log = logging.getLogger("test")
DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
HDR = ("Value", "Fix? (yes/no)", "Type", "Notes", "Cases", "Origin")
ORIG = "Original Text (real names - do not share)"


def _decisions(*rows):
    return P._pn_parse_decision_rows(
        [HDR] + [(v, c, "", "", "", "") for v, c in rows])


def _scan_doc(lines, visible=(), rotate=0, text_rotate=0):
    """A 'scanned' page: an image with an INVISIBLE text layer over it, plus
    any `visible` lines drawn in ordinary type."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    if rotate:
        page.set_rotation(rotate)
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 60, 30), False)
    pix.clear_with(210)
    page.insert_image(fitz.Rect(40, 40, 570, 750), pixmap=pix)
    for i, line in enumerate(lines):
        # Rotated text runs UP the page from its origin, so start it low.
        y = 400 if text_rotate else 100
        page.insert_text((72, y + 20 * i), line, fontsize=11,
                         render_mode=3, fontname="helv", rotate=text_rotate)
    for i, line in enumerate(visible):
        page.insert_text((72, 400 + 20 * i), line, fontsize=11, fontname="helv")
    return doc


def _terms(names=("John Smith",), decisions=None):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    if decisions:
        terms = P._pn_apply_ocr_fixes(decisions, terms, reg, log)
    return terms, reg


# ── what a decision corrects, as a whole ────────────────────────────────────

def test_the_whole_text_of_a_decision():
    d = _decisions(("Smlth", "*Smith"))["smlth"]
    assert P._pn_ocr_whole_text(d) == "Smith"
    d = _decisions(("avidsaid", "*David {said}"))["avidsaid"]
    assert P._pn_ocr_whole_text(d) == "David said"
    d = _decisions(("Smith", "~Smyth"))["smith"]
    assert P._pn_ocr_whole_text(d) is None


def test_apply_ocr_fixes_records_the_correction_on_the_registry():
    terms, reg = _terms(decisions=_decisions(("Smlth", "*Smith"),
                                             ("cuve!nants", "*covenants"),
                                             ("Same", "*Same")))
    assert reg.ocr_corrections["smlth"] == ("Smlth", "Smith")
    assert reg.ocr_corrections["cuve!nants"] == ("cuve!nants", "covenants")
    assert "same" not in reg.ocr_corrections          # names itself: no fix


def test_a_fix_the_pass_declines_is_not_recorded():
    # `allow_rebind=False` (--fix-leaks) leaves a bound value alone — in the
    # export AND in the PDF, or the two would say different things.
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Smlth"], [], [], registry=reg)
    terms = P._pn_apply_ocr_fixes(_decisions(("Smlth", "*Smith")), terms, reg,
                                  log, allow_rebind=False)
    assert reg.ocr_corrections == {}


def test_corrections_are_read_back_off_loaded_terms():
    # A reused key hands an OCR-fix row back as a live term with the correct
    # text's STAND-IN for its fake; the correct text is the real value that
    # stand-in belongs to — or the fake itself where nothing owns it.
    terms, reg = _terms()
    tok = next(t for t in terms if t.category == "person-token"
               and t.real.lower() == "smith")
    loaded = P._PnTerm("person-token", "Smlth", tok.fake, whole_word=True,
                       case_sensitive=False, priority=1, source="pseudonym key",
                       derived=True)
    loaded.ocr_fix = loaded.loaded = True
    verbatim = P._PnTerm("ocr-fix", "cuve!nants", "covenants", whole_word=True,
                         case_sensitive=False, priority=2,
                         source="pseudonym key", derived=True)
    verbatim.ocr_fix = verbatim.loaded = True
    corr = P._pn_ocr_corrections(terms + [loaded, verbatim], reg)
    assert corr["smlth"] == ("Smlth", "Smith")
    assert corr["cuve!nants"] == ("cuve!nants", "covenants")
    # …and `--fix-leaks` asks only about THIS worksheet's fixes.
    assert P._pn_ocr_corrections(terms + [loaded, verbatim], reg,
                                 loaded=False) == {}


def test_the_text_correction_is_whole_word_and_cased():
    corr = {"smlth": ("Smlth", "Smith"), "cuve!nants": ("cuve!nants", "covenants")}
    out = P._pn_correct_ocr_text(
        "Mr. SMLTH's cuve!nants; smlth-jones met Smlthson.", corr)
    assert out == "Mr. SMITH's covenants; smith-jones met Smlthson."
    assert P._pn_correct_ocr_text("nothing here", corr) == "nothing here"
    assert P._pn_correct_ocr_text("x", {}) == "x"


# ── the PDF's text layer ────────────────────────────────────────────────────

def test_the_invisible_layer_is_corrected_and_visible_type_left_alone():
    doc = _scan_doc(["DECLARATION OF JOHN SMLTH",
                     "I, John Smlth, declare as follows:",
                     "The cuve!nants were breached by SMLTH."],
                    visible=["Visible Smlth stays"])
    corr = {"smlth": ("Smlth", "Smith"), "cuve!nants": ("cuve!nants", "covenants")}
    assert P._pn_fix_ocr_in_pdf(doc, corr, log) == 1
    text = doc[0].get_text("text")
    assert "DECLARATION OF JOHN SMITH" in text
    assert "I, John Smith, declare as follows:" in text
    assert "The covenants were breached by SMITH." in text
    assert "Visible Smlth stays" in text            # printed type untouched
    assert len(doc[0].get_images()) == 1           # the scan itself is kept
    # Every word of the layer is still invisible.
    assert all(sp["type"] == 3 for sp in doc[0].get_texttrace()
               if "Visible" not in "".join(chr(c[0]) for c in sp["chars"]))
    # Idempotent: nothing left to correct.
    assert P._pn_fix_ocr_in_pdf(doc, corr, log) == 0


def test_the_layer_keeps_its_reading_order():
    # The whole layer is re-drawn in stream order — a lone word inserted
    # after the fact would land at the END of the page's text.
    lines = ["First line names Smlth here.", "Second line follows.",
             "Third line closes."]
    doc = _scan_doc(lines)
    P._pn_fix_ocr_in_pdf(doc, {"smlth": ("Smlth", "Smith")}, log)
    got = [l for l in doc[0].get_text("text").splitlines() if l.strip()]
    assert got == ["First line names Smith here.", "Second line follows.",
                   "Third line closes."]


def test_a_rotated_page_and_rotated_text_are_corrected_in_place():
    doc = _scan_doc(["Signed by John Smlth"], rotate=90)
    assert P._pn_fix_ocr_in_pdf(doc, {"smlth": ("Smlth", "Smith")}, log) == 1
    assert "Signed by John Smith" in doc[0].get_text("text")
    doc = _scan_doc(["Signed by John Smlth"], text_rotate=90)
    before = doc[0].get_texttrace()[0]
    assert P._pn_fix_ocr_in_pdf(doc, {"smlth": ("Smlth", "Smith")}, log) == 1
    assert "Signed by John Smith" in doc[0].get_text("text")
    after = doc[0].get_texttrace()
    assert all(sp["dir"] == before["dir"] for sp in after)   # runs the same way
    union = fitz.Rect(after[0]["bbox"])
    for sp in after[1:]:
        union |= fitz.Rect(sp["bbox"])
    # …over the same run of the page: the re-drawn layer sits where the old
    # one did, to within a point or two.
    for a, b in zip(union, before["bbox"]):
        assert abs(a - b) < 2


def test_visible_type_over_the_layer_refuses_the_page(caplog):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "John Smlth signed", fontsize=11,
                     render_mode=3, fontname="helv")
    page.insert_text((72, 100), "FILED", fontsize=11, fontname="helv")  # over it
    with caplog.at_level(logging.WARNING):
        assert P._pn_fix_ocr_in_pdf(doc, {"smlth": ("Smlth", "Smith")}, log) == 0
    assert "John Smlth signed" in page.get_text("text")
    assert "FILED" in page.get_text("text")
    assert "visible text lies over its OCR layer" in caplog.text


def test_a_garble_in_visible_type_only_is_left_as_printed(caplog):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "John Smlth signed", fontsize=11, fontname="helv")
    with caplog.at_level(logging.INFO):
        assert P._pn_fix_ocr_in_pdf(doc, {"smlth": ("Smlth", "Smith")}, log) == 0
    assert "John Smlth signed" in page.get_text("text")
    assert "VISIBLE text" in caplog.text


def test_a_multi_word_garble_and_a_possessive():
    doc = _scan_doc(["Defendant Jonh Smlth's motion was denied."])
    corr = {"jonh smlth": ("Jonh Smlth", "John Smith")}
    assert P._pn_fix_ocr_in_pdf(doc, corr, log) == 1
    assert "Defendant John Smith's motion was denied." in doc[0].get_text("text")


# ── the full run: PDF, export and original from one source ──────────────────

def test_the_full_run_corrects_pdf_export_and_original(tmp_path):
    pdf = tmp_path / "Brief.pdf"
    # Enough words that the text-layer gate reads the page as a document.
    filler = ["The parties agreed that the lease would run for five years "
              "from the date of execution and renew on notice."] * 6
    _scan_doc(["Defendant John Smlth breached the cuve!nants."] + filler).save(pdf)
    terms, reg = _terms(decisions=_decisions(("Smlth", "*Smith"),
                                             ("cuve!nants", "*covenants")))
    pz = P.Pseudonymizer(terms, DET, registry=reg)
    assert P.process_pdf(pdf, log, pseudonymizer=pz, original_subdir=ORIG)
    with fitz.open(pdf) as doc:
        text = doc[0].get_text("text")
    assert "John Smith breached the covenants" in text        # the PDF
    orig = next((tmp_path / ORIG).glob("*.txt")).read_text(encoding="utf-8")
    assert "John Smith breached the covenants" in orig        # the original
    export = next((tmp_path / "Text Files").glob("*.txt")).read_text(
        encoding="utf-8")
    fake = next(t for t in terms if t.real == "John Smith").fake
    assert fake in export and "Smlth" not in export           # the export
    assert "covenants" in export and "cuve!nants" not in export


def test_a_visible_garble_is_still_corrected_in_the_original(tmp_path):
    pdf = tmp_path / "Brief.pdf"
    doc = fitz.open()
    doc.new_page(width=612, height=792).insert_text(
        (72, 100), "Defendant John Smlth breached the cuve!nants.", fontsize=11)
    doc.save(pdf)
    terms, reg = _terms(decisions=_decisions(("Smlth", "*Smith"),
                                             ("cuve!nants", "*covenants")))
    pz = P.Pseudonymizer(terms, DET, registry=reg)
    with fitz.open(pdf) as d:
        P._write_text_version(pdf, d, log, pz, "Text Files", ORIG)
    orig = next((tmp_path / ORIG).glob("*.txt")).read_text(encoding="utf-8")
    assert "John Smith breached the covenants" in orig
    cached = list(P._originals_cache_dir(tmp_path).glob("*.txt"))
    assert cached and "John Smith breached the covenants" in \
        cached[0].read_text(encoding="utf-8")
    export = next((tmp_path / "Text Files").glob("*.txt")).read_text(
        encoding="utf-8")
    assert "Smlth" not in export and "covenants" in export


def test_the_word_path_corrects_its_body(tmp_path):
    src = tmp_path / "Letter.docx"
    src.write_bytes(b"")
    terms, reg = _terms(decisions=_decisions(("Smlth", "*Smith")))
    pz = P.Pseudonymizer(terms, DET, registry=reg)
    assert P._write_word_text_version(
        src, "Dear John Smlth,\nThe covenants hold.\n", log, pz,
        "Text Files", ORIG)
    orig = (tmp_path / ORIG / "Letter.txt").read_text(encoding="utf-8")
    assert "Dear John Smith," in orig
    export = next((tmp_path / "Text Files").glob("*.txt")).read_text(
        encoding="utf-8")
    assert "Smlth" not in export and "Smith" not in export


def test_the_pdf_is_corrected_before_the_export_is_extracted():
    src = inspect.getsource(P.process_pdf)
    assert src.index("_pn_fix_ocr_in_pdf(") < src.index("_write_text_version(")
    assert src.index("_ocr_image_regions(") < src.index("_pn_fix_ocr_in_pdf(")


# ── --fix-leaks ─────────────────────────────────────────────────────────────

def test_fix_leaks_corrects_the_originals_and_the_pdf(tmp_path):
    pdf = tmp_path / "Brief.pdf"
    _scan_doc(["Defendant John Smlth breached the cuve!nants."]).save(pdf)
    td = tmp_path / "Text Files"
    td.mkdir()
    (td / "Brief.txt.LEAK").write_text(
        "====== Page 1 ======\nDefendant John Smlth breached the cuve!nants.\n",
        encoding="utf-8")
    od = tmp_path / ORIG
    od.mkdir()
    (od / "Brief.txt").write_text(
        "====== Page 1 ======\nDefendant John Smlth breached the cuve!nants.\n",
        encoding="utf-8")
    P._cache_original(tmp_path, "Brief",
                      "Defendant John Smlth breached the cuve!nants.\n")
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Pseudonym Key"
    ws.append(["Category", "Real Value", "Replacement", "Status", "Source",
               "Occurrences"])
    ws.append(["person", "Filler Party", "Fake Party", "replaced", "--term", "1"])
    wb.save(tmp_path / "pseudonym_key.xlsx")
    wb2 = openpyxl.Workbook(); w2 = wb2.active; w2.title = "LEAKS"
    w2.append(["File", "Type", "Value", "Where (page:line)", "Fix? (yes/no)",
               "Notes"])
    w2.append(["Brief.txt.LEAK", "REVIEW", "John Smlth", "p.1:1", "*John Smith", ""])
    w2.append(["Brief.txt.LEAK", "REVIEW", "cuve!nants", "p.1:1", "*covenants", ""])
    wb2.save(tmp_path / "LEAKS.xlsx")
    args = types.SimpleNamespace(term=[], key=str(tmp_path / "pseudonym_key.xlsx"))
    P._fix_leaks_mode(tmp_path, args, {}, log)
    with fitz.open(pdf) as doc:
        assert "Defendant John Smith breached the covenants." in \
            doc[0].get_text("text")
    assert not (tmp_path / "Brief_temp.pdf").exists()
    assert "John Smith breached the covenants" in \
        (od / "Brief.txt").read_text(encoding="utf-8")
    # The evidence cache is corrected too — and then DROPPED, as it always is
    # once the folder comes out clean (`_clear_originals_cache`).
    assert not list(P._originals_cache_dir(tmp_path).glob("*.txt"))
    exports = list(td.glob("Brief.txt*"))
    body = exports[0].read_text(encoding="utf-8")
    assert "Smlth" not in body and "cuve!nants" not in body
    assert "John Smith breached the covenants" in body   # unbound: verbatim


def test_fix_leaks_asks_only_about_this_worksheets_fixes():
    src = inspect.getsource(P._fix_leaks_mode)
    assert "_pn_ocr_corrections(terms, registry, loaded=False)" in src
    assert "_pn_fix_ocr_in_folder_pdfs(folder, ocr_corr, log)" in src
    assert "_pn_correct_original_files(folder, cfg, ocr_corr, log)" in src
