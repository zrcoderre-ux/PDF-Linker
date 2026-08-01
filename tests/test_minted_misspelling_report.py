"""A misspelling in the export has two possible authors, and the run says which.

The typo fold mints a misspelling ON PURPOSE: a source that spells one party
several ways ("Palladino", "Palladina", "Pallading") must give each spelling a
distinct reversible stand-in, and folding them onto typos of the one fake is
what keeps them reading as one person. A scan mangling a word is a different
thing entirely — it means the page wants re-scanning — and in the export the
two are the same shape.

Every `_PN_CONFUSABLES` pair is a plausible scan slip — that is why the fold
uses it — so reading the export an operator cannot tell the two apart; reading
the log they can. The one collision that mattered most is closed at the source:
"a y came out as a v" is the signature of a page recognised below
`_OCR_LOW_DPI` (the descender is the first stroke lost), so the map is an
involution that mints a `v` only from a `u`, and a v-for-y is now always the
scan's work.

Run:  cd PDF-Linker && python3 -m pytest tests/test_minted_misspelling_report.py -v
"""

import logging

import pdf_linker as P


class _Log:
    """Collect what the run says, at the level it says it."""

    def __init__(self):
        self.lines = []

    def _add(self, msg):
        self.lines.append(str(msg))

    info = warning = error = _add

    def __contains__(self, needle):
        return any(needle in ln for ln in self.lines)

    @property
    def text(self):
        return "\n".join(self.lines)


def _fold(canon, variant):
    """Bind `canon`, then hand the registry a near spelling of it — exactly what
    a document does when OCR reads the same surname two ways."""
    reg = P._PnFakeRegistry()
    base = reg.token(canon.lower(), P._PN_NAME_WORDS, "nametok")
    got = reg.token(variant.lower(), P._PN_NAME_WORDS, "nametok")
    return reg, base, got


def test_a_folded_variant_is_recorded_as_ours():
    reg, base, got = _fold("Palladino", "Palladina")
    assert got != base                      # its own stand-in, still reversible
    assert [(r, f, br, bf) for r, f, br, bf, _op in reg.typo_folds] == [
        ("palladina", got, "palladino", base)]


def test_an_ordinary_pool_draw_is_not_recorded():
    """Two unrelated surnames each draw a clean pool word — nothing was minted
    as a misspelling, so nothing is claimed as one."""
    reg = P._PnFakeRegistry()
    reg.token("palladino", P._PN_NAME_WORDS, "nametok")
    reg.token("hollingsworth", P._PN_NAME_WORDS, "nametok")
    assert reg.typo_folds == []


def test_the_run_names_the_misspellings_it_minted():
    reg, base, got = _fold("Palladino", "Palladina")
    pz = P.Pseudonymizer([], {}, registry=reg)
    log = _Log()
    pz._report_minted_misspellings(log)
    assert "deliberate misspelling" in log
    assert repr(got) in log and repr(base) in log
    assert "'palladina'" in log.text and "'palladino'" in log.text


def test_a_run_that_minted_none_says_nothing():
    """Silence is the useful default: a folder with no folded spelling must not
    make the operator read a report about zero of them."""
    pz = P.Pseudonymizer([], {}, registry=P._PnFakeRegistry())
    log = _Log()
    pz._report_minted_misspellings(log)
    assert log.lines == []


def test_a_long_list_is_capped_but_says_how_many():
    reg = P._PnFakeRegistry()
    reg.typo_folds = [(f"real{i}", f"Fake{i}", "base", "Base", "sub")
                      for i in range(12)]
    pz = P.Pseudonymizer([], {}, registry=reg)
    log = _Log()
    pz._report_minted_misspellings(log)
    assert "12 stand-in(s)" in log
    assert "+4 more" in log
    assert "'Fake11'" not in log.text          # capped
    assert "'Fake0'" in log.text               # ...but the head is shown


def test_the_report_points_at_the_other_author():
    """The log line is only useful if it says what a misspelling NOT listed
    means — otherwise the operator learns nothing about the scan."""
    reg, _base, _got = _fold("Palladino", "Palladina")
    pz = P.Pseudonymizer([], {}, registry=reg)
    log = _Log()
    pz._report_minted_misspellings(log)
    assert "came off the page" in log
    assert str(P._OCR_LOW_DPI) in log.text


def test_the_confusable_map_is_an_involution():
    """The map used to funnel u, w AND y onto `v` — the one letter whose
    appearance-in-place-of-a-y is the signature of a low-dpi scan, so the fold
    was deliberately minting the artifact an operator most needs to read as
    scan damage. Now every letter swaps with exactly one partner: injective
    (each substituted letter has ONE possible source, so the report can name
    the letter it bent) and involutory (the pair reads as one confusion in
    both directions). A change here changes every folded fake, so it must stay
    a deliberate decision and not a silent edit."""
    m = P._PN_CONFUSABLES
    for src, dst in m.items():
        assert m[dst] == src, f"{src}->{dst} is not a symmetric pair"
        assert src != dst
    # Injective follows from the involution, but say it outright — no sinks.
    targets = list(m.values())
    assert len(targets) == len(set(targets))


def test_a_v_can_only_come_from_a_u():
    """The specific collision the redesign closes: `y -> v` belongs to the
    scanner. A fold must never produce it, so a v-for-y in an export now has
    exactly one author and the operator needs no log line to know which."""
    sources_of_v = {s for s, d in P._PN_CONFUSABLES.items() if d == "v"}
    assert sources_of_v == {"u"}
    assert P._PN_CONFUSABLES.get("y") != "v"
    assert P._PN_CONFUSABLES.get("w") != "v"


def test_a_folded_fake_never_bends_y_into_v():
    """End to end: bind a y-heavy fake's real, hand the registry a
    one-substitution variant, and check the minted typo — whatever letter it
    bends — did not turn a y into a v."""
    reg = P._PnFakeRegistry()
    base = reg.token("yancey", P._PN_NAME_WORDS, "nametok")
    got = reg.token("yancoy", P._PN_NAME_WORDS, "nametok")   # o->a slip
    assert got != base
    for i, (b, g) in enumerate(zip(base, got)):
        if b != g:
            assert not (b.lower() == "y" and g.lower() == "v"), (base, got)


def test_the_registry_survives_a_pseudonymizer_without_folds():
    """`_report_minted_misspellings` reads the registry defensively — a test
    double or an older pickled registry has no `typo_folds` and must not take
    the end-of-run key check down with it."""

    class _Bare:
        pass

    pz = P.Pseudonymizer([], {}, registry=P._PnFakeRegistry())
    pz.registry = _Bare()
    log = _Log()
    pz._report_minted_misspellings(log)          # must not raise
    assert log.lines == []
