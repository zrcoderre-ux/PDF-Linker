"""
The reduced/welded scrub must reach a party's BARE NAME TOKENS.

A column-spliced page welds a caption name to its neighbour ("MICHAELCARROLL",
"AMEZCUApain", "JUANthe"). The boundary-anchored term patterns cannot match a
welded token, so the reduced-substring pass is the only thing that can — but its
core-length gate was a flat >=8, and first/last names are mostly 4-7 characters
("michael", "carroll", "amezcua", "maria", "juan"). So the pass skipped exactly
the values it exists to recover: the defendant's name rode into the export while
`surviving_reals` reported the file clean, and the operator got 25 un-answerable
"unscrubbed name?" triage rows instead.

A short core is now allowed, but only for a PERSON token named by the operator's
own party list, that is not an ordinary English word, and only where it is
genuinely WELDED — an entity's generic words ("law", "firm") and a connector
("De") must never match inside "lawsuit", "confirm" or "defendant".

Run:  cd PDF-Linker && python3 -m pytest tests/test_short_name_weld.py -v
"""
import logging

import pdf_linker as P

log = logging.getLogger("test")


def _pz(names, terms=()):
    reg = P._PnFakeRegistry()
    built = P._pn_build_terms(list(names), list(terms), [], registry=reg)
    return P.Pseudonymizer(built, list(P._PN_DEFAULT_DETECTORS), registry=reg)


PARTIES = ["Maria Antonia Cruz De Amezcua", "Juan Carlos Amezcua",
           "Michael Patrick Carroll"]


def test_welded_short_person_tokens_are_cured():
    z = _pz(PARTIES)
    body = ("MICHAELCARROLL was served. MICHAELPlaintiffs allege. "
            "JUANthe court found. AMEZCUApain and suffering.")
    out = z.scrub_welded(z.apply(body))
    for real in ("MICHAEL", "CARROLL", "JUAN", "AMEZCUA"):
        assert real not in out.upper(), f"{real} survived: {out}"


def test_welded_short_token_is_reported_before_it_is_cured():
    # Detection and replacement must stay mirrored: a value the reduced scan
    # reports but scrub_welded cannot cure quarantines an export nothing can
    # clean, and one it cures but never reported is a silent rewrite.
    z = _pz(PARTIES)
    welded = "MICHAELCARROLL was served."
    assert "Michael" in z.surviving_reals_reduced(welded)
    assert z.surviving_reals_reduced(z.scrub_welded(welded)) == []


def test_short_token_standing_alone_is_left_to_the_ordinary_pass():
    # No weld, no cure: a clean occurrence is the boundary-anchored pass's to
    # make, and that pass yields to keeps and citation protection which the
    # reduced pass cannot see.
    z = _pz(PARTIES)
    assert z.scrub_welded("Michael was served.") == "Michael was served."
    assert z.surviving_reals_reduced("Michael was served.") == []


def test_generic_entity_words_never_match_inside_a_real_word():
    z = _pz(["Law Brothers, LLP", "Lalezary Law Firm, LLP"])
    text = "The lawsuit will confirm the outlawed practice."
    assert z.scrub_welded(text) == text
    assert z.surviving_reals_reduced(text) == []


def test_name_connector_never_matches_inside_a_real_word():
    # "De" of "Cruz De Amezcua" is a connector; _trusted_party_tokens drops it,
    # so "Defendant" and "declaration" are safe.
    z = _pz(PARTIES)
    text = "Defendant filed a declaration denying the debt."
    assert z.scrub_welded(text) == text


def test_short_core_must_come_from_the_party_list():
    # A declarant read off a signature block is an inference, not a party the
    # operator named — it keeps the long-core bar.
    z = _pz(PARTIES)
    rec = {"category": "person-token", "real": "Ruiz", "fake": "Vance",
           "source": "declarant", "count": 0, "pattern": "Ruiz", "flags": 0}
    z.records[("person-token", "ruiz")] = rec
    core, short = z._weld_core(rec)
    assert core == "" and short is False


def test_long_cores_still_work():
    # The behaviour the pass already had must be untouched.
    z = _pz(["Schilleci & Tortorici, P.C."])
    out = z.scrub_welded("AZUL@SCHILLECITORTORICILAW")
    assert "SCHILLECITORTORICI" not in out.upper()
