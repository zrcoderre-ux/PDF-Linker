"""
A pseudonym mapping must never be self-identical (fake == real). A name made
entirely of single-letter tokens plus punctuation — "M & M", "J&J", "A. B." —
used to fake to itself: the per-token person faker keeps every initial verbatim,
so the "fake" equalled the input. A self-map is a no-op scrub that (a) ships the
real party name in a "clean" export and (b) makes --fix-leaks re-flag the value
forever (a non-terminating loop). Three layers close it: the faker gives
all-initials names a distinct fake, a guard rejects any self-identical record at
the point it is built, and key load self-heals an already-broken row.

Run:  cd PDF-Linker && python3 -m pytest tests/test_no_self_map.py -v
"""
import logging

import openpyxl
import pytest

import pdf_linker as P

log = logging.getLogger("test")


@pytest.mark.parametrize("val", ["M & M", "J&J", "H&M", "A. B.", "M&M",
                                 "m & m", "A & B & C"])
def test_faker_never_self_maps(val):
    reg = P._PnFakeRegistry()
    for t in P._pn_build_terms([], [], [val], reg):
        assert P._pn_norm_map(t.fake) != P._pn_norm_map(t.real), (val, t.fake)


@pytest.mark.parametrize("val,sep", [("M & M", " & "), ("J&J", "&"),
                                     ("A & B", " & ")])
def test_initials_fake_preserves_shape_and_repeats(val, sep):
    reg = P._PnFakeRegistry()
    fake = P._pn_fake_initials_name(val, reg)
    assert sep in fake                              # separators preserved
    r_letters = [c for c in val if c.isalpha()]
    f_letters = [c for c in fake if c.isalpha()]
    assert len(f_letters) == len(r_letters)         # one fake letter per initial
    # A repeated real letter maps to the same fake letter (same-party shape).
    if r_letters[0] == r_letters[-1]:
        assert f_letters[0] == f_letters[-1]
    else:
        assert f_letters[0] != f_letters[-1]


def test_mixed_name_still_keeps_its_initial_verbatim():
    # The all-initials rule must NOT touch a normal name with a real surname.
    fake, _ = P._pn_fake_person("J. Brett Griffin", P._PnFakeRegistry())
    assert fake.startswith("J. ")                   # first initial kept verbatim
    assert "Griffin" not in fake                     # the surname WAS faked


def test_apply_actually_scrubs_the_value():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms([], [], ["M & M"], reg)
    out = P.Pseudonymizer(terms, [], registry=reg).apply("Claim by M & M is denied.")
    assert "M & M" not in out


def test_add_terms_guard_reminting_a_self_mapped_term():
    # A term arriving self-mapped from ANY source (a hand-typed key, a detector)
    # must be re-minted, never recorded as a no-op.
    reg = P._PnFakeRegistry()
    t = P._PnTerm("person", "M & M", "M & M", whole_word=False,
                  case_sensitive=False, priority=2, source="--term")
    z = P.Pseudonymizer([t], [], registry=reg)
    rec = z.records[("person", "m & m")]
    assert P._pn_norm_map(rec["fake"]) != P._pn_norm_map("M & M")


def _write_key(path, rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Category", "Real Value", "Replacement", "Source", "Occurrences"])
    for r in rows:
        ws.append(r)
    wb.save(path)


def test_load_key_self_heals_a_self_mapped_row(tmp_path):
    kp = tmp_path / "pseudonym_key.xlsx"
    _write_key(kp, [["person", "M & M", "M & M", "--term", 3]])
    reg = P._PnFakeRegistry()
    terms, _ = P._pn_load_key(kp, reg, log)
    assert len(terms) == 1
    healed = terms[0]
    assert healed.real == "M & M"
    assert P._pn_norm_map(healed.fake) != P._pn_norm_map("M & M")   # repaired
    # And the repaired binding actually scrubs.
    z = P.Pseudonymizer(terms, [], registry=reg)
    assert "M & M" not in z.apply("M & M appears here.")


def test_self_map_does_not_survive_as_a_leak(tmp_path):
    # The loop's fixed point was: apply() leaves "M & M", the survivor scan
    # re-flags it, forever. With a distinct fake the value is gone, so nothing
    # survives to re-quarantine.
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms([], [], ["M & M"], reg)
    z = P.Pseudonymizer(terms, [], registry=reg)
    scrubbed = z.apply("M & M and M & M again.")
    assert z.surviving_reals(scrubbed) == []      # nothing left to re-quarantine
