"""The machine-wide OCR core budget: two runs SHARE the cores, never double them.

`_ocr_workers` sizes one run's OCR pool at cores-1, and every run answered that
the same way — so two folders started together spawned cores-1 Tesseracts each
and oversubscribed the machine. `_ocr_lease` leases the cores actually free when
a pass starts, one byte-range lock per core, and drops them when it ends.

Never blocks, never returns zero, and fails OPEN where byte-range locking is
unsupported: a gate that cannot be taken must never stop legitimate work — the
same rule `_acquire_folder_lock` follows.

Run:  cd PDF-Linker && python3 -m pytest tests/test_ocr_core_budget.py -v
"""
import os

import pytest

import pdf_linker as P


@pytest.fixture
def budget(tmp_path, monkeypatch):
    """A budget file of this test's own, and no env override in the way."""
    monkeypatch.setattr(P, "_OCR_SLOT_FH", None)
    monkeypatch.setattr(P, "_OCR_SLOTS_OK", True)
    monkeypatch.setattr(P, "_OCR_PRIORITY_HELD", False)
    monkeypatch.setattr(P, "_OCR_WORKERS", None)
    monkeypatch.delenv("PDF_LINKER_OCR_WORKERS", raising=False)
    monkeypatch.delenv("PDF_LINKER_NO_OCR_SLOTS", raising=False)
    monkeypatch.setattr(P, "_ocr_slot_path", lambda: tmp_path / "slots.lock")
    return tmp_path / "slots.lock"


@pytest.fixture
def log():
    """A real logger, so the lines these paths write are part of what is
    pinned: "this run is slow" and "this run is sharing the machine" are
    indistinguishable in the log without them."""
    import logging
    return logging.getLogger("pdf_linker.test.budget")


def _cores(monkeypatch, n):
    monkeypatch.setattr(P, "_ocr_slot_capacity", lambda: n)
    monkeypatch.setattr(P, "_ocr_workers", lambda: n)


def test_one_run_alone_leases_everything_it_would_have_taken(budget, monkeypatch):
    # The whole point of the budget is to be invisible to a run with the machine
    # to itself — the case that was never the problem.
    _cores(monkeypatch, 8)
    with P._ocr_lease(100) as workers:
        assert workers == 8


def test_a_pass_never_leases_a_core_it_cannot_use(budget, monkeypatch):
    # Three pages cannot occupy eight Tesseracts, and a core leased to nobody is
    # a core the other run cannot have.
    _cores(monkeypatch, 8)
    with P._ocr_lease(3) as workers:
        assert workers == 3


def test_a_second_run_gets_what_is_left_not_a_second_full_pool(budget,
                                                               monkeypatch):
    # The defect this exists for: 2 runs x cores-1 Tesseracts on cores-1 cores.
    _cores(monkeypatch, 4)
    first = P._ocr_lease(100)
    try:
        assert first.workers == 4
        # A separate process is what really contends; within one process POSIX
        # record locks do not conflict, so the second lease is taken against a
        # budget file the first has already emptied from a FRESH handle.
        second_held = _lease_from_another_process(budget, want=4)
        assert second_held == 0        # nothing free
    finally:
        first.release()
    assert _lease_from_another_process(budget, want=4) == 4   # released


def _lease_from_another_process(path, want):
    """How many cores a DIFFERENT process could lease right now. Run out of
    process because POSIX record locks are per-process: a second lock taken
    here would succeed against our own and prove nothing."""
    import subprocess
    import sys
    code = (
        "import sys, os\n"
        "fh = open(sys.argv[1], 'a+b')\n"
        "n = 0\n"
        "for i in range(int(sys.argv[2])):\n"
        "    try:\n"
        "        if os.name == 'nt':\n"
        "            import msvcrt; fh.seek(i); msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)\n"
        "        else:\n"
        "            import fcntl; fcntl.lockf(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB, 1, i, 0)\n"
        "        n += 1\n"
        "    except OSError:\n"
        "        pass\n"
        "print(n)\n")
    out = subprocess.run([sys.executable, "-c", code, str(path), str(want)],
                         capture_output=True, text=True, timeout=60)
    return int(out.stdout.strip())


def test_a_full_machine_proceeds_on_one_core_and_never_waits(budget,
                                                             monkeypatch):
    # Waiting for a core would trade a slow run for a stopped one.
    _cores(monkeypatch, 2)
    monkeypatch.setattr(P, "_ocr_slot_lock",
                        lambda fh, i, release=False: False)   # all leased
    with P._ocr_lease(100) as workers:
        assert workers == 1


def test_leases_are_dropped_however_the_pass_ends(budget, monkeypatch):
    # The per-file loop CATCHES an exception and carries on to the next file, so
    # a pass that raised without releasing would starve every later pass.
    _cores(monkeypatch, 4)
    lease = P._ocr_lease(100)
    with pytest.raises(RuntimeError):
        with lease:
            raise RuntimeError("OCR blew up")
    assert _lease_from_another_process(budget, want=4) == 4


def test_unsupported_locking_fails_open_on_the_nominal_width(budget,
                                                            monkeypatch):
    # A filesystem without byte-range locks gets exactly today's behaviour.
    _cores(monkeypatch, 6)
    monkeypatch.setattr(P, "_ocr_slot_lock",
                        lambda fh, i, release=False: None)
    with P._ocr_lease(100) as workers:
        assert workers == 6


def test_an_explicit_worker_count_bypasses_the_budget(budget, monkeypatch):
    # An operator naming a number has made a decision about their own machine;
    # the budget must not trim it.
    monkeypatch.setattr(P, "_ocr_slot_capacity", lambda: 4)
    monkeypatch.setenv("PDF_LINKER_OCR_WORKERS", "7")
    monkeypatch.setattr(P, "_OCR_WORKERS", None)
    with P._ocr_lease(100) as workers:
        assert workers == 7
    assert _lease_from_another_process(budget, want=4) == 4   # took nothing


def test_the_budget_can_be_switched_off(budget, monkeypatch):
    _cores(monkeypatch, 5)
    monkeypatch.setenv("PDF_LINKER_NO_OCR_SLOTS", "1")
    with P._ocr_lease(100) as workers:
        assert workers == 5
    assert _lease_from_another_process(budget, want=5) == 5   # took nothing


def test_capacity_matches_the_single_run_default(monkeypatch):
    # The budget is sized to what one run already assumed it could have, so the
    # solo case is unchanged by construction.
    monkeypatch.setattr(P.os, "cpu_count", lambda: 12)
    assert P._ocr_slot_capacity() == 11
    monkeypatch.setattr(P.os, "cpu_count", lambda: 1)
    assert P._ocr_slot_capacity() == 1
    monkeypatch.setattr(P.os, "cpu_count", lambda: None)
    assert P._ocr_slot_capacity() == 1


# ── --first: the folder the operator is actually waiting on ──────────────────

import subprocess
import sys
import textwrap


class _RivalRun:
    """A REAL second process holding a byte of the budget file, because POSIX
    record locks do not conflict within one process — a rival faked in-process
    would prove nothing."""

    def __init__(self, path, offset):
        code = textwrap.dedent("""
            import os, sys
            fh = open(sys.argv[1], 'a+b')
            i = int(sys.argv[2])
            if fh.seek(0, os.SEEK_END) < i + 1:
                fh.write(b'.' * (i + 1 - fh.tell())); fh.flush()
            if os.name == 'nt':
                import msvcrt; fh.seek(i); msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl; fcntl.lockf(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB, 1, i, 0)
            print('held', flush=True)
            sys.stdin.read()
        """)
        self.proc = subprocess.Popen(
            [sys.executable, "-c", code, str(path), str(offset)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        assert self.proc.stdout.readline().strip() == "held"

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.proc.stdin.close()
        self.proc.wait(timeout=60)
        return False


def test_first_claims_the_cores_and_says_so(budget, monkeypatch, caplog, log):
    _cores(monkeypatch, 4)
    with caplog.at_level("INFO"):
        assert P._claim_ocr_priority(log) is True
    assert P._OCR_PRIORITY_HELD is True
    assert "holds the machine's OCR cores" in caplog.text
    # Idempotent: a second claim by the run that already holds it is not a race
    # it can lose against itself.
    assert P._claim_ocr_priority(log) is True


def test_a_priority_run_keeps_its_full_pool(budget, monkeypatch, log):
    _cores(monkeypatch, 6)
    P._claim_ocr_priority(log)
    with P._ocr_lease(100) as workers:
        assert workers == 6            # never yields to its own claim


def test_every_other_run_narrows_to_one_core(budget, monkeypatch, caplog, log):
    _cores(monkeypatch, 6)
    with _RivalRun(budget, P._ocr_priority_offset()):
        with caplog.at_level("INFO"):
            with P._ocr_lease(100, log) as workers:
                assert workers == 1
        assert "--first" in caplog.text
    # ...and gets its width back the moment the priority run ends.
    with P._ocr_lease(100) as workers:
        assert workers == 6


def test_a_narrowed_run_is_never_stopped(budget, monkeypatch):
    # --first costs the other folders time, never their progress.
    _cores(monkeypatch, 8)
    with _RivalRun(budget, P._ocr_priority_offset()):
        with P._ocr_lease(100) as workers:
            assert workers >= 1


def test_only_one_run_at_a_time_can_be_first(budget, monkeypatch, caplog, log):
    _cores(monkeypatch, 4)
    with _RivalRun(budget, P._ocr_priority_offset()):
        with caplog.at_level("INFO"):
            assert P._claim_ocr_priority(log) is False
        assert P._OCR_PRIORITY_HELD is False
        assert "already holds" in caplog.text
    # Refusing the claim must not refuse the RUN: the folder still processes.
    with P._ocr_lease(100) as workers:
        assert workers == 4


def test_a_claim_that_cannot_be_taken_leaves_the_run_sharing(budget,
                                                             monkeypatch,
                                                             caplog, log):
    _cores(monkeypatch, 5)
    monkeypatch.setattr(P, "_ocr_slot_lock",
                        lambda fh, i, release=False: None)   # unsupported
    with caplog.at_level("INFO"):
        assert P._claim_ocr_priority(log) is False
    assert "cannot lock" in caplog.text
    assert P._OCR_PRIORITY_HELD is False


def test_probing_for_priority_never_leaves_the_claim_taken(budget, monkeypatch):
    # The probe takes the byte and gives it straight back; a probe that kept it
    # would throttle every run on the machine and answer to nobody.
    _cores(monkeypatch, 4)
    fh = P._ocr_slot_handle()
    assert P._another_run_holds_priority(fh) is False
    assert _lease_from_another_process(budget, want=P._ocr_priority_offset() + 1) \
        == P._ocr_priority_offset() + 1
