"""The lower-case tier of the misspelling sweep reports names, not prose.

Measured on 1.5 MB of legal and technical prose against 257 tracked names,
every false lower-case "misspelled name?" row came through the
stand-in-adjacent site: "Rasho's motive" (a possessive stand-in), "Rodgers
erred" and "Irving firing" (a SURNAME fake on the LEFT of an ordinary word,
where the half-scrubbed pair is a given fake hard against the surname),
"marker's" (one possessive occurrence corroborated while fifteen plain ones
were not), "person's" (admitted at the wide reach through a variant). Four
screens close them; the delivered true positives stay.

Run:  cd PDF-Linker && python3 -m pytest tests/test_lowercase_noise.py -v
"""
import logging

import pdf_linker as P

log = logging.getLogger("test")


def _pz(names):
    reg = P._PnFakeRegistry()
    z = P.Pseudonymizer(P._pn_build_terms(list(names), [], [], registry=reg),
                        {}, registry=reg)
    return z


def _rows(names, text):
    z = _pz(names)
    z.note_original(text)
    out = z.apply(text)
    return {v for _t, v in z.fuzzy_survivor_scan(out)}, out


def test_a_possessive_stand_in_is_not_the_half_scrubbed_pair():
    rows, out = _rows(["Helen Rasho", "Mortimer Fane"],
                      "Rasho's motive was plain. Helen Rasho moved.")
    assert "motive" not in rows, (rows, out)


def test_a_surname_fake_on_the_left_of_a_verb_is_prose():
    rows, out = _rows(["Michael Rodgers", "Ferrers Holdings", "Irving Cole"],
                      "Michael Rodgers erred. Rodgers erred again. Irving Cole "
                      "objected to the firing.")
    assert "erred" not in rows and "firing" not in rows, (rows, out)


def test_every_occurrence_of_the_base_word_is_asked_about():
    text = ("Helen Rasho signed the marker's card. The marker was moved; the "
            "marker fell; a marker stood there; the marker read Rasho.")
    rows, out = _rows(["Helen Rasho", "Mercer Lane"], text)
    assert "marker's" not in rows and "marker" not in rows, (rows, out)


def test_a_lower_case_word_is_held_to_the_close_reach():
    text = ("Ollerton Lane and Rolleston Way met. Helen Rasho: the person's "
            "claim; Iller and Rolleston were there.")
    rows, out = _rows(["Helen Rasho", "Ollerton Lane"], text)
    assert "person's" not in rows, (rows, out)


def test_the_label_site_stops_at_the_next_label():
    text = ("Name: Manuel Vazquez   Title: general manager of the dealership   "
            "Date: 4/4/2025\n")
    rows, out = _rows(["Manuel Vazquez", "Dana Manager"], text)
    assert not any(w in rows for w in ("general", "manager", "dealership")), rows


def test_the_delivered_true_positives_still_report():
    text = ("Name: Manuel vazqvez\nPrnt Name: Manuel v~zquei\n"
            "Manuel Vazquez, vizquez executed a written Personal Guaranty.")
    rows, out = _rows(["Manuel Vazquez"], text)
    assert {"vazqvez", "vizquez"} <= rows, (rows, out)


def test_the_capital_tiers_second_degree_applies_the_vocabulary_screen():
    text = ("Laker Rates and Lakes were bound. Later the parties met; later "
            "still, the dates and Dates were set; later, later, later.")
    rows, out = _rows(["Laker Rates", "Lakes Lakeside", "Laken Ratev"], text)
    assert "Later" not in rows and "Dates" not in rows, (rows, out)


def test_name_fake_positions_split_given_from_surname():
    z = _pz(["Manuel Vazquez", "Rasho"])
    given, surname = z.name_fake_positions()
    fakes = {t.real: t.fake for t in z.terms}
    g, s_ = fakes["Manuel Vazquez"].split()
    assert g.lower() in given and s_.lower() in surname
    assert fakes["Rasho"].lower() in surname
