"""Memory the kernel can take back is headroom: page cache is not counted as in use.

Measured on two live runs: `memory.current` counts every file page a cgroup read or wrote, so a worker at 7.45 of its
8 GiB refused every build and suite for five minutes; one round's 32 tests were blamed on a fix, which was reverted.
"""
from __future__ import annotations

from app.tools import resources

GiB = 1024**3


def _a_cgroup(tmp_path, monkeypatch, current, stat):
    (tmp_path / "memory.max").write_text(str(8 * GiB))
    (tmp_path / "memory.current").write_text(str(current))
    (tmp_path / "memory.stat").write_text("".join(f"{name} {value}\n" for name, value in stat.items()))
    monkeypatch.setattr(resources, "_CGROUP_V2", str(tmp_path))
    monkeypatch.setattr(resources, "_CGROUP_V1_MEMORY", str(tmp_path / "v1"))


def test_clean_page_cache_is_headroom(tmp_path, monkeypatch):
    _a_cgroup(tmp_path, monkeypatch, current=int(7.45 * GiB),
              stat={"anon": GiB, "file": int(6.4 * GiB), "active_file": 4 * GiB, "inactive_file": int(2.4 * GiB),
                    "file_dirty": 0, "file_writeback": 0})

    state = resources.read_resource_state()

    assert state.memory_in_use < int(1.1 * GiB)
    assert resources.enough_headroom(GiB, state)[0] is True


def test_dirty_pages_still_count_as_in_use(tmp_path, monkeypatch):
    _a_cgroup(tmp_path, monkeypatch, current=int(7.45 * GiB),
              stat={"anon": GiB, "active_file": 4 * GiB, "inactive_file": int(2.4 * GiB),
                    "file_dirty": 3 * GiB, "file_writeback": GiB})

    assert resources.read_resource_state().memory_in_use > 5 * GiB


def test_memory_the_processes_hold_is_still_refused(tmp_path, monkeypatch):
    _a_cgroup(tmp_path, monkeypatch, current=int(7.9 * GiB),
              stat={"anon": int(7.8 * GiB), "active_file": 50 * 1024**2, "inactive_file": 50 * 1024**2})

    allowed, why = resources.enough_headroom(GiB, resources.read_resource_state())

    assert allowed is False and "Not enough memory" in why


def test_a_cgroup_without_its_stat_file_reads_as_before(tmp_path, monkeypatch):
    _a_cgroup(tmp_path, monkeypatch, current=int(7.45 * GiB), stat={})
    (tmp_path / "memory.stat").unlink()

    assert resources.read_resource_state().memory_in_use == int(7.45 * GiB)
