"""A REVIEW row never names a value the key already binds.

A worksheet row is a QUESTION — "is this a name, and should I fake it?" For a
value already in `pseudonym_key.xlsx` the tool has ANSWERED it: the fake is
minted, the binding is written, and every occurrence the scrub was allowed to
reach carries the stand-in. So the row is unanswerable in both directions —
`yes` mints a term for a value that already has one, `no` says leave verbatim a
value the exports are full of the stand-in for — and `--fix-leaks` cannot clear
it, because that pass runs the same `_substitute` that refused the site in the
first place.

What put one there is the deliberate silence of `_surviving_records`. It is the
MIRROR of `_substitute`, so it reports a tracked value only where the write side
was allowed to replace it, and says nothing about a real standing inside a
protected citation, an operator KEEP, a whitelisted verification link, or as the
lower-case occurrence of a cap-only bare token. The REVIEW tiers that read the
output RAW have no such mirror.

The two-tier design read back: a bound value really standing where the scrub
could have reached it is `surviving_reals`' finding, reported as a LEAK, which
gates delivery — and a LEAK row is never screened here.

Run:  cd PDF-Linker && python3 -m pytest tests/test_bound_value_not_a_review_row.py -v
"""
import pdf_linker as P


def _pz(names=(), terms_extra=()):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), list(terms_extra), [], registry=reg)
    return P.Pseudonymizer(terms, [], registry=reg)


def _rows(pz, findings):
    """Put `findings` (class, value) on both the worksheet list and the review
    list the way a per-file block does, then run the folder-level confirm."""
    pz.leak_report = [{"file": "Brief.txt", "type": c, "value": v,
                       "where": "p.1:1"} for c, v in findings]
    pz.review = list(findings)
    pz.confirm_findings(None)
    return ([r["value"] for r in pz.leak_report], [v for _c, v in pz.review])


# ── the delivered shape ─────────────────────────────────────────────────────

def test_a_bar_number_kept_inside_a_cite_is_not_a_review_row():
    """The reported case. A State Bar number is bound off the attorney line and
    faked there; the same number stands byte-for-byte inside a published cite,
    which `_substitute` refuses to touch and `_surviving_records` therefore
    refuses to report. `reid_scan` reads the output raw and reported it — under
    the very value the key shows `replaced`."""
    pz = _pz()
    src = ("Counsel: Jane Roe (State Bar No. 214785).\n"
           "See Roe v. Bell (State Bar No. 214785) (2019) 33 Cal.App.5th 1.")
    pz.register_identifiers(src)
    out = pz.apply(src)

    # bound, faked, and in the key
    assert "214785" in pz.bound_reals()
    assert "285252" not in [str(r["real"]) for r in pz.records.values()]
    assert any(r["count"] > 0 for r in pz.records.values())
    # the write side kept the cite verbatim, and the leak tier is rightly quiet
    assert "See Roe v. Bell (State Bar No. 214785)" in out
    assert pz.surviving_reals(out) == []
    # the raw-reading tier still finds it...
    assert ("REID bar number", "214785") in pz.reid_scan(out)
    # ...and it never reaches the worksheet.
    sheet, review = _rows(pz, pz.review)
    assert sheet == [] and review == []


# ── the rule, stated ────────────────────────────────────────────────────────

def test_a_leak_row_for_a_bound_value_is_never_screened():
    """`surviving_reals` reports nothing BUT bound values, so screening the
    LEAK tier would empty the gate. A bound value standing where the scrub was
    allowed to reach it is exactly what must still be asked about."""
    pz = _pz(["Sunrise Motors Group"])
    real = "Sunrise Motors Group"
    assert P.Pseudonymizer._finding_key(real) in pz.bound_reals()
    sheet, _review = _rows(pz, [])
    pz.leak_report = [{"file": "Brief.txt", "type": "LEAK", "value": real,
                       "where": "p.1:1"}]
    pz.review = []
    pz.confirm_findings(None)
    assert [r["value"] for r in pz.leak_report] == [real]


def test_a_value_the_key_does_not_bind_still_earns_its_row():
    """The screen is about bindings, not about names: an unbound survivor is
    what the REVIEW tiers exist for."""
    pz = _pz(["Sunrise Motors Group"])
    sheet, review = _rows(pz, [("unscrubbed name?", "Travelers Casualty")])
    assert sheet == ["Travelers Casualty"]
    assert review == ["Travelers Casualty"]


def test_the_identity_ignores_case_and_a_pleading_wrap():
    """A scan reports the run as the page printed it, and a run crossing a
    gutter carries the wrap's own spacing — two spellings of one value, not
    two values."""
    pz = _pz(["Sunrise Motors Group"])
    sheet, review = _rows(pz, [("unscrubbed name?", "SUNRISE   MOTORS\n Group")])
    assert sheet == [] and review == []


def test_a_binding_that_matched_nothing_screens_too():
    """A count of zero is not the opposite case. A term whose only occurrences
    were line-wrapped matches nothing and is STILL a binding the key carries
    and that `yes` cannot add to."""
    pz = _pz(["Sunrise Motors Group"])
    rec = next(r for r in pz.records.values()
               if str(r["real"]) == "Sunrise Motors Group")
    assert rec["count"] == 0                    # nothing applied in this test
    sheet, review = _rows(pz, [("unscrubbed name?", "Sunrise Motors Group")])
    assert sheet == [] and review == []


def test_every_review_tier_is_covered_by_the_one_screen():
    """Asked at the single choke point every finding passes through, so a tier
    added later cannot be added without it. Four scans carried the screen by
    hand and six did not; the class of the row is irrelevant here."""
    pz = _pz(["Sunrise Motors Group"])
    classes = ["unscrubbed name?", "REID bar number", "half-scrubbed name?",
               "url/domain", "defined name?", "party acronym",
               "name on a form rule?", "possible contact?"]
    sheet, review = _rows(pz, [(c, "Sunrise Motors Group") for c in classes])
    assert sheet == [] and review == []
