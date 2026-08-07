"""Our own stand-in must never become a tracked REAL value.

A delivered key carried this row:

    display-name | Lowther Rolleston EE | Winchcombe Penrose VENTRIS | leaked | 60

"Lowther" and "Rolleston" are this tool's stand-ins for "Gregory" and "Walton",
and "EE" is a word a master `no` KEEP left standing — so the whole Real Value is
the tool's OWN OUTPUT, faked a second time and applied 60 times. `DeAnonymize`
walking that map lands on "Lowther Rolleston EE", never on "Gregory Walton EE".

Two independent faults produced it, and the folder could not converge:

1. `--fix-leaks` works on text an earlier run already scrubbed, which is why its
   detectors are switched OFF. A display-name mint is the same hazard and was
   not: it read "Lowther Rolleston EE <addr>" as a fresh person.
2. `confirm_findings` reduced the finding to its real remainder ("EE") for the
   WORKSHEET but left the old phrasing gating delivery. "EE" carries a KEEP so
   it earned no row, while "Lowther Rolleston EE" held four exports — no row to
   answer, and no re-run could clear it.

Run:  cd PDF-Linker && python3 -m pytest tests/test_second_generation_fake.py -v
"""
import logging

import pdf_linker as P

log = logging.getLogger("test")

PAIR = "Contact Gregory Walton EE <gwalton@example.com> today."


def _full_run():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Gregory Wayne Walton"], [], [], registry=reg)
    return P.Pseudonymizer(terms, list(P._PN_DEFAULT_DETECTORS), registry=reg)


def _fix_leaks_pass():
    # What `_fix_leaks_mode` builds: no detectors, and no new display names.
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Gregory Wayne Walton"], [], [], registry=reg)
    z = P.Pseudonymizer(terms, [], registry=reg)
    z.mint_display_names = False
    return z


# ── 1. no second generation ─────────────────────────────────────────────────

def test_a_fix_leaks_pass_mints_no_display_name():
    scrubbed = _full_run().apply(PAIR)
    assert "Gregory" not in scrubbed and "Walton" not in scrubbed

    z = _fix_leaks_pass()
    again = z.apply(scrubbed)
    assert again == scrubbed, again           # our own output, left alone
    assert not [r for (c, _rl), r in z.records.items() if c == "display-name"]


def test_a_full_run_still_mints_one():
    # The pass exists for a reason: on the SOURCE text a display name beside an
    # address is a real person and must be faked.
    z = _full_run()
    out = z.apply(PAIR)
    minted = [r for (c, _rl), r in z.records.items() if c == "display-name"]
    assert minted, "a real display name must still be recognised"
    assert minted[0]["real"] == "Gregory Walton EE", minted[0]
    assert "Gregory Walton EE" not in out


def test_an_already_known_display_name_is_still_applied():
    # Refusing to INVENT one must not stop an existing binding being applied —
    # that is what `--fix-leaks` is for.
    z = _fix_leaks_pass()
    z.records[("display-name", "gregory walton ee")] = {
        "category": "display-name", "real": "Gregory Walton EE",
        "fake": "Lowther Rolleston VENTRIS", "source": "regex", "count": 0,
        "pattern": P.re.escape("Gregory Walton EE"), "flags": 0}
    out = z.apply(PAIR)
    assert "Gregory Walton EE" not in out, out
    assert "Lowther Rolleston VENTRIS" in out, out


# ── 2. the gate follows the reduction ───────────────────────────────────────

def _reduced_case():
    z = _full_run()
    z.keep_soft = {"EE"}                      # the master `no` on "EE"
    z.note_original("Contact Gregory Walton EE for scheduling.")
    z.note_leaks(["Lowther Rolleston EE"])
    z.leak_report.append({"file": "M.txt", "type": "LEAK", "context": "",
                          "value": "Lowther Rolleston EE", "where": "p.1:1",
                          "notes": ""})
    return z


def test_the_gate_asks_what_the_worksheet_shows():
    z = _reduced_case()
    z.confirm_findings(log)
    rows = [r["value"] for r in z.leak_report]
    assert rows == ["EE"], rows
    # The gate must hold the SAME value, not the old phrasing.
    assert z.leaked == {"ee"}, z.leaked


def test_a_suppressed_remainder_stops_the_quarantine():
    z = _reduced_case()
    z.confirm_findings(log)
    z.suppressed = {"ee"}                     # "EE" is marked `no`
    gating = {v for v in z.leaked if str(v).lower() not in z.suppressed}
    assert not gating, gating                 # the folder can converge


def test_a_remainder_that_is_a_real_name_still_gates():
    # The reduction must not become an amnesty: a genuine survivor left in the
    # remainder still holds the export, under the value the worksheet shows.
    z = _full_run()
    z.note_original("Contact Gregory Walton and Ashely Penuela today.")
    z.note_leaks(["Lowther Ashely"])
    z.leak_report.append({"file": "M.txt", "type": "LEAK", "context": "",
                          "value": "Lowther Ashely", "where": "p.1:1",
                          "notes": ""})
    z.confirm_findings(log)
    assert [r["value"] for r in z.leak_report] == ["Ashely"]
    assert z.leaked == {"ashely"}, z.leaked


def test_a_value_reduced_to_nothing_still_stops_gating():
    # The half that already worked, kept: a finding made only of our own
    # stand-ins never gated and still does not.
    z = _full_run()
    z.note_original("Contact Gregory Walton today.")
    z.note_leaks(["Lowther Rolleston"])
    z.leak_report.append({"file": "M.txt", "type": "LEAK", "context": "",
                          "value": "Lowther Rolleston", "where": "p.1:1",
                          "notes": ""})
    z.confirm_findings(log)
    assert z.leak_report == []
    assert z.leaked == set(), z.leaked
