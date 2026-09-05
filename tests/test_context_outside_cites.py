"""
A Context quote prefers an occurrence OUTSIDE a cited case name, and never
ends a sentence at the " v." of one.

Four worksheet rows quoted a published decision's name — the flagged word's
first prose occurrence — when the scans had flagged the word somewhere else
entirely; and the sentence splitter, reading " v." as a full stop, opened
the quote on the defendant with the plaintiff left behind it.

Run:  cd PDF-Linker && python3 -m pytest tests/test_context_outside_cites.py -v
"""
import pdf_linker as P

BODY = [
    "====== Page 4 ======",
    " 1  The Act is remedial.  (Oregel v. American Suzuki Motor Corp. (2008) 160 Cal.App.4th 53, 58.)  As such,",
    " 2  the standard is not permitted.  In Hoover Community Hotel Development Corp. v. Ford Motor Co. (1989)",
    " 3  214 Cal.App.3d 878, the court considered the scope of the agency relationship.",
    " 4  Ford filed its answer on March 3 and American Honda served discovery the same week.",
]


def _quote(lines, value):
    return P._pn_context_hit(P._pn_body_lines("\n".join(lines)), value)[0]


def test_an_occurrence_outside_a_cite_wins_over_the_cited_one():
    q = _quote(BODY, "Ford")
    assert "Ford filed its answer" in q
    assert "Ford Motor Co. (1989)" not in q.split("Ford filed")[-1]
    q = _quote(BODY, "American")
    assert "American Honda served discovery" in q
    assert "Suzuki" not in q


def test_a_value_standing_only_in_cites_is_still_quoted():
    q = _quote(BODY, "Development")
    assert "Hoover Community Hotel Development Corp." in q


def test_v_is_not_a_sentence_end():
    # The cite is one sentence: the quote carries the plaintiff, the " v."
    # and the defendant together, never the defendant alone.
    q = _quote(BODY, "Development")
    assert "Development Corp. v. Ford Motor Co." in q
    q = _quote(["Plaintiff relies on Oregel v. American Suzuki Motor Corp. "
                "(2008) 160 Cal.App.4th 53, 58."], "Suzuki")
    assert q.startswith("Plaintiff relies on Oregel v. American Suzuki")
    # …while an outline heading's numeral still ends its line.
    ends = [m.end() for m in P._PN_SENT_END_RE.finditer(
        "IV. ARGUMENT. Smith v. Jones is cited. Jones vs. Smith too.")]
    text = "IV. ARGUMENT. Smith v. Jones is cited. Jones vs. Smith too."
    assert text[ends[0] - 1] == "." and ends[0] == 3
    assert not any(text[e - 3:e] in (" v.", "vs.") for e in ends)


def test_a_cited_prose_hit_beats_a_cited_heading_hit_when_nothing_else():
    body = ["====== Page 1 ======",
            " 1  B. Oregel v. American Suzuki Motor Corp. (2008) 160 Cal.App.4th 53 Controls Here",
            " 2  In Oregel v. American Suzuki Motor Corp. (2008) 160 Cal.App.4th 53, 58, the court held",
            " 3  that the statute applied to every party."]
    q = _quote(body, "Suzuki")
    assert "the court held" in q


def test_an_uncited_heading_still_beats_a_cited_sentence():
    # A value found in a heading and otherwise only inside cites is quoted as
    # that heading — the site the row is about.
    body = ["====== Page 1 ======",
            " 1  THE DEVELOPMENT AGREEMENT WAS BREACHED",
            " 2  In Hoover Community Hotel Development Corp. v. Thomson (1985) 168 Cal.App.3d 485, the court held",
            " 3  that the statute applied to every party."]
    q = _quote(body, "Development")
    assert q.startswith("THE DEVELOPMENT AGREEMENT")
