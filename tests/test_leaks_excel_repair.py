"""Why Excel offered to repair `LEAKS.xlsx` — the fifth cause, and the first
that is not a cell.

The four before it were all cell CONTENT: a character XML forbids, a cell over
32,767, a value openpyxl typed as a formula, a rich run that loses its
whitespace. This one is the sheet's own furniture. The Fix? column carries a
dropdown, and hangs the explanation of every control word off it as the
validation's input message — text Excel holds to **255** characters, three
orders of magnitude under a cell's limit. Over it, Excel repairs the workbook by
DROPPING the validation: the operator opens the worksheet they are meant to type
decisions into and the one statement of what may be typed is gone, with the
"we found a problem with some content" prompt in front of it.

It arrived the way the others did — nobody added a long string, a feature added
a clause. Documenting `*OTHER VALUE` (the misspelling alias) took the prompt
from 181 characters to 291, and neither openpyxl nor `_pn_xl_verify` says a
word: the file is well-formed and reads back perfectly, which is exactly why
`_pn_xl_audit` exists and exactly where it was blind.

Three things hold it shut. The authored text stays under the limit; every
workbook is cut to Excel's limits at the one save boundary
(`_pn_xl_fit_validations`); and the audit now walks the validations too, so the
sixth cause is a line in `pdf_linker.log` rather than another round of
inference.

Run:  cd PDF-Linker && python3 -m pytest tests/test_leaks_excel_repair.py -v
"""
import logging
import xml.etree.ElementTree as ET
import zipfile

import openpyxl
import pytest

import pdf_linker as P

log = logging.getLogger("test")

_NS = P._PN_XL_NS


def _validations(path):
    """Every `<dataValidation>` of every worksheet in `path`, as elements."""
    out = []
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.startswith("xl/worksheets/") and name.endswith(".xml"):
                out += list(ET.fromstring(z.read(name))
                            .iter(_NS + "dataValidation"))
    return out


def _leaks(tmp_path, value="Rasho"):
    P._pn_write_leak_report(tmp_path, [
        {"file": "Motion.pdf", "type": "name?", "value": value,
         "where": "p.1:14", "notes": "",
         "context": f"The summons was served on {value} at his residence."}],
        log)
    return tmp_path / "LEAKS.xlsx"


def _dv(prompt, title="Fix?", source='"yes,no,never"'):
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = openpyxl.Workbook()
    wb.active.title = P._PN_LEAK_SHEET
    dv = DataValidation(type="list", formula1=source, allow_blank=True)
    dv.showErrorMessage = False
    dv.showInputMessage = True
    dv.promptTitle = title
    dv.prompt = prompt
    wb.active.add_data_validation(dv)
    dv.add("B2:B9")
    return wb


# ── 1. what the worksheet actually ships ────────────────────────────────────

def test_the_dropdown_survives_into_the_written_worksheet(tmp_path):
    """The premise of the whole file: the validation is there to be dropped."""
    dvs = _validations(_leaks(tmp_path))
    assert len(dvs) == 1, dvs
    assert dvs[0].get("promptTitle") == "Fix?"


@pytest.mark.parametrize("attr,cap", [
    ("prompt", P._PN_XL_DV_TEXT_MAX),
    ("promptTitle", P._PN_XL_DV_TITLE_MAX),
])
def test_the_authored_text_is_under_excels_limit(tmp_path, attr, cap):
    """Measured on the FILE, not on the source: the cut at the save boundary is
    the belt, and this is the thing it should never have to do."""
    for dv in _validations(_leaks(tmp_path)):
        assert len(dv.get(attr) or "") <= cap, dv.get(attr)


def test_the_list_source_is_under_the_limit_too(tmp_path):
    for dv in _validations(_leaks(tmp_path)):
        f1 = dv.find(_NS + "formula1")
        assert len(f1.text or "") <= P._PN_XL_DV_LIST_MAX


def test_shortening_it_dropped_no_control_word(tmp_path):
    """The prompt got shorter by losing PROSE. Every control word the Fix?
    column accepts is still named in it, because this text is the only place
    the worksheet says what may be typed."""
    prompt = _validations(_leaks(tmp_path))[0].get("prompt")
    for word in ("yes", "no", "never", "*OTHER VALUE", "[bracket]",
                 "replacement"):
        assert word in prompt, (word, prompt)


def test_the_worksheet_passes_the_audit(tmp_path):
    assert P._pn_xl_audit(_leaks(tmp_path)) == []


# ── 2. the belt: cut at the one save boundary ───────────────────────────────

def test_an_over_long_prompt_is_cut_before_it_reaches_the_file(tmp_path):
    path = tmp_path / "LEAKS.xlsx"
    P._pn_xl_save(_dv("x" * 291), path, "leak-review worksheet")
    dv = _validations(path)[0]
    assert len(dv.get("prompt")) == P._PN_XL_DV_TEXT_MAX
    # Cut, not dropped: what Excel would have thrown away whole survives.
    assert dv.get("prompt").startswith("xxx")


def test_an_over_long_title_is_cut_too(tmp_path):
    path = tmp_path / "LEAKS.xlsx"
    P._pn_xl_save(_dv("short", title="T" * 40), path, "leak-review worksheet")
    assert len(_validations(path)[0].get("promptTitle")) \
        == P._PN_XL_DV_TITLE_MAX


def test_text_within_the_limit_is_left_exactly_alone(tmp_path):
    path = tmp_path / "LEAKS.xlsx"
    P._pn_xl_save(_dv("yes = auto fake · no = leave it here"), path, "sheet")
    assert _validations(path)[0].get("prompt") == \
        "yes = auto fake · no = leave it here"


def test_a_workbook_with_no_validation_still_saves(tmp_path):
    wb = openpyxl.Workbook()
    wb.active["A1"] = "ok"
    P._pn_xl_save(wb, tmp_path / "k.xlsx", "reversal key")
    assert (tmp_path / "k.xlsx").exists()


# ── 3. the witness ──────────────────────────────────────────────────────────
# `_pn_xl_verify` cannot see this — the file is valid XML and openpyxl reads it
# back happily, which is the property every one of these five causes shares.

def test_verify_reads_an_over_long_validation_back_happily(tmp_path):
    path = tmp_path / "raw.xlsx"
    _dv("x" * 291).save(path)           # not _pn_xl_save: the point is the gap
    P._pn_xl_verify(path)               # no raise


@pytest.mark.parametrize("kwargs,expected", [
    ({"prompt": "x" * 291}, "prompt is 291 characters"),
    ({"prompt": "ok", "title": "T" * 40}, "promptTitle is 40 characters"),
    ({"prompt": "ok", "source": '"' + ",".join(["yes"] * 100) + '"'},
     "list source is"),
])
def test_the_audit_names_the_validation_and_the_reason(tmp_path, kwargs,
                                                       expected):
    path = tmp_path / "raw.xlsx"
    _dv(**kwargs).save(path)
    found = P._pn_xl_audit(path)
    assert any(expected in f and P._PN_LEAK_SHEET in f for f in found), found


def test_the_audit_still_sees_the_cell_causes_beside_it(tmp_path):
    """Adding the validation walk must not cost the four it already had."""
    wb = _dv("x" * 291)
    wb.active["A1"] = "carries \x7f a control"
    path = tmp_path / "raw.xlsx"
    wb.save(path)
    found = P._pn_xl_audit(path)
    assert any("control character U+007F" in f for f in found), found
    assert any("prompt is 291 characters" in f for f in found), found
