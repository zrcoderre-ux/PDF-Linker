"""
`combined_text = on` AND `keep_original_text = on`: the UNSCRUBBED copies in
the do-not-share subfolder are also written into one file there —
`Combined Original Text.txt`, beside the individual originals — with the same
DOCUMENT banners the shareable `Combined Text.txt` carries. It lives ONLY in
that subfolder (it holds every real name in the folder), is never gated or
withheld (an original never is), is removed when either setting is off, and
is the tool's own artifact: never an export, never read back as an original.

Run:  cd PDF-Linker && python3 -m pytest tests/test_combined_original_text.py -v
"""
import importlib.util
import logging
import sys
import types
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)

log = logging.getLogger("test")
_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
ORIG = "Original Text (real names - do not share)"
NAME = pl._COMBINED_ORIGINAL_NAME
SHARE = pl._COMBINED_TEXT_NAME


def _originals(tmp_path, **files):
    od = tmp_path / ORIG
    od.mkdir(exist_ok=True)
    for name, body in files.items():
        (od / name).write_text(body, encoding="utf-8")
    return od


def _docx(path, text):
    body = f'<w:p><w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
    doc = (f'<?xml version="1.0" encoding="UTF-8"?>'
           f'<w:document xmlns:w="{_W}"><w:body>{body}</w:body></w:document>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", doc)
    return path


# ── the writer ───────────────────────────────────────────────────────────────

def test_it_lands_inside_the_original_folder_beside_the_originals(tmp_path):
    od = _originals(tmp_path, **{
        "Brief.txt": "====== Page 1 ======\nHelen Rasho sued.\n",
        "Reply.txt": "====== Page 1 ======\nQuillmark replied.\n"})
    out = pl._write_combined_original(tmp_path, ORIG, log)
    assert out == od / NAME and out.is_file()
    # Never in the case folder and never in Text Files: real names.
    assert not (tmp_path / NAME).exists()
    assert not (tmp_path / "Text Files" / NAME).exists()
    # The individual originals are exactly as they were.
    assert sorted(p.name for p in od.glob("*.txt")) == sorted(
        ["Brief.txt", NAME, "Reply.txt"])


def test_every_original_is_in_it_whole_and_the_header_says_do_not_share(tmp_path):
    _originals(tmp_path, **{
        "Reply.txt": "====== Page 1 ======\nQuillmark replied.\n",
        "Brief.txt": "====== Page 1 ======\nHelen Rasho sued.\n"})
    text = pl._write_combined_original(tmp_path, ORIG, log).read_text(
        encoding="utf-8")
    assert pl._combined_sections(text) == [
        ("Brief.txt", "====== Page 1 ======\nHelen Rasho sued."),
        ("Reply.txt", "====== Page 1 ======\nQuillmark replied.")]
    head = text[:1500]
    assert "REAL NAMES" in head and "NOT to be shared" in head
    assert f'"{ORIG}"' in head
    assert "uploading" not in head           # the shareable file's line


def test_it_is_byte_stable_and_not_rewritten_for_nothing(tmp_path):
    od = _originals(tmp_path, **{"Brief.txt": "Helen Rasho sued."})
    a = pl._write_combined_original(tmp_path, ORIG, log)
    first = a.read_bytes()
    mtime = a.stat().st_mtime_ns
    b = pl._write_combined_original(tmp_path, ORIG, log)
    assert b == a and b.read_bytes() == first
    assert b.stat().st_mtime_ns == mtime


def test_the_tools_own_files_are_never_members_and_it_never_nests(tmp_path):
    od = _originals(tmp_path, **{"Brief.txt": "Helen Rasho sued."})
    pl._write_combined_original(tmp_path, ORIG, log)
    # A second write must not fold the first combined file into itself.
    (od / "Reply.txt").write_text("Quillmark replied.", encoding="utf-8")
    text = pl._write_combined_original(tmp_path, ORIG, log).read_text(
        encoding="utf-8")
    assert [n for n, _b in pl._combined_sections(text)] == ["Brief.txt",
                                                            "Reply.txt"]
    assert text.count(pl._COMBINE_MARK) == 1


def test_no_original_folder_writes_nothing(tmp_path):
    assert pl._write_combined_original(tmp_path, ORIG, log) is None
    assert not (tmp_path / ORIG).exists()


def test_nothing_to_combine_drops_a_stale_one(tmp_path):
    od = _originals(tmp_path)
    (od / NAME).write_text(f"{'#' * 78}\n# {pl._COMBINE_MARK} — stale\n",
                           encoding="utf-8")
    assert pl._write_combined_original(tmp_path, ORIG, log) is None
    assert not (od / NAME).exists()


def test_either_setting_off_removes_the_file_a_run_wrote(tmp_path):
    od = _originals(tmp_path, **{"Brief.txt": "Helen Rasho sued."})
    assert pl._combined_original_after_run(tmp_path, ORIG, True, log)
    assert (od / NAME).exists()
    assert pl._combined_original_after_run(tmp_path, ORIG, False, log) is None
    assert not (od / NAME).exists()
    assert (od / "Brief.txt").exists()          # the originals are untouched


def test_a_file_of_the_operators_under_that_name_is_never_removed(tmp_path):
    od = _originals(tmp_path)
    (od / NAME).write_text("my own notes", encoding="utf-8")
    pl._combined_original_after_run(tmp_path, ORIG, False, log)
    assert (od / NAME).read_text(encoding="utf-8") == "my own notes"


# ── it is the tool's own artifact ────────────────────────────────────────────

def test_it_is_never_an_export_and_never_read_back_as_an_original(tmp_path):
    od = _originals(tmp_path, **{"Brief.txt": "Helen Rasho sued.",
                                 "Reply.txt": "Quillmark replied."})
    pl._write_combined_original(tmp_path, ORIG, log)
    assert pl._is_tool_txt_artifact(od / NAME)
    # `_pn_original_texts` hands `--fix-leaks` the originals: each ONCE.
    texts, where = pl._pn_original_texts(tmp_path, {})
    assert where == ORIG
    assert sorted(texts) == ["Helen Rasho sued.", "Quillmark replied."]
    # The superseded-combined sweep (an older version's consolidation) does
    # not remove it, though every member has its own copy beside it.
    pl._drop_superseded_combined_exports(tmp_path, ORIG, log)
    assert (od / NAME).exists()


def test_an_ocr_correction_rebuilds_it_from_the_corrected_originals(tmp_path):
    od = _originals(tmp_path, **{"Brief.txt": "Jonh Smlth sued."})
    pl._write_combined_original(tmp_path, ORIG, log)
    corr = {"smlth": ("Smlth", "Smith")}
    n = pl._pn_correct_original_files(tmp_path, {}, corr, log)
    assert n == 1                               # the member, not the combined
    assert "Smith" in (od / "Brief.txt").read_text(encoding="utf-8")
    text = pl._combined_original_after_run(tmp_path, ORIG, True, log
                                           ).read_text(encoding="utf-8")
    assert "Smith sued" in text and "Smlth" not in text


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
    _docx(folder / "Filing.docx", "The filing body was served on the parties.")
    _docx(folder / "Reply.docx", "The reply body answered it.")
    return folder


def test_a_full_run_with_both_on_writes_it_inside_the_original_folder(
        tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch,
            "combined_text = on\nkeep_original_text = on\n")
    folder = _word_case(tmp_path)
    assert _run_main(folder, monkeypatch) == 0
    od = folder / ORIG
    text = (od / NAME).read_text(encoding="utf-8")
    assert [n for n, _b in pl._combined_sections(text)] == ["Filing.txt",
                                                            "Reply.txt"]
    assert "The filing body" in text and "The reply body" in text
    # Along with, never instead of, the individual originals.
    assert sorted(p.name for p in od.glob("*.txt")) == sorted(
        ["Filing.txt", NAME, "Reply.txt"])
    # The shareable combined file is where it always was, and the original
    # one is nowhere else.
    assert (folder / SHARE).is_file()
    assert not (folder / NAME).exists()
    assert not (folder / "Text Files" / NAME).exists()


def test_a_full_run_with_originals_off_writes_no_combined_original(
        tmp_path, monkeypatch):
    _config(tmp_path, monkeypatch,
            "combined_text = on\nkeep_original_text = off\n")
    folder = _word_case(tmp_path)
    _run_main(folder, monkeypatch)
    assert (folder / SHARE).is_file()
    assert not (folder / ORIG).exists()


def test_switching_combined_off_removes_it_on_the_next_run(tmp_path,
                                                            monkeypatch):
    path = _config(tmp_path, monkeypatch,
                   "combined_text = on\nkeep_original_text = on\n")
    folder = _word_case(tmp_path)
    _run_main(folder, monkeypatch)
    assert (folder / ORIG / NAME).exists()
    path.write_text("combined_text = off\nkeep_original_text = on\n",
                    encoding="utf-8")
    _run_main(folder, monkeypatch)
    assert not (folder / ORIG / NAME).exists()
    assert (folder / ORIG / "Filing.txt").exists()


def test_the_setting_block_says_so():
    block = dict(pl._CONFIG_BLOCKS)["combined_text"]
    assert NAME in block and "keep_original_text" in block


# ── --fix-leaks ──────────────────────────────────────────────────────────────

def _held_folder(tmp_path, fix):
    import openpyxl
    td = tmp_path / "Text Files"
    td.mkdir()
    (td / "Brief.txt.LEAK").write_text(
        "====== Page 1 ======\nRaytheon Technologies opposed.\n",
        encoding="utf-8")
    _originals(tmp_path, **{
        "Brief.txt": "====== Page 1 ======\nRaytheon Technologies opposed.\n"})
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


def test_fix_leaks_writes_it_with_both_settings_on(tmp_path):
    args = _held_folder(tmp_path, "yes")
    assert pl._fix_leaks_mode(tmp_path, args, {"combined_text": "on",
                                               "keep_original_text": "on"},
                              log) == 0
    text = (tmp_path / ORIG / NAME).read_text(encoding="utf-8")
    assert [n for n, _b in pl._combined_sections(text)] == ["Brief.txt"]
    assert "Raytheon Technologies" in text      # the ORIGINAL, unscrubbed


def test_fix_leaks_writes_it_even_while_an_export_is_held(tmp_path):
    # An original is never quarantined, so its combined copy is not withheld
    # the way the shareable one is.
    args = _held_folder(tmp_path, "Raytheon Technologies")
    pl._fix_leaks_mode(tmp_path, args, {"combined_text": "on",
                                        "keep_original_text": "on"}, log)
    assert (tmp_path / "Text Files" / "Brief.txt.LEAK").exists()   # still held
    assert not (tmp_path / SHARE).exists()
    assert (tmp_path / ORIG / NAME).is_file()


def test_fix_leaks_removes_it_when_the_setting_is_off(tmp_path):
    args = _held_folder(tmp_path, "yes")
    (tmp_path / ORIG / NAME).write_text(
        f"{'#' * 78}\n# {pl._COMBINE_MARK} — stale\n", encoding="utf-8")
    pl._fix_leaks_mode(tmp_path, args, {"keep_original_text": "on"}, log)
    assert not (tmp_path / ORIG / NAME).exists()
