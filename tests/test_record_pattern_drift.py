"""
A record's own pattern is the SCAN's pattern, so it must be no looser than any
substitution pass — and a keep must see every spelling the term it beats sees.

Three mirror-drift bugs, each confirmed on crafted text before the fix:

* A DISPLAY-NAME record stored a bare `re.escape` pattern with no boundaries
  and no IGNORECASE, while the repeat-substitution pass is word-bounded and
  case-insensitive. `surviving_reals` therefore reported the name against
  clean text wherever it sat INSIDE a longer name ("Wei Li" inside "Wei Lin"),
  and `scrub_survivors` then "cured" it by splicing the fake mid-word:
  "Wei Lin" — a different person — shipped as "<fake of Wei Li>n", with a key
  row promising a reversal onto the wrong name. Detector records (email,
  phone, address, url, ssn) had the identical shape.

* `_keep_spans` matched an operator keep with a bare escape, while the party
  term it must beat folds whitespace runs and both apostrophe marks
  (`_pn_build_pattern`). So a `no` on "Rachel Green's Trust" held for the
  straight-quote spelling and was overridden for Word's "’" spelling, and a
  `no` on "Marcus Delacroix" was overridden exactly where the name wrapped
  across a pleading line — silently, because a kept value is suppressed from
  the worksheet.

* `Pseudonymizer.__init__` skipped the RECORD of a term whose fake the
  self-map guard refused but left the TERM in `self.terms`, so the first
  substitution pass that matched it crashed on the record lookup.

Run:  cd PDF-Linker && python3 -m pytest tests/test_record_pattern_drift.py -v
"""
import pdf_linker as P

DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}


def _pz(terms=()):
    return P.Pseudonymizer(list(terms), DET, registry=P._PnFakeRegistry())


# ── a display name never touches a longer name ──────────────────────────────

def test_a_display_name_never_matches_inside_a_longer_name():
    pz = _pz()
    text = ("From: Wei Li <wli@firmmail.com>\n"
            "Wei Lin, the custodian of records, authenticated the file.")
    out = pz.scrub_survivors(pz.apply(text))
    assert "Wei Lin," in out                  # the OTHER person is untouched
    assert "Wei Li <" not in out              # the display name is faked
    assert not pz.surviving_reals(out)        # and nothing phantom-reported


def test_a_single_word_display_name_never_matches_a_prefix():
    pz = _pz()
    text = ("Served by Rodgers <rodgers@mail.com>.\n"
            "Deputy Rodgerson accepted service.")
    out = pz.scrub_survivors(pz.apply(text))
    assert "Rodgerson" in out


def test_an_all_caps_survivor_of_a_display_name_is_reported():
    pz = _pz()
    pz.apply("From: Yasmin Valadez <yv@firmmail.com>")
    # The scan is case-insensitive like the substitution pass, so a shouting
    # letterhead occurrence of the same name is seen, not silently missed.
    assert any("valadez" in v.lower()
               for v in pz.surviving_reals("YASMIN VALADEZ, paralegal"))


# ── a keep sees the spellings the term sees ─────────────────────────────────

def _kept_pz(value, party):
    terms = P._pn_build_terms([(party, False)], [], [])
    pz = P.Pseudonymizer(terms, {}, registry=P._PnFakeRegistry())
    pz.keep_soft.add(value)
    pz.keep_soft_local.add(value)
    return pz


def test_a_keep_holds_across_the_typographic_apostrophe():
    pz = _kept_pz("Rachel Green's Trust", "Rachel Green's Trust")
    assert "Green’s Trust" in pz.apply("The assets of Rachel Green’s Trust "
                                       "were sold.")


def test_a_keep_holds_across_a_line_wrap():
    pz = _kept_pz("Marcus Delacroix", "Marcus Delacroix")
    out = pz.apply_lines(["Notice was served on Marcus", "Delacroix at home."])
    assert out == ["Notice was served on Marcus", "Delacroix at home."]


# ── a refused record takes its term with it ─────────────────────────────────

def test_a_self_mapped_term_is_dropped_whole():
    t = P._PnTerm("entity", "M & M", "M & M", whole_word=True,
                  case_sensitive=False, priority=1, source="--term")
    pz = P.Pseudonymizer([t], {}, registry=P._PnFakeRegistry())
    # Either the guard reminted a distinct fake (term stays, record exists) or
    # the pair was dropped together — never a term without its record.
    for term in pz.terms:
        assert (term.category, term.real.lower()) in pz.records
    pz.apply("The M & M partnership answered.")   # must not raise
