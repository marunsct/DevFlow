"""The parallel fan-out must not run two tasks that name the same file.

They go in the same superstep, so each reads the file, plans an edit against the
line numbers it saw, and the second one's numbers have moved by the time it
writes. The guards catch it - a `replace_lines` whose anchor shifted is refused,
and so is an edit leaving the file unparseable - so nothing corrupt ships, and
every one of those refusals still cost a model call.

Measured on one run, a seven-task milestone in which four tasks named
`app.js`: of 400 calls 64 failed, and 45 of those were this one thing - 28
redundant reads of `app.js`, 13 identical `replace_lines`, 7 identical
`edit_artifact`, each stage retrying against a file another stage was moving.

`_a_file_another_specialist_is_also_given` already detects this and its note has
fired correctly in production. A note is all it can be, because by the time a
specialist reads it both tasks are running. Deferring one costs a superstep.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.graph.workflow import _that_do_not_share_a_file


@dataclass
class Task:
    specialist_role: str
    task_description: str
    acceptance_criteria: list[str] = field(default_factory=list)


def _pending(*tasks: Task) -> list[tuple[int, Task]]:
    return list(enumerate(tasks))


def _roles(sent: list[tuple[int, Task]]) -> list[str]:
    return [task.specialist_role for _, task in sent]


class TestWhatGoesAtOnce:
    def test_tasks_naming_different_files_all_go(self) -> None:
        """Parallelism is kept wherever it is real."""
        pending = _pending(
            Task("ui_ux", "Build index.html and style.css."),
            Task("backend", "Implement app.js with the pure functions."),
            Task("testing", "Write app.test.mjs covering them."),
        )

        assert _roles(_that_do_not_share_a_file(pending)) == ["ui_ux", "backend", "testing"]

    def test_a_second_task_naming_the_same_file_is_deferred(self) -> None:
        pending = _pending(
            Task("backend", "Implement app.js with the pure functions."),
            Task("testing", "Add the DOM wiring to app.js."),
        )

        assert _roles(_that_do_not_share_a_file(pending)) == ["backend"]

    def test_the_run_1bdbc08a_shape(self) -> None:
        """Seven tasks, four of them naming `app.js`, as that milestone did.

        `specialist_backend_2`, `specialist_backend_3`, `specialist_testing_5`
        and `specialist_testing_6` all edited `app.js` at once there. One should
        go now and the other three wait; the tasks naming other files are
        unaffected, so four go in this superstep.
        """
        pending = _pending(
            Task("ui_ux", "Build index.html."),
            Task("ui_ux", "Build style.css."),
            Task("backend", "Create app.js with createTask and saveTasks."),
            Task("backend", "Add the filter functions to app.js."),
            Task("testing", "Write app.test.mjs."),
            Task("testing", "Add the wiring tests to app.js."),
            Task("testing", "Add the storage adapter to app.js."),
        )
        going = _that_do_not_share_a_file(pending)
        on_app_js = [index for index, task in going if "app.js " in task.task_description or task.task_description.endswith("app.js.")]

        assert len(on_app_js) == 1, "only one task may hold `app.js` at a time"
        assert len(going) == 4, (
            "the three tasks naming index.html, style.css and app.test.mjs are "
            "independent and must not be held back"
        )

    def test_the_deferred_task_goes_on_the_next_pass(self) -> None:
        """Nothing is dropped - the dispatcher re-enters until none are pending."""
        first = Task("backend", "Create app.js.")
        second = Task("testing", "Add tests inside app.js.")
        going = _that_do_not_share_a_file(_pending(first, second))

        assert _roles(going) == ["backend"]
        # Next superstep: the finished one is no longer pending.
        assert _roles(_that_do_not_share_a_file([(1, second)])) == ["testing"]


class TestProgressIsAlwaysMade:
    def test_every_task_naming_one_file_still_runs_one_at_a_time(self) -> None:
        """A fan-out that dispatched nothing would hang the run."""
        pending = _pending(
            Task("backend", "Edit app.js part one."),
            Task("testing", "Edit app.js part two."),
            Task("ui_ux", "Edit app.js part three."),
        )
        going = _that_do_not_share_a_file(pending)

        assert len(going) == 1
        assert going[0][0] == 0, "the first pending task is the one that goes"

    def test_tasks_naming_no_file_at_all_are_never_held_back(self) -> None:
        pending = _pending(
            Task("backend", "Review the architecture and report."),
            Task("testing", "Summarise the coverage gaps."),
        )

        assert len(_that_do_not_share_a_file(pending)) == 2

    def test_a_single_task_is_returned_unchanged(self) -> None:
        pending = _pending(Task("backend", "Create app.js."))

        assert _that_do_not_share_a_file(pending) == pending

    def test_an_empty_list_stays_empty(self) -> None:
        assert _that_do_not_share_a_file([]) == []

    def test_the_original_indices_survive(self) -> None:
        """The index is what names the stage, so it must not be re-derived."""
        pending = [(4, Task("backend", "Create app.js.")), (9, Task("ui_ux", "Build index.html."))]

        assert [index for index, _ in _that_do_not_share_a_file(pending)] == [4, 9]


class TestItNeverBlocksADispatch:
    def test_a_task_whose_prose_cannot_be_read_still_runs(self) -> None:
        """A hint must never be the thing that stops a sprint."""

        class Awkward:
            specialist_role = "backend"

            @property
            def task_description(self) -> str:
                raise RuntimeError("no description")

            acceptance_criteria: tuple[str, ...] = ()

        pending = [(0, Awkward()), (1, Task("ui_ux", "Build index.html."))]

        assert len(_that_do_not_share_a_file(pending)) == 2

    def test_the_same_file_spelled_two_ways_is_one_file(self) -> None:
        """One task writes `src/app.js`, another `app.js`; the plan does both."""
        pending = _pending(
            Task("backend", "Create src/app.js."),
            Task("testing", "Add the wiring to app.js."),
        )

        assert len(_that_do_not_share_a_file(pending)) == 1


class TestAResumeDispatchesThePausedWorker:
    """A pause inside the fan-out must get every pending task back.

    The resume carries a decision for the worker that paused, and that decision
    is delivered by re-dispatching it. Deferring it leaves the decision with no
    hanging call to answer: "ValueError: Number of human decisions (2) does not
    match number of hanging tool calls (1)". That failure predates this filter -
    it ended one run on 2026-09-11 - and staggering is a new way to reach
    it.

    That used to be met by sending every pending task on any resume, which
    switched the staggering off for the rest of the milestone after its first
    approval. Now the paused worker is forced through and the rest are
    staggered against the files it holds.

    The paused worker is named by `pending_inner_thread_id`, not by `stage`: a
    parallel resume reaches this router with `stage` already rewritten to
    `specialist_dispatch_parallel`, which is the shape these states use.
    """

    @staticmethod
    def _route(state: dict) -> object:
        from app.graph.workflow import _route_from_stage

        return _route_from_stage(state)

    @staticmethod
    def _state(**extra) -> dict:
        class Plan:
            delegated_tasks = [
                Task("backend", "Create app.js with the pure functions."),
                Task("testing", "Add the wiring tests to app.js."),
            ]

        return {
            "stage": "specialist_dispatch_parallel",
            "milestone_plan": Plan(),
            "specialist_outputs": {},
            **extra,
        }

    def test_a_clean_fan_out_is_staggered(self) -> None:
        sent = self._route(self._state())

        assert isinstance(sent, list) and len(sent) == 1

    def test_the_paused_worker_goes_even_when_it_would_be_held_back(self) -> None:
        """The testing task pauses second in the plan and shares app.js."""
        sent = self._route(self._state(
            pending_decision={"kind": "approve"},
            pending_inner_thread_id="thread-x:specialist_testing_1:abcd1234",
        ))

        names = [s.arg["__worker_index"] for s in sent]
        assert 1 in names, "the paused worker must be among them or its decision answers nothing"

    def test_a_task_sharing_its_file_waits(self) -> None:
        """One run: the first approval released a task onto app.js."""
        sent = self._route(self._state(
            pending_decision={"kind": "approve"},
            pending_inner_thread_id="thread-x:specialist_backend_0:abcd1234",
        ))

        assert [s.arg["__worker_index"] for s in sent] == [0]

    def test_a_queued_pause_is_dispatched_too(self) -> None:
        """A worker whose pause waits behind another re-surfaces it; it must be sent."""
        sent = self._route(self._state(
            pending_decision={"kind": "approve"},
            pending_inner_thread_id="thread-x:specialist_backend_0:abcd1234",
            specialist_pauses={"specialist_testing_1": {"pending_inner_thread_id": "t:specialist_testing_1:ef"}},
        ))

        assert sorted(s.arg["__worker_index"] for s in sent) == [0, 1]
