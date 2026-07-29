"""
Motion-practice vocabulary is boilerplate, not a party.

The high-recall review scan reads a capitalised run as a possible unscrubbed
name unless its words are in the `_PN_COMMON_WORDS` gazetteer. "Seeks" and
"EVIDENTIARY OBJECTIONS TO" were missing from it, so an opposition brief's own
argument headings and objection captions became triage rows the operator had to
answer one by one — and neither `yes` nor `no` is a correct answer for a phrase
that names nobody.

The gazetteer must never swallow a word that is also a real surname or one of
the fake pools' words, so the additions are checked against both.

Run:  cd PDF-Linker && python3 -m pytest tests/test_review_boilerplate_words.py -v
"""
import logging

import pdf_linker as P

log = logging.getLogger("test")

ADDED = ("seek seeks seeking sought contend contends contended contention "
         "contentions object objects objected objection objections "
         "evidentiary").split()


def test_added_words_are_in_the_gazetteer():
    for w in ADDED:
        assert w in P._PN_COMMON_WORDS, w


def test_added_words_collide_with_no_fake_pool_word():
    pools = {w.lower() for w in P._PN_NAME_WORDS}
    pools |= {w.lower() for w in P._PN_ENTITY_WORDS}
    assert [w for w in ADDED if w in pools] == []


def test_seeks_is_not_flagged_as_an_unscrubbed_name():
    found = P._pn_person_review_findings("Plaintiff Seeks Punitive Damages")
    assert [s for _c, s in found if "Seeks" in s] == []


def test_objection_caption_is_not_flagged():
    assert P._pn_is_procedural_phrase("EVIDENTIARY OBJECTIONS TO")
    found = P._pn_person_review_findings(
        "EVIDENTIARY OBJECTIONS TO THE DECLARATION")
    assert [s for _c, s in found if "OBJECTIONS" in s.upper()] == []


def test_a_real_name_beside_the_new_words_still_surfaces():
    # The gazetteer must widen boilerplate, never hide a party: an unlisted
    # name is still flagged when the new words sit right beside it.
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Alejandro Orellana"], [], [], registry=reg)
    z = P.Pseudonymizer(terms, list(P._PN_DEFAULT_DETECTORS), registry=reg)
    out = z.apply("Defendant Travelers objects to the declaration. "
                  "The motion Seeks sanctions.")
    flagged = {s for _c, s in z.unknown_name_scan(out)}
    assert any("Travelers" in s for s in flagged), flagged
    assert not any("Seeks" in s or "objects" in s for s in flagged), flagged
