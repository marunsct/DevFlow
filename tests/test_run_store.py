"""Run metadata persistence, atomic transitions and tenant scoping."""

from datetime import datetime, timezone

import pytest

from app.server.runner import RunRecord


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _record(run_id: str, **overrides) -> RunRecord:
    defaults = dict(
        run_id=run_id,
        thread_id=f"thread-{run_id}",
        document_names=["brief.md"],
        document_paths=[f"/tmp/{run_id}.md"],
        owner="alice",
        tenant_id="acme",
    )
    defaults.update(overrides)
    return RunRecord(**defaults)


# ---------------------------------------------------------------------------
# Round-tripping
# ---------------------------------------------------------------------------


def test_a_saved_record_round_trips(run_store):
    run_store.save(_record("run-1"))

    loaded = run_store.load("run-1")
    assert loaded.run_id == "run-1"
    assert loaded.owner == "alice"
    assert loaded.tenant_id == "acme"
    assert loaded.document_names == ["brief.md"]
    assert loaded.status == "created"


def test_loading_an_unknown_run_returns_none(run_store):
    assert run_store.load("run-does-not-exist") is None


def test_saving_twice_updates_rather_than_duplicating(run_store):
    run_store.save(_record("run-2"))
    record = run_store.load("run-2")
    record.reviewer = "bob"
    run_store.save(record)

    assert run_store.load("run-2").reviewer == "bob"
    assert run_store.count() == 1


def test_model_overrides_round_trip(run_store):
    run_store.save(_record("run-3", model_overrides={"model_name": "gpt-4o"}))
    assert run_store.load("run-3").model_overrides == {"model_name": "gpt-4o"}


# ---------------------------------------------------------------------------
# Atomic transitions - the double-submit regression
# ---------------------------------------------------------------------------


def test_a_transition_from_the_expected_status_succeeds(run_store):
    run_store.save(_record("run-4"))
    assert run_store.compare_and_set_status("run-4", "created", "running", updated_at=_now())
    assert run_store.load("run-4").status == "running"


def test_only_one_of_two_competing_transitions_wins(run_store):
    """The check and the write are one statement, so a double-click cannot
    dispatch the same run twice."""
    run_store.save(_record("run-5"))

    first = run_store.compare_and_set_status("run-5", "created", "running", updated_at=_now())
    second = run_store.compare_and_set_status("run-5", "created", "running", updated_at=_now())

    assert first is True
    assert second is False


def test_a_transition_from_the_wrong_status_is_refused(run_store):
    run_store.save(_record("run-6", status="completed"))
    assert not run_store.compare_and_set_status("run-6", "created", "running", updated_at=_now())


def test_a_transition_accepts_several_expected_statuses(run_store):
    run_store.save(_record("run-7", status="waiting_for_review"))
    assert run_store.compare_and_set_status(
        "run-7", ("waiting_for_approval", "waiting_for_review"), "running", updated_at=_now()
    )


def test_clearing_the_error_on_resume(run_store):
    run_store.save(_record("run-8", status="failed", error="boom"))
    run_store.compare_and_set_status(
        "run-8", "failed", "running", updated_at=_now(), clear_error=True
    )
    assert run_store.load("run-8").error is None


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


def test_requesting_cancellation_sets_the_flag(run_store):
    run_store.save(_record("run-9", status="running"))
    assert run_store.request_cancel("run-9", _now())
    assert run_store.is_cancel_requested("run-9")


def test_a_terminal_run_cannot_be_cancelled(run_store):
    run_store.save(_record("run-10", status="completed"))
    assert not run_store.request_cancel("run-10", _now())


def test_cancellation_does_not_clobber_the_worker_status(run_store):
    """The flag is separate from status precisely so the worker's next persist
    does not overwrite the cancellation."""
    run_store.save(_record("run-11", status="running"))
    run_store.request_cancel("run-11", _now())
    assert run_store.load("run-11").status == "running"
    assert run_store.is_cancel_requested("run-11")


def test_task_id_is_recorded_for_revocation(run_store):
    run_store.save(_record("run-12"))
    run_store.set_task_id("run-12", "celery-task-abc")
    assert run_store.load("run-12").task_id == "celery-task-abc"


# ---------------------------------------------------------------------------
# Tenancy and paging
# ---------------------------------------------------------------------------


def test_listing_is_scoped_to_a_tenant(run_store):
    run_store.save(_record("run-a", tenant_id="acme"))
    run_store.save(_record("run-b", tenant_id="acme"))
    run_store.save(_record("run-c", tenant_id="other"))

    acme = {r.run_id for r in run_store.list_all(tenant_id="acme")}
    assert acme == {"run-a", "run-b"}
    assert run_store.count("acme") == 2


def test_listing_without_a_tenant_returns_everything(run_store):
    run_store.save(_record("run-d", tenant_id="acme"))
    run_store.save(_record("run-e", tenant_id="other"))
    assert run_store.count() == 2


def test_listing_is_bounded_even_when_a_large_limit_is_asked_for(run_store):
    for i in range(5):
        run_store.save(_record(f"run-p{i}"))
    assert len(run_store.list_all(limit=2)) == 2
    assert len(run_store.list_all(limit=10_000)) == 5


def test_paging_walks_the_whole_set(run_store):
    for i in range(5):
        run_store.save(_record(f"run-q{i}"))
    first = run_store.list_all(limit=2, offset=0)
    second = run_store.list_all(limit=2, offset=2)
    assert {r.run_id for r in first}.isdisjoint({r.run_id for r in second})


# ---------------------------------------------------------------------------
# Shared uploads
# ---------------------------------------------------------------------------


def test_a_document_shared_with_a_clone_is_reported_as_in_use(run_store):
    """Deleting one run must not remove files a clone still needs."""
    run_store.save(_record("run-orig", document_paths=["/tmp/shared.md"]))
    run_store.save(_record("run-clone", document_paths=["/tmp/shared.md"]))

    assert run_store.document_in_use("/tmp/shared.md", exclude_run_id="run-orig")


def test_an_unshared_document_is_free_to_delete(run_store):
    run_store.save(_record("run-solo", document_paths=["/tmp/solo.md"]))
    assert not run_store.document_in_use("/tmp/solo.md", exclude_run_id="run-solo")


def test_deleting_removes_the_row(run_store):
    run_store.save(_record("run-del"))
    run_store.delete("run-del")
    assert run_store.load("run-del") is None
