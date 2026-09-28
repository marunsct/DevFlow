"""Per-stage memory must be per stage, including when stages run at once.

`stage_memory` keys on the inner agent's `thread_id`, read back through
`langgraph.config.get_config()`. That resolves correctly while stages run one at
a time and collapses under a parallel fan-out, because every `Send` in a
superstep sees the parent graph's config rather than its own.

Measured on one run's first milestone, a seven-task parallel sprint. The
redundant-read refusal quotes an ordinal, and across six concurrent specialists
those formed a single interleaved sequence:

    specialist_backend_2  12      specialist_testing_5  13
    specialist_testing_4  14      specialist_backend_2  15
    specialist_testing_6  16      specialist_testing_5  17 .. 19
    specialist_testing_4  20, 21  specialist_testing_6  22
    ...                           specialist_testing_5  34

while every sequential stage after them restarted at 12 - `test_round_0` ran
12-17, `defect_fix_1_0` 12-14, `defect_fix_1_2` 12. Stage-scoped when alone,
pooled when concurrent.

The wrong number was the symptom. This memory holds which lines of which files a
stage has been given, so a pooled slot means one specialist is refused a read
because a *different* specialist read that file, and is told it has "already been
given" content it has never seen. Of one run's 70 failed calls at that
point, 32 were redundant-read refusals raised during that fan-out.
"""

from __future__ import annotations

import threading

import pytest

from app.agents.stage_memory import (
    current_stage_key,
    forget_everything,
    remembering,
    store,
)


@pytest.fixture(autouse=True)
def _clean() -> None:
    forget_everything()
    yield
    forget_everything()


def _count(times: int) -> int:
    """Increment this stage's tally `times` times and return it."""
    for _ in range(times):
        slot = store("repeated_reads", {})
        slot["count"] = slot.get("count", 0) + 1
    return store("repeated_reads", {}).get("count", 0)


class TestConcurrentStagesAreIsolated:
    def test_three_stages_counting_at_once_each_count_their_own(self) -> None:
        """The one run shape: concurrent workers, one tally each."""
        totals: dict[str, int] = {}

        def worker(key: str, times: int) -> None:
            with remembering(key):
                totals[key] = _count(times)

        threads = [
            threading.Thread(target=worker, args=(f"thread:specialist_{n}:abcd", 5))
            for n in range(3)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert totals == {f"thread:specialist_{n}:abcd": 5 for n in range(3)}, (
            "a shared slot shows 15 somewhere; each stage counted five"
        )

    def test_two_stages_in_sequence_still_do_not_see_each_other(self) -> None:
        with remembering("thread:backend:aaaa"):
            first = _count(4)
        with remembering("thread:testing:bbbb"):
            second = _count(1)

        assert (first, second) == (4, 1)

    def test_the_same_stage_resumed_keeps_its_count(self) -> None:
        """The whole point of this module: a pause must not reset the tally.

        `_run_gated_agent` reuses `pending_inner_thread_id` across a pause, so
        the same key comes back.
        """
        with remembering("thread:backend:aaaa"):
            _count(3)
        with remembering("thread:backend:aaaa"):
            resumed = _count(1)

        assert resumed == 4

    def test_one_stage_s_read_spans_are_not_offered_to_another(self) -> None:
        """The consequence that matters, not the counter.

        A pooled slot is how a specialist gets told it has "already been given"
        lines another specialist read.
        """
        with remembering("thread:backend:aaaa"):
            store("read_spans", {})["app.js"] = ("digest", {1, 2, 3}, 0)
        with remembering("thread:testing:bbbb"):
            theirs = store("read_spans", {})

        assert "app.js" not in theirs


class TestItChangesNothingWhereItWasAlreadyRight:
    def test_a_declared_key_is_preferred_over_the_config(self) -> None:
        with remembering("thread:declared:aaaa"):
            assert current_stage_key() == "thread:declared:aaaa"

    def test_the_key_is_dropped_again_on_the_way_out(self) -> None:
        """A leaked key would attribute the next stage's work to this one."""
        with remembering("thread:declared:aaaa"):
            pass

        assert current_stage_key() is None

    def test_an_empty_key_declares_nothing(self) -> None:
        """A caller without a thread id leaves the previous behaviour alone."""
        with remembering(""):
            assert current_stage_key() is None

    def test_nesting_restores_the_outer_key(self) -> None:
        with remembering("thread:outer:aaaa"):
            with remembering("thread:inner:bbbb"):
                assert current_stage_key() == "thread:inner:bbbb"
            assert current_stage_key() == "thread:outer:aaaa"

    def test_a_raise_inside_the_block_still_restores(self) -> None:
        with pytest.raises(RuntimeError):
            with remembering("thread:boom:aaaa"):
                raise RuntimeError("boom")

        assert current_stage_key() is None

    def test_outside_any_stage_callers_keep_their_own_state(self) -> None:
        """What every test relies on: no key means the fallback is returned."""
        own = {"count": 7}

        assert store("repeated_reads", own) is own


def test_every_function_that_invokes_an_agent_declares_a_stage() -> None:
    """Checked per function, because scope is not a matter of line counts.

    The first version of this counted `agent.invoke(` against `with remembering(`
    inside `workflow` alone, and passed while the invocation that matters sat in
    `approval`: with `auto_approve` every gated tool interrupts, so after the
    first one a stage does the rest of its work - reads included - inside
    `resume_with_decision`. Leaving that unwrapped left six concurrent
    specialists sharing one slot, which one run showed by reporting
    redundant-read ordinals of 12 to 20 across six different stages after the
    first attempt at this fix was deployed.

    The second version counted both modules and failed on `_resumed`, whose two
    invocations are both inside the scope its caller opens. So this asks the
    question properly: every function containing an invocation either opens the
    scope itself or is named here as one that runs inside a caller's.
    """
    import ast
    import inspect

    from app.agents import approval
    from app.graph import workflow

    #: Functions whose caller opens the scope. Each is private, and the
    #: assertion below re-checks that the named caller still exists.
    called_within_a_scope = {"_resumed": "resume_with_decision"}

    def invokes_an_agent(node: ast.AST) -> bool:
        """A real `agent.invoke(...)` call, not the words in a docstring."""
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "invoke"
                and isinstance(func.value, ast.Name)
                and func.value.id == "agent"
            ):
                return True
        return False

    for module in (workflow, approval):
        source = inspect.getsource(module)
        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not invokes_an_agent(node):
                continue
            body = ast.get_source_segment(source, node) or ""
            if "with remembering(" in body:
                continue
            caller = called_within_a_scope.get(node.name)
            assert caller is not None, (
                f"{module.__name__}.{node.name} invokes an agent without "
                "declaring a stage key, so its tools run against whatever key a "
                "fan-out reports"
            )
            assert f"{node.name}(" in source.split(f"def {caller}(", 1)[-1], (
                f"{node.name} is recorded as running inside {caller}'s scope, "
                "and that caller no longer calls it"
            )


def test_the_resume_path_declares_the_thread_it_resumes() -> None:
    """Specifically, and with the key that identifies the stage.

    `resume_with_decision` is handed the inner thread id, which is the stage's
    identity, so it has the right key already.
    """
    import inspect

    from app.agents.approval import resume_with_decision

    source = inspect.getsource(resume_with_decision)

    assert "with remembering(thread_id):" in source
