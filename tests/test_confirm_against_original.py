"""
The ORIGINAL text as evidence: a flagged value that is not in the source
document is this run's own output, and cannot be a leak.

A leak finding claims "real information survived into the export". The run's own
output cannot satisfy that claim — and where `known_fake_words` only INFERS
which words are ours, the unscrubbed original says so outright.

"Langley" is one folder's stand-in for "Liu": 44 times in the export, ZERO times
in the PDF. It reached the triage worksheet twice anyway — once dragged along by
a real misspelling, once inside an argument heading — and a value in that
worksheet can be marked `yes`, which mints it into an authoritative term. That
is how a cited decision came to be renamed.

Fed from the "original text files" option on a full run, and read back off that
folder by `--fix-leaks`, which never reopens the PDFs.

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


@pytest.mark.parametrize("value", ["Langley", "Holloway", "Holloway Langley"])
def test_a_pure_fake_is_not_a_finding(value):
    assert not _pz()._finding_is_in_original(value), (
        f"{value!r} is this run's own stand-in and is absent from the source")


@pytest.mark.parametrize("value", [
    "Melissa Penuela",      # a genuine survivor, verbatim in the original
    "Ashely Langley",       # HALF-scrubbed: "Ashely" is the source's own typo
    "Melissa Sable",        # HALF-scrubbed: "Melissa" is real, "Sable" is ours
])
def test_a_value_with_anything_real_in_it_is_kept(value):
    assert _pz()._finding_is_in_original(value), (
        f"{value!r} carries real information and must still be triaged")


def test_the_check_is_word_by_word_not_whole_phrase():
    # The finding that matters most is half-scrubbed, and never appears verbatim
    # in the original. Requiring the whole phrase would throw away the one real
    # thing in it.
    z = _pz()
    assert "Ashely Langley" not in ORIGINAL
    assert z._finding_is_in_original("Ashely Langley")


def test_a_welded_value_is_matched_on_the_reduction():
    z = P.Pseudonymizer([], {}, registry=P._PnFakeRegistry())
    z.note_original("Served on ASHELYLIU at the address.")
    assert z._finding_is_in_original("Ashely Liu")


def test_no_original_means_nothing_is_dropped():
    # With no evidence recorded the check must be inert — never a silent
    # suppressor of real findings.
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(["Ashley Liu"], [], [], registry=reg),
                        {}, registry=reg)
    assert z._finding_is_in_original("Langley")
    assert z.confirm_findings(log) == []


def test_confirm_findings_clears_the_row_and_the_gate():
    z = _pz()
    z.leak_report = [
        {"file": "Complaint.txt", "type": "LEAK", "value": "Langley",
         "where": "p.2:15"},
        {"file": "Complaint.txt", "type": "LEAK", "value": "Melissa Penuela",
         "where": "p.9:3"},
    ]
    z.review = [("unscrubbed declarant name?", "Langley"),
                ("possible person name", "Melissa Penuela")]
    z.note_leaks(["Langley", "Melissa Penuela"])
    z.leaked_by_file = {"Complaint.txt": {"langley", "melissa penuela"}}

    dropped = z.confirm_findings(log)

    assert dropped == ["Langley"], dropped
    assert [r["value"] for r in z.leak_report] == ["Melissa Penuela"]
    assert z.review == [("possible person name", "Melissa Penuela")]
    assert "langley" not in z.leaked, "a fake must not quarantine an export"
    assert z.leaked_by_file["Complaint.txt"] == {"melissa penuela"}
