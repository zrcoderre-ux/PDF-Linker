"""Curing a tracked value the main pass left standing, instead of asking about it.

A worksheet row asking "should I fake this?" for a value the case has ALREADY
bound is not a decision — the fake is minted, the key row exists, and the answer
can only be yes. `scrub_survivors` applies the binding instead of queueing it,
the same shape `scrub_emails` already had for the one category that got it.

Two things put a bound value there, and neither is an operator's call:

  * A RECORD IS NOT A TERM. `_term_cands` iterates `self.terms`, so anything
    minted into `self.records` during the run is substituted only where its own
    minting pass looked — the gap that let a display name be faked at its
    "Name <addr>" pair and nowhere else.
  * `apply`'s overlap resolution drops a shorter candidate wherever a longer one
    claimed the span, even when that longer one is then itself dropped for
    overlapping a citation, leaving the span scrubbed by neither.

What the pass must NOT do is the whole point: a published citation stays
byte-for-byte and an operator KEEP stays verbatim, because it is handed the same
protected set the main pass uses.

Run:  cd PDF-Linker && python3 -m pytest tests/test_survivor_sweep.py -v
"""
import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("pdf_linker", _ROOT / "pdf_linker.py")
pl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(pl)


def _pz(names=(), terms=None, detectors=()):
    reg = pl._PnFakeRegistry()
    t = pl._pn_build_terms(list(names), [], list(terms or []), reg)
    return pl.Pseudonymizer(t, list(detectors), reg), reg


def test_a_record_that_is_not_a_term_is_cured():
    # The documented gap: minted into records during the run, so the main pass
    # only ever replaced it where its own minting pass happened to look.
    pz, _ = _pz()
    pz._detector_record("person", "Marguerite Penuela", lambda v: "Sable Ellery")
    body = ("Declaration of Marguerite Penuela in support. "
            "Marguerite Penuela states:")
    assert pz.surviving_reals(body) == ["Marguerite Penuela"]
    cured = pz.scrub_survivors(body)
    assert "Marguerite Penuela" not in cured
    assert cured.count("Sable Ellery") == 2
    assert pz.surviving_reals(cured) == []


def test_it_applies_the_fake_the_record_already_carries():
    # No new fake, no pool draw, no new key row — that is what makes this a
    # cure rather than a decision. The binding is the one already agreed.
    pz, reg = _pz()
    pz._detector_record("person", "Marguerite Penuela", lambda v: "Sable Ellery")
    before = dict(reg._memo)
    cured = pz.scrub_survivors("Marguerite Penuela signed it.")
    assert "Sable Ellery" in cured
    assert reg._memo == before                 # nothing drawn from any pool


def test_the_occurrence_count_is_recorded():
    # So the key row reads "replaced" rather than "leaked": it WAS replaced.
    pz, _ = _pz()
    rec = pz._detector_record("person", "Marguerite Penuela", lambda v: "Sable Ellery")
    pz.scrub_survivors("Penuela? Marguerite Penuela. Marguerite Penuela.")
    assert pz.records[("person", "marguerite penuela")]["count"] == 2


def test_a_cited_authority_is_never_rewritten():
    # The one failure that is worse than leaving a name in. The party name is
    # faked in ordinary prose and left byte-for-byte inside the citation.
    pz, _ = _pz(names=[("Alameda Plaza", False)])
    src = ("Under Alameda Plaza v. Ford Motor Co. (2020) 9 Cal.5th 1, the rule "
           "is clear. Alameda Plaza signed the lease.")
    cured = pz.scrub_survivors(pz.apply(src))
    assert "Alameda Plaza v. Ford Motor Co. (2020) 9 Cal.5th 1" in cured
    assert "Alameda Plaza signed" not in cured


def test_an_operator_keep_is_left_verbatim():
    # A kept value is present ON PURPOSE. The sweep is handed the same protected
    # set the main pass is, so it cannot undo the decision.
    pz, _ = _pz()
    pz.keep_soft = {"Cal"}
    pz._detector_record("person", "Cal", lambda v: "Bramwell")
    assert pz.scrub_survivors("The Cal report was filed.") == \
        "The Cal report was filed."


def test_a_clean_export_is_returned_untouched():
    # Identity, not a rewrite: a file is only written when its content changes,
    # and a re-run must reproduce a delivered export byte for byte.
    pz, _ = _pz(names=[("Ka Wai Kwan", False)])
    body = pz.apply("Ka Wai Kwan appeared. The motion is denied.")
    assert pz.scrub_survivors(body) is body or pz.scrub_survivors(body) == body
    assert pz.surviving_reals(body) == []


def test_a_self_mapped_record_is_skipped():
    # Nothing to apply, and substituting a value with itself would loop the
    # survivor scan forever.
    pz, _ = _pz()
    pz._detector_record("person", "Same Name", lambda v: "Same Name")
    assert pz.scrub_survivors("Same Name here.") == "Same Name here."


def test_the_scan_and_the_cure_share_one_eligibility_rule():
    # `_surviving_records` is the single rule, so the pair cannot drift: a value
    # the scan reports but the cure cannot touch quarantines an export nothing
    # is able to clean, which is what `_weld_core` exists to prevent for the
    # welded pair.
    pz, _ = _pz()
    pz._detector_record("person", "Marguerite Penuela", lambda v: "Sable Ellery")
    body = "Marguerite Penuela signed."
    assert [r["real"] for r in pz._surviving_records(body)] == \
        pz.surviving_reals(body)


@pytest.mark.parametrize("category", ["person", "entity", "email", "address"])
def test_every_tracked_category_is_swept(category):
    # The pass is the general form of scrub_emails, not another per-category
    # special case.
    pz, _ = _pz()
    pz._detector_record(category, "Redmond Parrish", lambda v: "Lockridge Vane")
    cured = pz.scrub_survivors("Contact Redmond Parrish today.")
    assert "Redmond Parrish" not in cured, category
