"""A `no` typed in THIS folder survives the folder's own re-harvest.

`_pn_retire_kept_key_terms` drops the pseudonym key's own row for a value the
operator marked `no`, so the key comes back clean. But the folder PRE-SCAN then
re-reads the same name out of the PDF as a fresh party term, the full-party
override in `_keep_spans` releases the keep, and the value is faked again by the
leftover token rows — "Marcus Delacroix" came back as "Rathmore Symington",
composed from `Marcus` and `Delacroix`. The log meanwhile said the `no` "will be
honored".

Two things had to change, and the second was the one actually doing the damage:

  * `keep_soft_local` — a `no` typed HERE (this folder's key or LEAKS) is an
    instruction about this case's parties, not another folder's lesson about a
    word, so it beats a party match the keep COVERS. It still yields to one that
    reaches BEYOND the kept text, which is what stops a single-word `no` leaving
    a longer party standing.
  * `scrub_welded` was never handed the keep spans. Every other write path gets
    them (`apply`, `apply_lines`, `scrub_survivors`), so the keep held through
    the substitution and was then undone by the reduced pass, which reads
    through the alphanumeric reduction and never sees the word boundaries the
    keep was matched on. Its detection mirror `surviving_reals_reduced` had the
    same gap and had to move with it, or the export would be quarantined for a
    value the substituter now refuses to touch.

Run:  cd PDF-Linker && python3 -m pytest tests/test_local_keep_survives_reharvest.py -v
"""
import logging

import pdf_linker as P

log = logging.getLogger("test")

PARTIES = ["Helen Rasho", "Marcus Delacroix", "Court Reporter Services, LLC"]
TEXT = ("Plaintiff Helen Rasho and Marcus Delacroix filed the complaint. "
        "Court Reporter Services, LLC transcribed the hearing.")


def _pz(soft=(), local=(), drop_full=None):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(PARTIES), [], [], registry=reg)
    if drop_full:
        # The state a re-run actually reaches: the key's own row for the kept
        # value was retired, and only the bare token rows survive it.
        terms = [t for t in terms if str(t.real).lower() != drop_full.lower()]
    z = P.Pseudonymizer(terms, list(P._PN_DEFAULT_DETECTORS), registry=reg)
    z.keep_soft, z.keep_soft_local = set(soft), set(local)
    return z


# ── the fix ─────────────────────────────────────────────────────────────────

def test_a_local_no_on_a_party_name_is_left_verbatim():
    z = _pz(soft=["Marcus Delacroix"], local=["Marcus Delacroix"])
    out = z.apply(TEXT)
    assert "Marcus Delacroix" in out
    # ...and the OTHER parties are still scrubbed. A keep is one value, not an
    # amnesty.
    assert "Helen Rasho" not in out
    assert "Court Reporter Services, LLC" not in out


def test_it_survives_the_re_harvest_that_replaces_the_retired_row():
    # The full person term is gone (retired by the `no`); the pre-scan's token
    # rows are what re-faked the name word by word.
    z = _pz(soft=["Marcus Delacroix"], local=["Marcus Delacroix"],
            drop_full="Marcus Delacroix")
    out = z.apply(TEXT)
    assert "Marcus Delacroix" in out, out


def test_the_reduced_cure_no_longer_undoes_the_keep():
    # `scrub_welded` ran AFTER the substitution and put the fake back. This is
    # the pass that actually broke it end to end.
    z = _pz(soft=["Marcus Delacroix"], local=["Marcus Delacroix"],
            drop_full="Marcus Delacroix")
    out = z.scrub_welded(z.apply(TEXT), spliced=True)
    assert "Marcus Delacroix" in out, out
    out = z.scrub_survivors(out)
    assert "Marcus Delacroix" in out, out


def test_the_reduced_scan_does_not_report_what_the_cure_now_refuses():
    # Detection must never out-run replacement: a value reported here but
    # refused there quarantines an export nothing can ever clean.
    z = _pz(soft=["Marcus Delacroix"], local=["Marcus Delacroix"],
            drop_full="Marcus Delacroix")
    out = z.scrub_welded(z.apply(TEXT), spliced=True)
    assert "Marcus Delacroix" not in z.surviving_reals_reduced(out, spliced=True)
    assert "Marcus Delacroix" not in z.surviving_reals(out)


# ── the two boundaries that keep it safe ────────────────────────────────────

def test_an_inherited_no_still_loses_to_the_party_match():
    """The cross-case safety rule is untouched.

    A `no` off the master KEEP sheet is another folder's lesson about a word,
    not an instruction about this case's parties — it must keep losing, or one
    folder's decision would silently un-scrub a party in every other folder.
    """
    z = _pz(soft=["Marcus Delacroix"], local=[])       # inherited, not local
    out = z.apply(TEXT)
    assert "Marcus Delacroix" not in out, out


def test_a_one_word_local_no_cannot_leave_a_longer_party_standing():
    """`no` on "Court" keeps the standalone word and still fakes the firm.

    This is why the tier is released by a party match reaching BEYOND the kept
    text rather than by none at all: protecting the span outright would drop the
    party candidate that overlaps it and leave "Court Reporter Services, LLC" in
    the clear — the exact failure the party override exists to prevent.
    """
    z = _pz(soft=["Court"], local=["Court"])
    out = z.apply(TEXT + " Counsel appeared for the Court on that date.")
    assert "Court Reporter Services, LLC" not in out, out
    assert "for the Court on that date" in out, out


def test_a_local_no_covering_only_part_of_a_party_still_releases():
    # "Rasho" alone is covered by the keep, but the party "Helen Rasho" reaches
    # past it, so the party is still faked whole.
    z = _pz(soft=["Rasho"], local=["Rasho"])
    out = z.apply(TEXT)
    assert "Helen Rasho" not in out, out
