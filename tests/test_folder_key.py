"""Folder-local key discovery: a re-run should resolve its own inputs from the
case folder — reuse pseudonym_key.xlsx if present, otherwise START OVER from an
Order*.xlsx template — without needing a Downloads copy or a typed --key."""
import logging

import pdf_linker as P

log = logging.getLogger("test_folder_key")
log.addHandler(logging.NullHandler())


def _touch(folder, name):
    p = folder / name
    p.write_bytes(b"x")
    return p


def test_order_template_only_starts_over_from_it(tmp_path):
    _touch(tmp_path, "Order_Template_Input.xlsx")
    got = P._pn_find_folder_key(tmp_path, log)
    assert got is not None and got.name == "Order_Template_Input.xlsx"


def test_pseudonym_key_is_preferred_over_order_template(tmp_path):
    _touch(tmp_path, "Order_Template_Input.xlsx")
    _touch(tmp_path, "pseudonym_key.xlsx")
    got = P._pn_find_folder_key(tmp_path, log)
    assert got is not None and got.name == "pseudonym_key.xlsx"   # reuse fakes


def test_deleting_the_key_falls_back_to_the_order_template(tmp_path):
    order = _touch(tmp_path, "Order_Template_Input.xlsx")
    key = _touch(tmp_path, "pseudonym_key.xlsx")
    key.unlink()                                   # operator forces fresh fakes
    got = P._pn_find_folder_key(tmp_path, log)
    assert got == order                            # starts over from the template


def test_no_key_and_no_template_is_none(tmp_path):
    _touch(tmp_path, "SomeBrief.pdf")
    assert P._pn_find_folder_key(tmp_path, log) is None


def test_excel_lock_files_are_ignored(tmp_path):
    _touch(tmp_path, "~$Order_Template_Input.xlsx")
    assert P._pn_find_folder_key(tmp_path, log) is None


def test_newest_order_template_wins(tmp_path):
    import os
    import time
    old = _touch(tmp_path, "Order_old.xlsx")
    new = _touch(tmp_path, "Order_new.xlsx")
    # Make `new` unambiguously the more recently modified file.
    past = time.time() - 1000
    os.utime(old, (past, past))
    got = P._pn_find_folder_key(tmp_path, log)
    assert got == new
