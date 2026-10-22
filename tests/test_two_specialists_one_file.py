"""Two specialists given one file will each write all of it.

In parallel mode the delegated specialists run at the same time. A whole-file
`write_artifact` from one discards whatever the other has just written; the
workspace mutation lock serialises the writes, it cannot make them agree.

Measured across the 27 current-generation runs: 157 writes were one stage writing
content byte-identical to what a *different* stage had already written.
One run is the clearest - three specialists each wrote the same
`package.json`, the same `app.js`, the same test file and the same
`jest.config.cjs`. Two of each three produced nothing, having each paid a model
call to generate it.

The cause is upstream. Of 25 stored sprint plans, 17 assign the same file to more
than one specialist:

    one run  app.js        -> backend, ui_ux
    one run  app.js        -> backend, testing, ui_ux
    a000000b  app.js        -> backend, testing, ui_ux
    one run  app.test.mjs  -> testing, ui_ux

So two things: the Technical Lead is asked for one owner per file, and the
specialist is told when the plan does it anyway. A note rather than a refusal -
two tasks touching one file is sometimes the right plan, and it is never this
stage's fault.

Nothing here is about JavaScript. The files are read out of the task's own prose
by `paths_a_plan_named`, which is language-agnostic by construction.
"""

from __future__ import annotations

import pytest

from app.agents.specialists import (
    MAX_SHARED_FILES_NAMED,
    _a_file_another_specialist_is_also_given,
    build_specialist_task_request,
)


class Task:
    def __init__(self, description: str, criteria=()) -> None:
        self.task_description = description
        self.acceptance_criteria = list(criteria)


#: One run's own shape: three roles, one `app.js`.
THE_PLAN_THAT_OVERLAPPED = [
    Task("Write app.js with the localStorage adapter and the pure functions"),
    Task("Update app.js renderTasks() to add the completed class to each item"),
    Task("Create app.test.mjs with unit tests for the four pure functions"),
]


def _brief(task, others):
    return build_specialist_task_request(
        task.task_description, task.acceptance_criteria, "/tmp", "javascript",
        other_tasks=others,
    )["messages"][0]["content"]


class TestTheSharedFileIsNamed:
    def test_a_specialist_sharing_a_file_is_told(self):
        brief = _brief(THE_PLAN_THAT_OVERLAPPED[0], THE_PLAN_THAT_OVERLAPPED)

        assert "`app.js` is named by another task in this sprint" in brief

    def test_it_says_they_may_be_running_now(self):
        """Which is what makes a whole-file write destructive rather than merely
        wasteful, and is true only because parallel mode exists."""
        brief = _brief(THE_PLAN_THAT_OVERLAPPED[0], THE_PLAN_THAT_OVERLAPPED)

        assert "may be running right now" in brief

    def test_it_asks_for_a_targeted_change(self):
        brief = _brief(THE_PLAN_THAT_OVERLAPPED[0], THE_PLAN_THAT_OVERLAPPED)

        assert "`edit_artifact`" in brief

    def test_it_gives_an_escape_that_is_not_a_rewrite(self):
        """A task that truly needs the whole file must have somewhere to go."""
        brief = _brief(THE_PLAN_THAT_OVERLAPPED[0], THE_PLAN_THAT_OVERLAPPED)

        assert "say so in your structured response" in brief

    def test_a_task_with_a_file_of_its_own_is_not_told(self):
        brief = _brief(THE_PLAN_THAT_OVERLAPPED[2], THE_PLAN_THAT_OVERLAPPED)

        assert "another task in this sprint" not in brief

    def test_the_list_is_capped(self):
        shared = [Task(f"Touch file{n}.ts and shared.ts") for n in range(6)]
        mine = Task("Touch file0.ts and file1.ts and file2.ts and file3.ts and shared.ts")

        note = _a_file_another_specialist_is_also_given(
            mine.task_description, [], shared
        )

        assert note.count("`") <= MAX_SHARED_FILES_NAMED * 2 + 6


class TestItReadsAcceptanceCriteriaToo:
    def test_a_file_named_only_in_the_criteria_counts(self):
        mine = Task("Wire the filter bar", ["index.html carries the three buttons"])
        theirs = [mine, Task("Style the filter bar", ["index.html gets the markup"])]

        note = _a_file_another_specialist_is_also_given(
            mine.task_description, mine.acceptance_criteria, theirs
        )

        assert "index.html" in note


class TestEveryLanguage:
    @pytest.mark.parametrize(
        "shared",
        ["main.rs", "app.py", "Program.cs", "main.go", "index.php", "App.java"],
    )
    def test_the_note_is_not_about_javascript(self, shared):
        mine = Task(f"Add the parser to {shared}")
        theirs = [mine, Task(f"Add the formatter to {shared}")]

        note = _a_file_another_specialist_is_also_given(mine.task_description, [], theirs)

        assert shared in note


class TestNeverGettingInTheWay:
    def test_no_other_tasks_says_nothing(self):
        assert _a_file_another_specialist_is_also_given("Write app.js", [], []) == ""

    def test_a_task_naming_no_file_says_nothing(self):
        theirs = [Task("Write app.js")]

        assert _a_file_another_specialist_is_also_given("Improve the styling", [], theirs) == ""

    def test_the_task_does_not_match_itself(self):
        """The list handed in contains this task, and it must not count as another."""
        mine = Task("Write app.js with the adapter")

        assert _a_file_another_specialist_is_also_given(
            mine.task_description, [], [mine]
        ) == ""

    def test_junk_in_the_other_tasks_does_not_raise(self):
        """A malformed sibling must not cost the brief its note or its life."""
        siblings = [None, object(), Task("Update app.js renderTasks()")]

        assert "app.js" in _a_file_another_specialist_is_also_given(
            "Write app.js with the adapter", [], siblings
        )

    def test_the_legacy_call_is_unchanged(self):
        """Every existing caller passes no siblings and must get what it always did."""
        brief = build_specialist_task_request("Write app.js", [], "/tmp", "javascript")[
            "messages"
        ][0]["content"]

        assert "another task in this sprint" not in brief
        assert "Delegated task" in brief

    def test_the_rest_of_the_brief_survives(self):
        brief = _brief(THE_PLAN_THAT_OVERLAPPED[0], THE_PLAN_THAT_OVERLAPPED)

        assert "Delegated task" in brief
        assert "Acceptance criteria" in brief
        assert "ONE project directory" in brief


class TestTheLeadIsAskedToPreventIt:
    def test_the_prompt_asks_for_one_owner_per_file(self):
        from app.agents.technical_lead import _SYSTEM_PROMPT

        assert "One file, one owner" in _SYSTEM_PROMPT

    def test_the_measurement_is_kept_beside_the_rule_not_in_it(self):
        """The rule's evidence stays in the module, where its maintainers read
        it; the prompt carries the rule (Initiative X.4)."""
        import inspect
        import re

        from app.agents import technical_lead

        flat = re.sub(r"\s+", " ", technical_lead._SYSTEM_PROMPT)
        source = re.sub(r"[#\s]+", " ", inspect.getsource(technical_lead))

        assert "17 of 25 sprint plans" not in flat
        assert "17 of 25 sprint plans" in source and "157 writes" in source

    def test_it_allows_a_shared_file_with_stated_parts(self):
        """Two roles on one file is sometimes right; unowned is what is wrong."""
        import re

        from app.agents.technical_lead import _SYSTEM_PROMPT

        flat = re.sub(r"\s+", " ", _SYSTEM_PROMPT)

        assert "which part of it that task owns" in flat

    def test_the_workflow_passes_the_siblings(self):
        import inspect

        from app.graph import workflow

        source = inspect.getsource(workflow)
        call = source.index("request = build_specialist_task_request(")

        assert "other_tasks=tasks" in source[call : call + 700]


class TestBothCallSitesAreWired:
    """There are two `build_specialist_task_request` call sites, and wiring one
    left the fix dead in the mode that needs it.

    `specialist_node` runs tasks one at a time; `specialist_worker_node` is the
    parallel path, and parallel is the mode where specialists genuinely run at
    once - so it is the one where a file two tasks share matters most. It was the
    unwired one.

    Caught by auditing one run rather than by a test: its plan named
    `app.js` in four of six delegated tasks, five stages wrote `app.js`, and not
    one brief mentioned the overlap. The helper passed its own tests the whole
    time.
    """

    def test_every_call_site_passes_the_siblings(self):
        import ast
        import inspect

        from app.graph import workflow

        tree = ast.parse(inspect.getsource(workflow))
        sites = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", "") == "build_specialist_task_request"
        ]

        assert len(sites) == 2, f"expected two call sites, found {len(sites)}"
        for site in sites:
            keywords = {keyword.arg for keyword in site.keywords}
            assert "other_tasks" in keywords, (
                "a call site does not pass other_tasks, so the shared-file note "
                "cannot fire from it"
            )

    def test_the_parallel_site_reads_the_plan(self):
        """It is handed one task at a time, so the siblings come from the plan."""
        import inspect

        from app.graph import workflow

        source = inspect.getsource(workflow.build_graph) if hasattr(workflow, "build_graph") else inspect.getsource(workflow)
        at = source.index("def specialist_worker_node")
        block = source[at : at + 2600]

        assert "other_tasks=" in block
        assert "delegated_tasks" in block
