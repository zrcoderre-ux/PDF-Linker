"""
Gold-set harness: a fully annotated synthetic filing with an explicit
MUST_SCRUB / MUST_KEEP contract, so recall (nothing sensitive survives) and
keep-fidelity (nothing load-bearing is corrupted) are MEASURED on every run
instead of discovered by a human reading the delivered exports. Add a new
value to the right list when a leak class is fixed; the number then guards it.

Run:  cd PDF-Linker && python3 -m pytest tests/test_goldset.py -v
"""

import re
import pytest

import pdf_linker as P


NAMES = [
    "Alejandro Orellana",
    "AHC Acquisition, LLC",
    "Travelers Casualty and Surety Company of America",
    "Rafael Quintero",
    "Quintero & Vega LLP",
    "Tom of Finland Foundation, Inc.",
]
CASENOS = ["24STCV06764"]

GOLD_SOURCE = """\
SUPERIOR COURT OF THE STATE OF CALIFORNIA
COUNTY OF LOS ANGELES

ALEJANDRO ORELLANA, an individual, Plaintiff, v. AHC ACQUISITION, LLC, a
California limited liability company; TRAVELERS CASUALTY AND SURETY COMPANY
OF AMERICA; and DOES 1-10, Defendants.

Case No. 24STCV06764

RAFAEL QUINTERO, ESQ., SBN 175977
QUINTERO & VEGA LLP
817 N. La Brea Avenue, Inglewood, CA 90301
Telephone: (626) 292-0899   Email: rq@quinterovega.com

STATEMENT OF FACTS

1. Plaintiff Alejandro Orellana purchased a 2023 Jeep Wrangler, VIN
1C4JJXP65PW699184 ("Vehicle"), DEAL# 23071, from AHC Acquisition, LLC on
June 6, 2025 (the RISC header reads 0610612025).

2. Amicus Tom of Finland Foundation, Inc. ("ToFF") appeared. ToFF supports
neither side. Plaintiff filed an ISO and RJN with this Court.

3. Defendant Travelers joined. Defendant Consumers Credit Union financed
the purchase.

4. Compelling arbitration requires an agreement. Sanchez v. Valencia
Holding Co., LLC (2015) 61 Cal.4th 899, 912.
"""

# Every value here must be ABSENT (case-insensitive) from the scrubbed output.
MUST_SCRUB = [
    "Orellana", "Alejandro",                 # plaintiff, both tokens
    "AHC Acquisition",                       # defendant entity
    "Travelers Casualty and Surety",         # surety (full form)
    "Rafael", "Quintero",                    # attorney + shared firm token
    "ToFF",                                  # document-defined acronym
    "175977",                                # bar number
    "1C4JJXP65PW699184",                     # VIN
    "23071",                                 # account id
    "292-0899",                              # phone
    "quinterovega",                          # firm email domain
    "La Brea",                               # street name
    "24STCV06764",                           # case number (as a whole)
]

# Every string here must appear VERBATIM in the scrubbed output.
MUST_KEEP = [
    "SUPERIOR COURT OF THE STATE OF CALIFORNIA",
    "COUNTY OF LOS ANGELES",
    "STATEMENT OF FACTS",
    "limited liability company",
    "Inglewood, CA 90301",                   # locality survives, street goes
    "June 6, 2025",
    "0610612025",                            # OCR'd date is not a phone
    "ISO", "RJN", "ESQ",
    "SBN", "VIN", "DEAL#",                   # labels stay, values go
    "Sanchez v. Valencia Holding Co., LLC (2015) 61 Cal.4th 899",
]


def _gold_run():
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(list(NAMES), list(CASENOS), [], registry=reg)
    det = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}
    z = P.Pseudonymizer(terms, det, registry=reg)
    # Mirror the pipeline's document-learning passes.
    z.register_declarant_names(GOLD_SOURCE)
    z.register_dba_names(GOLD_SOURCE)
    z.register_firm_names(GOLD_SOURCE)
    z.register_label_names(GOLD_SOURCE)
    z.register_short_names(GOLD_SOURCE)
    z.register_identifiers(GOLD_SOURCE)
    return z, z.apply(GOLD_SOURCE)


def test_goldset_recall_is_total():
    _z, out = _gold_run()
    low = out.lower()
    missed = [v for v in MUST_SCRUB if v.lower() in low]
    n = len(MUST_SCRUB)
    assert not missed, (
        f"gold-set recall {n - len(missed)}/{n}: survivors {missed}\n--- output"
        f" ---\n{out}")


def test_goldset_keep_fidelity_is_total():
    _z, out = _gold_run()
    # Whitespace-normalized: a citation may wrap across a source line break,
    # which is layout, not corruption.
    flat = re.sub(r"\s+", " ", out)
    corrupted = [v for v in MUST_KEEP if re.sub(r"\s+", " ", v) not in flat]
    m = len(MUST_KEEP)
    assert not corrupted, (
        f"gold-set keep {m - len(corrupted)}/{m}: corrupted {corrupted}\n---"
        f" output ---\n{out}")


def test_goldset_high_recall_net_flags_the_unlisted():
    # Tier 2: a name the term list does NOT cover (the P3-J third party) must
    # surface in the unknown-name scan — never silently pass. The bare
    # "Travelers" used to be deferred to this net; a party's distinctive word
    # is its own token now (`test_entity_word_rows.py`), so it is SCRUBBED.
    z, out = _gold_run()
    flagged = {s for _c, s in z.unknown_name_scan(out)}
    assert "Travelers" not in out, out
    assert any("Consumers Credit Union" in s for s in flagged), flagged


def test_goldset_reid_scan_certifies_clean():
    # The adversarial re-identification pass over the finished output must
    # come back empty — every lookup-key identifier was replaced.
    z, out = _gold_run()
    assert z.reid_scan(out) == []
