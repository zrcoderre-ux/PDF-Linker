"""A pre-printed form is read against its own TEMPLATE.

A Judicial Council form has a predetermined layout, and a scan of one hands
the OCR the labels to read afresh — "ATTORNEY OR PARTY WlTHOUT ATTORNEY",
"CASE NUMBFR:". The blank official form says exactly what those labels are, so
where the page is recognised as that form with enough confidence its labels
are restored from the template and the typed VALUES are left as read.

Run:  cd PDF-Linker && python3 -m pytest tests/test_form_templates.py -v
"""
import logging
from pathlib import Path

import pytest

fitz = pytest.importorskip("fitz")

import pdf_linker as P

log = logging.getLogger("test")

FORM = "PLD-PI-001"
FOOTER = f"{FORM} [Rev. January 1, 2007]"
# (label text, x, y) — the pre-printed furniture of the template page.
LABELS = [
    ("ATTORNEY OR PARTY WITHOUT ATTORNEY (Name, State Bar number, and address):", 40, 60),
    ("TELEPHONE NO.:", 40, 120), ("FAX NO. (Optional):", 220, 120),
    ("E-MAIL ADDRESS (Optional):", 40, 140),
    ("ATTORNEY FOR (Name):", 40, 160),
    ("SUPERIOR COURT OF CALIFORNIA, COUNTY OF", 40, 190),
    ("STREET ADDRESS:", 40, 210), ("MAILING ADDRESS:", 40, 230),
    ("CITY AND ZIP CODE:", 40, 250), ("BRANCH NAME:", 40, 270),
    ("PLAINTIFF:", 40, 300), ("DEFENDANT:", 40, 330),
    ("DOES 1 TO", 40, 360), ("COMPLAINT-Personal Injury, Property Damage, Wrongful Death", 40, 390),
    ("CASE NUMBER:", 380, 300), ("Jurisdiction (check all that apply):", 40, 420),
    ("ACTION IS A LIMITED CIVIL CASE", 60, 440),
    ("Amount demanded does not exceed $10,000", 80, 460),
    ("exceeds $10,000, but does not exceed $25,000", 80, 480),
    ("ACTION IS AN UNLIMITED CIVIL CASE (exceeds $25,000)", 60, 500),
    ("Plaintiff (name or names):", 40, 540),
    ("alleges causes of action against defendant (name or names):", 40, 560),
    ("This pleading, including attachments and exhibits, consists of the following number of pages:", 40, 580),
    ("Page 1 of 3", 480, 760),
]
# Field rects — where a VALUE stands, and the words the blank form prints
# inside one (a default) are never labels.
FIELDS = [("AttyName", (40, 70, 400, 110)), ("Phone", (110, 112, 210, 126)),
          ("CaseNo", (380, 310, 560, 326)), ("Party1", (100, 292, 370, 308)),
          ("CrtCounty", (300, 180, 560, 194))]
# The form's checkboxes, each just left of the caption it governs.
BOXES = [(46, 432, 55, 441), (66, 452, 75, 461), (46, 492, 55, 501)]
VALUES = [("Helen Rasho, Esq. (SBN 123456)", 44, 82),
          ("(213) 555-0100", 114, 123), ("25STCV37838", 384, 320),
          ("HELEN RASHO", 104, 304)]
# What the scan's OCR makes of the labels: one slip inside a word, here and
# there, exactly as a fax generation reads them.
MISREADS = {"WITHOUT": "WlTHOUT", "NUMBER:": "NUMBFR:", "TELEPHONE": "TELEPH0NE",
            "SUPERIOR": "SUPER1OR", "COUNTY": "C0UNTY", "attachments": "attachrnents",
            "Jurisdiction": "Jurisdictlon", "DEFENDANT:": "DEFENOANT:"}


def _blank_template(path):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for text, x, y in LABELS:
        page.insert_text((x, y), text, fontsize=8, fontname="helv")
    page.insert_text((40, 775), FOOTER, fontsize=7, fontname="helv")
    for name, rect in FIELDS:
        w = fitz.Widget()
        w.field_name = name
        w.field_type = fitz.PDF_WIDGET_TYPE_TEXT
        w.rect = fitz.Rect(*rect)
        page.add_widget(w)
    for i, rect in enumerate(BOXES):
        w = fitz.Widget()
        w.field_name = f"CheckBox{i}"
        w.field_type = fitz.PDF_WIDGET_TYPE_CHECKBOX
        w.rect = fitz.Rect(*rect)
        page.add_widget(w)
    doc.save(str(path))
    doc.close()


def _library(tmp_path, monkeypatch, name="PLD-PI-001.pdf"):
    lib = tmp_path / "Form Templates"
    lib.mkdir(exist_ok=True)
    _blank_template(lib / name)
    monkeypatch.setenv(P._TEMPLATE_ENV, str(lib))
    monkeypatch.setattr(P, "_TEMPLATE_DIR_OVERRIDE", None)
    P._TEMPLATE_CACHE.clear()
    return lib


def _printed_image(marked, dpi=200, broken=False):
    """The page as PRINTED and scanned: labels, the three checkbox squares,
    an X drawn in each box in `marked`, rendered to a grayscale image. With
    `broken` the squares lose their right edge, as a light scan loses one."""
    v = fitz.open()
    pg = v.new_page(width=612, height=792)
    for text, x, y in LABELS:
        pg.insert_text((x, y), text, fontsize=8, fontname="helv")
    sh = pg.new_shape()
    for i, (x0, y0, x1, y1) in enumerate(BOXES):
        if broken:
            sh.draw_polyline([(x1, y0), (x0, y0), (x0, y1), (x1, y1)])
        else:
            sh.draw_rect(fitz.Rect(x0, y0, x1, y1))
        if i in marked:
            sh.draw_line((x0 + 1.5, y0 + 1.5), (x1 - 1.5, y1 - 1.5))
            sh.draw_line((x0 + 1.5, y1 - 1.5), (x1 - 1.5, y0 + 1.5))
    sh.finish(width=0.8, color=(0, 0, 0))
    sh.commit()
    pix = pg.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    v.close()
    return pix


def _scan(misreads=MISREADS, footer=FOOTER, scale=1.0, dx=0.0, dy=0.0,
          ocr=True, values=VALUES, marked=None, broken=False):
    """A scanned copy: the labels as the OCR read them, INVISIBLE (render
    mode 3) at their printed places, the typed values as visible text, and
    the page marked as read by OCR — under a scale and offset where asked,
    which is what a scanner's feed does to the page. With `marked` given
    the page carries the PICTURE of the printed form too, its boxes drawn
    and those in `marked` crossed, so the ink pass has a raster to read."""
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    if marked is not None:
        page.insert_image(page.rect, pixmap=_printed_image(set(marked), broken=broken))
    for text, x, y in LABELS:
        words = []
        for w in text.split():
            words.append(misreads.get(w, w))
        page.insert_text((x * scale + dx, y * scale + dy), " ".join(words),
                         fontsize=8 * scale, fontname="helv", render_mode=3)
    if footer:
        page.insert_text((40 * scale + dx, 775 * scale + dy), footer,
                         fontsize=7 * scale, fontname="helv", render_mode=3)
    for text, x, y in values:
        page.insert_text((x * scale + dx, y * scale + dy), text,
                         fontsize=9 * scale, fontname="helv")
    if ocr:
        setattr(doc, P._OCR_READ_ATTR, {page.number})
    return doc, page


def _settled(page):
    return P._drop_overdrawn_spans(P._page_text_spans(page), page)


def _texts(spans):
    return " ".join(sp["text"] for sp in spans)


# ── the library ──────────────────────────────────────────────────────────────

def test_the_library_indexes_a_blank_form_by_its_footer(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    pages = P._template_library(log)
    assert len(pages) == 1
    tpl = pages[0]
    assert tpl["form"] == FORM
    assert tpl["revision"] == "january12007"
    assert len(tpl["widgets"]) == len(FIELDS) + len(BOXES)
    assert len(tpl["boxes"]) == len(BOXES)
    keys = {w[0] for w in tpl["words"]}
    assert "without" in keys and "attorney" in keys
    # A word the blank form prints INSIDE a field is a default, not a label.
    assert all(not any(r[0] <= (b[0] + b[2]) / 2 <= r[2]
                       and r[1] <= (b[1] + b[3]) / 2 <= r[3]
                       for r in tpl["widgets"]) for _k, _t, b in tpl["words"])


def test_an_absent_library_is_empty_and_costs_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv(P._TEMPLATE_ENV, str(tmp_path / "nowhere"))
    monkeypatch.setattr(P, "_TEMPLATE_DIR_OVERRIDE", None)
    P._TEMPLATE_CACHE.clear()
    assert P._template_library(log) == []
    doc, page = _scan()
    before = _texts(P._page_text_spans(page))
    assert _texts(_settled(page)) == before


def test_the_setting_and_the_env_var_resolve_the_folder(tmp_path, monkeypatch):
    monkeypatch.delenv(P._TEMPLATE_ENV, raising=False)
    monkeypatch.setattr(P, "_config_path", lambda: tmp_path / "pdf_linker.config")
    P._set_form_templates_dir("")
    assert P._form_templates_dir() == tmp_path / P._TEMPLATE_DIR_NAME
    monkeypatch.setenv(P._TEMPLATE_ENV, str(tmp_path / "env"))
    assert P._form_templates_dir() == tmp_path / "env"
    P._set_form_templates_dir(str(tmp_path / "cfg"))
    assert P._form_templates_dir() == tmp_path / "cfg"
    P._set_form_templates_dir("")


# ── restoration ──────────────────────────────────────────────────────────────

def test_misread_labels_are_restored_and_values_are_not(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    doc, page = _scan()
    raw = _texts(P._page_text_spans(page))
    assert "WlTHOUT" in raw and "NUMBFR" in raw
    out = _texts(_settled(page))
    for bad, good in [("WlTHOUT", "WITHOUT"), ("NUMBFR:", "NUMBER:"),
                      ("TELEPH0NE", "TELEPHONE"), ("SUPER1OR", "SUPERIOR"),
                      ("attachrnents", "attachments"), ("DEFENOANT:", "DEFENDANT:")]:
        assert bad not in out and good in out, (bad, out)
    # The values the filer typed are exactly as read.
    for text, _x, _y in VALUES:
        assert text in out
    rec = getattr(doc, P._TEMPLATE_ATTR)[page.number]
    assert rec["form"] == FORM and rec["labels"] >= 6


def test_a_value_that_reads_like_a_label_is_never_touched(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    # A typed value one slip from a label word, standing INSIDE its field.
    doc, page = _scan(values=VALUES + [("PLAINTIFE", 200, 304)])
    out = _texts(_settled(page))
    assert "PLAINTIFE" in out


def test_a_word_the_template_does_not_carry_stays_as_read(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    doc, page = _scan(values=VALUES + [("Jonh Smlth, a minor", 60, 620)])
    out = _texts(_settled(page))
    assert "Jonh Smlth, a minor" in out


def test_a_shifted_and_scaled_scan_is_still_recognised(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    doc, page = _scan(scale=0.96, dx=14.0, dy=-9.0)
    out = _texts(_settled(page))
    assert "WlTHOUT" not in out and "WITHOUT" in out
    assert "NUMBFR" not in out
    tpl, fit = P._template_recognise(page, P._page_text_spans(page))
    sx, sy, tx, ty = fit
    assert abs(sx - 0.96) < 0.02 and abs(sy - 0.96) < 0.02
    assert abs(tx - 14.0) < 3.0 and abs(ty + 9.0) < 3.0


def test_every_renderer_reads_the_restored_label(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    doc, page = _scan()
    visual = P._page_visual_text(page) or ""
    detect = P._page_detect_text(page)
    assert "WITHOUT" in visual and "WlTHOUT" not in visual
    assert "WITHOUT" in detect and "WlTHOUT" not in detect


def test_the_export_banner_says_what_was_restored(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    doc, page = _scan()
    pdf = tmp_path / "Complaint.pdf"
    doc.save(str(pdf))
    doc.close()
    d = fitz.open(str(pdf))
    setattr(d, P._OCR_READ_ATTR, {0})
    assert P._write_text_version(pdf, d, log)
    text = (tmp_path / "Text Files" / "Complaint.txt").read_text(encoding="utf-8")
    assert f"RESTORED from the {FORM} form template" in text
    assert "WlTHOUT" not in text and "WITHOUT" in text
    d.close()


# ── the gate ─────────────────────────────────────────────────────────────────

def test_a_page_with_no_form_id_is_left_alone(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    doc, page = _scan(footer="")
    out = _texts(_settled(page))
    assert "WlTHOUT" in out


def test_a_different_form_id_is_left_alone(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    doc, page = _scan(footer="CIV-100 [Rev. January 1, 2007]")
    assert "WlTHOUT" in _texts(_settled(page))


def test_a_scan_that_misreads_the_form_id_is_still_recognised(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    doc, page = _scan(footer="PLD-Pl-001 [Rev. January 1, 2007]")
    assert "WlTHOUT" not in _texts(_settled(page))


def test_a_different_revision_is_left_alone(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    doc, page = _scan(footer=f"{FORM} [Rev. July 1, 2016]")
    assert "WlTHOUT" in _texts(_settled(page))


def test_a_revision_the_scan_cannot_read_is_not_held_against_it(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    doc, page = _scan(footer=f"{FORM} [Rev. J~nu%ry 1, 2007]")
    assert "WlTHOUT" not in _texts(_settled(page))


def test_a_born_digital_page_is_never_fitted(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    doc, page = _scan(ocr=False)
    assert "WlTHOUT" in _texts(_settled(page))
    assert page.number not in getattr(doc, P._TEMPLATE_ATTR, {})


def test_too_few_matching_labels_refuse_the_fit(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    # A page that names the form in its footer but carries other text.
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    for i in range(20):
        page.insert_text((40, 60 + 20 * i), f"Paragraph {i} of a declaration "
                         f"about WlTHOUT and NUMBFR: things", fontsize=8,
                         fontname="helv", render_mode=3)
    page.insert_text((40, 775), FOOTER, fontsize=7, fontname="helv", render_mode=3)
    setattr(doc, P._OCR_READ_ATTR, {page.number})
    assert "WlTHOUT" in _texts(_settled(page))


def test_a_scan_garbled_past_recognition_is_left_alone(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    # Every label word mangled: nothing exact to anchor a fit on.
    garble = {}
    for text, _x, _y in LABELS:
        for w in text.split():
            garble[w] = "".join(chr(((ord(c) - 33 + 7) % 90) + 33) for c in w)
    doc, page = _scan(misreads=garble)
    before = _texts(P._page_text_spans(page))
    assert _texts(_settled(page)) == before


def test_the_slip_rule_is_a_third_of_the_word():
    assert P._template_word_slip("wlthout", "without")
    assert P._template_word_slip("numbfr", "number")
    assert P._template_word_slip("no", "no")
    assert not P._template_word_slip("plaintiff", "defendant")
    assert P._template_word_slip("dates", "rates")      # one slip, admitted
    # The confusable pairs are ONE slip: "rn" for "m", a digit for its letter.
    assert P._template_word_slip("whorn", "whom")
    assert P._template_word_slip("frorn", "from")
    assert P._template_word_slip("c0unty", "county")
    assert not P._template_word_slip("ab", "cd")


def test_the_config_names_the_setting():
    keys = [k for k, _b in P._CONFIG_BLOCKS]
    assert "form_templates" in keys
    live = P._config_live(P._CONFIG_TEMPLATE)
    assert live["form_templates"] == ""


# ── the form's own boxes and fields ─────────────────────────────────────────

def test_a_letter_suffix_is_part_of_the_form_id():
    assert P._PN_FORM_ID_RE.match("POS-040(P)")
    assert P._PN_FORM_ID_RE.match("PLD-PI-001(1)")
    assert P._template_form_key("POS-040(P)") != P._template_form_key("POS-040(D)")
    assert P._template_form_key("PLD-Pl-001") == P._template_form_key("PLD-PI-001")


def test_a_new_form_states_its_revision_with_new(tmp_path, monkeypatch):
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((40, 775), "POS-040(D) [New January 1, 2005]", fontsize=7)
    assert P._template_revision(page) == "january12005"


def test_a_field_is_classified_by_its_name():
    cls = P._template_field_class
    assert cls("JUD-100[0].Page1[0].P1Caption[0].AttyInfo[0].AttyName[0]") == "name"
    assert cls("topmostSubform[0].Page1[0].PersonServed_ft[3]") == "name"
    assert cls("JUD-100[0].Page1[0].P1Caption[0].TitlePartyName[0].Party1[0]") == "name"
    assert cls("JUD-100[0].Page1[0].P1Caption[0].AttyInfo[0].AttyFor[0]") == "name"
    assert cls("JUD-100[0].Page1[0].P1Caption[0].AttyInfo[0].AttyFirm[0]") == "name"
    assert cls("topmostSubform[0].Page1[0].CaseNumber_ft[0]") == "case_number"
    assert cls("JUD-100[0].Page1[0].P1Caption[0].AttyInfo[0].AttyBarNo_dc[0]") == "contact"
    assert cls("JUD-100[0].Page1[0].P1Caption[0].AttyInfo[0].Phone[0]") == "contact"
    assert cls("JUD-100[0].Page1[0].P1Caption[0].CourtInfo[0].CrtCounty[0]") == "court"
    assert cls("JUD-100[0].Page1[0].P1Caption[0].CourtInfo[0].Street[0]") == "contact"
    assert cls("JUD-100[0].Page1[0].List3[0].Lia[0].FillText10[0]") is None
    assert cls("JUD-100[0].Page2[0].List6[0].Lia[0].Table1[0].EXPN[0]") is None


def test_the_values_typed_into_the_form_are_read_by_field(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    doc, page = _scan(values=VALUES + [("LOS ANGELES", 304, 191)])
    got = {name: (cls, text) for cls, name, text in P._template_field_values(page)}
    assert got["AttyName"] == ("name", "Helen Rasho, Esq. (SBN 123456)")
    assert got["Party1"] == ("name", "HELEN RASHO")
    assert got["CaseNo"] == ("case_number", "25STCV37838")
    assert got["Phone"][0] == "contact"
    assert got["CrtCounty"] == ("court", "LOS ANGELES")


def test_a_name_field_registers_its_value_as_a_party(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    doc, page = _scan(values=VALUES + [("LOS ANGELES", 304, 191)])
    values = P._template_field_values(page)
    reg = P._PnFakeRegistry()
    pz = P.Pseudonymizer([], {}, registry=reg)
    n = pz.register_form_fields(values)
    reals = {t.real.lower() for t in pz.terms}
    assert "helen rasho" in reals
    assert n >= 1
    # The court's county is the venue and is never a party; a docket is not
    # a name; a one-word value clears no screen.
    assert "los angeles" not in reals and "25stcv37838" not in reals
    assert pz.register_form_fields([("name", "Party1", "ACME")]) == 0
    # A short title is two parties.
    pz2 = P.Pseudonymizer([], {}, registry=P._PnFakeRegistry())
    pz2.register_form_fields([("name", "Party_ft", "HELEN RASHO v. QUILLMARK BUILDERS LLC")])
    reals2 = {t.real.lower() for t in pz2.terms}
    assert "helen rasho" in reals2 and "quillmark builders llc" in reals2


def test_checkbox_states_are_read_at_the_templates_box_positions(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    doc, page = _scan(marked={1})
    got = P._ink_form_cells(page)
    assert got is not None
    cells, boxes, marked, unsure, exact, _consumed = got
    assert (boxes, marked, unsure) == (3, 1, 0)
    assert exact is False                      # read off the raster, and said
    states = sorted((round(y), t) for y, _h, _x, t in cells if t in ("[X]", "[ ]", "[?]"))
    assert [t for _y, t in states] == ["[ ]", "[X]", "[ ]"]
    # Laid where the printed box is: the raster's own measurement of it.
    for (y, _t), (_x0, y0, _x1, y1) in zip(states, BOXES):
        assert abs(y - (y0 + y1) / 2) <= 2
    rec = getattr(doc, P._TEMPLATE_ATTR)[page.number]
    assert rec["boxes"] == 3
    render = P._form_page_render(page)
    assert render is not None and render["boxes"] == 3
    assert "[X] Amount demanded does not exceed $10,000" in render["text"]


def test_the_banner_names_the_boxes_read_from_the_template(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    doc, page = _scan(marked={0, 2})
    pdf = tmp_path / "Complaint.pdf"
    doc.save(str(pdf))
    doc.close()
    d = fitz.open(str(pdf))
    setattr(d, P._OCR_READ_ATTR, {0})
    assert P._write_text_version(pdf, d, log)
    text = (tmp_path / "Text Files" / "Complaint.txt").read_text(encoding="utf-8")
    assert f"3 checkbox state(s) were read at the {FORM} form template's own box positions" in text
    assert "[X] ACTION IS A LIMITED CIVIL CASE" in text
    assert "[X] ACTION IS AN UNLIMITED CIVIL CASE" in text
    assert "[ ] Amount demanded does not exceed $10,000" in text
    d.close()


def test_a_box_whose_border_the_scan_broke_is_still_read(tmp_path, monkeypatch):
    _library(tmp_path, monkeypatch)
    doc, page = _scan(marked={2}, broken=True)
    cells, boxes, marked, unsure, exact, _consumed = P._ink_form_cells(page)
    assert (boxes, marked, unsure) == (3, 1, 0)
    states = [t for _y, _h, _x, t in sorted(cells) if t in ("[X]", "[ ]", "[?]")]
    assert states == ["[ ]", "[ ]", "[X]"]


def test_a_misread_form_id_still_names_the_form(tmp_path, monkeypatch):
    assert P._template_form_key("P0S-O40(P)") == P._template_form_key("POS-040(P)")
    assert P._template_form_key("PLD-Pl-0O1") == P._template_form_key("PLD-PI-001")
    _library(tmp_path, monkeypatch)
    doc, page = _scan(footer="P1D-PI-0O1 [Rev. January 1, 2007]")
    assert P._form_page_number(page) == ""            # the strict gate refuses it
    assert P._template_footer_key(page) == P._template_form_key(FORM)
    assert "WlTHOUT" not in _texts(_settled(page))


def test_the_default_folder_is_created_beside_the_config(tmp_path, monkeypatch):
    monkeypatch.delenv(P._TEMPLATE_ENV, raising=False)
    monkeypatch.setattr(P, "_config_path", lambda: tmp_path / "pdf_linker.config")
    P._set_form_templates_dir("")
    assert P._ensure_form_templates_dir(log) is True
    assert (tmp_path / P._TEMPLATE_DIR_NAME).is_dir()
    assert P._ensure_form_templates_dir(log) is False      # already there
    # A folder the operator NAMED is never made for them.
    P._set_form_templates_dir(str(tmp_path / "elsewhere"))
    assert P._ensure_form_templates_dir(log) is False
    assert not (tmp_path / "elsewhere").exists()
    P._set_form_templates_dir("")


def test_an_information_sheet_is_a_form_with_a_suffix():
    """MC-013-INFO is footed and filed beside the form it explains, and the
    id shapes refused its suffix: no template page indexed, and nothing
    saying the id was never a value to fake. The suffix is admitted whole
    and stays bounded, so a longer word behind the hyphen is no id."""
    assert P._PN_FORM_ID_RE.match("MC-013-INFO")
    assert P._pn_is_never_fake("MC-013-INFO")
    m = P._JC_FORM_NO_RE.search("MC-013-INFO, Page 1 of 3")
    assert m and m.group(1) == "MC-013-INFO"
    assert P._TEMPLATE_LOOSE_ID_RE.search("MC-O13-INFO, Page 2 of 3")
    assert P._template_form_key("MC-O13-INFO") == P._template_form_key("MC-013-INFO")
    assert not P._JC_FORM_NO_RE.search("MC-013-INFORMATION")
    assert not P._PN_FORM_ID_RE.match("MC-013-INFORMATION")
    assert P._JC_FORM_NO_RE.search("MC-013, Page 1").group(1) == "MC-013"


def test_every_committed_blank_indexes_as_a_template():
    """The repo carries the official blanks in `Form Templates/`, and every
    one of them must yield at least one template page — a blank the library
    cannot key is a file the operator committed for nothing."""
    import logging
    folder = Path(P.__file__).resolve().parent / "Form Templates"
    pdfs = sorted(folder.glob("*.pdf"))
    assert len(pdfs) >= 39
    keyed = set()
    for pdf in pdfs:
        doc = fitz.open(pdf)
        keys = {P._template_footer_key(pg) for pg in doc}
        keys.discard("")
        assert keys, pdf.name
        keyed |= keys
    assert "mc013info" in keyed
    assert "jud100" in keyed
