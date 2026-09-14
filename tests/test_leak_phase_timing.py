"""The leak block SAYS where its time went.

A run says "running the leak scans over the export" and then nothing until
they are over. On a delivered folder's 70-page declaration of fax exhibits it
stayed there longer than every other phase of that file put together, and the
operator read it as a hang — which is what an unmoving log looks like whatever
is actually happening.

One line at the end named the TOTAL, and "the leak scans" is not one thing:
four cures, two survivor scans and a dozen REVIEW tiers, each over the whole
export, differing by an order of magnitude in cost. Naming the phase is half
the answer and not the useful half — which of the fourteen steps ran long is
what separates "this filing is big" from a pass that wants an algorithmic fix.

Run:  cd PDF-Linker && python3 -m pytest tests/test_leak_phase_timing.py -v
"""
import inspect
import logging
import time

import pytest

import pdf_linker as P


class _Log:
    """Collects what the run would have written."""

    def __init__(self):
        self.lines = []

    def info(self, msg):
        self.lines.append(str(msg))

    warning = error = info

    def said(self, needle):
        return [l for l in self.lines if needle in l]


def _pz():
    reg = P._PnFakeRegistry()
    return P.Pseudonymizer(
        P._pn_build_terms(["Helen Rasho"], [], [], registry=reg), [],
        registry=reg)


# ── the stopwatch ──────────────────────────────────────────────────────────

def test_the_clock_attributes_time_to_the_step_that_spent_it():
    mark, spent, started = P._phase_clock()
    time.sleep(0.02)
    mark("slow")
    mark("quick")
    assert spent["slow"] > spent["quick"]
    assert started <= time.monotonic()


def test_a_repeated_step_accumulates():
    """Two marks under one name are one step — the pleading-row render is
    asked for twice on a form page."""
    mark, spent, _ = P._phase_clock()
    time.sleep(0.01)
    mark("x")
    first = spent["x"]
    time.sleep(0.01)
    mark("x")
    assert spent["x"] > first


def test_the_summary_is_largest_first_and_drops_the_trivial():
    out = P._phase_summary({"small": 0.1, "big": 12.4, "mid": 3.0})
    assert out == "big 12s, mid 3s"


def test_an_all_trivial_summary_is_empty_so_no_dash_is_printed():
    assert P._phase_summary({"a": 0.1, "b": 0.2}) == ""


# ── the battery reports itself ─────────────────────────────────────────────

def test_the_tiers_name_their_own_seconds(monkeypatch):
    """Past the floor, the line names the tiers that cost something."""
    monkeypatch.setattr(P, "_LEAK_SLOW_SEC", 0.0)
    real = P.Pseudonymizer.fuzzy_survivor_scan

    def slow(self, body):
        time.sleep(0.6)
        return real(self, body)

    monkeypatch.setattr(P.Pseudonymizer, "fuzzy_survivor_scan", slow)
    log = _Log()
    _pz().leak_findings("Mr. Spellman confirmed the transfer.\n",
                        "Mr. Spellman confirmed the transfer.\n", log=log)
    said = log.said("review tiers in")
    assert said, log.lines
    assert "fuzzy sweep" in said[0]


def test_it_is_quiet_under_the_floor():
    """An ordinary document's log does not move."""
    log = _Log()
    _pz().leak_findings("Nothing to see here.\n", "Nothing to see here.\n",
                        log=log)
    assert log.said("review tiers in") == []


def test_no_log_is_no_line_and_no_error():
    """The battery is called from tests and from tools with no logger."""
    assert _pz().leak_findings("", "") == []


def test_the_findings_are_unchanged_by_being_timed():
    """Instrumentation must not move a single row."""
    body = ("Counsel of record, State Bar No. 214785, appeared.\n"
            "Mr. Spellman confirmed the transfer in March.\n")
    quiet = _pz().leak_findings(body, body)
    timed = _pz().leak_findings(body, body, log=_Log())
    assert quiet == timed
    assert quiet, "the battery reported nothing at all"


def test_a_tier_that_raises_still_leaves_the_line(monkeypatch):
    """`a line written afterwards is a line never written` — the report is in
    a `finally`, so a death inside the battery still names the step it was in
    when it died."""
    monkeypatch.setattr(P, "_LEAK_SLOW_SEC", 0.0)

    def boom(self, body):
        raise RuntimeError("tesseract fell over")

    monkeypatch.setattr(P.Pseudonymizer, "reid_scan", boom)
    log = _Log()
    with pytest.raises(RuntimeError):
        _pz().leak_findings("x\n", "x\n", log=log)
    assert log.said("review tiers in"), log.lines


# ── and the block around it ────────────────────────────────────────────────

def test_both_writers_hand_the_battery_their_log():
    """A tier breakdown the Word path could not print would be the split the
    one-list rule exists to refuse, arriving as a missing log line."""
    for writer in (P._write_text_version, P._write_word_text_version):
        src = inspect.getsource(writer)
        assert "leak_findings(" in src, writer.__name__
        call = src[src.index("leak_findings("):]
        assert "log=log" in call[:call.index(")") + 1], writer.__name__


def test_the_pdf_block_names_its_cures_and_survivor_scans():
    """The tiers are only part of it: the cures and the survivor scans run
    first, and `_surviving_records` is the most expensive thing on the path."""
    src = inspect.getsource(P._write_text_version)
    for step in ("column copy", "email cure", "weld cure", "survivor cure",
                 "survivor scan", "review tiers"):
        assert f'_leak_mark("{step}")' in src, step
    assert "_phase_summary(_leak_spent)" in src


def test_every_tier_of_the_battery_is_marked():
    """A tier added without a mark is a step whose cost hides inside its
    neighbour's — the silence this exists to break, one notch in."""
    src = inspect.getsource(P.Pseudonymizer.leak_findings)
    tiers = src.count("self.") - src.count("self._")
    assert src.count("mark('") == tiers, src
