"""
Complaint/declaration paragraph bookmarking must not stop at triple digits. A
long complaint runs well past 99 paragraphs; the old `1 <= N <= 99` guard
silently dropped every paragraph from 100 on, so a page of paragraphs 100-103
produced no candidates and no bookmarks.

Run:  cd PDF-Linker && python3 -m pytest tests/test_paragraph_anchors.py -v
"""
import pdf_linker as P


def _anchors(*bodies):
    return [{"body_text": b} for b in bodies]


def _nums(anchors):
    return [a.get("paragraph_num") for a in anchors]


def test_triple_digit_paragraphs_are_tagged():
    out = P._annotate_paragraphs(_anchors(
        "100. Plaintiff realleges the foregoing.",
        "Continuation of paragraph 100.",
        "101. Defendant breached the contract.",
        "102. Plaintiff suffered damages."))
    assert _nums(out) == [100, 100, 101, 102]
    assert [a["starts_paragraph"] for a in out] == [True, False, True, True]


def test_sequence_crossing_the_99_boundary():
    out = P._annotate_paragraphs(_anchors(
        "98. First.", "99. Second.", "100. Third.", "101. Fourth."))
    assert _nums(out) == [98, 99, 100, 101]


def test_two_digit_paragraphs_still_work():
    out = P._annotate_paragraphs(_anchors(
        "4. Alpha.", "5. Bravo.", "6. Charlie."))
    assert _nums(out) == [4, 5, 6]


def test_isolated_number_is_not_a_paragraph():
    # Fewer than 3 sequential starts -> not declaration-style -> no tagging.
    out = P._annotate_paragraphs(_anchors(
        "As stated in 7. Above, the claim fails.",
        "Ordinary prose line.",
        "More ordinary prose."))
    assert _nums(out) == [None, None, None]


def test_four_digit_run_is_not_a_paragraph():
    # A year like "2024." must not be read as a paragraph number (regex caps at
    # 3 digits), so a page of years doesn't qualify.
    out = P._annotate_paragraphs(_anchors(
        "2021. Something happened.", "2022. Then more.", "2023. Finally."))
    assert _nums(out) == [None, None, None]
