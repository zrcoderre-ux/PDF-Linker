"""A config file that PREDATES a setting is topped up with it.

The template used to be written once, when no config file existed — so every
setting added later was invisible to anyone who already had one, which after
the first run is everyone. A real operator's file sat with four settings in it
while the tool had grown twelve, and the only way to find `copy_to` or
`defer_run` was to read the source.

The file is APPENDED to, never rewritten: their values, their ordering, their
own comments and any key this version has never heard of all stay exactly as
they are.

Run:  cd PDF-Linker && python3 -m pytest tests/test_config_topup.py -v
"""
import logging
import re
from pathlib import Path

import pytest

import pdf_linker as P

log = logging.getLogger("test")

# The file a real operator had, verbatim in shape: a header, one documented
# setting, and three lines typed under it.
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
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip().lower()] = v.strip()
    return out


# ── the blocks ───────────────────────────────────────────────────────────────

def test_every_setting_has_a_block_and_the_template_is_their_sum():
    keys = [k for k, _b in P._CONFIG_BLOCKS]
    assert len(keys) == len(set(keys)), keys
    assert P._CONFIG_TEMPLATE == P._CONFIG_HEADER + "".join(
        b for _k, b in P._CONFIG_BLOCKS)


def test_a_block_sets_exactly_one_key():
    # What makes topping up safe: a block can never re-set a key the file
    # already carries, so a default appended below can never override a value
    # the operator typed above.
    for key, block in P._CONFIG_BLOCKS:
        setters = [ln for ln in block.splitlines()
                   if re.match(r"^[ \t]*(#[ ]?)?[A-Za-z_][A-Za-z0-9_]*[ \t]*=",
                               ln)]
        assert len(setters) == 1, (key, setters)
        assert re.match(r"^[ \t]*(#[ ]?)?" + re.escape(key) + r"[ \t]*=",
                        setters[0]), (key, setters[0])


def test_the_defaults_in_the_template_are_the_code_defaults():
    # The invariant that lets a setting be appended mid-run: the line written
    # describes what the run was already going to do.
    live = _live(P._CONFIG_TEMPLATE)
    assert P._config_bool(live, "pseudonymize", False) is True
    assert P._config_bool(live, "partial_names", True) is False
    assert P._config_bool(live, "defer_run", True) is False
    assert P._config_bool(live, "keep_original_text", True) is False
    assert P._config_bool(live, "master_leaks", True) is False
    assert live["text_subfolder"] == "Text Files"
    assert float(live["column_band_tol"]) == P._COLUMN_BAND_TOL
    assert live["leak_gate"] == "primary"
    # The two that ship commented out are OFF by absence.
    assert "copy_to" not in live and "master_leaks_path" not in live


# ── topping up ───────────────────────────────────────────────────────────────

def test_the_missing_settings_are_added(tmp_path, monkeypatch):
    path = _cfg(tmp_path, monkeypatch)
    added = P._config_add_missing(path, log)
    assert "defer_run" in added and "copy_to" in added
    text = path.read_text()
    for key, _b in P._CONFIG_BLOCKS:
        assert P._config_key_re(key).search(text), key


def test_what_the_operator_wrote_is_untouched(tmp_path, monkeypatch):
    path = _cfg(tmp_path, monkeypatch)
    P._config_add_missing(path, log)
    assert path.read_text().startswith(OLD)


def test_a_value_they_set_is_never_overridden_by_a_default(tmp_path,
                                                           monkeypatch):
    # keep_original_text is ON here and OFF in the template. Appending the
    # block that sets it would silently flip the setting, because the reader
    # takes the LAST line for a key.
    path = _cfg(tmp_path, monkeypatch)
    P._config_add_missing(path, log)
    assert _live(path.read_text())["keep_original_text"] == "on"
    assert P._read_config(log)["keep_original_text"] == "on"


def test_an_unknown_key_survives(tmp_path, monkeypatch):
    path = _cfg(tmp_path, monkeypatch, OLD + "future_setting = 7\n")
    P._config_add_missing(path, log)
    assert _live(path.read_text())["future_setting"] == "7"


def test_a_commented_out_setting_counts_as_mentioned(tmp_path, monkeypatch):
    # Commenting one out is a decision; re-adding it on the next run would
    # undo it every time.
    path = _cfg(tmp_path, monkeypatch, OLD + "# defer_run = on\n")
    assert "defer_run" not in P._config_add_missing(path, log)


def test_a_second_run_adds_nothing(tmp_path, monkeypatch):
    path = _cfg(tmp_path, monkeypatch)
    P._config_add_missing(path, log)
    text = path.read_text()
    assert P._config_add_missing(path, log) == []
    assert path.read_text() == text          # no churn


def test_a_complete_file_is_not_rewritten(tmp_path, monkeypatch):
    path = _cfg(tmp_path, monkeypatch, P._CONFIG_TEMPLATE)
    assert P._config_add_missing(path, log) == []
    assert path.read_text() == P._CONFIG_TEMPLATE


def test_reading_the_config_tops_it_up(tmp_path, monkeypatch):
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

    def boom(*a, **k):
        raise OSError("read-only")
    monkeypatch.setattr(Path, "write_text", boom)
    assert P._config_add_missing(path, log) == []


def test_prose_that_MENTIONS_a_setting_is_not_a_setting(tmp_path, monkeypatch):
    # The copy_to block explains itself with indented lines naming defer_run;
    # reading one as the setting itself would report a setting as documented
    # when it is only being talked about.
    path = _cfg(tmp_path, monkeypatch,
                "pseudonymize = on\n"
                "#   defer_run = off  the copy is made at the END of the run\n")
    assert "defer_run" in P._config_add_missing(path, log)
