"""The text reader (pdf-viewer's viewer/text-reader.html) answers LEAKS.xlsx
by rewriting the worksheet's Fix? cells IN PLACE: every other part of the
workbook is copied through byte for byte and each decided cell is written
as an INLINE STRING (``t="inlineStr"``), never a shared string and never a
formula. This pins that ``_pn_read_leak_decisions`` reads such a cell
exactly as it reads one typed in Excel — the contract the reader writes
against — on a workbook rebuilt the way the reader rebuilds it (zipfile,
the one sheet part edited by hand), so the check does not depend on
openpyxl's own writer having produced the cell."""
import re
import zipfile

import openpyxl

import pdf_linker as P


def _reader_edits(path, cells):
    """Rewrite `path` as the reader does: the LEAKS sheet's XML edited by
    reference, every other zip entry copied through; `cells` is
    {"B2": "text"}."""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        parts = {n: z.read(n) for n in names}
    # The LEAKS sheet is the workbook's first sheet here.
    sheet = "xl/worksheets/sheet1.xml"
    xml = parts[sheet].decode("utf-8")
    for ref, text in cells.items():
        esc = (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        new = (f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">'
               f'{esc}</t></is></c>' if text else f'<c r="{ref}"/>')
        pat = re.compile(rf'<c r="{ref}"(?:\s[^>]*)?(?:/>|>.*?</c>)', re.S)
        assert pat.search(xml), ref
        xml = pat.sub(new, xml, count=1)
    parts[sheet] = xml.encode("utf-8")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n in names:
            z.writestr(n, parts[n])


def test_inline_string_fix_cells_read_as_typed(tmp_path):
    xlsx = tmp_path / "LEAKS.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = P._PN_LEAK_SHEET
    ws.append(list(P._PN_LEAK_HEADERS))
    for value in ("Helen Rasho", "Vazqez", "Smlth", "Cross River Bank",
                  "Alder Law, P.C.", "Marcus Delacroix", "Owen Blakely"):
        ws.append([value, "", "ctx", "MTC.pdf", "LEAK", "p.2:7", ""])
    wb.save(xlsx)
    _reader_edits(xlsx, {
        "B2": "no", "B3": "~Vazquez", "B4": "*Smith", "B5": "phrase",
        "B6": "[Law]", "B7": "=Marcus Delacroy",   # the old alias mark: text, not a formula
        "B8": "never",
    })
    d = P._pn_read_leak_decisions(tmp_path)
    assert d["helen rasho"]["fix"] == "no"
    assert d["vazqez"]["fix"] == "yes" and d["vazqez"]["alias"] == "Vazquez"
    assert d["smlth"]["fix"] == "yes" and d["smlth"]["ocr_fix"] == "Smith"
    assert d["cross river bank"]["fix"] == "yes" and d["cross river bank"]["phrase"]
    assert d["alder law, p.c."]["fix"] == "yes"
    assert d["alder law, p.c."]["fake_values"] and \
        all("Law" not in f for f in d["alder law, p.c."]["fake_values"])
    # An inline string opening with "=" is the alias it says, not "#NAME?".
    assert d["marcus delacroix"]["alias"] == "Marcus Delacroy"
    assert d["owen blakely"]["fix"] == "no"
    assert d["owen blakely"]["fixcell"] == P._PN_NEVER_CONTROL
    # The worksheet still reads as ours: the sheet by name, the header row whole.
    assert not P._pn_triage_pending(tmp_path, "Text Files")


def test_a_cleared_inline_cell_is_undecided(tmp_path):
    xlsx = tmp_path / "LEAKS.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = P._PN_LEAK_SHEET
    ws.append(list(P._PN_LEAK_HEADERS))
    ws.append(["Helen Rasho", "yes", "ctx", "MTC.pdf", "LEAK", "p.2:7", ""])
    wb.save(xlsx)
    _reader_edits(xlsx, {"B2": ""})
    d = P._pn_read_leak_decisions(tmp_path)
    assert d["helen rasho"]["fix"] == ""
    assert P._pn_triage_pending(tmp_path, "Text Files")
