"""
Firm furniture — "LAW OFFICES OF …", "& Associates", "the …" — is never faked.

Those words name the trade and a connector, not a party, so faking them hides
nothing and destroys the caption ("Braxton Mansffield bancroft Merrick C.
Whitlock"). They must be kept verbatim inside a composed fake, must never be
registered as a bare token, must never be harvested into a key row, and — the
loop that made this survive every KEEP the operator typed — must never come
BACK as a live term when an older key is reused.

Run:  cd PDF-Linker && python3 -m pytest tests/test_firm_furniture.py -v
"""
import logging

import openpyxl
import pytest

import pdf_linker as P

log = logging.getLogger("test")
DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}

FURNITURE = ("law", "laws", "office", "offices", "firm", "of", "the", "and",
             "associates", "associated", "attorney", "attorneys", "counsel")


# ── composing a fake ────────────────────────────────────────────────────────

@pytest.mark.parametrize("real", [
    "Law Offices of Scott C. Stratman",
    "Law Office of Steven W Burt",
    "Ryan G. Block Associated Attorney",
    "the Waggoner",
])
def test_person_path_keeps_furniture_verbatim(real):
    fake, _bare = P._pn_fake_person(real, P._PnFakeRegistry())
    for r, f in zip(real.split(), fake.split()):
        if P._pn_word_base(r) in FURNITURE:
            assert f == r, f"{real!r} -> {fake!r}: {r!r} was faked as {f!r}"
    # ...and the party itself is still scrubbed.
    assert "Stratman" not in fake and "Burt" not in fake
    assert "Waggoner" not in fake and "Block" not in fake


def test_entity_path_keeps_furniture_and_initials():
    fake = P._pn_fake_entity("Law Offices of Philip Y Kim, APC",
                             P._PnFakeRegistry())
    assert fake.startswith("Law Offices of ")
    assert fake.endswith(", APC")
    assert " Y " in fake          # a lone initial is not a whole entity word
    assert "Kim" not in fake and "Philip" not in fake


def test_firm_name_reads_as_a_firm():
    """The whole point: the fake still says what kind of thing it names."""
    reg = P._PnFakeRegistry()
    assert P._pn_fake_entity("Alder Law, P.C.", reg).endswith(" Law, P.C.")
    assert P._pn_fake_entity("Mitilian Law Group", reg).endswith(" Law Group")


@pytest.mark.parametrize("real", ["The Law Firm", "Attorneys at Law"])
def test_an_all_furniture_name_still_scrubs(real):
    """Keeping the furniture must never leave the fake equal to the real value —
    that ships the name in a "clean" export and loops --fix-leaks forever."""
    fake, _ = P._pn_fake_person(real, P._PnFakeRegistry())
    assert P._pn_norm_map(fake) != P._pn_norm_map(real)
    ent = P._pn_fake_entity(real, P._PnFakeRegistry())
    assert P._pn_norm_map(ent) != P._pn_norm_map(real)


def test_furniture_is_never_a_bare_token():
    terms = P._pn_build_terms(
        ["Law Offices of Scott C. Stratman", "Law Offices of Philip Y Kim, APC"],
        [], [])
    bare = {t.real.lower() for t in terms
            if t.category in ("person-token", "entity-token")
            and len(t.real.split()) == 1}
    assert not (bare & set(FURNITURE)), f"bare furniture tokens: {bare}"
    assert "stratman" in bare


def test_no_pool_word_is_spent_on_furniture():
    """The pools are drawn without replacement; a caption with three firms in it
    used to burn a surname apiece on "Law", "Offices" and "of"."""
    reg = P._PnFakeRegistry()
    P._pn_build_terms(["Law Offices of Scott C. Stratman"], [], [], registry=reg)
    used = len(reg._used)
    reg2 = P._PnFakeRegistry()
    P._pn_build_terms(["Scott C. Stratman"], [], [], registry=reg2)
    assert used == len(reg2._used)


# ── the key round trip ──────────────────────────────────────────────────────

def _write_and_reload(tmp_path, names, sample):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), [], [], registry=reg)
    pz = P.Pseudonymizer(terms, DET, registry=reg)
    pz.apply(sample)
    key = tmp_path / "pseudonym_key.xlsx"
    pz.write_key(key, log)
    rows = [r for ws in openpyxl.load_workbook(key).worksheets
            for r in ws.iter_rows(min_row=2, values_only=True) if r and r[0]]
    reg2 = P._PnFakeRegistry()
    loaded, _dec = P._pn_load_key(key, reg2, log)
    return rows, loaded


def test_key_carries_no_furniture_token_row(tmp_path):
    rows, _ = _write_and_reload(
        tmp_path, ["Law Offices of Scott C. Stratman"],
        "Served by Law Offices of Scott C. Stratman on May 1.")
    tokens = {str(r[1]).lower() for r in rows if str(r[0]).endswith("-token")}
    assert not (tokens & set(FURNITURE)), f"furniture rows in key: {tokens}"
    assert "stratman" in tokens


def test_a_stale_furniture_row_is_not_reloaded_as_a_term(tmp_path):
    """The loop this closes: an older key harvested a row per word, and every
    row comes back as a live matching term — so "the" was faked document-wide
    on the next run whatever the operator bracketed."""
    key = tmp_path / "pseudonym_key.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Category", "Real Value", "Replacement", "Status", "Source",
               "Occurrences"])
    ws.append(["person", "the Waggoner", "chetwood Atwater", "replaced",
               "--term", 19])
    ws.append(["person-token", "the", "chetwood", "replaced", "--term", 19])
    ws.append(["person-token", "of", "bancroft", "no match", "spreadsheet", 0])
    ws.append(["person-token", "Law", "Braxton", "no match", "spreadsheet", 0])
    ws.append(["person-token", "Waggoner", "Atwater", "replaced", "--term", 3])
    wb.save(key)

    terms, _dec = P._pn_load_key(key, P._PnFakeRegistry(), log)
    reals = {t.real.lower() for t in terms}
    assert not (reals & {"the", "of", "law"})
    assert "waggoner" in reals
    # ...and the stored composed fake is repaired, so the folder stops
    # reproducing "chetwood" the moment the key is reused.
    full = next(t for t in terms if t.category == "person")
    assert full.fake == "the Atwater"


def test_reloaded_key_leaves_the_words_alone(tmp_path):
    key = tmp_path / "pseudonym_key.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Category", "Real Value", "Replacement", "Status", "Source",
               "Occurrences"])
    ws.append(["person-token", "the", "chetwood", "replaced", "--term", 19])
    ws.append(["person-token", "Offices", "Mansffield", "replaced",
               "spreadsheet", 4])
    ws.append(["person-token", "Stratman", "Whitlock", "replaced",
               "spreadsheet", 4])
    wb.save(key)

    reg = P._PnFakeRegistry()
    terms, _dec = P._pn_load_key(key, reg, log)
    out = P.Pseudonymizer(terms, DET, registry=reg).apply(
        "The Law Offices of Stratman filed the opposition.")
    assert "the opposition" in out
    assert "Law Offices of" in out
    assert "Stratman" not in out
