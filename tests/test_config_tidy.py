"""The config file is kept TIDY, not merely complete.

The top-up solved "a setting added later is invisible to anyone who already has
a config" by APPENDING the blocks a file did not mention. Two rounds of that
and a real operator's file came back carrying TWO "Settings this file did not
mention" banners, a retired setting (`max_text_files`, whose feature was
removed) still sitting there looking live, and its settings in the order three
versions happened to add them.

So the file is RE-EMITTED every run, in canonical order. That reverses the
append-never-rewrite rule at the owner's direction, and the reasons that rule
existed are kept as invariants of the rewrite: every value, every comment of
theirs and every unrecognised key survives, and the rewrite is refused outright
unless it reads back to exactly the same settings.

Run:  cd PDF-Linker && python3 -m pytest tests/test_config_tidy.py -v
"""
import logging
import re
from pathlib import Path

import pdf_linker as P

log = logging.getLogger("test")

# The file a real operator had, in shape: a header, one documented setting and
# three lines typed under it.
OLD = """# pdf_linker settings. Edit the values below to change behaviour without
# touching the code. Lines starting with # are comments. A command-line
# flag (e.g. --no-pseudonymize) overrides the matching setting here.

# Pseudonymize the .txt exports? on/off (default: on). When on, party /
# attorney names, case numbers, and detected PII in the .txt exports are
# swapped for stable fakes using the newest Order*.xlsx in Downloads; the
# PDFs themselves are never modified.
pseudonymize = on
keep_original_text = on
master_leaks = on
master_leaks_path = C:\\Users\\ZCoderre\\Documents\\Master Leaks.xlsx
"""


def _cfg(tmp_path, monkeypatch, text=OLD):
    path = tmp_path / "pdf_linker.config"
    path.write_text(text, encoding="utf-8")
    monkeypatch.setattr(P, "_config_path", lambda: path)
    return path


def _live(text):
    """{key: value} for the settings a file actually sets."""
    return P._config_live(text)


# ── the blocks ───────────────────────────────────────────────────────────────

def test_every_setting_has_a_block_and_the_template_is_their_sum():
    keys = [k for k, _b in P._CONFIG_BLOCKS]
    assert len(keys) == len(set(keys)), keys
    assert P._CONFIG_TEMPLATE == (P._CONFIG_HEADER + "".join(
        b for _k, b in P._CONFIG_BLOCKS)).rstrip("\n") + "\n"


def test_the_template_is_what_the_tidy_would_write():
    # The identity that makes a fresh file already tidy, and a tidy of one a
    # no-op: rendering with nothing to substitute IS the template.
    assert P._config_render({}, {}, [], []) == P._CONFIG_TEMPLATE
    assert P._config_tidy_text(P._CONFIG_TEMPLATE)[0] == P._CONFIG_TEMPLATE


def test_a_block_sets_exactly_one_key():
    # What kept topping up safe and still bounds the rewrite: a block can never
    # re-set a key the file already carries.
    for key, block in P._CONFIG_BLOCKS:
        setters = [ln for ln in block.splitlines()
                   if P._CONFIG_SETTING_RE.match(ln)]
        assert len(setters) == 1, (key, setters)
        assert re.match(r"^[ \t]*(#[ ]?)?" + re.escape(key) + r"[ \t]*=",
                        setters[0]), (key, setters[0])


def test_the_two_readers_of_a_setting_line_agree():
    # `_CONFIG_SETTING_RE` is the generic form of `_config_key_re`. Two readers
    # drawing the line in different places is how a block of prose comes to be
    # read as a setting, or a setting as prose.
    for line in ("copy_to = X", "# copy_to = X", "  copy_to=X", "copy_to\t= X",
                 "#   defer_run = off  the copy is made at the END",
                 "# This mentions copy_to = nothing in particular",
                 "not a setting at all"):
        generic = P._CONFIG_SETTING_RE.match(line)
        keyed = P._config_key_re(
            (generic.group(2) if generic else "copy_to")).search(line)
        assert bool(generic) == bool(keyed), line


def test_the_defaults_in_the_template_are_the_code_defaults():
    # The invariant that lets a setting be added mid-run: the line written
    # describes what the run was already going to do.
    live = _live(P._CONFIG_TEMPLATE)
    assert P._config_bool(live, "pseudonymize", False) is True
    assert P._config_bool(live, "partial_names", True) is False
    assert P._config_bool(live, "defer_run", True) is False
    assert P._config_bool(live, "keep_original_text", True) is False
    assert P._config_bool(live, "master_leaks", True) is False
    assert P._config_bool(live, "combined_text", True) is False
    assert live["text_subfolder"] == "Text Files"
    assert float(live["column_band_tol"]) == P._COLUMN_BAND_TOL
    assert live["leak_gate"] == "primary"
    # The two whose default is "do nothing" ship LIVE AND EMPTY — no '# ' in
    # front of them to be left there by an operator filling the value in.
    assert live["copy_to"] == "" and live["master_leaks_path"] == ""
    assert P._copy_dest_root(live, None) is None
    assert P._pn_master_leaks_path(live) is None


# ── what the tidy must never move ────────────────────────────────────────────

def test_the_missing_settings_are_added(tmp_path, monkeypatch):
    path = _cfg(tmp_path, monkeypatch)
    added, _removed = P._config_tidy(path, log)
    assert "defer_run" in added and "copy_to" in added
    text = path.read_text()
    for key, _b in P._CONFIG_BLOCKS:
        assert P._config_key_re(key).search(text), key


def test_every_value_they_set_survives(tmp_path, monkeypatch):
    path = _cfg(tmp_path, monkeypatch)
    before = _live(path.read_text())
    P._config_tidy(path, log)
    after = _live(path.read_text())
    assert before.items() <= after.items(), (before, after)
    # keep_original_text is ON here and OFF in the template; re-emitting the
    # block must carry the operator's value, not the default.
    assert after["keep_original_text"] == "on"
    assert P._read_config(log)["keep_original_text"] == "on"


def test_a_commented_out_setting_stays_commented_with_its_own_value(
        tmp_path, monkeypatch):
    # Commenting one out is a decision; the value typed into it is theirs too,
    # so the placeholder must not come back over the top of it.
    mine = "# copy_to = C:\\Users\\Zed\\OneDrive - Court\\Downloads\n"
    path = _cfg(tmp_path, monkeypatch, OLD + mine)
    P._config_tidy(path, log)
    text = path.read_text()
    assert mine in text
    assert "copy_to" not in _live(text)
    assert len(P._config_key_re("copy_to").findall(text)) == 1


def test_an_unknown_key_survives(tmp_path, monkeypatch):
    # Not this version's to drop: it is either from a newer build or typed by
    # hand, and either way it is theirs.
    path = _cfg(tmp_path, monkeypatch, OLD + "future_setting = 7\n")
    P._config_tidy(path, log)
    text = path.read_text()
    assert _live(text)["future_setting"] == "7"
    assert P._CONFIG_UNKNOWN_NOTE.splitlines()[1] in text


def test_a_comment_the_operator_typed_survives(tmp_path, monkeypatch):
    note = "# leave this off until the OneDrive sync settles down\n"
    path = _cfg(tmp_path, monkeypatch, OLD + note + "partial_names = off\n")
    P._config_tidy(path, log)
    text = path.read_text()
    assert note in text
    # ...carried with the setting it was written under.
    assert text.index(note) < text.index("partial_names = off")


def test_a_previous_versions_prose_is_not_kept_as_their_note(tmp_path,
                                                             monkeypatch):
    # The other half of carrying comments forward: a file written against
    # version N carries version N's wording of a block, and preserving that
    # beside version N+1's would make the tidy a way of accumulating stale
    # documentation for ever.
    stale = ("# ALSO write every .txt export into ONE file? on/off "
             "(default: on).\ncombined_text = on\n")
    path = _cfg(tmp_path, monkeypatch, OLD + stale)
    P._config_tidy(path, log)
    text = path.read_text()
    assert _live(text)["combined_text"] == "on"
    assert "ONE file? on/off (default: on)" not in text
    assert text.count("ALSO write every .txt export into ONE file") == 1


def test_the_banners_are_folded_into_one_file(tmp_path, monkeypatch):
    # The reported symptom: two rounds of top-up, two banners, and the settings
    # scattered between them.
    banner = P._CONFIG_UNKNOWN_NOTE  # any ruled section header will do
    doubled = (OLD + "\n" + banner + "partial_names = off\n"
               + "\n" + banner + "combined_text = on\n")
    path = _cfg(tmp_path, monkeypatch, doubled)
    P._config_tidy(path, log)
    text = path.read_text()
    assert text.count("Settings this version does not recognise") == 0
    for key, _b in P._CONFIG_BLOCKS:
        assert len(P._config_key_re(key).findall(text)) == 1, key


def test_the_settings_come_out_in_the_blocks_own_order(tmp_path, monkeypatch):
    path = _cfg(tmp_path, monkeypatch)
    P._config_tidy(path, log)
    text = path.read_text()
    at = [text.index(P._config_key_re(k).search(text).group(0))
          for k, _b in P._CONFIG_BLOCKS]
    assert at == sorted(at)


# ── the retired setting ──────────────────────────────────────────────────────

def test_a_retired_setting_is_dropped_and_named(tmp_path, monkeypatch):
    path = _cfg(tmp_path, monkeypatch, OLD + "max_text_files = 40\n")
    _added, removed = P._config_tidy(path, log)
    assert removed == ["max_text_files"]
    text = path.read_text()
    assert "max_text_files" not in _live(text)
    assert P._CONFIG_REMOVED_LEAD + "max_text_files." in text


def test_the_removal_note_persists(tmp_path, monkeypatch):
    # It is the answer to "where did my setting go", and the operator may not
    # open the file until long after the run that dropped it.
    path = _cfg(tmp_path, monkeypatch, OLD + "max_text_files = 40\n")
    P._config_tidy(path, log)
    for _ in range(3):
        P._config_tidy(path, log)
        assert P._CONFIG_REMOVED_LEAD + "max_text_files." in path.read_text()
    # ...and it is only REPORTED by the run that actually dropped it.
    assert P._config_tidy(path, log)[1] == []


def test_a_retired_settings_prose_goes_with_it(tmp_path, monkeypatch):
    path = _cfg(tmp_path, monkeypatch,
                OLD + "# Most .txt exports one folder may deliver - the upload\n"
                      "# limit of the tool they are sent to (default: 20).\n"
                      "max_text_files = 40\n")
    P._config_tidy(path, log)
    assert "the upload" not in path.read_text()


# ── the licence for rewriting their file at all ──────────────────────────────

def test_a_tidy_that_would_change_a_setting_is_refused(tmp_path, monkeypatch):
    path = _cfg(tmp_path, monkeypatch)
    before = path.read_text()
    monkeypatch.setattr(P, "_config_render",
                        lambda *a, **k: "leak_gate = off\n")
    assert P._config_tidy_text(before)[0] is None
    assert P._config_tidy(path, log) == ([], [])
    assert path.read_text() == before


def test_a_second_run_changes_nothing(tmp_path, monkeypatch):
    path = _cfg(tmp_path, monkeypatch, OLD + "future_setting = 7\n"
                                       + "max_text_files = 40\n")
    P._config_tidy(path, log)
    text = path.read_text()
    assert P._config_tidy(path, log) == ([], [])
    assert path.read_text() == text          # no churn


def test_a_complete_file_is_left_alone(tmp_path, monkeypatch):
    path = _cfg(tmp_path, monkeypatch, P._CONFIG_TEMPLATE)
    assert P._config_tidy(path, log) == ([], [])
    assert path.read_text() == P._CONFIG_TEMPLATE


def test_reading_the_config_tidies_it(tmp_path, monkeypatch):
    # It happens on the ordinary path, so an operator gets the new settings by
    # running the tool rather than by being told to delete their config.
    path = _cfg(tmp_path, monkeypatch)
    cfg = P._read_config(log)
    # ...and this run still used the file as they left it.
    assert cfg["master_leaks"] == "on" and "defer_run" not in cfg
    assert P._config_key_re("defer_run").search(path.read_text())


def test_a_missing_file_still_gets_the_whole_template(tmp_path, monkeypatch):
    path = tmp_path / "pdf_linker.config"
    monkeypatch.setattr(P, "_config_path", lambda: path)
    assert P._read_config(log) == {}
    assert path.read_text() == P._CONFIG_TEMPLATE


def test_an_unwritable_config_never_fails_the_run(tmp_path, monkeypatch):
    path = _cfg(tmp_path, monkeypatch)
    before = path.read_text()

    def boom(*a, **k):
        raise OSError("read-only")
    monkeypatch.setattr(Path, "write_text", boom)
    assert P._config_tidy(path, log) == ([], [])
    assert path.read_text() == before
    assert not list(tmp_path.glob("*.tmp"))      # nothing left behind


def test_prose_that_MENTIONS_a_setting_is_not_a_setting(tmp_path, monkeypatch):
    # The copy_to block explains itself with indented lines naming defer_run;
    # reading one as the setting itself would report a setting as documented
    # when it is only being talked about.
    path = _cfg(tmp_path, monkeypatch,
                "pseudonymize = on\n"
                "#   defer_run = off  the copy is made at the END of the run\n")
    assert "defer_run" in P._config_tidy(path, log)[0]


# ── the commented-out setting that is doing nothing ──────────────────────────

def test_a_commented_out_setting_with_a_typed_value_is_reported(tmp_path,
                                                                monkeypatch):
    # The reported failure: copy_to pointing at a real OneDrive folder, with
    # the '# ' the template's placeholder line came with still in front of it.
    # No copy was ever made and nothing said why.
    mine = "C:\\Users\\Zed\\OneDrive - Court\\Downloads"
    text = OLD + f"# copy_to = {mine}\n"
    assert P._config_commented_out(text) == {"copy_to": mine}
    said = []
    P._warn_commented_out_settings(
        text, type("L", (), {"warning": lambda _s, m: said.append(m)})())
    assert len(said) == 1 and "copy_to" in said[0] and mine in said[0]
    assert "COMMENTED OUT" in said[0]


def test_the_untouched_placeholder_says_nothing(tmp_path, monkeypatch):
    # Nothing in a fresh config is commented out any more, and an older file
    # still carrying the placeholder it used to ship is not a decision either.
    assert P._config_commented_out(P._CONFIG_TEMPLATE) == {}
    for key, values in P._CONFIG_PLACEHOLDERS.items():
        for v in values:
            assert P._config_commented_out(f"# {key} = {v}\n") == {}


def test_the_old_placeholder_line_is_replaced_by_the_live_empty_one(
        tmp_path, monkeypatch):
    # An older file carries `# copy_to = C:\Users\you\Documents\Cases`,
    # which is the trap, not a choice. It is dropped for the line that ships
    # now, so the setting can be filled in without a '# ' to remember.
    old = "# copy_to = C:\\Users\\you\\Documents\\Cases\n"
    path = _cfg(tmp_path, monkeypatch, OLD + old)
    P._config_tidy(path, log)
    text = path.read_text()
    assert old not in text
    assert "\ncopy_to =\n" in text
    assert _live(text)["copy_to"] == ""       # still off, which is the default


def test_a_commented_out_value_is_still_never_applied(tmp_path, monkeypatch):
    path = _cfg(tmp_path, monkeypatch,
                OLD + "# copy_to = C:\\Users\\Zed\\Cases\n")
    assert "copy_to" not in P._read_config(log)
    assert "copy_to" not in _live(path.read_text())


def test_the_real_operator_file_tidies_cleanly(tmp_path, monkeypatch):
    """End to end on the shape that was reported: two banners, a retired
    setting, and copy_to filled in but left commented out."""
    mine = "C:\\Users\\ZCoderre\\OneDrive - Los Angeles Superior Court\\Downloads"
    theirs = (OLD
              + "\n# \u2500\u2500 Settings this file did not mention \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
                "# Added by a newer PDF-Linker, at their defaults. Nothing above was\n"
                "# changed: your own settings, values and notes are exactly as you left\n"
                "# them, and a default appended here does the same thing the tool was\n"
                "# already doing. Edit or delete these freely.\n\n"
              + "partial_names = off\ndefer_run = on\n"
              + f"# copy_to = {mine}\n"
              + "text_subfolder = Text Files\nmax_text_files = 40\n"
                "leak_gate = strict\n"
              + "\n# \u2500\u2500 Settings this file did not mention \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
                "# Added by a newer PDF-Linker, at their defaults. Nothing above was\n"
                "# changed: your own settings, values and notes are exactly as you left\n"
                "# them, and a default appended here does the same thing the tool was\n"
                "# already doing. Edit or delete these freely.\n\n"
              + "combined_text = on\n")
    path = _cfg(tmp_path, monkeypatch, theirs)
    before = _live(theirs)
    P._config_tidy(path, log)
    text = path.read_text()
    # Every value they set, bar the retired one this version no longer has.
    del before["max_text_files"]
    after = _live(text)
    assert before.items() <= after.items(), (before, after)
    assert "max_text_files" not in after
    # One block each, no banner, the note naming what went, and their copy_to
    # path still there — still commented out, because that is their decision.
    for key, _b in P._CONFIG_BLOCKS:
        assert len(P._config_key_re(key).findall(text)) == 1, key
    assert "Settings this file did not mention" not in text
    assert P._CONFIG_REMOVED_LEAD + "max_text_files." in text
    assert f"# copy_to = {mine}\n" in text
    # ...and it settles: the next run rewrites nothing.
    assert P._config_tidy(path, log) == ([], [])


def test_deleting_the_hash_is_all_it_takes(tmp_path, monkeypatch):
    """The whole of the reported failure, both ways round: the commented line
    copies nothing, and the same line with the '# ' gone reaches the copier."""
    dest = tmp_path / "OneDrive - Court" / "Downloads"
    dest.mkdir(parents=True)
    args = type("A", (), {"copy_to": None, "no_copy": False})()

    path = _cfg(tmp_path, monkeypatch, OLD + f"# copy_to = {dest}\n")
    assert P._copy_dest_root(P._read_config(log), args, log) is None

    path.write_text(path.read_text().replace(f"# copy_to = {dest}",
                                             f"copy_to = {dest}"))
    assert P._copy_dest_root(P._read_config(log), args, log) == dest
    # ...and the tidy leaves it on.
    assert _live(path.read_text())["copy_to"] == str(dest)
