"""
A COMBINED export left behind by an older version of this tool.

That version folded a folder's exports down to an upload limit of 20 files,
writing single files that held several documents each behind DOCUMENT banners.
Combining is gone. What is left is the folder it may have left behind: a
`COMBINED …` file that no source PDF maps to, so a full re-run does not
overwrite it and it would ship as a stale duplicate of documents already in the
folder under their own names.

It is dropped once every document in it has a separate export again — and NOT
before, because a member whose source PDF is gone has no other copy.

Run:  cd PDF-Linker && python3 -m pytest tests/test_stale_combined_export.py -v
"""
import logging

import pytest

import pdf_linker as P

log = logging.getLogger("test")


def _combined(members):
    """The file an older version wrote: a banner naming it, then each member
    behind its own DOCUMENT banner. `members` is [(export name, body), ...]."""
    n = len(members)
    out = ["#" * 78,
           f"# {P._COMBINE_MARK} — {n} documents in one file",
           "#" * 78]
    for i, (name, body) in enumerate(members, start=1):
        out.append(f"\n{'#' * 8} DOCUMENT {i} OF {n} IN THIS COMBINED FILE: "
                   f"{name} {'#' * 8}\n\n{body}\n")
    return "\n".join(out)


def _setup(tmp_path, members, present):
    tdir = tmp_path / "Text Files"
    tdir.mkdir()
    (tdir / "COMBINED 2 documents.txt").write_text(_combined(members),
                                                   encoding="utf-8")
    for name in present:
        (tdir / name).write_text(f"====== Page 1 ======\n{name} body\n",
                                 encoding="utf-8")
    return tdir


# ── reading one back ─────────────────────────────────────────────────────────

def test_sections_are_read_off_the_banners():
    text = _combined([("Brief.txt", "the brief"), ("Reply.txt", "the reply")])
    assert P._combined_sections(text) == [("Brief.txt", "the brief"),
                                          ("Reply.txt", "the reply")]


def test_an_ordinary_export_is_not_a_combined_one():
    assert P._combined_sections("====== Page 1 ======\nOrdinary text.\n") is None


# ── the sweep ────────────────────────────────────────────────────────────────

def test_a_superseded_combined_export_is_dropped(tmp_path):
    tdir = _setup(tmp_path, [("Brief.txt", "the brief"),
                             ("Reply.txt", "the reply")],
                  present=["Brief.txt", "Reply.txt"])
    P._drop_superseded_combined_exports(tmp_path, "Text Files", log)
    assert not (tdir / "COMBINED 2 documents.txt").exists()
    assert (tdir / "Brief.txt").exists() and (tdir / "Reply.txt").exists()


def test_it_is_kept_while_a_member_has_no_other_copy(tmp_path):
    # The source PDF for Reply is gone, so this file is the only copy of that
    # document there is. Dropping it would lose it.
    tdir = _setup(tmp_path, [("Brief.txt", "the brief"),
                             ("Reply.txt", "the reply")],
                  present=["Brief.txt"])
    P._drop_superseded_combined_exports(tmp_path, "Text Files", log)
    assert (tdir / "COMBINED 2 documents.txt").exists()


def test_a_superseded_combined_quarantine_goes_too(tmp_path):
    tdir = _setup(tmp_path, [("Brief.txt", "the brief"),
                             ("Reply.txt", "the reply")],
                  present=["Brief.txt", "Reply.txt"])
    stale = tdir / "COMBINED 2 documents.txt"
    stale.replace(tdir / "COMBINED 2 documents.txt.LEAK")
    P._drop_superseded_combined_exports(tmp_path, "Text Files", log)
    assert not (tdir / "COMBINED 2 documents.txt.LEAK").exists()


def test_an_absent_folder_is_not_an_error(tmp_path):
    P._drop_superseded_combined_exports(tmp_path, "Text Files", log)


# ── through a full run ───────────────────────────────────────────────────────

# Enough prose that the text-layer check reads the page as native, so an
# export is actually written for it.
_PROSE = ["The motion came on regularly for hearing before this Court and the",
          "matter was argued by counsel for each of the appearing parties and",
          "then submitted for decision on the papers filed in support of and",
          "in opposition to the relief requested in the moving papers here.",
          "Having considered the moving, opposing and reply papers, and the",
          "arguments of counsel, the Court rules on the motion as follows."]


def _make_pdf(path, lines=_PROSE):
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    y = 100
    for ln in lines:
        page.insert_text((72, y), ln, fontsize=11)
        y += 24
    doc.save(path)
    doc.close()


def test_a_full_run_clears_the_leftover(tmp_path, monkeypatch):
    import sys
    _make_pdf(tmp_path / "Brief.pdf")
    _make_pdf(tmp_path / "Reply.pdf")
    tdir = tmp_path / "Text Files"
    tdir.mkdir()
    (tdir / "COMBINED 2 documents.txt").write_text(
        _combined([("Brief.txt", "old brief text"),
                   ("Reply.txt", "old reply text")]), encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["pdf_linker.py", str(tmp_path)])
    P.main()

    assert not (tdir / "COMBINED 2 documents.txt").exists()
    # …and the folder is exactly one export per document, freshly written.
    assert {p.name for p in tdir.glob("*.txt")} == {"Brief.txt", "Reply.txt"}
    assert "old brief text" not in (tdir / "Brief.txt").read_text()


def test_a_full_run_leaves_one_whose_document_is_gone(tmp_path, monkeypatch):
    import sys
    _make_pdf(tmp_path / "Brief.pdf")
    tdir = tmp_path / "Text Files"
    tdir.mkdir()
    (tdir / "COMBINED 2 documents.txt").write_text(
        _combined([("Brief.txt", "old brief text"),
                   ("Reply.txt", "the only copy of the reply")]),
        encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["pdf_linker.py", str(tmp_path)])
    P.main()

    kept = tdir / "COMBINED 2 documents.txt"
    assert kept.exists()
    assert "the only copy of the reply" in kept.read_text()
