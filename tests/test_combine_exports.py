"""
The UPLOAD CAP: a case folder may deliver at most 20 .txt exports, because that
is what the drafting tool accepts. A bigger folder has some of its exports
COMBINED into single files whose opening banner says so.

Two rules, in order: parts of ONE document go back together first (Brief (1),
Brief part 2, Brief 2 of 3), and if that is not enough the SMALLEST exports are
bundled until the count fits. Both may be needed.

What must hold, beyond the arithmetic:
  * nothing is dropped or shortened — every document is in there in full;
  * the file says what happened, and names its members, in its own header;
  * a grouping is REPRODUCED on a later run (the banners are the record), so a
    folder already sent comes back the same;
  * a combined file is only allowed to supersede its parts once they exist as
    separate exports — otherwise it is the only copy there is;
  * the leak gate and --fix-leaks work on the file that now carries the text:
    a leak in any member holds the whole combined file, and a fix releases it
    whole, located by the member document it was found in.

Run:  cd PDF-Linker && python3 -m pytest tests/test_combine_exports.py -v
"""
import logging
from pathlib import Path

import openpyxl
import pytest

import pdf_linker as P

log = logging.getLogger("test")


def _export(tdir, name, body="body text", pages=1):
    """A plausible .txt export: page banners and a line of body per page."""
    out = []
    for i in range(1, pages + 1):
        out.append(f"====== Page {i} ======\n {i}  {body}\n")
    p = tdir / name
    p.write_text("\n".join(out), encoding="utf-8")
    return p


def _tdir(tmp_path):
    d = tmp_path / "Text Files"
    d.mkdir()
    return d


def _txts(tdir):
    return sorted(p.name for p in tdir.glob("*.txt"))


# ─── Rule one: the same name with a part marker after it ─────────────────────

@pytest.mark.parametrize("stem,base,order", [
    ("Smith Decl (1)", "Smith Decl", (1,)),
    ("Smith Decl (2)", "Smith Decl", (2,)),
    ("Smith Decl part 2", "Smith Decl", (2,)),
    ("Smith Decl Part. 3", "Smith Decl", (3,)),
    ("Exhibit A vol 1", "Exhibit A", (1,)),
    ("Exhibit A Vol. II", "Exhibit A", (2,)),
    ("Depo Transcript 2 of 5", "Depo Transcript", (2,)),
    ("Reply Brief 3", "Reply Brief", (3,)),
    ("Appendix part 1 vol 2", "Appendix", (1, 2)),
])
def test_a_part_marker_is_split_off(stem, base, order):
    assert P._combine_split_part(stem) == (base, order)


@pytest.mark.parametrize("stem", [
    "Motion to Compel",
    "Order 2024",                 # a YEAR is not a part number ("Order 20"!)
    "Notice of Ruling",
    "1 of 3",                     # no document name left to group on
    "Complaint filed 03-14-2025",
])
def test_an_ordinary_name_carries_no_part_marker(stem):
    assert P._combine_split_part(stem) == (None, ())


def test_same_name_parts_group_and_bare_names_do_not(tmp_path):
    tdir = _tdir(tmp_path)
    paths = [_export(tdir, n) for n in
             ("Smith Decl.txt", "Smith Decl (1).txt", "Smith Decl (2).txt",
              "Motion.txt", "Opposition.txt")]
    groups = P._combine_same_name_groups(paths)
    assert len(groups) == 1
    base, members = groups[0]
    assert base == "Smith Decl"
    # The unmarked original leads: a Windows duplicate download is "Brief.pdf"
    # beside "Brief (1).pdf", and (1) follows the file it was copied from.
    assert [m.name for m in members] == [
        "Smith Decl.txt", "Smith Decl (1).txt", "Smith Decl (2).txt"]


def test_parts_alone_get_the_folder_under_the_cap(tmp_path):
    tdir = _tdir(tmp_path)
    for i in range(19):
        _export(tdir, f"Filing {chr(65 + i)}.txt")      # 19 ordinary exports
    _export(tdir, "Smith Decl part 1.txt")
    _export(tdir, "Smith Decl part 2.txt")
    _export(tdir, "Smith Decl part 3.txt")              # 22 in all
    out = P._combine_exports_for_upload(tmp_path, "Text Files",
                                        {"max_text_files": "20"}, log)
    assert len(_txts(tdir)) == 20
    assert [p.name for p, _m in out] == ["Smith Decl (COMBINED 3 parts).txt"]
    body = out[0][0].read_text()
    assert P._COMBINE_MARK in body.split("DOCUMENT 1 OF")[0]   # says so up top
    # every part is in there, in full, behind its own banner — and gone from
    # the folder as a separate file
    assert [n for n, _b in P._combined_sections(body)] == [
        "Smith Decl part 1.txt", "Smith Decl part 2.txt",
        "Smith Decl part 3.txt"]
    assert not (tdir / "Smith Decl part 1.txt").exists()


def test_a_big_part_set_is_sliced_not_swallowed_whole(tmp_path):
    # Three files over, with a three-part declaration and a twelve-part exhibit
    # set to choose from. The small group goes whole; the big one gives up the
    # two parts still needed and keeps the other ten as their own files.
    # Combining is a cost — one leak holds every document in the file — so it
    # is paid only to the extent the cap demands.
    tdir = _tdir(tmp_path)
    for i in range(8):
        _export(tdir, f"Filing {chr(65 + i)}.txt")
    for i in range(1, 13):
        _export(tdir, f"Exhibit Set part {i}.txt")
    _export(tdir, "Short Decl part 1.txt")
    _export(tdir, "Short Decl part 2.txt")
    _export(tdir, "Short Decl part 3.txt")              # 8 + 12 + 3 = 23
    out = P._combine_exports_for_upload(tmp_path, "Text Files",
                                        {"max_text_files": "20"}, log)
    assert len(_txts(tdir)) == 20
    assert sorted(p.name for p, _m in out) == [
        "Exhibit Set (COMBINED 2 of 12 parts).txt",
        "Short Decl (COMBINED 3 parts).txt"]
    assert (tdir / "Exhibit Set part 7.txt").exists()   # the other ten stand
    assert not (tdir / "Exhibit Set part 1.txt").exists()


# ─── Rule two: the smallest exports ──────────────────────────────────────────

def test_the_smallest_files_are_bundled_when_no_parts_exist(tmp_path):
    tdir = _tdir(tmp_path)
    for i in range(20):
        _export(tdir, f"Filing {chr(65 + i)}.txt", body="x" * 400)
    _export(tdir, "Tiny A.txt", body="a")
    _export(tdir, "Tiny B.txt", body="b")
    _export(tdir, "Tiny C.txt", body="c")               # 23 exports, 3 over
    out = P._combine_exports_for_upload(tmp_path, "Text Files",
                                        {"max_text_files": "20"}, log)
    assert len(_txts(tdir)) == 20
    assert [p.name for p, _m in out] == ["COMBINED 4 documents.txt"]
    members = [n for n, _b in P._combined_sections(out[0][0].read_text())]
    # excess + 1 = 4 smallest: the three tiny ones plus one ordinary filing
    assert {"Tiny A.txt", "Tiny B.txt", "Tiny C.txt"} <= set(members)
    assert len(members) == 4


def test_both_rules_run_when_parts_alone_are_not_enough(tmp_path):
    tdir = _tdir(tmp_path)
    for i in range(19):
        _export(tdir, f"Filing {chr(65 + i)}.txt", body="x" * 400)
    _export(tdir, "Decl part 1.txt", body="x" * 400)
    _export(tdir, "Decl part 2.txt", body="x" * 400)    # -1 -> 21
    _export(tdir, "Tiny A.txt", body="a")
    _export(tdir, "Tiny B.txt", body="b")               # 23 in all
    out = P._combine_exports_for_upload(tmp_path, "Text Files",
                                        {"max_text_files": "20"}, log)
    assert len(_txts(tdir)) == 20
    names = sorted(p.name for p, _m in out)
    # the two parts shed one file; the remaining two come off the smallest
    assert names == ["COMBINED 3 documents.txt", "Decl (COMBINED 2 parts).txt"]
    tiny = [n for n, _b in P._combined_sections(
        (tdir / "COMBINED 3 documents.txt").read_text())]
    assert {"Tiny A.txt", "Tiny B.txt"} <= set(tiny) and len(tiny) == 3


def test_a_folder_under_the_cap_is_left_alone(tmp_path):
    tdir = _tdir(tmp_path)
    for n in ("Brief (1).txt", "Brief (2).txt", "Motion.txt"):
        _export(tdir, n)
    assert P._combine_exports_for_upload(tmp_path, "Text Files", {}, log) == []
    assert _txts(tdir) == ["Brief (1).txt", "Brief (2).txt", "Motion.txt"]


# ─── The file says what happened ─────────────────────────────────────────────

def test_the_header_explains_itself_and_lists_its_documents(tmp_path):
    tdir = _tdir(tmp_path)
    _export(tdir, "Decl part 1.txt", body="first document body")
    _export(tdir, "Decl part 2.txt", body="second document body")
    out = P._combine_exports_for_upload(tmp_path, "Text Files",
                                        {"max_text_files": "1"}, log)
    body = out[0][0].read_text()
    head = body.split("DOCUMENT 1 OF")[0]
    assert "COMBINED TEXT EXPORT — 2 documents in one file" in head
    assert "NOTHING was dropped or shortened" in head
    assert "#   1. Decl part 1.txt" in head and "#   2. Decl part 2.txt" in head
    assert "Page numbering restarts" in head
    assert "first document body" in body and "second document body" in body
    # the page banners inside are untouched, and a DOCUMENT banner is not one
    assert body.count("====== Page 1 ======") == 2
    assert P._pn_body_lines(body)                      # still parses


# ─── Stability across runs ───────────────────────────────────────────────────

def test_a_previous_grouping_is_reproduced_not_re_derived(tmp_path):
    # The hazard: adding a document changes which files are "the smallest", so
    # a re-derived plan reshuffles a folder already sent and invalidates every
    # draft written from it. The banners are the record; the grouping is read
    # back off them.
    tdir = _tdir(tmp_path)
    for i in range(20):
        _export(tdir, f"Filing {chr(65 + i)}.txt", body="x" * 400)
    _export(tdir, "Tiny A.txt", body="a")
    _export(tdir, "Tiny B.txt", body="b")
    cfg = {"max_text_files": "20"}
    first = P._combine_exports_for_upload(tmp_path, "Text Files", cfg, log)
    combined = first[0][0]
    before = combined.read_text()
    members = [n for n, _b in P._combined_sections(before)]

    # A re-run rewrites every per-document export…
    for i in range(20):
        _export(tdir, f"Filing {chr(65 + i)}.txt", body="x" * 400)
    _export(tdir, "Tiny A.txt", body="a")
    _export(tdir, "Tiny B.txt", body="b")
    second = P._combine_exports_for_upload(tmp_path, "Text Files", cfg, log)
    assert [p.name for p, _m in second] == [combined.name]
    assert combined.read_text() == before        # byte-identical delivery
    assert len(_txts(tdir)) == 20

    # …and the incremental re-run — one more document dropped in — keeps the
    # same members in the same file, combining afresh only what it must.
    _export(tdir, "Late Filing.txt", body="x" * 400)
    third = P._combine_exports_for_upload(tmp_path, "Text Files", cfg, log)
    still = next(p for p, _m in third if p.name == combined.name)
    assert [n for n, _b in P._combined_sections(still.read_text())] == members
    assert still.read_text() == before
    assert len(_txts(tdir)) == 20


def test_a_grouping_is_kept_even_once_the_folder_fits(tmp_path):
    tdir = _tdir(tmp_path)
    _export(tdir, "Decl part 1.txt")
    _export(tdir, "Decl part 2.txt")
    P._combine_exports_for_upload(tmp_path, "Text Files",
                                  {"max_text_files": "1"}, log)
    assert _txts(tdir) == ["Decl (COMBINED 2 parts).txt"]
    # Now well under the cap. The file already went out as one document; the
    # run must not silently re-split it.
    P._combine_exports_for_upload(tmp_path, "Text Files",
                                  {"max_text_files": "20"}, log)
    assert _txts(tdir) == ["Decl (COMBINED 2 parts).txt"]


def test_a_member_with_no_separate_export_is_carried_forward(tmp_path):
    # The combined file is the ONLY copy of a document whose source PDF is gone
    # (or failed this run). Its section is carried over verbatim — deleting the
    # file to regroup would delete the document.
    tdir = _tdir(tmp_path)
    _export(tdir, "Decl part 1.txt", body="first body")
    _export(tdir, "Decl part 2.txt", body="second body")
    P._combine_exports_for_upload(tmp_path, "Text Files",
                                  {"max_text_files": "1"}, log)
    _export(tdir, "Decl part 1.txt", body="first body rewritten")
    out = P._combine_exports_for_upload(tmp_path, "Text Files",
                                        {"max_text_files": "1"}, log)
    body = out[0][0].read_text()
    assert "first body rewritten" in body        # the fresh copy wins
    assert "second body" in body                 # the orphan survives
    assert _txts(tdir) == ["Decl (COMBINED 2 parts).txt"]


def test_combining_off_still_honours_a_delivered_grouping(tmp_path):
    tdir = _tdir(tmp_path)
    _export(tdir, "Decl part 1.txt")
    _export(tdir, "Decl part 2.txt")
    P._combine_exports_for_upload(tmp_path, "Text Files",
                                  {"max_text_files": "1"}, log)
    _export(tdir, "Decl part 1.txt")             # a re-run rewrites the parts
    _export(tdir, "Decl part 2.txt")
    for i in range(30):                          # …and blows past any cap
        _export(tdir, f"Filing {chr(65 + i)}.txt")
    P._combine_exports_for_upload(tmp_path, "Text Files",
                                  {"max_text_files": "0"}, log)
    assert "Decl (COMBINED 2 parts).txt" in _txts(tdir)   # not re-split
    assert "Decl part 1.txt" not in _txts(tdir)           # nor duplicated
    assert len(_txts(tdir)) == 31                         # nothing NEW combined


def test_a_failed_write_leaves_every_part_where_it_was(tmp_path, monkeypatch):
    tdir = _tdir(tmp_path)
    _export(tdir, "Decl part 1.txt")
    _export(tdir, "Decl part 2.txt")

    def boom(self, *a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(Path, "write_text", boom)
    out = P._combine_exports_for_upload(tmp_path, "Text Files",
                                        {"max_text_files": "1"}, log)
    assert out == []
    assert _txts(tdir) == ["Decl part 1.txt", "Decl part 2.txt"]


# ─── The leak gate and --fix-leaks work on the combined file ─────────────────

def _pz():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Ford Motor Company"], ["24STCV24253"], [],
                              registry=reg)
    return P.Pseudonymizer(terms, {}, registry=reg)


def test_the_gate_quarantines_the_file_that_now_carries_the_leak(tmp_path):
    tdir = _tdir(tmp_path)
    a = _export(tdir, "Decl part 1.txt")
    b = _export(tdir, "Decl part 2.txt")
    pz = _pz()
    pz.written += [a, b]
    pz.leaked_by_file[b] = {"gregory yu"}
    P._combine_exports_for_upload(tmp_path, "Text Files",
                                  {"max_text_files": "1"}, log, pz)
    combined = tdir / "Decl (COMBINED 2 parts).txt"
    # the parts are gone, so a gate pointed at them would rename nothing
    assert pz.written == [combined]
    assert pz.leaked_by_file == {combined: {"gregory yu"}}
    assert pz.files_to_quarantine({"Gregory Yu"}) == [combined]
    assert pz.combined[combined] == ["Decl part 1.txt", "Decl part 2.txt"]


def test_fix_leaks_scrubs_a_combined_export_and_names_the_document(tmp_path):
    tdir = _tdir(tmp_path)
    _export(tdir, "Decl part 1.txt", body="Nothing to see here.")
    _export(tdir, "Decl part 2.txt", body="Gregory Yu testified.")
    P._combine_exports_for_upload(tmp_path, "Text Files",
                                  {"max_text_files": "1"}, log)
    combined = tdir / "Decl (COMBINED 2 parts).txt"
    # the gate would have held the whole file for the one member's leak
    combined.replace(combined.with_name(combined.name + ".LEAK"))

    pz = _pz()
    pz.apply("Ford Motor Company")
    pz.write_key(tmp_path / "pseudonym_key.xlsx", log)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["File", "Type", "Value", "Where", "Fix? (yes/no)", "Notes"])
    ws.append([combined.name + ".LEAK", "LEAK", "Gregory Yu", "p.1:1", "yes", ""])
    wb.save(tmp_path / "LEAKS.xlsx")

    class _Args:
        key = str(tmp_path / "pseudonym_key.xlsx")
        term = None

    assert P._fix_leaks_mode(tmp_path, _Args(), {}, log) == 0
    # released WHOLE, still combined, still self-describing, now scrubbed
    assert combined.exists() and not combined.with_name(
        combined.name + ".LEAK").exists()
    body = combined.read_text()
    assert "Gregory Yu" not in body
    assert len(P._combined_sections(body)) == 2
    assert _txts(tdir) == ["Decl (COMBINED 2 parts).txt"]


def test_a_finding_in_a_combined_export_names_its_member_document(tmp_path):
    # Every document in a combined file numbers its pages from 1, so a bare
    # "p.2:1" names two places. The member name is also the only thing left
    # saying which source document the leak came from.
    tdir = _tdir(tmp_path)
    _export(tdir, "Motion.txt", body="Nothing here.", pages=2)
    (tdir / "Opposition.txt").write_text(
        "====== Page 1 ======\n 1  Clean line.\n\n"
        "====== Page 2 ======\n 1  Gregory Yu testified.\n", encoding="utf-8")
    P._combine_exports_for_upload(tmp_path, "Text Files",
                                  {"max_text_files": "1"}, log)
    body = (tdir / "COMBINED 2 documents.txt").read_text()
    assert P._pn_locate_export(body, "Gregory Yu") == "Opposition p.2:1"
    # an ordinary export keeps the plain form
    assert P._pn_locate_export("====== Page 3 ======\n 7  Gregory Yu here.\n",
                               "Gregory Yu") == "p.3:7"


def test_end_to_end_a_run_delivers_no_more_than_the_cap(tmp_path, monkeypatch):
    # Through main(), on an all-Word folder (no fitz needed): the run writes an
    # export per document and the folder comes out at the cap, with everything
    # still in it.
    import sys
    import zipfile

    W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    for i in range(6):
        body = (f'<w:p><w:r><w:t xml:space="preserve">Body of filing {i}'
                f'</w:t></w:r></w:p>')
        with zipfile.ZipFile(tmp_path / f"Filing {chr(65 + i)}.docx", "w") as z:
            z.writestr("word/document.xml",
                       f'<?xml version="1.0" encoding="UTF-8"?>'
                       f'<w:document xmlns:w="{W}"><w:body>{body}</w:body>'
                       f'</w:document>')
    monkeypatch.setattr(P, "_read_config", lambda log=None: {
        "max_text_files": "4", "pseudonymize": "off"})
    monkeypatch.setattr(sys, "argv",
                        ["pdf_linker.py", str(tmp_path), "--no-pseudonymize"])
    P.main()
    tdir = tmp_path / "Text Files"
    assert len(_txts(tdir)) == 4
    combined = tdir / "COMBINED 3 documents.txt"
    assert combined.is_file()
    all_text = "".join(p.read_text() for p in tdir.glob("*.txt"))
    for i in range(6):
        assert f"Body of filing {i}" in all_text     # nothing dropped


def test_a_superseded_combined_quarantine_is_dropped(tmp_path):
    # The .LEAK is named for the combined file, so `_pn_drop_superseded_
    # quarantine` (which knows only source-PDF names) cannot see it. Left
    # behind, it is the one copy in the folder with the real names in it.
    tdir = _tdir(tmp_path)
    _export(tdir, "Decl part 1.txt")
    _export(tdir, "Decl part 2.txt")
    P._combine_exports_for_upload(tmp_path, "Text Files",
                                  {"max_text_files": "1"}, log)
    combined = tdir / "Decl (COMBINED 2 parts).txt"
    combined.replace(combined.with_name(combined.name + ".LEAK"))
    _export(tdir, "Decl part 1.txt")             # a full re-run rewrites both
    _export(tdir, "Decl part 2.txt")
    P._combine_exports_for_upload(tmp_path, "Text Files",
                                  {"max_text_files": "1"}, log)
    assert not combined.with_name(combined.name + ".LEAK").exists()
    assert combined.exists()
