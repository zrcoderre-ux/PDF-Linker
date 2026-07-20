"""
A US state (or DC) name is geography, not identity: it names no one and reads
the same for every business there, so it is kept VERBATIM inside a company/
entity party name and only the OTHER words are faked ("California Pizza Kitchen"
-> keep "California"). Scoped to entities on purpose — a state word that is part
of a PERSON's name (surname "Washington", first name "Georgia") is still an
identifier and is faked, so it never leaks.

Run:  cd PDF-Linker && python3 -m pytest tests/test_state_names.py -v
"""
import pytest

import pdf_linker as P


def _fake(value, text=None):
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms([value], [], [], registry=reg)
    z = P.Pseudonymizer(terms, [], registry=reg)
    return z.apply(text if text is not None else value)


@pytest.mark.parametrize("value,state,other", [
    ("California Pizza Kitchen, Inc.", "California", "Pizza"),
    ("Texas Roadhouse, Inc.", "Texas", "Roadhouse"),
    ("Delaware Widgets Limited", "Delaware", "Widgets"),
    ("Washington Mutual Bank", "Washington", "Mutual"),
    ("Ohio Valley Auto Group", "Ohio", "Valley"),
])
def test_state_kept_verbatim_in_entity_other_words_faked(value, state, other):
    out = _fake(value)
    assert state in out                  # the state name survives
    assert other not in out              # a distinctive word was faked


@pytest.mark.parametrize("value,state", [
    ("New York Life Insurance Company", "New York"),
    ("North Carolina Furniture Direct, Inc.", "North Carolina"),
    ("New Jersey Transit Holdings, LLC", "New Jersey"),
])
def test_multiword_state_kept_as_a_unit(value, state):
    assert state in _fake(value)


def test_state_kept_mid_name():
    out = _fake("Bay Cities of Ohio Holdings, LLC")
    assert " of Ohio " in " " + out + " "     # the mid-name state survives
    assert "Bay Cities" not in out             # the distinctive lead was faked


def test_leading_new_is_faked_when_not_part_of_a_state():
    # "new" is kept ONLY inside a multi-word state; alone it is an ordinary word
    # and the name around it fakes normally.
    out = _fake("New Horizon Robotics, Inc.")
    assert "Horizon" not in out
    assert "New York" not in out               # no spurious state introduced


@pytest.mark.parametrize("value,part", [
    ("Georgia Thompson", "Georgia"),
    ("John Washington", "Washington"),
    ("Virginia Nakamura", "Virginia"),
])
def test_state_word_in_a_person_name_is_still_faked(value, part):
    # A person is not an entity: a state-word name is identifying and must fake.
    assert part not in _fake(value)


def test_state_keep_flags_helper():
    assert P._pn_state_keep_flags(["california", "pizza", "kitchen"]) == \
        [True, False, False]
    assert P._pn_state_keep_flags(["new", "york", "life"]) == [True, True, False]
    # bare "new" (not followed by a state word) is not kept
    assert P._pn_state_keep_flags(["new", "horizon"]) == [False, False]
