"""Unit tests for pdf_linker's case-citation detection across line wraps.

These need no geometry — they exercise the pure text path
(_normalize_for_detection -> REPORTER_PATTERN -> *_TAIL -> find_all_citations),
so each case is just a string. The wrapped strings reproduce what PyMuPDF
actually emits for a reporter split across two printed lines: a trailing space
before the newline ("Cal. App. \n4th"), which normalization turns into a
DOUBLE space inside the reporter. That double space is what the wild bug
(Caliber Bodyworks missed in an Opposition's authorities appendix) tripped on.

Run with: pytest tests/test_citations.py
"""
import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)


def _keys(text):
    return {c["key"] for c in pl.find_all_citations(text)}


class TestReporterLineWraps:
    """A reporter split across a line wrap must still be detected. The wrap
    can fall at any internal position; PyMuPDF's trailing-space-then-newline
    means the reporter arrives with an embedded double space after
    normalization."""

    CITE = "Caliber Bodyworks, Inc. v. Superior Court (2005) 134 Cal.App.4th 365"

    def test_same_line_baseline(self):
        t = "See Caliber Bodyworks, Inc. v. Superior Court, 134 Cal. App. 4th 365 (2005)."
        assert self.CITE in _keys(t)

    def test_wrap_inside_reporter(self):
        # The reporter itself is broken: "134 Cal. App. \n4th 365". This is the
        # exact shape that was silently dropped from the appendix.
        t = "See Caliber Bodyworks, Inc. v. Superior Court, 134 Cal. App. \n4th 365 (2005)."
        assert self.CITE in _keys(t)

    def test_wrap_after_series(self):
        t = "See Caliber Bodyworks, Inc. v. Superior Court, 134 Cal. App. 4th \n365 (2005)."
        assert self.CITE in _keys(t)

    def test_wrap_between_volume_and_reporter(self):
        t = "See Caliber Bodyworks, Inc. v. Superior Court, 134 \nCal. App. 4th 365 (2005)."
        assert self.CITE in _keys(t)

    def test_compact_reporter_unaffected(self):
        t = "See LiMandri v. Judkins 52 Cal.App.4th 326 (1997)."
        assert "LiMandri v. Judkins (1997) 52 Cal.App.4th 326" in _keys(t)

    def test_three_token_reporter_wraps(self):
        # Cal. Rptr. 3d split mid-reporter.
        t = "See People v. Smith, 12 Cal. Rptr. \n3d 99 (2003)."
        assert any("Cal.Rptr.3d" in k for k in _keys(t))
