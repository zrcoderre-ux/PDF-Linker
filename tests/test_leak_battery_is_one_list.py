"""The REVIEW tiers are listed ONCE, and both export writers read that list.

`_write_text_version` and `_write_word_text_version` each carried their own
copy of the sequence — eleven tiers, written out twice — and two lists that
must agree, kept in two places, is how a tier comes to be added to one of
them. The project has already paid for exactly that shape: the Word path ran
the whole scan battery and none of the cures, so on a Word folder every value
the cures exist for was REPORTED rather than repaired, under a value the key
showed `replaced` (#269).

Run:  cd PDF-Linker && python3 -m pytest tests/test_leak_battery_is_one_list.py -v
"""
import inspect
import re

import pdf_linker as P

TIERS = ["review_scan", "review_definition_survivors", "defined_name_scan",
         "narrative_name_scan", "honorific_name_scan", "mail_header_name_scan",
         "form_rule_name_scan", "degraded_contact_scan", "unknown_name_scan",
         "fuzzy_survivor_scan", "half_scrubbed_scan", "reid_scan"]


def _src(fn):
    return inspect.getsource(fn)


class TestThereIsOnlyOneList:
    def test_every_tier_is_called_from_leak_findings_alone(self):
        """A tier called from anywhere else is a second list forming."""
        module = inspect.getsource(P)
        body = _src(P.Pseudonymizer.leak_findings)
        for tier in TIERS:
            calls = len(re.findall(rf"(?<![\w.])\w*\.{tier}\(", module))
            in_battery = len(re.findall(rf"self\.{tier}\(", body))
            assert in_battery >= 1, f"{tier} missing from leak_findings"
            assert calls == in_battery, (
                f"{tier} is called {calls} times but only {in_battery} of "
                f"them are in leak_findings — the list has split again")

    def test_both_writers_go_through_it(self):
        for writer in (P._write_text_version, P._write_word_text_version):
            assert "leak_findings(" in _src(writer), writer.__name__


class TestTheOrderIsPreserved:
    """The order is load-bearing, so it is pinned rather than assumed."""

    def test_the_tiers_run_in_the_documented_order(self):
        body = _src(P.Pseudonymizer.leak_findings)
        seen = [t for _, t in sorted(
            (body.index(f"self.{t}("), t) for t in TIERS)]
        assert seen == TIERS

    def test_reid_leads_the_result(self):
        """These invert the map in one lookup, so they outrank ordinary
        review and must be prepended, not appended."""
        body = _src(P.Pseudonymizer.leak_findings)
        assert re.search(r"return self\.reid_scan\(body\) \+ review", body)

    def test_the_fuzzy_sweep_runs_before_the_half_scrub(self):
        """…so the more specific class owns the row when a mangled survivor
        also stands beside one of our fakes."""
        body = _src(P.Pseudonymizer.leak_findings)
        assert (body.index("self.fuzzy_survivor_scan(")
                < body.index("self.half_scrubbed_scan("))


class TestItStillReturnsFindings:
    def test_a_body_with_a_reid_shape_reports_it_first(self):
        reg = P._PnFakeRegistry()
        pz = P.Pseudonymizer(P._pn_build_terms(["Helen Rasho"], [], [],
                                               registry=reg), [], registry=reg)
        body = ("Counsel of record, State Bar No. 214785, appeared.\n"
                "Mr. Spellman confirmed the transfer in March.\n")
        rows = pz.leak_findings(body, body)
        assert rows, "the battery reported nothing at all"
        assert isinstance(rows[0], tuple) and len(rows[0]) == 2

    def test_an_empty_body_is_quiet_and_does_not_raise(self):
        reg = P._PnFakeRegistry()
        pz = P.Pseudonymizer([], [], registry=reg)
        assert pz.leak_findings("", "") == []
