"""An export of no source document is named, and a stale copy is left alone.

An export is named for its source's scrubbed stem, so one an earlier run
wrote under an earlier key's fakes matches no source once the key has moved
on. A delivered batch carried such a file — a byte-level duplicate of a live
export under a stand-in no key row mapped — and the `--fix-leaks` sweep
re-scrubbed it into a second generation, while the combined file carried both.

Run:  cd PDF-Linker && python3 -m pytest tests/test_orphan_exports.py -v
"""
import logging

import pdf_linker as P

log = logging.getLogger("test")
BODY = "\n".join(f"{i:>2}  Line {i} of the objections, faked as Yeardley." for i in range(1, 31)) + "\n"


def _folder(tmp_path):
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(["Helen Rasho"], [], [], registry=reg),
                        {}, registry=reg)
    (tmp_path / "Rasho Decl.pdf").write_bytes(b"%PDF-1.4\n")
    td = tmp_path / "Text Files"
    td.mkdir()
    live = P._pseudonymized_txt_path(td, tmp_path / "Rasho Decl.pdf", z, log)
    live.write_text(BODY, encoding="utf-8")
    (td / "Bogus Decl.txt").write_text(BODY.replace("Line 3 ", "Line 3x "), encoding="utf-8")
    (td / "Lonely.txt").write_text("a different document entirely\n" * 25, encoding="utf-8")
    return z, td, live


def test_a_stale_duplicate_is_told_apart_from_a_mere_orphan(tmp_path, caplog):
    z, td, live = _folder(tmp_path)
    with caplog.at_level(logging.WARNING):
        orphans, stale = P._orphan_exports(tmp_path, "Text Files", z, log)
    assert orphans == {"Bogus Decl.txt", "Lonely.txt"}
    assert stale == {"Bogus Decl.txt"}
    assert live.name not in orphans
    assert "near-copy" in caplog.text and "Lonely.txt" in caplog.text


def test_the_combined_file_leaves_the_stale_copy_out(tmp_path):
    z, td, live = _folder(tmp_path)
    _o, stale = P._orphan_exports(tmp_path, "Text Files", z, log)
    path = P._write_combined_text(tmp_path, "Text Files", log, skip=stale)
    text = path.read_text(encoding="utf-8")
    assert live.name in text and "Lonely.txt" in text
    assert "Bogus Decl.txt" not in text


def test_a_folder_with_no_sources_flags_nothing(tmp_path):
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer([], {}, registry=reg)
    (tmp_path / "Text Files").mkdir()
    (tmp_path / "Text Files" / "x.txt").write_text(BODY)
    assert P._orphan_exports(tmp_path, "Text Files", z, log) == (set(), set())
