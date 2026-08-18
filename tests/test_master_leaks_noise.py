"""
Noise patterns read out of a delivered Master Leaks log, closed at their cause.

A review of 1,911 accumulated rows across 36 cases found the bulk of the
operator's triage burden in five recurring shapes — and the worst of them was
the tool flagging its OWN output, which taught the operator to answer with
keeps that baked real given names into the master KEEP sheet:

* `reid_scan` re-reported the tool's own faked Bates stamps whenever the
  spelling differed from the record — a RANGE tail the record does not carry
  ("KQWSCUTPJ254405-439"), or a pool-word-prefixed stamp the source spelled
  several ways ("AINSWORTHGO0058" beside "AINSWORTHOO0311") — 100+ rows of one
  master log, every one a question with no right answer. And "CCP1013" (a
  statute section that lost its space) was reported as a production number.
* the url/domain REVIEW class flagged public infrastructure — a court's own
  site and its OCR misspellings (lacourt.org / facourt.org / locourt.org each
  cost a separate decision), ADR providers, news sites, manufacturers in
  lemon-law briefs. Every one of the 51 url/domain decisions in the delivered
  master KEEP log is a `no`.
* one OCR'd host became many rows: `benefitcenter.com` / `benefiteenter.com`
  and the wrap-tail fragments `ters.org` / `n.com` were each their own value,
  row, and decision about the same host.
* a heading was flagged once per PHRASING ("Alleges That Lin Intended",
  "Alleges That Lin Participated") — the question in each is the name.

Run:  cd PDF-Linker && python3 -m pytest tests/test_master_leaks_noise.py -v
"""
import logging

import pdf_linker as P

log = logging.getLogger("test")


def _pz():
    return P.Pseudonymizer([], {}, registry=P._PnFakeRegistry())


def _rec(pz, cat, real, fake):
    pz.records[(cat, real.lower())] = {
        "category": cat, "real": real, "fake": fake, "source": "regex",
        "count": 1, "pattern": "x", "flags": 0}


# ── the reid scan never reports the tool's own stamps ───────────────────────

def test_a_range_tail_on_our_own_stamp_is_not_a_finding():
    pz = _pz()
    _rec(pz, "production", "WALTON254405", "KQWSCUTPJ254405")
    out = pz.reid_scan("Bates KQWSCUTPJ254405-439 and KQWSCUTPJ254405.")
    assert out == []


def test_a_pool_word_against_digits_is_our_own_stamp():
    pool = P._PN_NAME_WORDS[0]
    assert P._pn_own_stamp_shape(f"{pool.upper()}GO0058")
    assert P._pn_own_stamp_shape(f"{pool.upper()}0311")
    assert not P._pn_own_stamp_shape("WALTON000123")     # a real party's stamp
    out = _pz().reid_scan(f"Produced as {pool.upper()}OO0311 and WALTON000123.")
    assert [v for _c, v in out] == ["WALTON000123"]


def test_a_spaceless_statute_cite_is_not_a_production_number():
    out = _pz().reid_scan("Service is complete per CCP1013 on mailing.")
    assert out == []


# ── public infrastructure is not a review question ──────────────────────────

def test_public_hosts_and_their_ocr_spellings_are_not_flagged():
    text = ("See www.lacourt.org and facourt.org and https://ph.ucla.edu and "
            "www.jamsadr.org and onstar.com for details.")
    assert P._pn_review_findings(text) == []


def test_a_firm_host_is_still_flagged():
    found = P._pn_review_findings("Visit www.smithlawfirm.com today.")
    assert ("url/domain", "www.smithlawfirm.com") in found


# ── one host, one row ───────────────────────────────────────────────────────

def test_ocr_spellings_and_fragments_fold_onto_one_row():
    pz = _pz()
    _rec(pz, "email", "info@benefitcenter.com", "x@postbox.org")
    for v in ["https://sir.int.benefitcenter.com/MCPPortal",
              "benefiteenter.com", "ters.org", "swearpenters.org"]:
        pz.leak_report.append({"file": "A.pdf", "type": "url/domain",
                               "value": v, "where": "p.1:1", "context": ""})
    pz.confirm_findings(log)
    vals = [r["value"] for r in pz.leak_report]
    assert vals == ["https://sir.int.benefitcenter.com/MCPPortal",
                    "swearpenters.org"]
    # …and nothing the scans saw disappears from the record: the surviving
    # rows' Notes name what folded into them.
    assert "benefitcenter.com" in pz.triage_note(vals[0])
    assert "benefiteenter.com" in pz.triage_note(vals[0])
    assert "ters.org" in pz.triage_note(vals[1])


def test_a_gating_leak_row_is_annotated_never_dropped():
    pz = _pz()
    _rec(pz, "url", "araytheon.com", "y.org")
    for v in ["araytheon.com", "Oravtheon.com"]:
        pz.leak_report.append({"file": "A.pdf", "type": "LEAK", "value": v,
                               "where": "p.1:1", "context": ""})
        pz.leaked.add(v.lower())
    pz.confirm_findings(log)
    assert [r["value"] for r in pz.leak_report] == ["araytheon.com",
                                                    "Oravtheon.com"]
    assert "2 flagged spellings" in pz.triage_note("Oravtheon.com")
    assert {v.lower() for v in pz.leaked} == {"araytheon.com",
                                              "oravtheon.com"}


def test_unrelated_hosts_keep_their_own_rows():
    pz = _pz()
    for v in ["resolvelawla.com", "www.wildhaven-firm.com"]:
        pz.leak_report.append({"file": "A.pdf", "type": "url/domain",
                               "value": v, "where": "p.1:1", "context": ""})
    pz.confirm_findings(log)
    assert len(pz.leak_report) == 2


# ── a heading phrasing reduces to the name it carries ───────────────────────

def test_heading_phrasings_are_trimmed_and_merge():
    pz = _pz()
    for v in ["That Lin", "Alleges That Lin"]:
        pz.leak_report.append({"file": "A.pdf", "type": "unscrubbed name?",
                               "value": v, "where": "p.1:1", "context": ""})
    pz.confirm_findings(log)
    assert [r["value"] for r in pz.leak_report] == ["Lin"]


def test_a_gating_leak_value_is_never_trimmed():
    pz = _pz()
    pz.leak_report.append({"file": "A.pdf", "type": "LEAK",
                           "value": "That Lin", "where": "p.1:1",
                           "context": ""})
    pz.confirm_findings(log)
    assert [r["value"] for r in pz.leak_report] == ["That Lin"]


# ── a spaced hyphen is still one compound surname ───────────────────────────

def test_a_spaced_hyphen_compound_is_scrubbed_in_every_spelling():
    terms = P._pn_build_terms([("HECTOR SOLORIO - ESPINOZA", False)], [], [])
    pz = P.Pseudonymizer(terms, {}, registry=P._PnFakeRegistry())
    for t in ["Defendant HECTOR SOLORIO - ESPINOZA, an individual",
              "Defendant HECTOR SOLORIO-ESPINOZA, an individual",
              "served SOLORIO - ESPINOZA at his home",
              "served Solorio- Espinoza at his home"]:
        out = pz.apply(t)
        assert "SOLORIO" not in out.upper() or "ESPINOZA" not in out.upper(), t
