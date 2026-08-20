"""The pseudonym key and the LEAKS worksheet each carry TWO Context columns,
at the owner's direction: the ORIGINAL sentence at column C and the export's
own sentence ("Scrubbed Context") at column D — what the document said beside
what the deliverable now says.

On the key the second column is searched by the FAKE (the real value is no
longer in that text) and bolds it; on the worksheet the flagged value stands
verbatim in both bodies, so both quotes are searched — and bolded — by the
value. Both columns carry forward from the key on disk, exactly as the first
always has, and every reader resolves them by header NAME.

Run:  cd PDF-Linker && python3 -m pytest tests/test_dual_context.py -v
"""
import logging

import openpyxl
import pytest

import pdf_linker as P

log = logging.getLogger("test")


def _pz(names=("Roxane Estrada",)):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    return P.Pseudonymizer(terms, det, registry=reg)


ORIGINAL = ("====== Page 1 ======\n"
            " 1  The process server handed the summons to Roxane Estrada at\n"
            " 2  her residence in Van Nuys on the fourth of July.\n")


def _key_cells(path):
    # BOTH sheets: a binding no export carries lives on the pinned one, and a
    # re-run that matched nothing moves every row there.
    wb = openpyxl.load_workbook(path)
    hdr, out = None, []
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        hdr = hdr or [str(h) for h in rows[0]]
        out.extend(rows[1:])
    return hdr, out


class TestKeyColumns:
    def _written(self, tmp_path):
        z = _pz()
        scrubbed = z.apply(ORIGINAL)
        z.note_key_context(ORIGINAL, scrubbed)
        key = tmp_path / "pseudonym_key.xlsx"
        z.write_key(key, log)
        return z, scrubbed, _key_cells(key)

    def test_original_at_c_then_scrubbed_then_replacement(self, tmp_path):
        _z, _s, (hdr, _rows) = self._written(tmp_path)
        assert hdr[2] == "Context" and hdr[3] == "Scrubbed Context"
        assert hdr.index("Replacement") > hdr.index("Scrubbed Context")

    def test_the_two_quotes_show_the_two_texts(self, tmp_path):
        z, scrubbed, (hdr, rows) = self._written(tmp_path)
        cx, sx = hdr.index("Context"), hdr.index("Scrubbed Context")
        rp = hdr.index("Replacement")
        row = next(r for r in rows if str(r[1]) == "Roxane Estrada")
        fake = str(row[rp])
        assert "Roxane Estrada" in str(row[cx])       # the document's sentence
        assert fake in str(row[sx])                   # the export's sentence
        assert "Roxane Estrada" not in str(row[sx])
        assert fake in scrubbed                       # and it really is there

    def test_the_scrubbed_quote_is_carried_forward(self, tmp_path):
        _z, _s, _cells = self._written(tmp_path)
        z2 = _pz()
        nothing = "Nothing relevant here."
        z2.note_key_context(nothing, z2.apply(nothing))
        z2.write_key(tmp_path / "pseudonym_key.xlsx", log)
        hdr, rows = _key_cells(tmp_path / "pseudonym_key.xlsx")
        sx = hdr.index("Scrubbed Context")
        row = next(r for r in rows if str(r[1]) == "Roxane Estrada")
        assert row[sx], "the scrubbed quote was lost on the re-run"

    def test_the_scrubbed_quote_bolds_the_fake(self, tmp_path):
        z = _pz()
        scrubbed = z.apply(ORIGINAL)
        z.note_key_context(ORIGINAL, scrubbed)
        key = tmp_path / "pseudonym_key.xlsx"
        z.write_key(key, log)
        wb = openpyxl.load_workbook(key, rich_text=True)
        hdr = [str(c.value) for c in wb.active[1]]
        sx, rp = hdr.index("Scrubbed Context"), hdr.index("Replacement")
        for r in wb.active.iter_rows(min_row=2):
            if str(r[1].value) == "Roxane Estrada":
                cell = r[sx].value
                bolded = "".join(
                    str(part) for part in cell
                    if getattr(getattr(part, "font", None), "b", False))
                assert str(r[rp].value).split()[0] in bolded
                return
        pytest.fail("no row for the party")


class TestLeaksColumn:
    def test_worksheet_carries_both_quotes(self, tmp_path, monkeypatch):
        pz = _pz()
        src_text = ("Ashely attended the deposition of Roxane Estrada. "
                    "The parties met afterwards.")
        monkeypatch.setattr(pz, "surviving_reals", lambda body: {"Ashely"})
        src = tmp_path / "Letter.docx"
        src.write_bytes(b"")
        assert P._write_word_text_version(src, src_text, log, pz)
        fake = pz.apply("Roxane Estrada")
        row = next(r for r in pz.leak_report if r["value"] == "Ashely")
        assert "Roxane Estrada" in row["context"]            # the original
        assert fake in row["scrubbed_context"]               # the export
        P._pn_write_leak_report(tmp_path, pz.leak_report, log)
        wb = openpyxl.load_workbook(P._pn_leak_xlsx_path(tmp_path))
        hdr = [str(c.value) for c in wb.active[1]]
        assert hdr[2] == "Context" and hdr[3] == "Scrubbed Context"
        body = next(r for r in wb.active.iter_rows(min_row=2, values_only=True)
                    if str(r[0]) == "Ashely")
        assert "Roxane Estrada" in str(body[2])
        assert fake in str(body[3])
