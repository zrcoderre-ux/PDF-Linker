"""
The leaks and the one corruption a garbled loan-exhibit batch shipped.

A Complaint's promissory-note exhibits (LaserPro documents, badly OCR'd) and
the conformed-copy stamps around them put four failures on display:

  * the scrub REWROTE ordinary English — "automatically" shipped as
    "lambournematically" through the whole Note, because the party's own
    "Auto" was a trusted 4-letter person token and the short-core weld tier
    matched it inside lower-case prose;
  * a wrapped e-mail left its bare LOCAL PART standing alone on a letterhead
    line ("nminassian") — the attorney's real initial-plus-surname, matched
    by nothing because the detector needs the "@";
  * an OCR'd stamp dropped the deputy line's furniture ("Ay: MN. Quintanilla
    Deputy" for "By: M. Quintanilla, Deputy Clerk") and the comma-anchored
    staff pattern matched nothing, so the deputy's real name shipped;
  * OCR clipped the lead of the clerk's given name ("avid HUNTINGDON.
    Bancroft") and the fragment stood lower-case beside two of our own
    stand-ins, invisible to every capitalised-pair tier.

Run:  cd PDF-Linker && python3 -m pytest tests/test_prose_rewrite_and_stamp_leaks.py -v
"""

import pdf_linker as P

DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}


def _pz(*names):
    reg = P._PnFakeRegistry()
    return P.Pseudonymizer(P._pn_build_terms(list(names), [], [], registry=reg),
                           DET, registry=reg)


# ── the short weld core must never rewrite lower-case prose ─────────────────

def test_a_short_core_never_fires_inside_lowercase_prose():
    """"auto" hard against "matically" passes every other screen — the case
    of the site is the screen no word list has to be kept for."""
    z = _pz("Maria Auto")
    body = P._NFKC("payments will be automatically deducted, and any "
                   "automatic stay of injunction survives")
    assert z.scrub_welded(body, spliced=True) == body
    assert z.surviving_reals_reduced(body, spliced=True) == []


def test_the_next_short_core_is_covered_without_a_list_entry():
    z = _pz("John Cont")
    body = P._NFKC("the contractor continued the work contemporaneously")
    assert z.scrub_welded(body, spliced=True) == body


def test_a_capitalised_weld_is_still_cured():
    z = _pz("Maria Amezcua", "Helen Rasho")
    for frag in ("suffering AMEZCUApain and distress",
                 "the caption reads HELENRASHO on line 10"):
        body = P._NFKC(frag)
        out = z.scrub_welded(body, spliced=True)
        assert out != body, frag
        assert "AMEZCUA" not in out and "RASHO" not in out
    # …and the detection mirror agrees with the cure, tier for tier.
    assert z.surviving_reals_reduced(
        P._NFKC("suffering AMEZCUApain and distress"), spliced=True)


def test_the_two_reduced_passes_stay_mirrored_on_the_case_rule():
    """A value one pass reports and the other refuses to touch quarantines an
    export nothing can clean."""
    z = _pz("Maria Auto")
    body = P._NFKC("it was automatically deducted")
    assert z.surviving_reals_reduced(body, spliced=True) == []
    assert z.scrub_welded(body, spliced=True) == body


# ── the wrapped address's bare local part ───────────────────────────────────

def test_a_bare_local_part_on_its_own_line_is_cured():
    z = _pz()
    body = ("E-MAIL ADDRESS: nminassian@lawfirmco.com\n"
            "Tel: (505) 909-1037\n"
            "    nminassian\n"
            "Attorneys for Plaintiff\n")
    out = z.scrub_emails(z.apply(body))
    assert "nminassian" not in out.lower()
    fake_local = next(str(r["fake"]).split("@")[0]
                      for (c, _), r in z.records.items() if c == "email")
    assert fake_local in out


def test_ordinary_vocabulary_is_never_cured_as_a_local_part():
    """"accounting@…" must not license rewriting the word in prose — and a
    generic local part alone on a line is left alone too."""
    z = _pz()
    body = ("Contact: accounting@lawfirmco.com\n"
            "    accounting\n"
            "the accounting was reviewed in detail\n")
    out = z.scrub_emails(z.apply(body))
    assert "the accounting was reviewed in detail" in out
    assert "\n    accounting\n" in out


def test_a_local_part_mid_prose_is_the_stated_residual():
    z = _pz()
    body = ("Reach nminassian@lawfirmco.com today.\n"
            "Ask nminassian about the filing schedule.\n")
    out = z.scrub_emails(z.apply(body))
    assert "Ask nminassian about" in out      # not cured: too ambiguous to rewrite


def test_the_short_and_generic_screens_hold():
    z = _pz()
    body = "From: info@lawfirmco.com\n    info\n"
    out = z.scrub_emails(z.apply(body))
    assert "\n    info\n" in out


# ── the garbled deputy stamp ────────────────────────────────────────────────

def test_the_garbled_by_deputy_sandwich_is_harvested():
    stamp = ("SUPERIOR COURT OF CALIFORNIA, COUNTY OF LOS ANGELES"
             "     Ay:  MN. Quintanilla Deputy\n")
    z = _pz()
    P._pn_learn_from_text(z, stamp)
    out = z.apply(stamp)
    assert "Quintanilla" not in out


def test_the_intact_by_deputy_clerk_line_still_works():
    stamp = "By: M. Quintanilla, Deputy Clerk\n"
    z = _pz()
    P._pn_learn_from_text(z, stamp)
    assert "Quintanilla" not in z.apply(stamp)


def test_prose_about_a_deputy_is_not_a_name():
    z = _pz()
    P._pn_learn_from_text(
        z, "The filing was approved by the Deputy on Monday.\n"
           "Notice signed by order, Deputy Clerk to follow.\n")
    assert not z.records


def test_a_timestamp_never_walks_into_the_name():
    """"PM" is two capitals with no period — admitting it would put the
    stamp's own clock into the clerk's name."""
    stamp = "12:41 PM David W. Slayton, Executive Officer/Clerk of Court\n"
    z = _pz()
    P._pn_learn_from_text(z, stamp)
    reals = [str(r["real"]) for r in z.records.values()]
    assert not any("PM" in r for r in reals), reals
    assert "Slayton" not in z.apply(stamp)


# ── the clipped given name beside a fake ────────────────────────────────────

def test_a_lead_clipped_real_beside_our_fake_is_reported():
    z = _pz("David W. Slayton")
    out = z.apply("David W. Slayton, Executive Officer\n"
                  "avid W. Slayton, Executive Officer\n")
    assert ("half-scrubbed name?", "avid") in z.half_scrubbed_scan(out)


def test_the_fragment_needs_our_fake_beside_it():
    """"avid" is an ordinary English word; alone in prose it is nobody."""
    z = _pz("David W. Slayton")
    out = z.apply("She was an avid reader of the daily law journal.\n")
    assert ("half-scrubbed name?", "avid") not in z.half_scrubbed_scan(out)


def test_the_fragment_must_be_a_clipped_tracked_token():
    z = _pz("David W. Slayton")
    out = z.apply("David W. Slayton signed.\nthe word beside Bancroft here\n"
                  .replace("Bancroft",
                           str(next(iter(z.records.values()))["fake"]).split()[0]))
    rows = [s for _c, s in z.half_scrubbed_scan(out)]
    assert "word" not in rows and "beside" not in rows
