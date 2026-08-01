"""
Service-of-process vocabulary is never a name.

A motion-to-quash batch shipped with the vocabulary of its own subject matter
replaced by surnames: "NOTICE AND MOTION TO MABRY SERVICE OF SUMMONS" (Quash),
"ELDRIDGE OF SERVICE" (Proof), "a registered California process radley"
(Server), and "https://scholar.denholm.com/" (Google). `_PN_COMMON_WORDS` was
built out of demurrer / summary-judgment / arbitration / employment corpora and
carried no service-of-process vocabulary at all, so a capitalized "Process
Server Institute" harvested "Server" as a name and applied it case-
insensitively across four files.

The words came back through the KEY on every re-run too — a loaded row is a
live term — so the gazetteer fix alone could not retire them:
`_pn_load_key` now declines a single-word HARVESTED person/entity row whose
word is ordinary vocabulary, exactly as it already declined generic `*-token`
rows. An AUTHORITATIVE row (template / --term) is never declined.

Vocabulary that doubles as a real surname (Bond, Branch, Store, Manager) is in
`_PN_SERVICE_GENERIC_WORDS`, not `_PN_COMMON_WORDS`: withheld from ever
becoming a bare token, still reportable when a party really carries the name.

Run:  cd PDF-Linker && python3 -m pytest tests/test_service_vocab.py -v
"""

import logging
import openpyxl
import pytest

import pdf_linker as P

log = logging.getLogger("test")


# ─────────────────── the vocabulary is generic, tier by tier ────────────────

@pytest.mark.parametrize("word", [
    "quash", "quashing", "summons", "subpoena", "server", "process", "proof",
    "diligence", "substituted", "mailbox", "registered", "registration",
    "commercial", "recipient", "google", "scholar",
])
def test_service_vocabulary_is_never_a_bare_token(word):
    assert P._pn_is_generic_token(word), (
        f"{word!r} is service-of-process vocabulary, not a name")


@pytest.mark.parametrize("word", ["store", "bond", "manager", "custodian"])
def test_surname_capable_vocabulary_is_withheld_but_reportable(word):
    # Never a bare token ("The UPS Store" must not mint "Store" -> surname)...
    assert P._pn_is_generic_token(word)
    # ...but NOT boilerplate to the leak scans: a party really named Bond
    # stays reportable, which is why these are not in _PN_COMMON_WORDS.
    assert word not in P._PN_COMMON_WORDS


def test_pools_do_not_collide_with_the_new_vocabulary():
    added = {"quash", "summons", "server", "process", "proof", "google",
             "scholar", "store", "bond", "manager", "custodian"}
    pools = ({w.lower() for w in P._PN_NAME_WORDS}
             | {w.lower() for w in P._PN_ENTITY_WORDS}
             | {w.lower() for w in P._PN_STREET_NAMES}
             | {w.lower() for w in P._PN_CITY_NAMES})
    assert not added & pools


# ─────────────────── the key stops resurrecting the bad rows ────────────────

def _key(tmp_path, rows):
    p = tmp_path / "pseudonym_key.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(list(P._PN_KEY_HEADERS))
    heads = [h.lower() for h in P._PN_KEY_HEADERS]

    def row(**kw):
        return [kw.get(h.replace(" ", "_"), "") for h in heads]

    for r in rows:
        ws.append(row(**r))
    wb.save(p)
    return p


def test_a_harvested_common_word_row_builds_no_term(tmp_path):
    p = _key(tmp_path, [
        {"category": "person", "real_value": "Server", "replacement": "Radley",
         "source": "document", "occurrences": 103},
        {"category": "person", "real_value": "Quash", "replacement": "Mabry",
         "source": "document", "occurrences": 35},
    ])
    reg = P._PnFakeRegistry()
    terms, _dec = P._pn_load_key(p, reg, log)
    assert not [t for t in terms if t.real in ("Server", "Quash")], (
        "a harvested ordinary-vocabulary row must not come back as a live term")
    # The binding is still seeded, so a delivered export stays reversible and
    # a re-derivation cannot mint a second fake for the same word.
    assert reg._memo.get(("name_or_entity", "server")) == "Radley"
    assert reg._memo.get(("name_or_entity", "quash")) == "Mabry"


def test_an_authoritative_common_word_row_is_kept(tmp_path):
    # Refusing a real party name is the failure the whole method exists to
    # prevent: a template/--term row is loaded whatever its word looks like.
    p = _key(tmp_path, [
        {"category": "person", "real_value": "Bond", "replacement": "Marlin",
         "source": "spreadsheet", "occurrences": 4},
    ])
    reg = P._PnFakeRegistry()
    terms, _dec = P._pn_load_key(p, reg, log)
    assert [t for t in terms if t.real == "Bond"], (
        "an operator-named party must never be declined by the gazetteer")


def test_a_party_named_bond_is_still_scrubbed():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["James Bond"], [], [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    z = P.Pseudonymizer(terms, det, registry=reg)
    out = z.apply("Defendant James Bond appeared specially.")
    assert "James Bond" not in out


def test_process_server_prose_is_left_alone():
    # The whole point: a case whose parties are ordinary people must never
    # have its subject-matter vocabulary rewritten.
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Helen Rasho"], [], [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    z = P.Pseudonymizer(terms, det, registry=reg)
    text = ("NOTICE AND MOTION TO QUASH SERVICE OF SUMMONS\n"
            "Proof of Service was executed by a registered California "
            "process server.")
    out = z.apply(text)
    for word in ("QUASH", "Proof", "server"):
        assert word in out, f"{word!r} was rewritten"
