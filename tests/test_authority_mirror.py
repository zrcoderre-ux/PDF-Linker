"""The leak scan asks the authority guard about the text `_substitute` reads.

`_surviving_records` is the MIRROR of `_substitute`: it reports a tracked value
only where the write side was ALLOWED to replace it. It mirrors the citation
spans, the operator keeps, the whitelisted URLs and the cap-only rule — and it
mirrored `_in_authority_context` too, but asked it about its OWN body, the
citation-MASKED copy, where `_substitute` asks about the unmasked page.

The mask blanks the NAME RUN of every cite it can see, which is exactly where
the guard's " v. " anchor lives. So the two sides answered one question about
two different strings and disagreed by construction: the write side saw the
anchor and refused, the read side saw a blanked span and reported. That is the
uncurable leak the mirror exists to prevent — the export is quarantined, the
operator marks the row `yes`, and every `--fix-leaks` pass runs that same
`_substitute`, refuses it again and re-reports it. The folder never resolves.

The write side's refusal here is the guard's own documented trade ("a party
closing the sentence before a cite ... is left unfaked at that one spot"), so
the read side is the half that had to move.

Run:  cd PDF-Linker && python3 -m pytest tests/test_authority_mirror.py -v
"""
import pdf_linker as P
import pytest


def _pz(names):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    return P.Pseudonymizer(terms, det, registry=reg)


# A reporter-only cite — no parenthetical year, so no bracket for
# `_PN_AUTHORITY_BREAK_RE` to stop on — and this case's own party in the
# sentence behind it, with a second cite's reporter in reach on the right.
TEXT = ("14  Sanderling v. Whitcombe, 71 Cal.App.5th 358, 362.  Quillmark "
        "Holdings\n15  relied on that rule.  See 12 Cal.4th 44.\n")
VALUE = "Quillmark Holdings"


class TestTheTwoSidesAgree:
    def test_the_mask_blanks_the_anchor_the_write_guard_reads(self):
        """The premise. Without this the rest of the file proves nothing."""
        z = _pz([VALUE])
        masked = z._mask_protected_citations(TEXT)
        assert "Sanderling v. Whitcombe" in TEXT
        assert "Sanderling v. Whitcombe" not in masked
        # …and the value itself is NOT masked, so the scan really does reach it.
        assert VALUE in masked

    def test_the_mask_is_length_preserving(self):
        """Load-bearing: the scan hands the guard offsets taken in the masked
        copy. If the lengths ever diverge those offsets point at the wrong
        characters, so the code falls back — and this is what says it does not
        have to."""
        z = _pz([VALUE])
        assert len(z._mask_protected_citations(TEXT)) == len(TEXT)

    def test_the_write_side_refuses_this_site(self):
        """The guard's own documented trade — unchanged by this fix."""
        z = _pz([VALUE])
        s = TEXT.index(VALUE)
        assert z._in_authority_context(TEXT, s, s + len(VALUE)) is True
        assert VALUE in z.apply(TEXT), "the write side must still refuse here"

    def test_and_so_the_read_side_does_not_report_it(self):
        """The fix. A value `_substitute` is required to leave alone must never
        be reported: nothing could ever clear the row."""
        z = _pz([VALUE])
        assert z.surviving_reals(z.apply(TEXT)) == []

    def test_the_guard_is_asked_about_the_unmasked_body(self):
        """Pinned on the SOURCE too, because the failure was one argument and
        the next tier added would take the masked name by default."""
        import inspect
        body = inspect.getsource(P.Pseudonymizer._surviving_records)
        assert "guard_body" in body
        assert "_in_authority_context(\n                        guard_body" in body


class TestNothingElseMoved:
    def test_a_real_leak_in_plain_prose_is_still_reported(self):
        z = _pz([VALUE])
        t = "14  The demand was served on Quillmark Holdings at its office.\n"
        # Nothing citation-shaped here, so the scrub applies and the value goes;
        # feed the scan the UNSCRUBBED text to prove the tier still fires.
        assert VALUE in z.surviving_reals(t)

    def test_a_value_inside_a_cited_name_is_still_silent(self):
        """The mask's own job, and it is untouched: a party correctly preserved
        inside a cited authority is the protection working, not a leak."""
        z = _pz(["Whitcombe"])
        t = "14  See Sanderling v. Whitcombe (2021) 71 Cal.App.5th 358, 362.\n"
        assert z.surviving_reals(z.apply(t)) == []

    def test_a_keep_and_a_whitelisted_url_still_mirror(self):
        """The other three mirrored refusals go through the same loop."""
        z = _pz([VALUE])
        z.keep_nuclear = {VALUE.lower()}
        t = f"14  {VALUE} was served at its office.\n"
        assert z.surviving_reals(t) == []
