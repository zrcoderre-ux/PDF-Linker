"""
A fax exhibit's text layer is soup, and a whole-word term cannot reach it.

A filing is born-digital and extracts cleanly; the EXHIBITS behind it are
whatever the parties had. One delivered export carried fifteen distinct
fax-scan spellings of its own plaintiff's name across two exhibit pages —
"Wcstlalce", "Weatla.ko", "Wesnuke", "Wi:t;Ulilke" — while the clean spelling
was faked on every other page. Every one was a leak and not one was reported.

Three things were wrong, and this file pins each:

  * `_tracked_name_token_index` held the PERSON categories only, so an ENTITY
    plaintiff was not a fuzzy target at all — the distance was never measured
    because the target was never in the index.
  * `fuzzy_survivor_scan` borrowed `_pn_name_fold_dist`, which is calibrated
    for MINTING a stand-in. A report and a substitution have costs orders of
    magnitude apart, so the scan was screened by the mint's risk.
  * Nothing said the region was degraded, so an export the scrub structurally
    could not clean was delivered looking exactly like one it had read.

Run:  cd PDF-Linker && python3 -m pytest tests/test_degraded_text_layer.py -v
"""

import pdf_linker as P

DET = {k: P._PN_DETECTORS[k] for k in P._PN_DEFAULT_DETECTORS}

# One paragraph of an ordinary filing, and the SAME paragraph as a fax
# generation renders it. The mangling is transcribed from a real exhibit.
CLEAN = (
    "Guarantor agrees to pay all of Westlake's costs, expenses and reasonable\n"
    "attorneys' fees incurred in enforcing the obligations, covenants and\n"
    "agreements of Dealer in the Dealer Agreement and other agreements between\n"
    "Westlake and Dealer or incurred by Westlake in enforcing this Guarantee.\n"
    "Guarantor waives notice of the acceptance of this Guarantee, presentment,\n"
    "protest, notice of protest, and any and all demands for performance or\n"
    "any and all notices of non-performance that might otherwise be a\n"
    "condition precedent to the liability of Guarantor under the Agreement.\n"
)
FAX = (
    "Guarantor agree& to pay all ot\"Wcstlalce's oott5, '°'PMse& and r~asonable\n"
    "atto.-neya' fees Incurred in enfo1cing the obl.lgatiallS, cuvenants and\n"
    "agreem~ts of Dcidcr in I.he Det.lcr Agrcemenl 11nd other agreement,\n"
    "bctwcc11 Wcrtlake and Dee.ler or incurred by Wllstlake ia eriforcing this\n"
    "Gua:-antcc. Guarmtorwaives na'.ice Qfthe acceptance of this Gua:-antec,\n"
    "pn:M!ltmcnt, pmtast, notice o{pro~, and 11ny and ul domands for any\n"
    "and alt notices ofnon-pelfonn11nce that might olherwae bo a condition\n"
    "pn:cedent to the liability of Guarantor under the Deafer Agrcement d~boor.\n"
)


def _pz(*names):
    reg = P._PnFakeRegistry()
    return P.Pseudonymizer(P._pn_build_terms(list(names), [], [], registry=reg),
                           DET, registry=reg)


def _scan(z, text):
    return [s for _c, s in z.fuzzy_survivor_scan(text)]


# ── the entity blind spot ───────────────────────────────────────────────────

def test_an_entity_party_is_a_fuzzy_target():
    """The plaintiff of most of what this tool processes is a company."""
    z = _pz("Westlake Services, LLC")
    _idx, toks = z._tracked_name_token_index()
    assert "westlake" in toks


def test_a_firm_name_s_generic_words_are_not_fuzzy_targets():
    """"Financial"/"Solar" are the vocabulary of the brief, not a name — the
    same screen the term builder applies before a bare token may exist."""
    z = _pz("Westlake Financial Solar Lending, LLC")
    _idx, toks = z._tracked_name_token_index()
    assert "westlake" in toks
    assert not ({"financial", "solar", "lending"} & toks)


def test_a_person_token_is_still_a_target():
    z = _pz("Michael Rodgers")
    _idx, toks = z._tracked_name_token_index()
    assert {"michael", "rodgers"} <= toks


def test_a_mangled_entity_survivor_is_reported():
    """The regression itself: the company name shipped and nothing said so."""
    z = _pz("Westlake Services, LLC")
    out = z.apply(FAX)
    assert any(s.lower().startswith("wc") or s.lower().startswith("wll")
               for s in _scan(z, out))


def test_the_clean_spelling_is_scrubbed_and_never_reported():
    # The short form is a `--term` here for the reason the real folder has one:
    # a business's bare WORDS are deliberately withheld from becoming tokens,
    # so the party list and the pre-scan are what supply "Westlake" alone.
    z = _pz("Westlake Services, LLC", "Westlake")
    out = z.apply(CLEAN)
    assert "Westlake" not in out
    assert _scan(z, out) == []


# ── the scan's own tolerance ────────────────────────────────────────────────

def test_the_scan_reaches_one_edit_past_the_minting_fold():
    a, b = "wcrtlake", "westlake"
    assert P._pn_osa_distance(a, b) == 2
    assert not P._pn_edit_distance_within(
        a, b, P._pn_name_fold_dist(a, b), min_len=P._PN_NAME_FOLD_MIN)
    assert P._pn_edit_distance_within(
        a, b, P._pn_scan_fold_dist(a, b), min_len=P._PN_NAME_FOLD_MIN)


def test_a_degraded_region_reaches_one_edit_further_again():
    a, b = "wcstlah", "westlake"
    assert P._pn_osa_distance(a, b) == 3
    assert not P._pn_edit_distance_within(
        a, b, P._pn_scan_fold_dist(a, b), min_len=P._PN_NAME_FOLD_MIN)
    assert P._pn_edit_distance_within(
        a, b, P._pn_scan_fold_dist(a, b, degraded=True),
        min_len=P._PN_NAME_FOLD_MIN)


def test_the_second_edit_is_licensed_by_the_tracked_name_not_the_survivor():
    """Three slips inside a five-letter token is 60% of it. A five-letter
    party word reached "Dealer", "Deale" and "Iller" that way — three of the
    five noise rows on the degraded pages — while every real hit came off an
    eight-letter one."""
    assert P._pn_scan_fold_dist("dealer", "sales", degraded=True) == \
        P._pn_scan_fold_dist("dealer", "sales")
    assert P._pn_scan_fold_dist("wcatlak", "westlake", degraded=True) > \
        P._pn_scan_fold_dist("wcatlak", "westlake")


def test_the_scan_distance_is_asymmetric_on_purpose():
    """`tracked` is the spelling the run is sure of; the survivor is the
    mangled half and may have lost characters outright."""
    assert P._pn_scan_fold_dist("wcatlak", "westlake", degraded=True) == 3
    assert P._pn_scan_fold_dist("westlake", "wcatlak", degraded=True) == 2


def test_the_minting_fold_itself_is_unmoved():
    """A folded fake is what a delivered key pins, so widening the REPORT must
    not move a single binding a re-run without its key would re-derive."""
    assert P._pn_name_fold_dist("abcdefg", "abcdefh") == 1
    assert P._pn_name_fold_dist("abcdefghij", "abcdefghik") == 2
    assert P._pn_name_fold_dist("abcdefghijklmnop", "abcdefghijklmnoq") == 3


def test_the_wider_reach_is_spent_only_where_the_text_is_degraded():
    """The three-slip spellings must NOT be reachable in clean prose for a
    name the run merely HARVESTED: that tolerance was measured as a
    worksheet nobody reads. (A party the operator NAMED is the exception,
    below — the net is cast wide for those at the owner's direction.)"""
    reg = P._PnFakeRegistry()
    terms = P._pn_build_terms(["Weishi Yang"], [], [], registry=reg)
    P._pn_append_name_terms(terms, "Westlake Services, LLC", "document", reg)
    z = P.Pseudonymizer(terms, DET, registry=reg)
    clean_with_survivor = CLEAN.replace(
        "condition precedent", "Wcstlah precedent")
    out = z.apply(clean_with_survivor)
    assert not P._pn_degraded_spans(out)
    assert "Wcstlah" not in _scan(z, out)


def test_a_named_party_takes_the_wider_reach_on_a_clean_page():
    """The operator's own template party is the spelling the run is surest
    of, so its three-slip spellings are asked about everywhere
    (`_pn_scan_fold_dist(party=True)`) — once the page has shown a SECOND
    spelling of it. A lone far variant must be a close match instead
    (`test_variant_reach.py`)."""
    z = _pz("Westlake Services, LLC")
    clean_with_survivor = CLEAN.replace(
        "condition precedent", "Wcstlah precedent").replace(
        "Guarantor agrees", "Wesnuke Guarantor agrees")
    out = z.apply(clean_with_survivor)
    assert not P._pn_degraded_spans(out)
    assert "Wcstlah" in _scan(z, out)
    lone = _pz("Westlake Services, LLC")
    out = lone.apply(CLEAN.replace("condition precedent", "Wcstlah precedent"))
    assert "Wcstlah" not in _scan(lone, out)


# ── the degradation measure ─────────────────────────────────────────────────

def test_ordinary_prose_reads_as_undegraded():
    assert P._pn_degraded_ratio(CLEAN * 3) < P._PN_DEGRADED_RATIO
    assert P._pn_degraded_spans(CLEAN * 3) == []


def test_a_fax_generation_page_reads_as_degraded():
    assert P._pn_degraded_ratio(FAX * 3) >= P._PN_DEGRADED_RATIO
    assert P._pn_degraded_spans(FAX * 3)


def test_the_measure_is_local_so_one_bad_exhibit_is_not_diluted():
    """A degraded exhibit sits inside a clean filing; a document-wide average
    washes it out, and the leak is local."""
    doc = CLEAN * 8 + FAX * 3 + CLEAN * 8
    spans = P._pn_degraded_spans(doc)
    assert spans
    s, e = spans[0]
    assert "Wcstlalce" in doc[s:e]
    assert doc[s:e].count("condition precedent") <= 1


def test_an_accented_latin_letter_is_never_a_mark():
    """The mark class is `\\w`-based, not ASCII: written against
    `[0-9A-Za-z]` it read "ó" as an interior mark, so "Alarcón" and
    "Rodríguez" scored as mangled — and a Los Angeles filing is full of them,
    so a page of Spanish surnames read as a degraded scan."""
    for w in ("Alarcón", "Rodríguez", "Óscar", "Ángela", "Peña", "Zürich"):
        assert not P._pn_token_is_mangled(w), w


def test_a_camelcase_brand_is_not_degradation():
    """An interior case flip was measured as a signal and rejected: it fires
    on every ordinary CamelCase word an exhibit carries."""
    for w in ("PayPal", "iPhone", "eBay", "YouTube", "McDonald", "DiGiorno"):
        assert not P._pn_token_is_mangled(w), w


def test_an_ink_form_checkbox_is_not_degradation():
    """`[X]`/`[ ]` is this tool's OWN rendering, and a statutory subdivision
    puts a paren inside an alphanumeric run — an ink-form page read as
    degraded on those alone."""
    page = ("[X] a. Enter default of defendant under CCP 585(a)\n"
            "[ ] b. Clerk's judgment requested per CCP 585(a)(1)\n"
            "[?] c. Court judgment under Rule 3.1800(a)(3)\n") * 12
    assert P._pn_degraded_ratio(page) < P._PN_DEGRADED_RATIO


def test_a_short_block_yields_no_verdict():
    assert P._pn_degraded_ratio("Wcstlalce oott5 r~asonable") is None


def test_a_url_is_never_a_mangled_token():
    """The authorities appendix this tool itself writes ends every export
    with verification links, and `?`/`=` read as interior marks — a JUD-100
    short enough for the appendix to dominate a block reported its own links
    as a degraded fax."""
    line = ("CCP § 585(a)  ->  https://leginfo.legislature.ca.gov/faces/"
            "codes_displaySection.xhtml?lawCode=CCP&sectionNum=585.")
    assert not any(P._pn_token_is_mangled(t) for t in line.split())
    appendix = "\n".join(
        f"CCP § {n}  ->  https://leginfo.legislature.ca.gov/faces/"
        f"codes_displaySection.xhtml?lawCode=CCP&sectionNum={n}."
        for n in range(400, 460))
    assert P._pn_degraded_spans(appendix) == []


def test_the_mangle_signals():
    for bad in ("miu!e", "d~boor", "o{pro~", "Wcstlalce", "roodificntiClllS"):
        assert P._pn_token_is_mangled(bad), bad
    # The mark class is narrow on purpose: an abbreviation, a pin cite, a time
    # stamp and a statutory subdivision all put a mark inside a word.
    for good in ("Guarantor", "attorneys'", "non-performance", "585(a)",
                 "Westlake", "e-mail", "U.S.C.", "P.C.", "25STCV52008",
                 "45:12-16", "2:09PM", "Cal.App.5th", "3.1800(a)(3)",
                 "O'Brien", "McDonald", "Amezcua", "clerk@courts.ca.gov"):
        assert not P._pn_token_is_mangled(good), good


# ── the run says so ─────────────────────────────────────────────────────────

def test_a_degraded_export_is_named_out_loud():
    z = _pz("Westlake Services, LLC")
    note = z.degraded_text_note(CLEAN * 8 + FAX * 3)
    assert note and "degraded" in note


def test_a_clean_export_says_nothing():
    z = _pz("Westlake Services, LLC")
    assert z.degraded_text_note(CLEAN * 8) is None


def test_the_note_mints_nothing_and_moves_no_fake():
    """REVIEW only: it gates nothing and must not touch the map."""
    z = _pz("Westlake Services, LLC")
    before = dict(z.records)
    z.degraded_text_note(FAX * 3)
    assert dict(z.records) == before
    assert z.leaked == set()


# ── cost ────────────────────────────────────────────────────────────────────

def test_the_measure_is_computed_once_per_body():
    """Two consumers ask about one export; the leak path is where this
    project's quadratics have lived, so the pass is memoized like the
    citation mask beside it."""
    z = _pz("Westlake Services, LLC")
    body = P._NFKC(CLEAN * 8 + FAX * 3)
    calls = []
    real = P._pn_degraded_spans
    P._pn_degraded_spans = lambda t: (calls.append(t), real(t))[1]
    try:
        z._degraded_spans(body)
        z._degraded_spans(body)
        z.degraded_text_note(CLEAN * 8 + FAX * 3)
    finally:
        P._pn_degraded_spans = real
    assert len(calls) == 1


def test_the_memo_holds_the_alternating_pair():
    """The scan block runs over an export AND its column-ordered twin, so a
    single slot would be evicted before it was ever read."""
    z = _pz("Westlake Services, LLC")
    a, b = P._NFKC(CLEAN * 8), P._NFKC(CLEAN * 8 + FAX * 3)
    z._degraded_spans(a)
    z._degraded_spans(b)
    assert set(z._degraded_memo) == {a, b}
    z._degraded_spans(a)          # still a hit, not a recompute
    assert set(z._degraded_memo) == {a, b}
