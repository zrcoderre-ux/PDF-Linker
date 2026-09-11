"""
`New Real Values.txt`: names the operator flagged in the text reader (the
pdf-viewer repo's viewer/text-reader.html), one per line in the CASE FOLDER,
read by every run in that folder — the full run and `--fix-leaks` alike — as
if each had been typed as a `--term`. The reader shows the scrubbed exports
with the real names put back on screen from the key and every pseudonym
marked, so the unmarked name is the one the run missed; this file is how that
sighting reaches the next pass. The same file carries the reader's KEEPS —
`no: VALUE` / `never: VALUE` for a value the run faked that should have been
left alone (a cited decision's name) — read as the worksheet's own decisions.

Run:  cd PDF-Linker && python3 -m pytest tests/test_new_real_values.py -v
"""
import importlib.util
import logging
import sys
import zipfile
from pathlib import Path

import openpyxl

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)

log = logging.getLogger("test")
NAME = pl._NEW_REAL_VALUES_FILE
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _docx(path, text):
    body = f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
    doc = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<w:document xmlns:w="{_W}"><w:body>{body}</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", doc)
    return path


# ── the reader ───────────────────────────────────────────────────────────────

def test_the_name_has_spaces_and_no_underscores():
    assert NAME == "New Real Values.txt"


def test_no_file_is_no_values(tmp_path):
    assert pl._pn_read_new_real_values(tmp_path, log) == []


def test_comments_blanks_bom_and_duplicates(tmp_path):
    (tmp_path / NAME).write_text(
        "﻿# New Real Values — written by the text reader.\n"
        "# one per line\n"
        "\n"
        "  Rosa   Delgado \n"
        "rosa delgado\n"
        "Sunbelt Rentals LLC\n"
        "#Not A Value\n",
        encoding="utf-8")
    assert pl._pn_read_new_real_values(tmp_path, log) == [
        "Rosa Delgado", "Sunbelt Rentals LLC"]


def test_it_is_never_an_export(tmp_path):
    # Under the older single-folder layout the case folder's .txt files are
    # read as exports; this one is a list of REAL names and must never be
    # scrubbed, quarantined, or folded into a combined file.
    assert pl._is_tool_txt_artifact(tmp_path / NAME)
    assert not pl._is_tool_txt_artifact(tmp_path / "Brief.txt")


# ── end to end ───────────────────────────────────────────────────────────────

def _run_main(folder, monkeypatch, *extra):
    monkeypatch.setattr(sys, "argv", ["pdf_linker.py", str(folder), *extra])
    try:
        pl.main()
    except SystemExit as e:
        return e.code
    return 0


def _key_rows(folder):
    wb = openpyxl.load_workbook(folder / "pseudonym_key.xlsx")
    rows = []
    for ws in wb.worksheets:
        rows += list(ws.iter_rows(min_row=2, values_only=True))
    return [r for r in rows if any(c is not None for c in r)]


def test_a_flagged_value_is_scrubbed_on_the_next_run(tmp_path, monkeypatch):
    folder = tmp_path / "Smith v Jones"
    folder.mkdir()
    _docx(folder / "Filing.docx",
          "The tenant Rosa Delgado signed the lease on the first of March.")
    (folder / NAME).write_text("# flagged in the text reader\nRosa Delgado\n",
                               encoding="utf-8")
    assert _run_main(folder, monkeypatch, "--pseudonymize") == 0
    export = (folder / "Text Files" / "Filing.txt").read_text(encoding="utf-8")
    assert "Rosa Delgado" not in export and "Delgado" not in export
    assert "signed the lease" in export
    # …and the binding is in the key as the operator's own instruction,
    # reversible like any other.
    rows = _key_rows(folder)
    reals = {str(r[1]) for r in rows}
    assert "Rosa Delgado" in reals
    src = next(r for r in rows if str(r[1]) == "Rosa Delgado")
    assert "--term" in [str(c) for c in src]
    # …and the list is CONSUMED, like the worksheet it is the reader's
    # counterpart to: the key now carries the binding, so a file still
    # sitting there would read as names still to scrub — and the reader
    # would show the flags again over text that already carries the
    # stand-in.
    assert not (folder / NAME).exists()


def test_fix_leaks_reads_it_too(tmp_path, monkeypatch):
    # The pass the operator clicks after reading: a value flagged in an export
    # is cured in the .txt with no PDF reopened.
    folder = tmp_path / "Smith v Jones"
    folder.mkdir()
    _docx(folder / "Filing.docx",
          "Acme Widgets Inc sued. The tenant Rosa Delgado signed the lease.")
    # A first run with a party list of one, so the folder carries the key
    # `--fix-leaks` insists on; the tenant is the name that run missed.
    assert _run_main(folder, monkeypatch, "--pseudonymize",
                     "--term", "Acme Widgets Inc") == 0
    export = folder / "Text Files" / "Filing.txt"
    first = export.read_text(encoding="utf-8")
    assert "Acme Widgets" not in first
    assert "Rosa Delgado" in first                                # the miss
    (folder / NAME).write_text("Rosa Delgado\n", encoding="utf-8")
    assert _run_main(folder, monkeypatch, "--fix-leaks") == 0
    text = export.read_text(encoding="utf-8")
    assert "Rosa Delgado" not in text and "signed the lease" in text
    assert "Rosa Delgado" in {str(r[1]) for r in _key_rows(folder)}
    assert not (folder / NAME).exists()          # consumed here too


def test_a_file_of_nothing_but_comments_is_left_alone(tmp_path, monkeypatch):
    # Nothing was spent, so there is nothing to consume — and removing a file
    # the operator may be part-way through typing into says nothing true.
    folder = tmp_path / "Smith v Jones"
    folder.mkdir()
    _docx(folder / "Filing.docx", "The tenant signed the lease in March.")
    (folder / NAME).write_text("# nothing flagged yet\n\n", encoding="utf-8")
    assert _run_main(folder, monkeypatch, "--pseudonymize") == 0
    assert (folder / NAME).exists()


def test_a_key_that_could_not_be_written_keeps_the_list(tmp_path, monkeypatch):
    # The exports carry fakes and nothing pins them; the operator's flags are
    # the one thing that could rebuild the binding, so they are not thrown
    # away with the key.
    folder = tmp_path / "Smith v Jones"
    folder.mkdir()
    _docx(folder / "Filing.docx", "The tenant Rosa Delgado signed the lease.")
    (folder / NAME).write_text("Rosa Delgado\n", encoding="utf-8")

    def _boom(self, path, log=None, **kw):
        raise OSError("disk full")

    monkeypatch.setattr(pl.Pseudonymizer, "write_key", _boom)
    _run_main(folder, monkeypatch, "--pseudonymize")
    assert (folder / NAME).exists()


# ── keeps ────────────────────────────────────────────────────────────────────

def test_keep_lines_are_decisions_and_never_terms(tmp_path):
    (tmp_path / NAME).write_text(
        "Rosa Delgado\nno: Stockton Theatres\nNEVER: Palermo\nnever: palermo\n",
        encoding="utf-8")
    assert pl._pn_read_new_real_values(tmp_path, log) == ["Rosa Delgado"]
    keeps = pl._pn_read_reader_keeps(tmp_path, log)
    assert set(keeps) == {"stockton theatres", "palermo"}
    assert keeps["stockton theatres"]["fix"] == "no"
    assert keeps["stockton theatres"].get("fixcell") in (None, "")
    assert keeps["palermo"]["fix"] == "no"
    assert keeps["palermo"]["fixcell"] == "never"


def test_a_typed_worksheet_cell_wins_over_the_readers_line(tmp_path):
    (tmp_path / NAME).write_text("no: Stockton\nno: Palermo\n", encoding="utf-8")
    sheet = {"stockton": {"value": "Stockton", "fix": "yes", "fixcell": None},
             "palermo": {"value": "Palermo", "fix": "", "fixcell": None}}
    merged = pl._pn_with_reader_keeps(sheet, tmp_path, log)
    assert merged["stockton"]["fix"] == "yes"       # the operator's own answer
    assert merged["palermo"]["fix"] == "no"         # an undecided row, answered


def test_a_kept_value_comes_back_unfaked_on_the_next_run(tmp_path, monkeypatch):
    folder = tmp_path / "Smith v Jones"
    folder.mkdir()
    _docx(folder / "Filing.docx",
          "Acme Widgets Inc cites Stockton Theatres throughout.")
    assert _run_main(folder, monkeypatch, "--pseudonymize",
                     "--term", "Acme Widgets Inc", "--term", "Stockton Theatres") == 0
    export = folder / "Text Files" / "Filing.txt"
    assert "Stockton Theatres" not in export.read_text(encoding="utf-8")
    # The reader says the case name was wrongly faked.
    (folder / NAME).write_text("no: Stockton Theatres\n", encoding="utf-8")
    assert _run_main(folder, monkeypatch, "--pseudonymize",
                     "--term", "Acme Widgets Inc", "--term", "Stockton Theatres") == 0
    text = export.read_text(encoding="utf-8")
    assert "Stockton Theatres" in text and "Acme Widgets" not in text
    # The line is spent — it lives on the cross-folder master KEEP sheet now,
    # under THIS folder's Origin, so a third run with no file at all still
    # honours it as the LOCAL keep the line made it.
    assert not (folder / NAME).exists()
    assert _run_main(folder, monkeypatch, "--pseudonymize",
                     "--term", "Acme Widgets Inc", "--term", "Stockton Theatres") == 0
    again = export.read_text(encoding="utf-8")
    assert "Stockton Theatres" in again and "Acme Widgets" not in again
