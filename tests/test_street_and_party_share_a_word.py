"""
A STREET NAME and a PARTY are two paths to one word, and a real-estate entity
is routinely named after its own address.

Reported from a delivered folder: "15200 Sunset Blvd." was faked to "15200
Marjoram Blvd." while "15200 Sunset LLC" — the party that owns the building —
came out "15200 Beacon, LLC". One real word, two unrelated stand-ins, so the
export hid the relationship the filing states, which is the ONE WORD, ONE FAKE
rule (`_pn_fake_name_token`) failing across a pool boundary: the person and
entity token paths already share a memo slot, and the street pool did not.

The street's name now draws through that same slot where the name is a SINGLE
word and the whole of the street identity (`_pn_addr_name_word`), from the
STREET pool when nothing has bound the word — so an address the case names and
no party carries is faked exactly as before.

Run:  cd PDF-Linker && python3 -m pytest tests/test_street_and_party_share_a_word.py -v
"""
import logging
import re

import pdf_linker as P

log = logging.getLogger("test")


def _pz(names, text=""):
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(names, [], [], registry=reg), {},
                        registry=reg)
    if text:
        z.register_addresses(text)
    return z


def _street_word(out):
    """The faked street name in "… 8721 <word> Blvd., …"."""
    m = re.search(r"8721 (\w+) Blvd", out)
    assert m, out
    return m.group(1)


def _llc_word(out):
    m = re.search(r"15200 (\w+) LLC", out)
    assert m, out
    return m.group(1)


TEXT = ("Defendant 15200 Sunset LLC owns the building.\n"
        "The notice was mailed to 8721 Sunset Blvd., Los Angeles, CA 90069.\n")


def test_the_party_and_the_street_read_as_one_word():
    # The party is on the template, so it binds FIRST — the reported order.
    z = _pz(["15200 Sunset LLC"], TEXT)
    out = z.apply(TEXT)
    assert _llc_word(out) == _street_word(out), out
    assert "Sunset" not in out


def test_the_street_binds_first_and_the_party_follows_it():
    # No template: the address is harvested before any party term exists, so
    # the street pool draws the word and the entity path reuses it.
    z = _pz([], TEXT)
    out = z.apply(TEXT)
    street = _street_word(out)
    assert street in P._PN_STREET_NAMES
    # …and a party met later composes onto it rather than drawing again.
    later = P._pn_fake_entity("15200 Sunset LLC", z.registry)
    assert later.split()[1] == street, later


def test_a_street_no_party_carries_is_still_a_street_pool_word():
    text = "Service at 8721 Sunset Blvd., Los Angeles, CA 90069.\n"
    z = _pz([], text)
    assert _street_word(z.apply(text)) in P._PN_STREET_NAMES


def test_a_directional_street_is_not_folded_onto_its_bare_name():
    # The composed fake keeps NO directional, so folding "S Maple Ave" and
    # "N Maple Ave" onto the one word "maple" would put two real addresses on
    # one fake address — the collapse the registry exists to prevent.
    assert P._pn_addr_name_word("s maple avenue") is None
    text = ("Notices went to 414 S. Maple Ave., Montebello, CA 90640 and to "
            "414 N. Maple Ave., Montebello, CA 90640.\n")
    z = _pz([], text)
    out = z.apply(text)
    fakes = re.findall(r"414 (\w+) Ave", out)
    assert len(fakes) == 2 and fakes[0] != fakes[1], out


def test_a_multi_word_street_name_keeps_its_shape():
    # "Pacific Coast Highway" draws ONE word, as it always has — folding word
    # for word would change the shape of every street fake in every folder.
    assert P._pn_addr_name_word("pacific coast highway") is None
    text = "The office is at 21225 Pacific Coast Hwy, Malibu, CA 90265.\n"
    z = _pz([], text)
    out = z.apply(text)
    m = re.search(r"21225 (\w+) Hwy", out)
    assert m and m.group(1) in P._PN_STREET_NAMES, out


def test_the_name_word_is_read_off_the_identity():
    assert P._pn_addr_name_word("sunset boulevard") == "sunset"
    assert P._pn_addr_name_word("broadway") == "broadway"
    # An ordinal street is not a name word: "5th" is not a word to bind in the
    # slot every party token is drawn from, and a two-letter one is debris.
    assert P._pn_addr_name_word("5th street") is None
    assert P._pn_addr_name_word("q street") is None


def test_the_two_bindings_stay_reversible(tmp_path):
    z = _pz(["15200 Sunset LLC"], TEXT)
    z.apply(TEXT)
    kp = tmp_path / "pseudonym_key.xlsx"
    z.write_key(kp, log=log)
    from conftest import key_body_rows
    rows = key_body_rows(kp)
    fakes = [str(r[2]) for r in rows]
    # One fake to one Real Value: the macro retires a Replacement two rows
    # claim, and the shared WORD must not become a shared ROW.
    assert len(fakes) == len(set(f.lower() for f in fakes)), rows


def test_a_reused_key_pins_the_street_and_a_new_party_follows_it(tmp_path):
    # Run 1: the address alone.
    addr = ("The notice was mailed to 8721 Sunset Blvd., "
            "Los Angeles, CA 90069.\n")
    z = _pz([], addr)
    first = _street_word(z.apply(addr))
    kp = tmp_path / "pseudonym_key.xlsx"
    z.write_key(kp, log=log)

    # Run 2: the same folder, plus a document naming the LLC. The delivered
    # export must come back byte-identical AND the new party must compose onto
    # the street's own stand-in.
    reg = P._PnFakeRegistry()
    terms, _dec = P._pn_load_key(kp, reg, log)
    terms += P._pn_build_terms(["15200 Sunset LLC"], [], [], registry=reg)
    z2 = P.Pseudonymizer(terms, {}, registry=reg)
    z2.register_addresses(TEXT)
    out = z2.apply(TEXT)
    assert _street_word(out) == first, out
    assert _llc_word(out) == first, out
