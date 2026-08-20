"""
D2 — a fake in an export must be reversible from the key.

The fee-motion corpus shipped `draft` -> "Ainsworth" 72 times and `review` ->
"Sterling" 84 times, with NEITHER mapping anywhere in `pseudonym_key.xlsx`. A
leak is visible; an unreversible substitution is silent and permanent — the
document reads perfectly and nothing maps it back to what it said.

The path, reproduced in `test_a_released_keep_keeps_its_key_row`: a value the
operator marked KEEP is dropped from the key on the reasoning that a kept value
has no fake to reverse. That reasoning holds only while the keep HELD, and a
soft `no` keep is deliberately RELEASED inside a multi-word capitalized name run
(and inside a full party match). Released, the value is faked by the very row
being dropped.

Run:  cd PDF-Linker && python3 -m pytest tests/test_key_completeness.py -v
"""

import logging
import pathlib
import tempfile

import openpyxl
import pytest

import pdf_linker as P

log = logging.getLogger("test")


def _pz(names=("Helen Rasho",), casenos=("25STCV14710",)):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(names), list(casenos), [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    return P.Pseudonymizer(terms, det, registry=reg)


def _harvest(z, word):
    """Register `word` the way the folder pre-scan does — a bare name token
    guessed from a document, with no party template behind it."""
    fake = z.registry.token(word.lower(), P._PN_NAME_WORDS, "nametok")
    z._add_terms([P._PnTerm("person-token", word, fake, whole_word=True,
                            case_sensitive=False, priority=1,
                            source="document")])
    return fake


def _key_rows(z):
    path = pathlib.Path(tempfile.mkdtemp()) / "pseudonym_key.xlsx"
    z.write_key(path, log)
    if not path.exists():
        return []
    return list(openpyxl.load_workbook(path).active.iter_rows(values_only=True))[1:]


def _reverses(rows, fake):
    return any(str(r[P._PN_KEY_HEADERS.index("Replacement")]) == fake
               for r in rows)


# ───────────────────────────── the defect ───────────────────────────────────

def test_a_released_keep_keeps_its_key_row():
    z = _pz()
    fake = _harvest(z, "Draft")
    # The operator triaged "Draft" out of the LEAKS worksheet with `no`.
    z.keep_soft = {"Draft"}
    z._keep_decisions = {"draft": {"fix": "no", "value": "Draft"}}
    z._keep_local = {"draft"}

    # Standing alone the keep holds; beside a name-shaped word it is RELEASED
    # and the bare token fakes it — which is the whole point of the release.
    out = z.apply("The draft is here. Draft Whitby signed it.")
    assert fake in out, "fixture no longer exercises the keep release"

    rows = _key_rows(z)
    _rp = P._PN_KEY_HEADERS.index("Replacement")
    assert _reverses(rows, fake), (
        f"{fake!r} is in the export and no key row reverses it; "
        f"rows written: {[(r[1], r[_rp]) for r in rows]}")
    assert z.unreversible == [], z.unreversible


def test_a_keep_that_held_still_writes_no_row():
    # The rule the drop exists for is unchanged: a kept value that was really
    # left verbatim has no fake to reverse, so it earns no row. The COUNT is
    # what tells the two apart.
    z = _pz()
    fake = _harvest(z, "Draft")
    z.keep_soft = {"Draft"}
    z._keep_decisions = {"draft": {"fix": "no", "value": "Draft"}}
    z._keep_local = {"draft"}
    out = z.apply("The draft is here and the draft is late.")
    assert fake not in out, "fixture no longer keeps the value verbatim"
    assert not _reverses(_key_rows(z), fake), (
        "a value that was never faked must not promise a reversal")


# ─────────────────────────── the class-wide gate ────────────────────────────

def test_gate_reports_an_applied_fake_with_no_row():
    z = _pz()
    fake = _harvest(z, "Draft")
    z.apply("Draft Whitby signed it.")
    applied, _stray = z.unreversible_fakes(keyrows=[])   # key wrote nothing
    assert (("Draft", fake, "person-token") in applied), (
        f"the gate missed an applied fake with no row: {applied}")


def test_gate_accepts_a_word_for_word_composed_fake():
    # "Ainsworth Sackett" is reversed by its two TOKEN rows; the gate must
    # understand that, or it would cry wolf on every composed party name.
    z = _pz(names=("Helen Rasho",))
    z.apply("Helen Rasho signed it.")
    rows = [r for r in z.records.values() if r["category"] == "person-token"]
    applied, _stray = z.unreversible_fakes(keyrows=rows)
    assert applied == [], applied


def test_gate_is_silent_on_a_clean_run():
    z = _pz()
    z.apply("Helen Rasho v. Acme, Case No. 25STCV14710.")
    rows = list(z.records.values())
    assert z.unreversible_fakes(keyrows=rows) == ([], [])


def test_gate_flags_a_minted_fake_standing_in_an_export():
    # Second tier: a stand-in the registry minted that no record accounts for,
    # found by reading the export back. Warning-only — a pool surname can also
    # be an ordinary word — but it must not be silent.
    z = _pz()
    fake = z.registry.token("penuela", P._PN_NAME_WORDS, "nametok")
    _applied, stray = z.unreversible_fakes(
        keyrows=[], texts=[f"Declaration of {fake} in support."])
    assert any(f == fake.lower() for _r, f, _c in stray), stray


# ───────────────────── the prose screen (D2 item 3) ─────────────────────────

def test_a_lowercase_prose_word_is_not_a_harvested_name():
    z = _pz()
    _harvest(z, "Draft")
    corpus = ("Draft opposition to motion. Counsel drafted the reply and the "
              "draft was circulated; a further draft followed the draft "
              "conference.")
    assert "Draft" in z.prune_prose_word_terms(corpus), (
        "a word the corpus writes in lower-case is prose, not a party name")
    assert ("person-token", "draft") not in z.records


def test_the_party_templates_own_word_survives_the_prose_screen():
    # A party really named Green keeps their term however the prose reads —
    # the screen only ever second-guesses a DOCUMENT harvest.
    z = _pz(names=("Green",))
    corpus = ("Green testified. The green vehicle, a green sedan, was green "
              "when purchased and remains green today.")
    assert ("person", "green") in z.records, "fixture no longer registers Green"
    assert z.prune_prose_word_terms(corpus) == []
    assert ("person", "green") in z.records


def test_a_capitalised_harvested_name_survives_the_prose_screen():
    z = _pz()
    _harvest(z, "Penuela")
    corpus = "Penuela signed. See Penuela Decl. Penuela further states."
    assert z.prune_prose_word_terms(corpus) == []
    assert ("person-token", "penuela") in z.records


def test_one_lowercase_slip_does_not_unbind_a_name():
    z = _pz()
    _harvest(z, "Penuela")
    corpus = "Penuela signed. Penuela states. An OCR slip wrote penuela once."
    assert z.prune_prose_word_terms(corpus) == []
