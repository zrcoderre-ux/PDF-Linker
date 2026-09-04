"""The Word export path cures what it reports.

`_surviving_records` is the SINGLE eligibility rule the leak scan
(`surviving_reals`, which reports) and the cure pass (`scrub_survivors`, which
repairs) share, so the two can never drift — a value one reports and the other
cannot touch quarantines an export nothing is able to clean.

The PDF path ran `scrub_emails`, `scrub_welded` and `scrub_survivors` before
scanning. The WORD path ran the whole scan battery and none of them, which
inverts the rule: detection out-ran replacement. Each cure exists because
`apply` alone structurally cannot finish — a RECORD IS NOT A TERM, so a display
name is substituted only where its minting pass looked, and `apply`'s overlap
resolution drops a shorter candidate wherever a longer one claimed the span.
On the PDF path those are cured with the fake the record already carries; here
the same value was REPORTED, so `LEAKS.xlsx` carried a row under a value the
key shows `replaced` — a row asking "should I fake this?" about a binding that
already exists, which is not a decision the operator can make.

Run:  cd PDF-Linker && python3 -m pytest tests/test_word_path_cures_survivors.py -v
"""
import inspect
import re

import pdf_linker as P


def _word_body():
    """The source of the Word export path's scrub-and-scan block."""
    return inspect.getsource(P._write_word_text_version)


def _pdf_body():
    return inspect.getsource(P._write_text_version)


CURES = ("scrub_emails", "scrub_welded", "scrub_survivors")


def test_the_word_path_runs_every_cure_the_pdf_path_runs():
    word, pdf = _word_body(), _pdf_body()
    for cure in CURES:
        assert f"pseudonymizer.{cure}(" in pdf, f"{cure} left the PDF path"
        assert f"pseudonymizer.{cure}(" in word, (
            f"{cure} is missing from the Word export path — it reports what it "
            f"cannot repair")


def test_the_word_path_cures_before_it_scans():
    """Order is the whole point: a cure after the scan repairs a file the gate
    has already quarantined."""
    word = _word_body()
    scan = word.index("surviving_reals(body)")
    for cure in CURES:
        assert word.index(f"pseudonymizer.{cure}(") < scan, (
            f"{cure} runs after the leak scan")


def test_both_tiers_of_the_mirror_are_present():
    """`scrub_welded` is the write side of `surviving_reals_reduced`; a cure
    with no scan under-reports and a scan with no cure quarantines."""
    word = _word_body()
    assert "surviving_reals_reduced(body" in word
    assert "spliced=False" in word          # born-digital: hard-seam pass only


def test_a_cure_pass_applies_only_bindings_that_already_exist():
    """What makes adding them safe: the cures mint no fake, draw no pool word
    and add no key row — they apply the fake the record already carries."""
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Zachary Coderre"], [], [], registry=reg)
    pz = P.Pseudonymizer(terms, [], registry=reg)
    body = pz.apply("Zachary Coderre signed the note.")
    before = {str(r["real"]): str(r["fake"]) for r in pz.records.values()}
    minted = set(reg.minted_fakes())

    for cure in CURES:
        body = (getattr(pz, cure)(body, spliced=False)
                if cure == "scrub_welded" else getattr(pz, cure)(body))

    after = {str(r["real"]): str(r["fake"]) for r in pz.records.values()}
    assert after == before                  # no new binding, none moved
    assert set(reg.minted_fakes()) == minted


def test_a_clean_body_is_returned_unchanged():
    """The cures early-out when nothing survived, so an ordinary Word export
    does not move."""
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Zachary Coderre"], [], [], registry=reg)
    pz = P.Pseudonymizer(terms, [], registry=reg)
    body = pz.apply("Zachary Coderre signed the note.")
    out = pz.scrub_survivors(pz.scrub_welded(pz.scrub_emails(body),
                                             spliced=False))
    assert out == body
    assert pz.surviving_reals(out) == []
