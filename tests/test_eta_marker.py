"""
Live ETA marker: a 0-byte file beside pdf_linker.log whose NAME carries the
estimated finish time, rewritten per file and removed on a clean finish. The
name must be valid on Windows (no colon) and must never disturb the real log.

Run:  cd PDF-Linker && python3 -m pytest tests/test_eta_marker.py -v
"""
import datetime
import tempfile
from pathlib import Path

import fitz
import pytest

import pdf_linker as P

_WINDOWS_ILLEGAL = set('<>:"/\\|?*')


@pytest.mark.parametrize("dt,want", [
    (datetime.datetime(2026, 7, 15, 17, 55), "5.55PM"),
    (datetime.datetime(2026, 7, 15, 0, 5), "12.05AM"),
    (datetime.datetime(2026, 7, 15, 12, 0), "12.00PM"),
    (datetime.datetime(2026, 7, 15, 9, 3), "9.03AM"),
    (datetime.datetime(2026, 7, 15, 23, 59), "11.59PM"),
])
def test_clock_is_colon_free_and_unpadded(dt, want):
    assert P._fmt_clock(dt) == want


def test_marker_name_is_windows_legal(tmp_path):
    P._write_eta_marker(tmp_path, "~5.55PM (4 of 10)")
    markers = list(tmp_path.glob("ETA *.txt"))
    assert len(markers) == 1
    assert not (set(markers[0].name) & _WINDOWS_ILLEGAL)
    assert markers[0].read_text() == ""          # the name is the message


def test_marker_is_replaced_not_accumulated(tmp_path):
    P._write_eta_marker(tmp_path, "~5.55PM (4 of 10)")
    first = list(tmp_path.glob("ETA *.txt"))[0].name
    P._write_eta_marker(tmp_path, "~5.40PM (5 of 10)")
    markers = list(tmp_path.glob("ETA *.txt"))
    assert len(markers) == 1 and markers[0].name != first


def test_clear_removes_marker_but_not_the_log(tmp_path):
    P._write_eta_marker(tmp_path, "~5.55PM (4 of 10)")
    (tmp_path / "pdf_linker.log").write_text("real log")
    P._clear_eta_markers(tmp_path)
    assert not list(tmp_path.glob("ETA *.txt"))
    assert (tmp_path / "pdf_linker.log").read_text() == "real log"


def test_clean_finish_stamps_done_marker(tmp_path):
    # Mid-run there is a live ETA marker; a clean finish renames it to a
    # 'DONE <clock>.txt' stamp of the actual finish time — not a deletion.
    P._write_eta_marker(tmp_path, "~6.04PM (6 of 13)")
    P._write_done_marker(tmp_path)
    assert not list(tmp_path.glob("ETA *.txt"))         # estimate is gone
    done = list(tmp_path.glob("DONE *.txt"))
    assert len(done) == 1
    assert done[0].read_text() == ""                    # name carries the time
    assert not (set(done[0].name) & _WINDOWS_ILLEGAL)   # Windows-legal


def test_next_run_clears_a_stale_done_stamp(tmp_path):
    # A DONE stamp from a previous run must not linger beside a fresh ETA marker.
    P._write_done_marker(tmp_path)
    (tmp_path / "pdf_linker.log").write_text("real log")
    P._write_eta_marker(tmp_path, "(estimating...)")
    assert not list(tmp_path.glob("DONE *.txt"))
    assert len(list(tmp_path.glob("ETA *.txt"))) == 1
    assert (tmp_path / "pdf_linker.log").read_text() == "real log"


def test_work_weight_prices_ocr_pages_over_bytes(tmp_path):
    # A native-text PDF vs a scanned-like one (empty text layer). The scanned
    # file can be SMALLER in bytes yet far costlier to process (OCR), which is
    # exactly why the ETA weights by OCR pages, not file size.
    doc = fitz.open()
    for _ in range(3):
        doc.new_page().insert_text((72, 100), "A real text layer with words.")
    native = tmp_path / "native.pdf"
    doc.save(native)
    doc.close()

    doc = fitz.open()
    for _ in range(5):
        doc.new_page()                       # no text -> will need OCR
    scanned = tmp_path / "scanned.pdf"
    doc.save(scanned)
    doc.close()

    wn = P._pdf_work_weight(native)
    ws = P._pdf_work_weight(scanned)
    assert wn == 3 * P._WORK_TEXT_PAGE
    assert ws == 5 * P._WORK_OCR_PAGE
    assert ws > wn * 10                       # OCR cost dominates
    # an unreadable file returns None so the caller can fall back to bytes
    bad = tmp_path / "bad.pdf"
    bad.write_text("not a pdf")
    assert P._pdf_work_weight(bad) is None


def test_eta_rate_round_trips_and_seeds_estimate(monkeypatch, tmp_path):
    # The remembered throughput lets a re-run project a finish time immediately.
    monkeypatch.setattr(P, "_eta_rate_path", lambda: tmp_path / "rate.txt")
    assert P._load_eta_rate() is None            # nothing saved yet
    P._save_eta_rate(2.5)                         # work-units per second
    assert P._load_eta_rate() == 2.5
    # a non-positive / garbage value never seeds a bogus estimate
    P._save_eta_rate(0)
    assert P._load_eta_rate() == 2.5             # unchanged (0 not written)
    (tmp_path / "rate.txt").write_text("garbage")
    assert P._load_eta_rate() is None
