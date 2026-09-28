"""A restarted container must not inherit a dead process's metric file.

`prometheus_client`'s multiprocess mode names each process's mmap file after
`os.getpid()`. Both containers here share the `appdata` volume so the two can be
aggregated, and `PROMETHEUS_MULTIPROC_DIR` is `/app/data/prometheus` inside it -
which means the files outlive the container. A container's PIDs start from 1
again on every restart, so a fresh process opens the file a long-dead process
left behind, and when the two disagree about its shape the read fails outright:

    RuntimeError: Read beyond file size detected, file is corrupted.

Measured on one run: that exception 17 times, once per stage, so not one
stage duration in the whole run was recorded. The directory held 49 `.db` files
going back three days - `counter_1.db`, `counter_354.db`, `counter_2673.db` -
PIDs belonging to container generations that no longer exist.

The directory cannot simply be emptied at startup, for the reason the module
already documents: a dead process's counters are still part of the total, and
both containers share the volume, so one of them starting would erase the
other's. Making the file name unique per process generation removes the
collision instead of arguing about who is allowed to delete what.

Three properties matter and each is tested here: a later process never reuses an
earlier one's file, a forked child gets its own, and a file that can no longer be
read is removed rather than left to fail every scrape of `/metrics`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"

#: Enough bytes to look like a file and not enough to be one.
GARBAGE = b"garbage that is not an mmap dict"


def _in_a_fresh_process(directory: Path, body: str) -> str:
    """Run `body` with the metrics module imported against `directory`.

    A subprocess because the whole subject is what one process inherits from
    another, and because `values.ValueClass` is bound at import.
    """
    environment = {
        **os.environ,
        "PROMETHEUS_MULTIPROC_DIR": str(directory),
        "PYTHONPATH": str(SRC),
    }
    finished = subprocess.run(
        [sys.executable, "-c", body],
        capture_output=True,
        text=True,
        env=environment,
        timeout=60,
    )
    assert finished.returncode == 0, finished.stderr
    return finished.stdout


RECORD = """
from app.observability.metrics import MetricsTracker, _the_identity_of_this_process
MetricsTracker.record_run()
MetricsTracker.record_stage_duration('technical_lead', 1.0)
print(_the_identity_of_this_process())
"""

#: Records without importing anything the fix added, so the corruption tests
#: fail on the old module for the reason they are about rather than on an import.
RECORD_ONLY = """
from app.observability.metrics import MetricsTracker
MetricsTracker.record_run()
MetricsTracker.record_stage_duration('technical_lead', 1.0)
"""

SCRAPE = """
from prometheus_client import CollectorRegistry, multiprocess, generate_latest
registry = CollectorRegistry()
multiprocess.MultiProcessCollector(registry)
for line in generate_latest(registry).decode().splitlines():
    if line.startswith('run_total ') or 'stage_duration_seconds_count' in line:
        print(line)
"""


@pytest.fixture
def a_metrics_directory(tmp_path):
    directory = tmp_path / "prometheus"
    directory.mkdir()
    return directory


class TestTheNameIsUniquePerProcess:
    def test_two_processes_do_not_share_a_file(self, a_metrics_directory):
        first = _in_a_fresh_process(a_metrics_directory, RECORD).strip()
        second = _in_a_fresh_process(a_metrics_directory, RECORD).strip()

        assert first != second
        counters = sorted(p.name for p in a_metrics_directory.glob("counter_*.db"))
        assert len(counters) == 2, counters

    def test_the_identity_carries_the_pid(self):
        """The fork half of the contract: a child must differ from its parent."""
        sys.path.insert(0, str(SRC))
        from app.observability.metrics import _the_identity_of_this_process

        assert str(os.getpid()) in _the_identity_of_this_process()

    def test_a_forked_child_writes_its_own_file(self, a_metrics_directory):
        """Celery's pool forks, and `__check_for_pid_change` is what notices.

        The library re-calls the identifier on every value it creates, so the
        generation being inherited is harmless as long as the pid is not.
        """
        body = """
import os
from app.observability.metrics import MetricsTracker
MetricsTracker.record_run()
pid = os.fork()
if pid == 0:
    MetricsTracker.record_run()
    os._exit(0)
os.waitpid(pid, 0)
"""
        _in_a_fresh_process(a_metrics_directory, body)

        counters = sorted(p.name for p in a_metrics_directory.glob("counter_*.db"))
        assert len(counters) == 2, counters

    def test_both_processes_are_still_summed(self, a_metrics_directory):
        """The point of the shared directory, and what a wipe would have cost."""
        for _ in range(3):
            _in_a_fresh_process(a_metrics_directory, RECORD)

        scraped = _in_a_fresh_process(a_metrics_directory, SCRAPE)

        assert "run_total 3.0" in scraped
        assert 'stage_duration_seconds_count{stage="technical_lead"} 3.0' in scraped


class TestRemovingWhatCannotBeRead:
    def test_a_corrupt_file_is_removed(self, a_metrics_directory):
        """Not a loss being taken: it is already lost.

        Left in place it fails every scrape of `/metrics`, not only the process
        that wrote it.
        """
        (a_metrics_directory / "counter_1.db").write_bytes(GARBAGE)

        _in_a_fresh_process(a_metrics_directory, RECORD_ONLY)

        assert not (a_metrics_directory / "counter_1.db").exists()

    def test_a_file_too_short_to_open_is_removed(self, a_metrics_directory):
        (a_metrics_directory / "histogram_2.db").write_bytes(b"x")

        _in_a_fresh_process(a_metrics_directory, RECORD_ONLY)

        assert not (a_metrics_directory / "histogram_2.db").exists()

    def test_the_scrape_works_afterwards(self, a_metrics_directory):
        """The whole failure, end to end: 17 lost stage durations became this.

        Checked by scraping, because a check that only called the reader without
        consuming it found nothing - it returns a generator, and that is exactly
        the bug this test caught in the fix itself.
        """
        (a_metrics_directory / "counter_1.db").write_bytes(GARBAGE)
        (a_metrics_directory / "histogram_2.db").write_bytes(b"x")

        _in_a_fresh_process(a_metrics_directory, RECORD_ONLY)
        scraped = _in_a_fresh_process(a_metrics_directory, SCRAPE)

        assert 'stage_duration_seconds_count{stage="technical_lead"} 1.0' in scraped

    def test_a_readable_file_is_kept(self, a_metrics_directory):
        """Only unreadable ones go. A working total must survive."""
        _in_a_fresh_process(a_metrics_directory, RECORD_ONLY)
        before = sorted(p.name for p in a_metrics_directory.glob("*.db"))

        _in_a_fresh_process(a_metrics_directory, RECORD_ONLY)

        assert set(before) <= set(p.name for p in a_metrics_directory.glob("*.db"))

    def test_a_file_older_than_the_window_is_dropped(self, a_metrics_directory):
        """Otherwise they accumulate for the life of the volume, and each one is
        read on every scrape."""
        sys.path.insert(0, str(SRC))
        from app.observability.metrics import DAYS_TO_KEEP_A_DEAD_PROCESS_FILE

        stale = a_metrics_directory / "counter_9999.db"
        _in_a_fresh_process(a_metrics_directory, RECORD_ONLY)
        readable = next(a_metrics_directory.glob("counter_*.db"))
        stale.write_bytes(readable.read_bytes())
        long_ago = os.path.getmtime(stale) - (DAYS_TO_KEEP_A_DEAD_PROCESS_FILE + 1) * 86400
        os.utime(stale, (long_ago, long_ago))

        _in_a_fresh_process(a_metrics_directory, RECORD_ONLY)

        assert not stale.exists()


class TestWithoutTheVariable:
    def test_nothing_is_touched_when_multiprocess_is_off(self, tmp_path, monkeypatch):
        """The CLI and this suite run single-process on the in-memory registry."""
        monkeypatch.delenv("PROMETHEUS_MULTIPROC_DIR", raising=False)
        sys.path.insert(0, str(SRC))
        from app.observability.metrics import _prepare_multiprocess_dir

        _prepare_multiprocess_dir()

        assert list(tmp_path.iterdir()) == []

    def test_recording_still_works(self):
        sys.path.insert(0, str(SRC))
        from app.observability.metrics import MetricsTracker

        MetricsTracker.record_stage_duration("product_manager", 0.5)
        MetricsTracker.record_defect_resolution(True)
        MetricsTracker.record_run()
