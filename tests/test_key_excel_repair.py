"""Why Excel kept offering to REPAIR `pseudonym_key.xlsx`, in three parts.

A repaired workbook is not a cosmetic complaint. Excel repairs by DROPPING what
it could not parse, and what it drops is reversal rows — so the symptom the
operator reports as "Excel had to fix the key" is the failure this project ranks
above a leak: a pseudonym standing in a delivered export with nothing left to
undo it.

1. THE CHARACTERS openpyxl LETS THROUGH. Its own filter covers the C0 controls
   and stops there, but XML 1.0 also forbids the surrogates and U+FFFE/U+FFFF.
   openpyxl writes those verbatim and the sheet XML that comes out is not
   well-formed at all — no reader can parse it, Excel included. The key's
   Context column quotes the UNSCRUBBED body, which carries the garbled text
   layer of every page with a broken encoding, so this is exactly the text that
   produces them.

2. THE LENGTH openpyxl STOPS CHECKING. It truncates an over-long cell for you in
   `Cell._bind_value` — and skips that step entirely for a `CellRichText`, which
   is precisely what the Context column is. Nothing else stood between a quote
   and Excel's 32,767-character cell.

3. THE WRITE THAT WAS NOT ATOMIC. `wb.save(path)` truncates the destination and
   then streams a zip into it. Anything that kills the process in that window —
   an out-of-memory kill on a big folder, a full disk, a sync client in a case
   folder that is by design synced — leaves a truncated zip WHERE THE KEY USED
   TO BE. `_pn_xl_save` writes beside it, reads it back, and only then replaces,
   so a key that cannot be opened is never the one on disk.

Run:  cd PDF-Linker && python3 -m pytest tests/test_key_excel_repair.py -v
"""
import logging
import xml.etree.ElementTree as ET
import zipfile

import openpyxl
import pytest

import pdf_linker as P

log = logging.getLogger("test")

# A lone surrogate half, and the two non-characters. Each is legal in a Python
# str, illegal in XML, and invisible to openpyxl's own filter.
SURROGATE = "\ud800"
NONCHARS = "￾￿"


def _pz(names):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    return P.Pseudonymizer(terms, list(P._PN_DEFAULT_DETECTORS), registry=reg)


def _sheet_xml(path):
    """Every worksheet part of `path`, as raw bytes."""
    with zipfile.ZipFile(path) as z:
        return [z.read(n) for n in z.namelist()
                if n.startswith("xl/worksheets/") and n.endswith(".xml")]


# ── 1. the characters openpyxl lets through ─────────────────────────────────

def test_openpyxls_own_filter_does_not_cover_them():
    """The reason `_PN_XL_BAD_CHARS_RE` has to exist at all.

    If openpyxl ever widens its filter this test fails, which is the moment to
    reconsider ours — not a reason to drop it silently.
    """
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    for ch in SURROGATE + NONCHARS:
        assert ILLEGAL_CHARACTERS_RE.sub("", ch) == ch


@pytest.mark.parametrize("ch", list(SURROGATE + NONCHARS))
def test_xl_text_strips_what_xml_forbids(ch):
    assert P._pn_xl_text(f"a{ch}b") == "ab"


@pytest.mark.parametrize("ch", ["�", "\t", "\n", "﷐", "\U0001fffe"])
def test_xl_text_keeps_what_xml_allows(ch):
    """Stripping more than XML forbids would quietly edit the document's text.

    U+FFFD is what a mangled decode leaves behind, U+FDD0 and the plane-end
    non-characters are legal `Char`s, and a tab is real layout. All are kept.
    """
    assert P._pn_xl_text(f"a{ch}b") == f"a{ch}b"


def test_the_key_is_well_formed_xml_with_such_a_value(tmp_path):
    """The end-to-end shape: a garbled page puts one of these in a tracked value
    AND in the sentence the key quotes for it. Before the strip, the sheet part
    would not parse — which is Excel's repair prompt, from the other side."""
    bad = f"EQUITY-WALTON_0007{SURROGATE} - HOIISING{NONCHARS}COMM"
    z = _pz(["Helen Rasho"])
    z.records[("identifier", bad.lower())] = {
        "category": "identifier", "real": bad, "fake": "DEAL-0001",
        "source": "prescan", "count": 3, "pattern": "x", "flags": 0}
    src = f"====== Page 1 ======\n 1  Helen Rasho signed {bad} today.\n"
    z.apply(src)
    z.note_key_context(src)

    key = tmp_path / "pseudonym_key.xlsx"
    z.write_key(key, log)

    parts = _sheet_xml(key)
    assert parts
    for part in parts:                       # used to raise: not well-formed
        ET.fromstring(part)
    rows = [r for ws in openpyxl.load_workbook(key).worksheets
            for r in ws.iter_rows(min_row=2, values_only=True) if r[1]]
    # The BINDING survives — the strip loses invisible characters, not the row.
    kept = [r[1] for r in rows if "EQUITY-WALTON" in str(r[1])]
    assert kept, rows
    assert not (set(SURROGATE + NONCHARS) & set(kept[0]))


def test_the_leaks_worksheet_is_well_formed_too(tmp_path):
    # Same sanitizer, same quote-from-the-original column, so the same hazard.
    bad = f"HOIISING{SURROGATE}COMM"
    P._pn_write_leak_report(tmp_path, [
        {"file": "M.pdf", "type": "name?", "value": bad, "where": "p.1:1",
         "context": f"The stamp reads {bad} on every page.", "notes": ""}], log)
    for part in _sheet_xml(tmp_path / "LEAKS.xlsx"):
        ET.fromstring(part)


# ── 2. the length openpyxl stops checking ───────────────────────────────────

def test_a_rich_text_cell_is_cut_to_excels_limit():
    """openpyxl truncates a plain string and NOT a `CellRichText`, so the cap
    has to be applied where both kinds of cell pass."""
    quote = "Rasho " + "x" * 60000
    cell = P._pn_rich_context(quote, "Rasho")
    assert len("".join(str(part) for part in cell)) == P._PN_XL_CELL_MAX


def test_an_over_long_quote_still_writes_a_readable_key(tmp_path):
    z = _pz(["Helen Rasho"])
    z.apply("Helen Rasho signed it.")
    z._key_context = {"helen rasho": "Helen Rasho " + "x" * 60000}
    key = tmp_path / "pseudonym_key.xlsx"
    z.write_key(key, log)
    for ws in openpyxl.load_workbook(key).worksheets:
        for row in ws.iter_rows(min_row=2, values_only=True):
            for cell in row:
                assert not isinstance(cell, str) or len(cell) <= P._PN_XL_CELL_MAX


# ── 3. the write that was not atomic ────────────────────────────────────────

def _one_row_workbook(text="ok"):
    wb = openpyxl.Workbook()
    wb.active.append([text])
    return wb


def test_a_save_that_fails_leaves_the_previous_key_standing(tmp_path, monkeypatch):
    key = tmp_path / "pseudonym_key.xlsx"
    _one_row_workbook("the good key").save(key)
    before = key.read_bytes()

    monkeypatch.setattr(P, "_pn_xl_verify",
                        lambda p: (_ for _ in ()).throw(ValueError("boom")))
    with pytest.raises(OSError):
        P._pn_xl_save(_one_row_workbook("the bad key"), key, "reversal key")

    assert key.read_bytes() == before
    assert not list(tmp_path.glob("*.tmp.xlsx")), "the temp file was left behind"


def test_write_key_leaves_the_old_key_and_raises(tmp_path, monkeypatch):
    """`write_key` does not swallow it: both call sites answer with
    `_PN_KEY_LOST_MSG`, which is the one message a run cannot afford to soften.
    """
    key = tmp_path / "pseudonym_key.xlsx"
    _one_row_workbook("the good key").save(key)
    before = key.read_bytes()

    monkeypatch.setattr(P, "_pn_xl_verify",
                        lambda p: (_ for _ in ()).throw(ValueError("boom")))
    z = _pz(["Helen Rasho"])
    z.apply("Helen Rasho signed it.")
    with pytest.raises(OSError):
        z.write_key(key, log)
    assert key.read_bytes() == before


def test_verify_rejects_a_truncated_workbook(tmp_path):
    """What an out-of-memory kill or a full disk leaves behind mid-`save`."""
    good = tmp_path / "good.xlsx"
    _one_row_workbook().save(good)
    cut = tmp_path / "cut.xlsx"
    cut.write_bytes(good.read_bytes()[:len(good.read_bytes()) // 2])
    with pytest.raises(Exception):
        P._pn_xl_verify(cut)


def test_verify_accepts_what_the_tool_writes(tmp_path):
    z = _pz(["Helen Rasho"])
    src = "====== Page 1 ======\n 1  Helen Rasho signed it today.\n"
    z.apply(src)
    z.note_key_context(src)
    key = tmp_path / "pseudonym_key.xlsx"
    z.write_key(key, log)
    P._pn_xl_verify(key)                     # the key's own sheets, walked


def test_the_temp_file_keeps_the_real_extension(tmp_path, monkeypatch):
    """A plain ".tmp" cannot be re-opened — openpyxl refuses the suffix — so
    every save would have reported itself broken on the name alone."""
    seen = []
    real_save = openpyxl.Workbook.save

    def spy(self, path):
        seen.append(str(path))
        return real_save(self, path)

    monkeypatch.setattr(openpyxl.Workbook, "save", spy)
    P._pn_xl_save(_one_row_workbook(), tmp_path / "pseudonym_key.xlsx", "key")
    assert seen and seen[0].endswith(".xlsx"), seen
    assert (tmp_path / "pseudonym_key.xlsx").exists()
    assert not list(tmp_path.glob("*.tmp.xlsx"))
