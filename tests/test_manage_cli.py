"""Operator CLI for user accounts.

This exists because `init_db` deliberately will not overwrite an existing admin
account, which left no way back in when the password was lost - and the first
release generated that password at random and only logged it.
"""

import pytest

from app.server import manage
from app.server.auth import get_db_connection, get_user, verify_password


@pytest.fixture
def users(test_db):
    """A clean users table with the default admin seeded."""
    yield


def _run(*argv) -> int:
    return manage.main(list(argv))


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------


def test_resetting_a_password_sets_it(users):
    assert _run("reset-password", "admin", "--password", "a-new-password") == 0

    user = get_user("admin")
    assert verify_password("a-new-password", user.hashed_password)


def test_a_generated_password_is_printed_and_works(users, capsys):
    assert _run("reset-password", "admin") == 0

    printed = capsys.readouterr().out
    assert "New password:" in printed
    generated = printed.split("New password:")[1].strip()

    assert verify_password(generated, get_user("admin").hashed_password)


def test_resetting_an_unknown_user_fails(users, capsys):
    assert _run("reset-password", "nobody", "--password", "x") == 1
    assert "No user named" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Account creation
# ---------------------------------------------------------------------------


def test_creating_a_user(users):
    assert _run("create-user", "alice", "--password", "pw", "--role", "operator") == 0

    alice = get_user("alice")
    assert alice.role == "operator"
    assert alice.tenant_id == "default"
    assert verify_password("pw", alice.hashed_password)


def test_creating_a_user_in_a_tenant(users):
    assert _run("create-user", "bob", "--password", "pw", "--tenant", "acme") == 0
    assert get_user("bob").tenant_id == "acme"


def test_creating_a_duplicate_user_fails(users, capsys):
    _run("create-user", "carol", "--password", "pw")
    assert _run("create-user", "carol", "--password", "pw") == 1
    assert "already exists" in capsys.readouterr().err


def test_an_invalid_role_is_refused(users, capsys):
    assert manage.create_user("dave", "pw", "superuser", "default") == 1
    assert "Role must be one of" in capsys.readouterr().err
    assert get_user("dave") is None


# ---------------------------------------------------------------------------
# Roles and status
# ---------------------------------------------------------------------------


def test_changing_a_role(users):
    _run("create-user", "erin", "--password", "pw", "--role", "viewer")
    assert _run("set-role", "erin", "admin") == 0
    assert get_user("erin").role == "admin"


def test_setting_a_role_on_an_unknown_user_fails(users):
    assert _run("set-role", "ghost", "admin") == 1


def test_an_invalid_role_change_is_refused(users):
    assert manage.set_role("admin", "wizard") == 1
    assert get_user("admin").role == "admin"


def test_disabling_and_re_enabling_an_account(users):
    _run("create-user", "frank", "--password", "pw")

    assert _run("disable-user", "frank") == 0
    assert get_user("frank").disabled is True

    assert _run("enable-user", "frank") == 0
    assert get_user("frank").disabled is False


def test_disabling_an_unknown_user_fails(users):
    assert _run("disable-user", "ghost") == 1


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


def test_listing_shows_role_and_status(users, capsys):
    _run("create-user", "grace", "--password", "pw", "--role", "viewer", "--tenant", "acme")

    assert _run("list-users") == 0
    output = capsys.readouterr().out
    assert "grace" in output
    assert "viewer" in output
    assert "acme" in output
    assert "active" in output


def test_listing_an_empty_table(users, capsys):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("TRUNCATE TABLE users")
        conn.commit()

    assert _run("list-users") == 0
    assert "No users." in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Upgrade path
# ---------------------------------------------------------------------------


def test_an_upgraded_admin_keeps_its_role(users):
    """A database created before roles existed would otherwise have its admin
    demoted to the ADD COLUMN default, locking every admin action out."""
    from app.server.auth import init_db

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE users SET role = 'operator' WHERE username = 'admin'")
        conn.commit()

    init_db()
    assert get_user("admin").role == "admin"


# ---------------------------------------------------------------------------
# Run reconciliation
# ---------------------------------------------------------------------------


def _stored_run(run_store, run_id: str, status: str, stage: str):
    from app.server.runner import RunRecord

    record = RunRecord(
        run_id=run_id, thread_id=f"thread-{run_id}",
        document_names=[], document_paths=[],
        status=status, current_stage=stage,
    )
    run_store.save(record)
    return record


def test_a_row_that_drifted_from_its_gate_is_repaired(run_store, capsys):
    """status=failed while the graph waits on an approval leaves no usable route."""
    _stored_run(run_store, "run-drift", "failed", "awaiting_approval:principal_architect")

    assert manage.reconcile_runs() == 0

    repaired = run_store.load("run-drift")
    assert repaired.status == "waiting_for_approval"
    assert repaired.stage_meaning == "Waiting for approval: principal_architect"
    assert "Repaired 1 run(s)." in capsys.readouterr().out


def test_a_dry_run_reports_without_writing(run_store, capsys):
    _stored_run(run_store, "run-dry", "failed", "awaiting_user_review:specification")

    assert manage.reconcile_runs(dry_run=True) == 0

    assert run_store.load("run-dry").status == "failed"
    assert "would be repaired" in capsys.readouterr().out


def test_consistent_rows_are_left_alone(run_store, capsys):
    _stored_run(run_store, "run-ok", "failed", "principal_architect")

    assert manage.reconcile_runs() == 0

    assert run_store.load("run-ok").status == "failed"
    assert "All runs agree" in capsys.readouterr().out


def test_terminal_runs_are_never_reopened(run_store):
    """A cancelled run must not be dragged back to a gate by its stale stage."""
    _stored_run(run_store, "run-cancelled", "cancelled", "awaiting_approval:principal_architect")

    manage.reconcile_runs()

    assert run_store.load("run-cancelled").status == "cancelled"


# ---------------------------------------------------------------------------
# Per-run provider pins
# ---------------------------------------------------------------------------


def _pinned_run(run_store, run_id: str, overrides: dict):
    from app.server.runner import RunRecord

    record = RunRecord(
        run_id=run_id, thread_id=f"thread-{run_id}",
        document_names=[], document_paths=[],
        status="failed", current_stage="product_manager",
        model_overrides=overrides,
    )
    run_store.save(record)
    return record


def test_a_stale_pin_is_cleared(run_store, capsys):
    """The pin was a copy of global settings, never a deliberate choice."""
    _pinned_run(run_store, "run-pinned", {"llm_provider": "local", "model_name": "old-model"})

    assert manage.clear_run_overrides() == 0

    assert run_store.load("run-pinned").model_overrides == {}
    assert "Cleared 1 run(s)" in capsys.readouterr().out


def test_a_single_run_can_be_targeted(run_store):
    _pinned_run(run_store, "run-a", {"model_name": "old-a"})
    _pinned_run(run_store, "run-b", {"model_name": "old-b"})

    manage.clear_run_overrides("run-a")

    assert run_store.load("run-a").model_overrides == {}
    assert run_store.load("run-b").model_overrides == {"model_name": "old-b"}


def test_a_dry_run_reports_without_writing(run_store, capsys):
    _pinned_run(run_store, "run-dry", {"model_name": "old-model"})

    assert manage.clear_run_overrides(dry_run=True) == 0

    assert run_store.load("run-dry").model_overrides == {"model_name": "old-model"}
    assert "would be cleared" in capsys.readouterr().out


def test_runs_without_a_pin_are_left_alone(run_store, capsys):
    _pinned_run(run_store, "run-clean", {})

    assert manage.clear_run_overrides() == 0

    assert "No run carries a provider pin." in capsys.readouterr().out


def test_an_unknown_run_fails(run_store, capsys):
    assert manage.clear_run_overrides("run-nope") == 1
    assert "No run named" in capsys.readouterr().err


def test_reconcile_leaves_a_live_unattended_run_alone(run_store, capsys):
    """The command used to set an unattended run to `waiting_for_approval`,
    which is the row state that lets a second Celery task be dispatched onto a
    thread the first is still driving."""
    record = _stored_run(run_store, "run-unattended", "running",
                         "awaiting_approval:product_manager")
    record.auto_approve = True
    run_store.save(record)

    manage.reconcile_runs(dry_run=True)

    assert "waiting_for_approval" not in capsys.readouterr().out
    assert run_store.load("run-unattended").status == "running"


def test_reconcile_does_not_unrepair_a_damaged_run(run_store):
    """Item 4 of the previous phase marked these `failed` deliberately."""
    record = _stored_run(run_store, "run-repaired", "failed",
                         "awaiting_approval:product_manager")
    record.auto_approve = True
    run_store.save(record)

    manage.reconcile_runs()

    assert run_store.load("run-repaired").status == "failed"


# ---------------------------------------------------------------------------
# Orphaned-run recovery
#
# A run is handed to one Celery task and the row says `running` for as long as
# that task lives. When the process dies without unwinding - a host losing
# power, a container replaced mid-task - nothing writes a terminal status. The
# row then says `running` forever: `resume_run` compare-and-sets from `failed`
# so it refuses, and `reconcile-runs` only repairs rows parked on a pause. Hit
# twice on run-0b55ad49, both times needing hand-written SQL to get out of.
# ---------------------------------------------------------------------------


def _with_task(run_store, run_id: str, status: str, stage: str, task_id: str | None):
    record = _stored_run(run_store, run_id, status, stage)
    if task_id:
        run_store.set_task_id(run_id, task_id)
    return record


def test_a_run_whose_worker_died_becomes_resumable(run_store, monkeypatch, capsys):
    """The recovery half, with the resume half turned off.

    A successful sweep now also puts the run back on the queue, which moves
    it out of `failed` again - see
    `test_a_recovered_run_is_carried_all_the_way_back` below. This one is
    about the state it must pass through, so the resume is disabled.
    """
    monkeypatch.setenv("RESUME_ORPHANS_ON_START", "false")
    _with_task(run_store, "run-orphan", "running", "specialist_ui_ux_0", "task-gone")
    # A worker answered, and did not claim this task.
    monkeypatch.setattr(manage, "_live_task_ids", lambda: {"task-someone-else"})

    assert manage.recover_orphaned_runs() == 0

    recovered = run_store.load("run-orphan")
    assert recovered.status == "failed", "the run must reach the state resume accepts"
    assert "resume continues from the last checkpoint" in recovered.error
    assert "Recovered 1 run(s)." in capsys.readouterr().out


def test_a_recovered_run_is_carried_all_the_way_back(run_store, monkeypatch, capsys):
    """Recovering without resuming left every deploy needing an operator.

    Measured over one session on 2026-09-19: four worker restarts, four runs
    correctly recovered, four manual resume calls. The sweep now finishes the
    job, and this asserts it end to end rather than against a double - the
    first version of the resume called a method that existed only in its own
    test's mock.
    """
    monkeypatch.delenv("RESUME_ORPHANS_ON_START", raising=False)
    monkeypatch.setattr(manage, "_worker_ran_out_of_memory", lambda: False)
    resumed: list[str] = []
    monkeypatch.setattr(manage, "_resume_one", resumed.append)
    manage._RESUMED_ON_START.clear()

    _with_task(run_store, "run-orphan", "running", "specialist_ui_ux_0", "task-gone")
    monkeypatch.setattr(manage, "_live_task_ids", lambda: {"task-someone-else"})

    assert manage.recover_orphaned_runs() == 0

    assert resumed == ["run-orphan"]
    assert "resumed 1 of them" in capsys.readouterr().out


def test_a_run_whose_task_is_alive_is_never_touched(run_store, monkeypatch, capsys):
    """Resurrecting a live run puts two writers on one thread."""
    _with_task(run_store, "run-live", "running", "principal_architect", "task-alive")
    monkeypatch.setattr(manage, "_live_task_ids", lambda: {"task-alive"})

    assert manage.recover_orphaned_runs() == 0

    assert run_store.load("run-live").status == "running"
    assert "No orphaned runs" in capsys.readouterr().out


def test_nothing_is_repaired_when_no_worker_answers(run_store, monkeypatch, capsys):
    """Silence from the broker is not evidence that a task is dead."""
    _with_task(run_store, "run-unknown", "running", "scrum_master", "task-maybe")
    monkeypatch.setattr(manage, "_live_task_ids", lambda: None)

    assert manage.recover_orphaned_runs() == 1

    assert run_store.load("run-unknown").status == "running"
    assert "nothing can be judged orphaned" in capsys.readouterr().out


def test_orphan_recovery_leaves_other_statuses_alone(run_store, monkeypatch, capsys):
    _with_task(run_store, "run-done", "completed", "complete", None)
    _with_task(run_store, "run-failed", "failed", "principal_architect", None)
    monkeypatch.setattr(manage, "_live_task_ids", lambda: set())

    assert manage.recover_orphaned_runs() == 0

    assert run_store.load("run-done").status == "completed"
    assert run_store.load("run-failed").status == "failed"


def test_orphan_recovery_dry_run_writes_nothing(run_store, monkeypatch, capsys):
    _with_task(run_store, "run-dry-orphan", "running", "technical_lead", "task-gone")
    monkeypatch.setattr(manage, "_live_task_ids", lambda: set())

    assert manage.recover_orphaned_runs(dry_run=True) == 0

    assert run_store.load("run-dry-orphan").status == "running"
    assert "would be recovered" in capsys.readouterr().out
