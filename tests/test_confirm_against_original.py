"""
The ORIGINAL text as evidence: a flagged value is reduced to the part the source
document can account for, and dropped when nothing of it is real.

A leak finding claims "real information survived into the export". The run's own
output cannot satisfy that claim — and where `known_fake_words` only INFERS
which words are ours, the unscrubbed original says so outright.

"Langley" is one folder's stand-in for "Liu": 44 times in the export, ZERO times
in the PDF. It reached the triage worksheet twice anyway — once dragged along by
a real misspelling, once inside an argument heading — and a value in that
worksheet can be marked `yes`, which mints it into an authoritative term. That
is how a cited decision came to be renamed.

The finding is REDUCED rather than kept-or-dropped whole, because that is what
makes the worksheet answerable: "Ashely Langley" reads like the tool flagging
its own output, and the real question in it is "Ashely".

Run:  cd PDF-Linker && python3 -m pytest tests/test_confirm_against_original.py -v
"""

import logging

import pytest

import pdf_linker as P

log = logging.getLogger("test")

# What the source document actually said.
ORIGINAL = (
    'Defendant Ashely Liu ("Liu") is a resident of the county.\n'
    "F. Liu Submitted No Declaration and Relies on Inadmissible Hearsay.\n"
    "Melissa Penuela signed the proof of service.\n"
)


def _pz():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Weishi Yang", "Ashley Liu"], ["26STCV08967"],
                              [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    z = P.Pseudonymizer(terms, det, registry=reg)
    z.note_original(ORIGINAL)
    return z


def _fakes(z):
    """(given, surname) this run minted for the defendant."""
    return z.records[("person", "ashley liu")]["fake"].split()


# ───────────────────── nothing real left -> no row at all ───────────────────

def test_a_pure_stand_in_leaves_nothing(_=None):
    z = _pz()
    for fake in _fakes(z) + [" ".join(_fakes(z))]:
        assert z._real_remainder(fake) == "", (
            f"{fake!r} is this run's own output and is absent from the source")


# ──────────────── the real remainder is what gets reported ──────────────────

def test_a_half_scrubbed_pair_reduces_to_its_real_word():
    # The whole point. "Ashely" is the complaint's own typo of the defendant's
    # given name — the real question — and the fake beside it is noise.
    z = _pz()
    surname = _fakes(z)[1]
    assert z._real_remainder(f"Ashely {surname}") == "Ashely"


def test_a_phrase_built_on_a_stand_in_loses_it():
    z = _pz()
    surname = _fakes(z)[1]
    assert z._real_remainder(f"{surname} Submitted No") == "Submitted No"


def test_a_genuine_finding_is_untouched():
    assert _pz()._real_remainder("Melissa Penuela") == "Melissa Penuela"


def test_a_stand_in_that_IS_in_the_source_is_kept():
    """The safety condition. A word is removed only when it is BOTH one of our
    fakes AND absent from the original — a stand-in that the source happens to
    contain is not this run's doing, and might be real information."""
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(["Ashley Liu"], [], [], registry=reg),
                        {}, registry=reg)
    surname = z.records[("person", "ashley liu")]["fake"].split()[1]
    z.note_original(f"The witness {surname} testified for the plaintiff.")
    assert z._real_remainder(f"Ashely {surname}") == f"Ashely {surname}"


def test_no_original_changes_nothing():
    # With no evidence the check is inert — never a silent suppressor.
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(["Ashley Liu"], [], [], registry=reg),
                        {}, registry=reg)
    surname = z.records[("person", "ashley liu")]["fake"].split()[1]
    assert z._real_remainder(surname) == surname
    assert z.confirm_findings(log) == []


# ─────────────────────── what the worksheet ends up with ────────────────────

def test_confirm_findings_rewrites_the_row_and_clears_the_gate():
    z = _pz()
    surname = _fakes(z)[1]
    z.leak_report = [
        {"file": "Complaint.txt", "type": "LEAK", "value": surname,
         "where": "p.2:15"},
        {"file": "Complaint.txt", "type": "unscrubbed name?",
         "value": f"Ashely {surname}", "where": "p.2:15"},
        {"file": "Complaint.txt", "type": "LEAK", "value": "Melissa Penuela",
         "where": "p.9:3"},
    ]
    z.review = [("unscrubbed name?", f"Ashely {surname}"),
                ("possible person name", "Melissa Penuela")]
    z.note_leaks([surname, "Melissa Penuela"])
    z.leaked_by_file = {"Complaint.txt": {surname.lower(), "melissa penuela"}}

    z.confirm_findings(log)

    assert [r["value"] for r in z.leak_report] == ["Ashely", "Melissa Penuela"]
    assert z.review == [("unscrubbed name?", "Ashely"),
                        ("possible person name", "Melissa Penuela")]
    assert surname.lower() not in z.leaked, "a stand-in must not gate delivery"
    assert z.leaked_by_file["Complaint.txt"] == {"melissa penuela"}


def test_two_phrasings_that_reduce_to_one_row_are_merged():
    z = _pz()
    given, surname = _fakes(z)
    z.leak_report = [
        {"file": "Complaint.txt", "type": "LEAK", "value": f"Ashely {surname}",
         "where": "p.2:15"},
        {"file": "Complaint.txt", "type": "LEAK",
         "value": f"{given} Ashely {surname}", "where": "p.4:2"},
    ]
    z.confirm_findings(log)
    assert [r["value"] for r in z.leak_report] == ["Ashely"], z.leak_report


# ───────── the evidence is available whether or not the option is on ────────

def test_the_cache_round_trips(tmp_path):
    """The check must not depend on an output preference. A full run caches the
    unscrubbed text in TEMP — keyed by folder, never in the case folder, which
    is the thing that gets synced — so `--fix-leaks`, which never reopens the
    PDFs, has evidence too."""
    folder = tmp_path / "case"
    folder.mkdir()
    P._cache_original(folder, "Complaint", ORIGINAL)
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(["Ashley Liu"], [], [], registry=reg),
                        {}, registry=reg)
    assert P._load_cached_originals(folder, z) == 1
    surname = z.records[("person", "ashley liu")]["fake"].split()[1]
    assert z._real_remainder(surname) == "", "the cached original is evidence"
    P._clear_originals_cache(folder)
    assert P._load_cached_originals(folder, P.Pseudonymizer([], {})) == 0


def test_the_cache_never_lands_in_the_case_folder(tmp_path):
    folder = tmp_path / "case"
    folder.mkdir()
    P._cache_original(folder, "Complaint", ORIGINAL)
    try:
        assert list(folder.iterdir()) == [], (
            "unscrubbed text must never be written into the case folder")
    finally:
        P._clear_originals_cache(folder)
