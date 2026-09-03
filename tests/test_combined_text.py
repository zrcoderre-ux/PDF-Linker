"""
`combined_text = on`: every .txt export is ALSO written into one file,
`Combined Text.txt`, in the CASE FOLDER — not the text subfolder — each
document in full behind its own DOCUMENT banner. The individual exports are
untouched; this adds a file.

It is built from the exports as delivered: a quarantined *.LEAK is never in
it, and while one is held the file is withheld (a stale one removed), the same
rule the copy follows. Apply Leak Fixes writes it once the last leak is
released. Off by default, and turning it off removes the file a run wrote.

Run:  cd PDF-Linker && python3 -m pytest tests/test_combined_text.py -v
"""
import importlib.util
import logging
import sys
import types
import zipfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)

log = logging.getLogger("test")
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NAME = pl._COMBINED_TEXT_NAME


def _docx(path, text):
    body = f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
    doc = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<w:document xmlns:w="{_W}"><w:body>{body}</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", doc)
    return path


def _exports(tmp_path, **files):
    td = tmp_path / "Text Files"
    td.mkdir(exist_ok=True)
    for name, body in files.items():
        (td / name).write_text(body, encoding="utf-8")
    return td


# ── the writer ───────────────────────────────────────────────────────────────

def test_it_lands_in_the_case_folder_not_the_text_subfolder(tmp_path):
    td = _exports(tmp_path, **{"Brief.txt": "====== Page 1 ======\nthe brief\n",
                               "Reply.txt": "====== Page 1 ======\nthe reply\n"})
    out = pl._write_combined_text(tmp_path, "Text Files", log)
    assert out == tmp_path / NAME and out.is_file()
    assert not (td / NAME).exists()
    # ...and the individual exports are exactly as they were.
    assert sorted(p.name for p in td.glob("*.txt")) == ["Brief.txt", "Reply.txt"]


def test_every_export_is_in_it_whole_and_the_banners_read_back(tmp_path):
    _exports(tmp_path, **{"Reply.txt": "====== Page 1 ======\nthe reply\n",
                          "Brief.txt": "====== Page 1 ======\nthe brief\n"})
    text = pl._write_combined_text(tmp_path, "Text Files", log).read_text(
        encoding="utf-8")
    # Same banner shape the older combined files used, so the one reader
    # reads it — and name order, so a re-run reproduces it.
    assert pl._combined_sections(text) == [
        ("Brief.txt", "====== Page 1 ======\nthe brief"),
        ("Reply.txt", "====== Page 1 ======\nthe reply")]
    assert text.index("1. Brief.txt") < text.index("2. Reply.txt")


def test_a_quarantined_export_and_the_tools_own_files_are_never_members(tmp_path):
    _exports(tmp_path, **{"Brief.txt": "clean brief",
                          "Leaky.txt.LEAK": "Raytheon Technologies opposed",
                          f"{pl._PN_LEAK_STEM}.txt": "worksheet companion"})
    (tmp_path / "Text Files" / "DONE 6.04PM.txt").touch()
    text = pl._write_combined_text(tmp_path, "Text Files", log).read_text(
        encoding="utf-8")
    assert [n for n, _b in pl._combined_sections(text)] == ["Brief.txt"]
    assert "Raytheon" not in text and "worksheet companion" not in text


def test_a_leftover_combined_file_is_not_folded_into_it(tmp_path):
    # An older version's COMBINED file that still stands as an export: its
    # banners would nest inside this file's and confuse every reader of it.
    old = "\n".join(["#" * 78, f"# {pl._COMBINE_MARK} — 1 documents in one file",
                     "#" * 78, "",
                     f"{'#' * 8} DOCUMENT 1 OF 1 IN THIS COMBINED FILE: "
                     f"Gone.txt {'#' * 8}", "", "the gone document", ""])
    _exports(tmp_path, **{"Brief.txt": "the brief",
                          "COMBINED 1 documents.txt": old})
    text = pl._write_combined_text(tmp_path, "Text Files", log).read_text(
        encoding="utf-8")
    assert [n for n, _b in pl._combined_sections(text)] == ["Brief.txt"]


def test_it_is_byte_stable_and_not_rewritten_for_nothing(tmp_path):
    _exports(tmp_path, **{"Brief.txt": "the brief"})
    out = pl._write_combined_text(tmp_path, "Text Files", log)
    first = out.read_bytes()
    stamp = out.stat().st_mtime_ns
    out2 = pl._write_combined_text(tmp_path, "Text Files", log)
    assert out2 == out and out.read_bytes() == first
    assert out.stat().st_mtime_ns == stamp          # untouched, not re-saved


def test_a_hold_withholds_it_and_removes_a_stale_one(tmp_path):
    _exports(tmp_path, **{"Brief.txt": "the brief"})
    pl._write_combined_text(tmp_path, "Text Files", log)
    assert (tmp_path / NAME).exists()
    assert pl._write_combined_text(tmp_path, "Text Files", log,
                                   hold="1 export(s) are quarantined") is None
    assert not (tmp_path / NAME).exists()


def test_nothing_to_combine_writes_nothing_and_drops_a_stale_one(tmp_path):
    _exports(tmp_path, **{"Brief.txt": "the brief"})
    pl._write_combined_text(tmp_path, "Text Files", log)
    (tmp_path / "Text Files" / "Brief.txt").unlink()
    assert pl._write_combined_text(tmp_path, "Text Files", log) is None
    assert not (tmp_path / NAME).exists()


def test_a_file_of_the_operators_under_that_name_is_never_removed(tmp_path):
    # Removal is keyed on the header mark this tool writes; a file that does
    # not carry it is somebody's, whatever it is called.
    (tmp_path / NAME).write_text("my own notes", encoding="utf-8")
    pl._combined_text_after_run(tmp_path, "Text Files", False, log)
    pl._write_combined_text(tmp_path, "Text Files", log, hold="held")
    assert (tmp_path / NAME).read_text(encoding="utf-8") == "my own notes"


def test_turning_the_setting_off_removes_the_file_a_run_wrote(tmp_path):
    _exports(tmp_path, **{"Brief.txt": "the brief"})
    assert pl._combined_text_after_run(tmp_path, "Text Files", True, log)
    assert pl._combined_text_after_run(tmp_path, "Text Files", False, log) is None
    assert not (tmp_path / NAME).exists()


def test_it_is_the_tools_own_artifact_never_an_export(tmp_path):
    # Under the older single-folder layout `--fix-leaks` reads the case
    # folder's .txt files as exports; this one must never be scrubbed or
    # folded into itself.
    assert pl._is_tool_txt_artifact(tmp_path / NAME)


# ── the setting ──────────────────────────────────────────────────────────────

def test_off_by_default():
    assert pl._config_bool({}, "combined_text", False) is False
    assert any(k == "combined_text" for k, _b in pl._CONFIG_BLOCKS)


# ── end to end ───────────────────────────────────────────────────────────────

def _config(tmp_path, monkeypatch, text):
    path = tmp_path / "pdf_linker.config"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(pl, "_config_path", lambda: path)
    return path


def _run_main(folder, monkeypatch, *extra):
    monkeypatch.setattr(sys, "argv", ["pdf_linker.py", str(folder), *extra])
    try:
        pl.main()
    except SystemExit as e:
        return e.code
    return 0


def _word_case(tmp_path):
    folder = tmp_path / "Smith v Jones"
    folder.mkdir()
    _docx(folder / "Filing.docx", "The filing body")
    _docx(folder / "Reply.docx", "The reply body")
    return folder


def test_a_full_run_writes_it_beside_the_individual_exports(tmp_path,
                                                            monkeypatch):
    _config(tmp_path, monkeypatch, "combined_text = on\n")
    folder = _word_case(tmp_path)
    assert _run_main(folder, monkeypatch, "--no-pseudonymize") == 0
    text = (folder / NAME).read_text(encoding="utf-8")
    names = [n for n, _b in pl._combined_sections(text)]
    assert names == ["Filing.txt", "Reply.txt"]
    assert "The filing body" in text and "The reply body" in text
    # In addition to, never instead of.
    assert sorted(p.name for p in (folder / "Text Files").glob("*.txt")) == [
        "Filing.txt", "Reply.txt"]
    assert not (folder / "Text Files" / NAME).exists()


def test_a_full_run_with_it_off_writes_nothing(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch, "combined_text = off\n")
    folder = _word_case(tmp_path)
    _run_main(folder, monkeypatch, "--no-pseudonymize")
    assert not (folder / NAME).exists()


def test_switching_it_off_removes_it_on_the_next_run(tmp_path, monkeypatch):
    path = _config(tmp_path, monkeypatch, "combined_text = on\n")
    folder = _word_case(tmp_path)
    _run_main(folder, monkeypatch, "--no-pseudonymize")
    assert (folder / NAME).exists()
    path.write_text("combined_text = off\n", encoding="utf-8")
    _run_main(folder, monkeypatch, "--no-pseudonymize")
    assert not (folder / NAME).exists()


def test_the_copy_carries_it(tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch,
            f"combined_text = on\ncopy_to = {tmp_path / 'dest'}\n")
    folder = _word_case(tmp_path)
    _run_main(folder, monkeypatch, "--no-pseudonymize")
    assert (tmp_path / "dest" / folder.name / NAME).is_file()


# ── the leak gate ────────────────────────────────────────────────────────────

def _held_folder(tmp_path, fix):
    """A folder with one quarantined export, one clean one, a key, and a
    worksheet answering the leak with `fix`."""
    import openpyxl
    td = tmp_path / "Text Files"
    td.mkdir()
    (td / "Brief.txt.LEAK").write_text(
        "====== Page 1 ======\nRaytheon Technologies opposed.\n",
        encoding="utf-8")
    (td / "Clean.txt").write_text("====== Page 1 ======\nNothing here.\n",
                                  encoding="utf-8")
    wb = openpyxl.Workbook(); ws = wb.active; ws.title = "Pseudonym Key"
    ws.append(["Category", "Real Value", "Replacement", "Status",
               "Source", "Occurrences"])
    ws.append(["person", "Filler Party", "Fake Party", "replaced", "--term", "1"])
    wb.save(tmp_path / "pseudonym_key.xlsx")
    wb2 = openpyxl.Workbook(); w2 = wb2.active; w2.title = "Potential Leaks"
    w2.append(["File", "Type", "Value", "Where (page:line)", "Fix? (yes/no)",
               "Notes"])
    w2.append(["Brief.txt.LEAK", "LEAK", "Raytheon Technologies", "p.1", fix, ""])
    wb2.save(tmp_path / "LEAKS.xlsx")
    return types.SimpleNamespace(term=[],
                                 key=str(tmp_path / "pseudonym_key.xlsx"))


def test_fix_leaks_writes_it_once_the_last_leak_is_released(tmp_path):
    args = _held_folder(tmp_path, "yes")
    rc = pl._fix_leaks_mode(tmp_path, args, {"combined_text": "on"}, log)
    assert rc == 0
    text = (tmp_path / NAME).read_text(encoding="utf-8")
    names = [n for n, _b in pl._combined_sections(text)]
    assert names == ["Brief.txt", "Clean.txt"]
    assert "Raytheon" not in text                 # the released export is FIXED


def test_fix_leaks_withholds_it_while_a_leak_stands(tmp_path):
    # A typed replacement equal to the value fixes nothing, so the file stays
    # quarantined — and a combined file must neither carry the leak nor read
    # as complete without that document.
    args = _held_folder(tmp_path, "Raytheon Technologies")
    (tmp_path / NAME).write_text(
        f"{'#' * 78}\n# {pl._COMBINE_MARK} — stale\n", encoding="utf-8")
    pl._fix_leaks_mode(tmp_path, args, {"combined_text": "on"}, log)
    assert (tmp_path / "Text Files" / "Brief.txt.LEAK").exists()   # still held
    assert not (tmp_path / NAME).exists()


def test_fix_leaks_leaves_it_alone_when_the_setting_is_off(tmp_path):
    args = _held_folder(tmp_path, "yes")
    pl._fix_leaks_mode(tmp_path, args, {}, log)
    assert not (tmp_path / NAME).exists()
