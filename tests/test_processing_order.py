"""
Files are processed HEAVIEST first (by OCR-weighted cost, not bytes), so the big
scanned evidence files run up front — while you're watching — and the batch
finishes on a tail of quick files, instead of grinding through many small files
and only reaching a monster at the very end. And the re-run launcher is written
UP FRONT, so an interrupted or hung run still leaves a clickable re-run.

Run:  cd PDF-Linker && python3 -m pytest tests/test_processing_order.py -v
"""
import subprocess
import sys
from pathlib import Path

import fitz

PDF_LINKER = str(Path(__file__).resolve().parent.parent / "pdf_linker.py")


def _native(path):
    d = fitz.open()
    for _ in range(2):
        d.new_page().insert_text((72, 100), "Real prose text layer, no OCR need.")
    d.save(str(path))
    d.close()


def _scanned(path):
    d = fitz.open()
    for _ in range(4):
        d.new_page()                      # no text -> counts as OCR work (heavy)
    d.save(str(path))
    d.close()


def test_heaviest_file_is_processed_first_and_launcher_exists_up_front(tmp_path):
    # Name the heavy file so it sorts LAST alphabetically and is SMALLER on disk,
    # so processing it first can only be the work-weight ordering, not name/size.
    _native(tmp_path / "aaa_brief.pdf")          # light (has text), bigger bytes
    _scanned(tmp_path / "zzz_scan.pdf")          # heavy (needs OCR), fewer bytes

    r = subprocess.run(
        [sys.executable, PDF_LINKER, str(tmp_path), "--no-pseudonymize"],
        capture_output=True, text=True, timeout=180)
    out = r.stdout

    assert "heaviest first" in out
    i_scan = out.index("Processing: zzz_scan.pdf")
    i_brief = out.index("Processing: aaa_brief.pdf")
    assert i_scan < i_brief, out                  # the OCR-heavy file went first

    # The re-run launcher exists even though we can inspect it right after the
    # run — the point is it is written before the processing loop, so a hang
    # leaves it behind.
    launchers = [p for p in tmp_path.iterdir()
                 if p.name.startswith("Re-run PDF-Linker")]
    assert launchers, list(tmp_path.iterdir())
