"""
An e-mail display name must scrub everywhere it is printed, not only beside the
address that revealed it.

`_display_name_cands` recognises the NAME in a "Name <addr@domain>" pair and
mints a `display-name` record for it. The record goes into `self.records` — so
`surviving_reals` reports it and `write_key` writes a reversal row for it — but
it never went into `self.terms`, and `_term_cands` iterates `self.terms`. So the
name was faked at the pair site and nowhere else: a firm's paralegal, named once
beside her address and then printed on every page of the letterhead, survived on
all of them. Worse than a plain miss, the key then PROMISED the reversal, so
DeAnonymize would map the fake back onto pages where the real name was still
standing.

Run:  cd PDF-Linker && python3 -m pytest tests/test_display_name_repeat.py -v
"""
import logging

import pdf_linker as P

log = logging.getLogger("test")

PAIR = "Yasmin Valadez <Valadez@lawbrothers.com>"


def _pz(names=("Law Brothers, LLP",)):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    return P.Pseudonymizer(terms, list(P._PN_DEFAULT_DETECTORS), registry=reg)


def _fake_of(z):
    return z.records[("display-name", "yasmin valadez")]["fake"]


def test_standalone_occurrence_is_faked_with_the_pair_s_fake():
    z = _pz()
    z.apply(PAIR)
    fake = _fake_of(z)
    out = z.apply("Prepared by Yasmin Valadez, paralegal.")
    assert "Yasmin Valadez" not in out
    assert fake in out


def test_same_text_covers_the_pair_and_its_repeats_in_one_pass():
    # The repeat pass runs after the pair pass, so a name first met in THIS text
    # has its other occurrences covered now — not only from the next page on.
    z = _pz()
    out = z.apply(f"{PAIR}\nYasmin Valadez\nYASMIN VALADEZ")
    assert "Valadez" not in out
    assert z.surviving_reals(out) == []


def test_all_caps_letterhead_is_case_matched():
    z = _pz()
    z.apply(PAIR)
    out = z.apply("YASMIN VALADEZ | LAW BROTHERS")
    assert "YASMIN VALADEZ" not in out
    assert out.split("|")[0].strip().isupper()


def test_no_longer_reported_as_a_surviving_real():
    z = _pz()
    z.apply(PAIR)
    body = z.apply("Contact Yasmin Valadez for scheduling.")
    assert z.surviving_reals(body) == []


def test_never_matches_inside_a_longer_word():
    z = _pz()
    z.apply(PAIR)
    text = "The Yasmin Valadezian doctrine is inapposite."
    assert z.apply(text) == text


def test_rescrubbing_is_a_fixed_point():
    # Applying to already-scrubbed text must not mint a second generation off
    # our own fake — the reversal chain would grow by one on every re-run.
    z = _pz()
    once = z.apply(f"{PAIR}\nYasmin Valadez")
    assert z.apply(once) == once
