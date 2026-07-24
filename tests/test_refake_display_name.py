"""
A display-name ("Name <addr@domain>") must not be re-faked on a re-run. The
previous run's fake sits beside its already-faked e-mail in the scrubbed .txt;
without the own-fakes guard the display-name path treated that fake as a fresh
real name and minted a new generation off it, growing pseudonym_key.xlsx and the
reversal chain by one every run. The guard mirrors _detector_cands.

Run:  cd PDF-Linker && python3 -m pytest tests/test_refake_display_name.py -v
"""
import logging
from pathlib import Path

import pytest

import pdf_linker as P

log = logging.getLogger("test")


def _seed_own_fakes(pz):
    # Both real entry points (fix-leaks ~11528, full-run reuse ~11889) seed
    # _own_fakes from the records they load; mirror that here.
    for r in pz.records.values():
        f = r.get("fake")
        if f:
            pz._own_fakes.add(str(f).lower().rstrip(" .,;:"))


def test_display_name_apply_is_idempotent():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Fairfax Sterling"], [], [], registry=reg)
    pz = P.Pseudonymizer(terms, [], registry=reg)   # empty detectors, like fix-leaks
    _seed_own_fakes(pz)

    text = "Fairfax S. Sterling <fairfax@postbox2.org>"
    first = pz.apply(text)
    assert first != text                             # it did fake the pair once
    disp_after_first = {k for (c, k) in pz.records if c == "display-name"}

    second = pz.apply(first)                          # feed the fake back in
    third = pz.apply(second)
    assert first == second == third                   # a fixed point, not a chain
    # No NEW display-name record minted off our own fake.
    assert {k for (c, k) in pz.records if c == "display-name"} == disp_after_first


def test_display_name_row_count_stable_across_key_reload(tmp_path):
    kp = tmp_path / "pseudonym_key.xlsx"

    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Fairfax Sterling"], [], [], registry=reg)
    pz = P.Pseudonymizer(terms, [], registry=reg)
    _seed_own_fakes(pz)
    run1 = pz.apply("Fairfax S. Sterling <fairfax@postbox2.org>")
    pz.write_key(kp, log)

    # Re-run: fresh registry, reload the key (the authoritative-binding path),
    # feed run-1's already-scrubbed output back in.
    reg2 = P._PnFakeRegistry()
    terms2, _ = P._pn_load_key(kp, reg2, log)
    pz2 = P.Pseudonymizer(terms2, [], registry=reg2)
    _seed_own_fakes(pz2)
    disp_before = {k for (c, k) in pz2.records if c == "display-name"}
    run2 = pz2.apply(run1)

    assert run2 == run1                                # stable, no new generation
    disp_after = {k for (c, k) in pz2.records if c == "display-name"}
    assert disp_after == disp_before                   # no fake-of-fake row added
