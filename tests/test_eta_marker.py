"""
Live ETA marker: a 0-byte file beside pdf_linker.log whose NAME carries the
estimated finish time, rewritten per file and removed on a clean finish. The
name must be valid on Windows (no colon) and must never disturb the real log.

Run:  cd PDF-Linker && python3 -m pytest tests/test_eta_marker.py -v
"""
import datetime
from pathlib import Path

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
    markers = list(tmp_path.glob("pdf_linker_ETA*"))
    assert len(markers) == 1
    assert not (set(markers[0].name) & _WINDOWS_ILLEGAL)
    assert markers[0].read_text() == ""          # the name is the message


def test_marker_is_replaced_not_accumulated(tmp_path):
    P._write_eta_marker(tmp_path, "~5.55PM (4 of 10)")
    first = list(tmp_path.glob("pdf_linker_ETA*"))[0].name
    P._write_eta_marker(tmp_path, "~5.40PM (5 of 10)")
    markers = list(tmp_path.glob("pdf_linker_ETA*"))
    assert len(markers) == 1 and markers[0].name != first


def test_clear_removes_marker_but_not_the_log(tmp_path):
    P._write_eta_marker(tmp_path, "~5.55PM (4 of 10)")
    (tmp_path / "pdf_linker.log").write_text("real log")
    P._clear_eta_markers(tmp_path)
    assert not list(tmp_path.glob("pdf_linker_ETA*"))
    assert (tmp_path / "pdf_linker.log").read_text() == "real log"
