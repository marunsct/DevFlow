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
