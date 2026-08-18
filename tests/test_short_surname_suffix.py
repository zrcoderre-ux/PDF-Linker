"""
A short surname that is also an English word — or a degree abbreviation — is
still a surname.

"Anh Do" is a real party name, and it met two independent screens that each
read "Do" as something else: `_pn_trim_edge_vocabulary` read it as sentence
vocabulary and trimmed it off the operator's own template value (so no term
for the full name was ever built), and `_pn_is_suffix_token` read it as the
D.O. degree (so even a term that survived composed "<fake> Do"). Either way
the party shipped half-scrubbed — the shape CLAUDE.md calls the most dangerous
thing the tool can emit — in every occurrence.

The degree reading survives only on EVIDENCE now: the token carries its dots
("D.O."), a comma precedes it ("John Smith, MD"), or it is ALL-CAPS inside a
mixed-case name ("Bob Jones MD"). An all-caps NAME gives the casing signal
nothing and is faked whole — a degree word faked is cosmetic, a surname kept
verbatim is a leak.

Also pinned here: `_pn_person_token_map` no longer mints a whole pool surname
for a bare INITIAL (`_pn_fake_person` keeps a single letter verbatim, so the
map's draw was a pool word burned per distinct letter and a live bare-letter
binding left in the registry); and `_pn_name_variants` keeps the FIRST-pair
transposition of a Title-case name ("Ashley" -> "Sahley"), which the casing of
a literal swap ("sAhley") used to hide from the name-token screen.

Run:  cd PDF-Linker && python3 -m pytest tests/test_short_surname_suffix.py -v
"""
import pdf_linker as P


def _fake(name):
    return P._pn_fake_person(name, P._PnFakeRegistry())[0]


# ── the surname is scrubbed ─────────────────────────────────────────────────

def test_a_short_word_surname_is_faked_not_kept():
    for name, surname in [("Anh Do", "Do"), ("Tou Pa", "Pa"),
                          ("Minh Than", "Than"), ("Truc Can", "Can"),
                          ("Bao An", "An")]:
        out = _fake(name)
        assert surname not in out.split(), (name, out)


def test_the_template_value_keeps_its_surname():
    for name in ["Anh Do", "Bao An", "Minh Than", "Truc Can"]:
        assert P._pn_trim_edge_vocabulary(name) == name
    # …and the trim still works on a real heading phrase.
    assert P._pn_trim_edge_vocabulary("That Lin") == "Lin"


def test_end_to_end_the_party_is_scrubbed_everywhere():
    terms = P._pn_build_terms([("Anh Do", False)], [], [])
    pz = P.Pseudonymizer(terms, {}, registry=P._PnFakeRegistry())
    out = pz.apply("Plaintiff Anh Do alleges service failed. Anh Do appeared.")
    assert "Anh" not in out and "Do " not in out


# ── the degree is still a degree, on evidence ───────────────────────────────

def test_a_degree_with_evidence_is_kept():
    assert _fake("Jane Smith, M.D.").endswith(", M.D.")
    assert _fake("John Smith, MD").endswith(", MD")
    assert _fake("Bob Jones MD").endswith(" MD")      # all-caps in mixed case
    for out in [_fake("Jane Smith, M.D."), _fake("John Smith, MD"),
                _fake("Bob Jones MD")]:
        assert "Smith" not in out and "Jones" not in out


def test_an_all_caps_name_is_faked_whole():
    out = _fake("ANH DO")
    assert "DO" not in out.split() and "ANH" not in out.split()


# ── the token map matches the composer ──────────────────────────────────────

def test_no_pool_word_is_minted_for_a_bare_initial():
    reg = P._PnFakeRegistry()
    m = P._pn_person_token_map("Steven W. Burt", reg)
    assert "w" not in m
    assert set(m) == {"steven", "burt"}


def test_the_token_map_carries_the_short_surname():
    m = P._pn_person_token_map("Anh Do", P._PnFakeRegistry())
    assert "do" in m


# ── the first-pair transposition variant survives its own casing ────────────

def test_the_first_pair_transposition_is_registered():
    vs = P._pn_name_variants("Ashley")
    assert "Sahley" in vs
    assert P._pn_name_variants("ASHLEY") >= {"SAHLEY"}
