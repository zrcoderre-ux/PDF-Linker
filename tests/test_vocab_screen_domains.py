"""The vocabulary screen does not read a DOMAIN as prose.

`_pn_vocabulary_screen` refuses a worksheet `yes` whose every word the
documents write in lower case at least as often as capitalised — the
`prune_prose_word_terms` rule, asked of the operator's answer. An e-mail
address and a URL are the one place every word is lower case by CONVENTION,
and a domain core is a firm's name far more often than a common noun. Counted,
they ran the screen backwards: "Email: rch@rchobbs.com" out-voted the
"RCHOBBS" standing in the exhibit's own letterhead, so a `yes` on the firm was
refused as vocabulary and the row came back on every pass.
"""
import pdf_linker as P


class TestADomainIsNotEvidenceOfVocabulary:
    def test_an_email_local_part_and_domain_do_not_screen_the_name(self):
        text = "Email: rch@rchobbs.com\nRCHOBBS Group Attn: Drummond\n"
        assert P._pn_vocabulary_screen([text])("RCHOBBS") == ""

    def test_a_bare_url_does_not_either(self):
        text = "See https://rchobbs.com/contact\nRCHOBBS Group\n"
        assert P._pn_vocabulary_screen([text])("RCHOBBS") == ""

    def test_and_the_domain_alone_still_says_nothing_for_it(self):
        # With no capitalised occurrence anywhere the screen is silent too —
        # it can only ever REFUSE, and it now has no evidence either way.
        text = "Email: rch@rchobbs.com\n"
        assert P._pn_vocabulary_screen([text])("RCHOBBS") == ""


class TestRealVocabularyIsStillRefused:
    def test_a_word_the_prose_writes_lower_case_is_screened(self):
        text = ("the contractors were unlicensed, and the contractors left.\n"
                "CONTRACTORS\n")
        why = P._pn_vocabulary_screen([text])("CONTRACTORS")
        assert "lower case" in why

    def test_a_domain_does_not_rescue_a_word_the_prose_also_writes(self):
        text = ("the contractors were unlicensed; see contractors.com.\n"
                "the contractors left. CONTRACTORS\n")
        assert "lower case" in P._pn_vocabulary_screen([text])("CONTRACTORS")

    def test_the_all_caps_rule_is_unmoved(self):
        why = P._pn_vocabulary_screen([""])("NAN")
        assert "four letters or fewer" in why
        assert "four letters or fewer" in P._pn_vocabulary_screen([""])("JTII")
