"""Scrum Master Deep Agent (Step 5.1).

This role worker consumes the approved technical specification and turns it
into an implementation plan made of independently verifiable sprints. Per the
plan: "Do not plan all implementation details before architecture approval" —
this agent should only be invoked after the Senior Architect Reviewer has
returned `status == "approved"`.
"""

from __future__ import annotations

from app.agents.project_layout import WORKSPACE_ROOT_NOTE

import re
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.scope_discipline import SCOPE_DISCIPLINE
from app.agents.project_layout import PLANNED_PROJECT_DIRECTORY
from app.agents.structured_response import STRUCTURED_RESPONSE_RULE
from app.agents.role_agent import create_role_agent

_STAGE = "sprint_planning"
_NAME = "scrum_master"


#: A list entry that opens with a key the way JSON writes one: `name":` with
#: the opening quote already consumed by the string it landed in.
_A_KEY_INSIDE_A_STRING = re.compile(r'^\s*"?[A-Za-z_][A-Za-z0-9_]*"\s*:\s*["\[{]')


class SprintDefinition(BaseModel):
    """One independently verifiable sprint in the implementation plan."""

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(..., description="The user-facing outcome this sprint delivers.")
    user_value: str = Field(..., description="Why this outcome matters to a real user or stakeholder.")
    in_scope: list[str] = Field(default_factory=list, description="Work explicitly included in this sprint.")
    out_of_scope: list[str] = Field(default_factory=list, description="Work explicitly deferred to a later sprint.")
    dependencies: list[str] = Field(default_factory=list, description="Other sprints or external work this depends on.")
    acceptance_criteria: list[str] = Field(default_factory=list)
    # The numbered criteria of the locked acceptance suite this sprint makes
    # pass. A sprint is done when these, and every earlier sprint's, pass.
    criteria: list[str] = Field(
        default_factory=list,
        description="The ids of the numbered acceptance criteria this sprint makes pass, e.g. [\"AC-1\", \"AC-3\"].",
    )
    test_strategy: list[str] = Field(default_factory=list, description="How this sprint's work will be verified.")
    security_checks: list[str] = Field(default_factory=list)
    documentation_work: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    rollback_notes: str = Field(default="", description="How to recover if this sprint's work needs to be reverted.")

    @field_validator(
        "in_scope", "out_of_scope", "dependencies", "acceptance_criteria",
        "test_strategy", "security_checks", "documentation_work", "risks",
    )
    @classmethod
    def _no_entry_is_the_rest_of_the_response(cls, value: list[str]) -> list[str]:
        """Refuse a list whose entries are the response's own structure.

        Measured on one run. The plan arrived as one sprint whose `in_scope`
        held four strings: the sprint's work, then `out_of_scope":"Any UI
        styling ...`, `dependencies_on_sprints":[]` and
        `acceptance_criteria":[...]} ,{` - the rest of the JSON, later sprints
        included, closed inside a string. It was a valid plan of one sprint
        with no criteria and no success measure assigned to it; that sprint
        was built, reviewed and accepted, and the run completed with a product
        that could add a task and do nothing else the brief asks for.

        A list entry that opens with a quoted key and a colon is not prose.
        The message says what to do, because a validation error is what the
        model sees when it tries again.
        """
        for entry in value or []:
            if _A_KEY_INSIDE_A_STRING.match(str(entry)):
                raise ValueError(
                    f"an entry begins `{str(entry)[:60]}` - that is a field of this "
                    "response written inside a string, so everything after it, the "
                    "later sprints included, was lost. Return every field as its own "
                    "key and every sprint as its own object in `sprints`; a list "
                    "entry is one short sentence of prose."
                )
        return value


class SprintPlanOutput(BaseModel):
    """Structured implementation plan produced by the Scrum Master."""

    model_config = ConfigDict(extra="forbid")

    sprints: list[SprintDefinition] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    success_measure_coverage: list[str] = Field(
        default_factory=list,
        description=(
            "One line per numbered success measure you were given, saying which "
            "sprint delivers it: 'N: Sprint K' (K counts from 1 in `sprints`), or "
            "'N: every sprint' for a constraint every sprint must keep."
        ),
    )


#: A coverage line: the measure's number, then the sprint that delivers it.
_COVERAGE_LINE = re.compile(r"^\s*(\d+)\s*[:.)\-]\s*(.+)$")
_NAMES_A_SPRINT = re.compile(r"\bsprints?\s*#?\s*(\d+)\b", re.I)
_EVERY_SPRINT = re.compile(r"\b(every|all|each)\s+sprints?\b", re.I)


def unaccounted_success_measures(plan: Any, measures: list[str]) -> list[int]:
    """The 1-based numbers of the success measures no sprint claims to deliver.

    The intake's success measures are the only place a requirement is sure to
    be stated plainly, and the Scrum Master was never shown them - it planned
    from the specification alone. Measured across the 33 stored runs whose
    intake required editing a task: the sprint plan never mentioned editing in
    12. The specification had dropped it in only 3; in the rest it mentioned
    editing once or twice, far down, and the plan followed the emphasis. Each
    omission was caught at the milestone review - on two runs
    and others - a full build cycle later, and spent one of the three revisions
    the run is allowed. Revision exhaustion is how the three low-brief runs
    before those died.

    This does not judge whether a sprint really delivers a measure; the
    milestone review still does that against the code. It asks only that each
    measure be assigned somewhere, which is the omission that was measured:
    the plan never considered the requirement at all. Accounting by number
    rather than matching words, because a word match would hand back a plan for
    missing "subsets" or "correctly" - and a plan handed back for nothing is
    a planning call wasted.

    A line counts when it names a sprint that exists, or says every sprint. A
    number with no such line, or a line naming sprint 7 of a two-sprint plan,
    is unaccounted for.
    """
    if not measures:
        return []
    sprint_count = len(getattr(plan, "sprints", None) or [])
    accounted: set[int] = set()
    for line in getattr(plan, "success_measure_coverage", None) or []:
        match = _COVERAGE_LINE.match(str(line))
        if not match:
            continue
        number, claim = int(match.group(1)), match.group(2)
        named = [int(k) for k in _NAMES_A_SPRINT.findall(claim)]
        if _EVERY_SPRINT.search(claim) or any(1 <= k <= sprint_count for k in named):
            accounted.add(number)
    return [n for n in range(1, len(measures) + 1) if n not in accounted]


def sprints_that_deliver_nothing(plan: Any, measures: list[str]) -> list[int]:
    """The 1-based numbers of the sprints no success measure is assigned to.

    The plan says, measure by measure, which sprint delivers it. A sprint none
    of those lines names ends with nothing the product is judged against: it is
    setup, and it still costs a build, a test round, two reviews and every
    attempt those are allowed.

    Measured over the low-brief runs of one day, by their own coverage lines.
    The two that shipped a sound product assigned a measure to every sprint.
    Three that failed did not: "Set up project structure and initial render",
    "Establish core architecture and persistence" and "Establish the
    foundation ... with unit tests" each opened a plan with no measure assigned
    to it. One of them spent three hours and four attempts on that first
    sprint - a page that rendered nothing, with a browser suite written to
    test it - and never reached the second.

    The system prompt already says setup is not a sprint. This is the same
    rule read off the plan's own accounting instead of asked for in prose, and
    `with_setup_folded_into_the_sprint_that_needs_it` is what acts on it.

    Nothing when the plan assigns no measure to any sprint by number: that is
    a different fault with its own handling, and every sprint would be listed.
    """
    sprint_count = len(getattr(plan, "sprints", None) or [])
    if not measures or sprint_count < 2:
        return []
    delivering: set[int] = set()
    for line in getattr(plan, "success_measure_coverage", None) or []:
        match = _COVERAGE_LINE.match(str(line))
        if not match:
            continue
        number, claim = int(match.group(1)), match.group(2)
        if not 1 <= number <= len(measures):
            continue
        delivering.update(
            int(k) for k in _NAMES_A_SPRINT.findall(claim) if 1 <= int(k) <= sprint_count
        )
    if not delivering:
        return []
    sprints = list(getattr(plan, "sprints", None) or [])
    return [
        k for k in range(1, sprint_count + 1)
        if k not in delivering and not _its_goal_names_a_capability(sprints[k - 1])
    ]


#: What a user does to the product, or a quality the product has. A sprint goal
#: naming one of these builds something, whatever its coverage lines say.
_A_CAPABILITY = re.compile(
    r"\b(?:add|create|edit|update|modify|delete|remove|toggle|complete|mark|filter|"
    r"search|sort|persist\w*|sav(?:e|es|ing)|stor(?:e|es|ing|age)|responsive\w*|"
    r"render\w*|display\w*)\b",
    re.I,
)


def _its_goal_names_a_capability(sprint: Any) -> bool:
    """Whether a sprint's goal names something the product does for its user.

    The coverage lines are the model's accounting, and it can leave a sprint
    out of them that plainly builds something. One run's plan put all six of
    its measures against sprint 3 and none against "Implement full task-list
    logic and persistence"; folded by its coverage alone, that sprint, a setup
    sprint and an end-to-end test sprint went into one, and the run was asked to
    build the whole product in a single sprint. "Set up project structure and
    core logic module" and "Implement Playwright end-to-end tests" still fold.
    """
    goal = str(getattr(sprint, "goal", "") or "")
    return bool(_A_CAPABILITY.search(goal))


def _renumbered(text: str, removed: int) -> str:
    """`text` with every "Sprint N" after the removed sprint counted one lower."""
    def lower(match: re.Match[str]) -> str:
        number = int(match.group(1))
        return match.group(0).replace(str(number), str(number - 1)) if number > removed else match.group(0)

    return _NAMES_A_SPRINT.sub(lower, str(text))


def with_setup_folded_into_the_sprint_that_needs_it(
    plan: Any, measures: list[str]
) -> tuple[Any, list[str]]:
    """`plan` with each sprint that delivers nothing merged into its neighbour, and their goals.

    What `sprints_that_deliver_nothing` finds, put right here instead of asked
    for. It was asked for at first: the plan was sent back with the sprint
    named. One run's plan assigned all ten of its measures, to sprints 2, 3 and
    4, behind a first sprint of "file layout, module boundaries, and test
    harness"; sent back, the model returned three sprints and no coverage
    lines at all, and the run was failed for a plan that "assigns none of the
    10 things" - one minute in, on a plan worse than the one it replaced.

    Folding needs no second answer. The sprint's work goes to the front of the
    next sprint - the last sprint's, to the end of the one before it - whose
    goal becomes both goals in order and whose user value is kept; the scope
    the folded sprint ruled out is dropped, since it ruled out what its
    neighbour builds. Coverage lines and
    dependencies are renumbered to match. A plan in which every sprint
    delivers is returned as it came.
    """
    folded: list[str] = []
    try:
        while True:
            empty = sprints_that_deliver_nothing(plan, measures)
            if not empty:
                return plan, folded
            sprints = list(plan.sprints)
            k = empty[0]
            gone = sprints[k - 1]
            into = k if k < len(sprints) else k - 2  # index of the neighbour
            target = sprints[into]
            first, second = (gone, target) if into == k else (target, gone)

            def both(field: str) -> list[str]:
                merged: list[str] = []
                for item in [*getattr(first, field), *getattr(second, field)]:
                    if item not in merged:
                        merged.append(item)
                return merged

            merged_sprint = target.model_copy(update={
                # Both goals, in the order the work is done: the sprint now
                # builds what both set out to, and a goal naming half of that
                # is what its review would hold it to.
                "goal": "; then ".join(
                    part.strip().rstrip(".") for part in (first.goal, second.goal) if part.strip()
                ) + ".",
                "in_scope": both("in_scope"),
                # The criteria it was given go with its work. Left out, one
                # run's folded sprint lost its "3" and the criterion was
                # assigned again from words.
                "criteria": both("criteria"),
                "acceptance_criteria": both("acceptance_criteria"),
                "test_strategy": both("test_strategy"),
                "security_checks": both("security_checks"),
                "documentation_work": both("documentation_work"),
                "risks": both("risks"),
            })
            sprints[into] = merged_sprint
            del sprints[k - 1]
            kept = []
            for index, sprint in enumerate(sprints, start=1):
                dependencies = [
                    _renumbered(item, k) for item in sprint.dependencies
                    # A sprint does not depend on the one folded into it.
                    if not (
                        index == (k if into == k else k - 1)
                        and [int(n) for n in _NAMES_A_SPRINT.findall(str(item))] == [k]
                    )
                ]
                dependencies = list(dict.fromkeys(
                    item for item in dependencies
                    if index not in [int(n) for n in _NAMES_A_SPRINT.findall(item)]
                ))
                kept.append(sprint.model_copy(update={"dependencies": dependencies}))
            plan = plan.model_copy(update={
                "sprints": kept,
                "success_measure_coverage": [
                    _renumbered(line, k) for line in plan.success_measure_coverage
                ],
            })
            folded.append(str(getattr(gone, "goal", "")).strip())
    except Exception:  # noqa: BLE001 - the plan as it came stands
        return plan, folded


def max_sprints_for_criteria_count(criteria_count: int, *, fast: bool = False) -> int:
    """The maximum number of sprints permitted for a given number of criteria.

    Fast delivery (`app.delivery`) builds a small product in one sprint: each
    sprint repeats a plan, a build, test rounds and five reviews, and one run
    spent most of thirteen hours on four of them for eighteen criteria.
    """
    if fast:
        return 1 if criteria_count <= 20 else 2 if criteria_count <= 40 else 3
    if criteria_count <= 10:
        return 2
    if criteria_count <= 15:
        return 3
    return 4



def with_capped_sprint_count(plan: Any, criteria_count: int, *, fast: bool = False) -> tuple[Any, list[str]]:
    """`plan` with sprint count capped according to the scope of criteria.

    If the number of sprints exceeds the maximum for the criteria count,
    excess sprints at the end are folded into earlier sprints.
    """
    max_sprints = max_sprints_for_criteria_count(criteria_count, fast=fast)
    sprints = list(getattr(plan, "sprints", None) or [])
    if len(sprints) <= max_sprints:
        return plan, []

    original_count = len(sprints)
    folded = []
    target_idx = max_sprints - 1
    while len(sprints) > max_sprints:
        # The sprint right after the target, so the merged sprint lists its
        # work in the plan's order.
        excess = sprints.pop(target_idx + 1)
        target = sprints[target_idx]

        def both(field: str) -> list[str]:
            merged: list[str] = []
            for item in [*getattr(target, field, []), *getattr(excess, field, [])]:
                if item not in merged:
                    merged.append(item)
            return merged

        # What the target deferred to the sprint now folded into it is its
        # own work: "PUT and DELETE (Sprint 2)" left in its out_of_scope tells
        # its builders not to build what it now owns.
        folded_number = target_idx + 2
        later = re.compile(rf"\bsprints?\s*#?\s*{folded_number}\b|\blater sprints?\b|\bnext sprint\b", re.I)
        merged_sprint = target.model_copy(update={
            "goal": f"{target.goal.rstrip('.')}; then {excess.goal.rstrip('.')}." if getattr(excess, "goal", "") else target.goal,
            "out_of_scope": [item for item in getattr(target, "out_of_scope", []) if not later.search(str(item))],
            "in_scope": both("in_scope"),
            "criteria": both("criteria"),
            "acceptance_criteria": both("acceptance_criteria"),
            "test_strategy": both("test_strategy"),
            "security_checks": both("security_checks"),
            "documentation_work": both("documentation_work"),
            "risks": both("risks"),
        })
        sprints[target_idx] = merged_sprint
        folded.append(str(getattr(excess, "goal", "")).strip())

    coverage = list(getattr(plan, "success_measure_coverage", None) or [])
    new_coverage = []
    for line in coverage:
        remapped_line = line
        for excess_num in range(max_sprints + 1, original_count + 1):
            remapped_line = re.sub(
                rf"\b(sprints?\s*#?\s*){excess_num}\b",
                rf"\g<1>{max_sprints}",
                remapped_line,
                flags=re.I,
            )
        new_coverage.append(remapped_line)

    update_dict: dict[str, Any] = {"sprints": sprints}
    if hasattr(plan, "success_measure_coverage"):
        update_dict["success_measure_coverage"] = new_coverage
    return plan.model_copy(update=update_dict), folded



#: Why a plan is the harness's, as its decision and its gap say.
THE_HARNESS_S_PLAN = "one sprint for every criterion, written by the harness"


def a_plan_the_harness_writes(
    criteria: list[Any], measures: list[str], file_plan: list[str], product: str = "",
) -> SprintPlanOutput:
    """One sprint that delivers every criterion and success measure: the plan when the planner gave none.

    A planning stage that runs out of every way to answer failed the run - one
    run's sprint planner did, after six replies - while a fix, build or test
    stage that cannot answer is recorded as blocked and the run goes on. One
    sprint over everything is the plan fast delivery mostly ends with anyway,
    and every input to it is the harness's own: the locked criteria, the
    intake's success measures, the specification's file plan. It says it is
    the harness's, and the release lists it as a gap.
    """
    name = product.strip() or "the product"
    ids = [str(getattr(c, "id", "")) for c in criteria if getattr(c, "id", "")]
    sprint = SprintDefinition(
        goal=f"Deliver {name} as the brief and the specification describe it: every acceptance criterion",
        user_value="Every criterion the brief sets passes in one release.",
        in_scope=[str(entry) for entry in file_plan] + [str(measure) for measure in measures],
        acceptance_criteria=[f"{getattr(c, 'id', '')}: {getattr(c, 'text', '')}" for c in criteria],
        criteria=ids,
        test_strategy=["Run the locked acceptance suite, which proves every criterion, and the unit tests."],
        rollback_notes="One sprint: a revert returns the project to its scaffold.",
    )
    return SprintPlanOutput(
        sprints=[sprint],
        open_questions=[f"The sprint plan is {THE_HARNESS_S_PLAN}: the planner gave no answer."],
        success_measure_coverage=[f"{index}: Sprint 1" for index in range(1, len(measures) + 1)],
    )

def how_much_a_plan_leaves_out(plan: Any, measures: list[str]) -> int:
    """How many success measures a plan fails to assign or to deliver in full."""
    return len(
        set(unaccounted_success_measures(plan, measures))
        | set(capabilities_the_plan_never_names(plan, measures))
    )


def _delivered_text(plan: Any) -> str:
    """What the plan commits to building. Deferrals and questions are not it."""
    parts: list[str] = []
    for sprint in getattr(plan, "sprints", None) or []:
        parts.append(str(getattr(sprint, "goal", "") or ""))
        parts.append(str(getattr(sprint, "user_value", "") or ""))
        for field in ("in_scope", "acceptance_criteria", "test_strategy"):
            parts.extend(str(item) for item in (getattr(sprint, field, None) or []))
    return "\n".join(parts)


def capabilities_the_plan_never_names(plan: Any, measures: list[str]) -> dict[int, list[str]]:
    """Items of a success measure's own list that no sprint delivers.

    Assignment alone was not enough. On one run the plan wrote
    "1: Sprint 1" for "Users can add, edit, and delete tasks without errors",
    and Sprint 1 delivered add and delete. Editing appeared nowhere in the plan
    - the same requirement dropped the same way as before the coverage lines
    existed, now with a line claiming it was covered.

    What the dropped requirement has in common every time is that it is one
    item of an enumeration the measure itself spells out. So the enumerations
    are what is checked: every item of an "and" list must be named somewhere a
    sprint commits to work, and at least one item of an "or" list must be.
    Words outside such lists - "correctly", "controls", "subsets" - are never
    required, which is what keeps this from handing back a plan for phrasing.
    Deferrals and open questions do not count as delivering anything.

    Returns {measure number: [missing items]}, empty when nothing is missing.
    """
    from app.agents.success_measures import capabilities_never_named

    return capabilities_never_named(_delivered_text(plan), measures)


def _the_success_measures(measures: list[str], gaps: list[Any]) -> str:
    """The numbered checklist, and - on a second pass - what the first one missed."""
    if not measures:
        return ""
    numbered = "\n".join(f"  {n}. {text}" for n, text in enumerate(measures, start=1))
    section = (
        "--- Success measures from the product intake ---\n"
        f"{numbered}\n\n"
        "These are what the finished product is judged against, with the MVP "
        "features the intake selected for this release, and the specification "
        "may state some of them only in passing. Every one must be delivered by "
        "a sprint - there is no release after this one to defer an MVP feature "
        "to. In `success_measure_coverage`, write one line per measure - "
        "'1: Sprint 1', '2: Sprint 2', '4: every sprint' for a "
        "constraint every sprint keeps - and make sure the sprint you name has "
        "that work in its scope and acceptance criteria.\n"
    )
    if gaps:
        lines = []
        for gap in gaps:
            # An int is a measure no line assigned; a dict also names the items
            # of the measure's own list that no sprint delivers.
            number = gap.get("measure") if isinstance(gap, dict) else gap
            if not isinstance(number, int) or not 1 <= number <= len(measures):
                continue
            words = gap.get("missing") if isinstance(gap, dict) else None
            named = f" - no sprint delivers: {', '.join(words)}" if words else ""
            lines.append(f"  {number}. {measures[number - 1]}{named}")
        section += (
            "\nYOUR LAST PLAN LEFT THESE UNASSIGNED - no sprint delivered them:\n"
            + "\n".join(lines)
            + "\nReturn the complete plan again with each of them - every item "
            "each measure lists - in the scope and acceptance criteria of a "
            "sprint, and a coverage line for every measure.\n"
        )
    return section + "\n"


def build_sprint_planning_request(
    technical_specification_text: str,
    repository_root: str,
    success_measures: list[str] | None = None,
    gaps: list[Any] | None = None,
    acceptance_criteria: str = "",
    built_ahead: list[str] | None = None,
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input from the approved technical specification.

    `acceptance_criteria` is the numbered list the locked acceptance suite
    proves (`app.acceptance`). The plan is made of vertical slices against it:
    each sprint names the criteria it makes pass. See
    `with_every_criterion_assigned`.

    Budgeted for the same reason as the architecture review request: this is a
    first message, so compaction cannot save it if the specification alone
    exceeds the window.

    `success_measures` are the intake's, numbered so the plan can account for
    each; `gaps` are the numbers a previous attempt left unassigned. See
    `unaccounted_success_measures`. `built_ahead` is what a previous attempt's
    scope built before the sprint whose criteria need it - see
    `scope_a_later_sprint_delivers`.
    """
    from app.agents.text_budget import excerpt, specification_budget

    specification = excerpt(
        technical_specification_text,
        specification_budget(),
        what="approved technical specification",
    )
    brief = (
        WORKSPACE_ROOT_NOTE
        + f"--- Approved technical specification (/docs/technical_specification.md) ---\n{specification}\n\n"
        + _the_success_measures(list(success_measures or []), list(gaps or []))
        + _the_acceptance_criteria(acceptance_criteria)
        + _built_ahead(list(built_ahead or []))
        + PLANNED_PROJECT_DIRECTORY
    )
    return {"messages": [{"role": "user", "content": brief}]}


def _the_acceptance_criteria(criteria: str) -> str:
    if not criteria.strip():
        return ""
    return (
        "--- Acceptance criteria, each proven by a locked acceptance test ---\n"
        f"{criteria}\n\n"
        "Plan in vertical slices against these. Sprint 1 is a walking skeleton: the "
        "product starts and at least one criterion works end to end through the "
        "product's real interface. Every later sprint makes more criteria pass. In each "
        "sprint's `criteria`, list the ids it makes pass; every id belongs to exactly one "
        "sprint. A sprint is done only when its criteria and every earlier sprint's pass, "
        "measured by the suite, so order sprints so that what a criterion needs is built "
        "no later than the sprint that claims it. A sprint's `in_scope` builds what its "
        "own criteria and earlier sprints' need, and no earlier: work only a later "
        "sprint's criteria need belongs in that sprint's scope - not built ahead as "
        "functions, wiring or placeholders.\n\n"
        f"{_how_many_sprints(criteria)}"
    )


def _how_many_sprints(criteria: str) -> str:
    """The most sprints these criteria allow, in the words the plan is cut back by.

    One rule, from `max_sprints_for_criteria_count`: this request, the system
    prompt and the cut each said something different - one sprint "where
    possible", one for five criteria or fewer, two for ten - and a plan written
    to one was cut by another.
    """
    count = len(set(re.findall(r"\b(?:AC|CR)-\d+\b", criteria)))
    if not count:
        return ""
    most = max_sprints_for_criteria_count(count)
    return (
        f"Plan at most {most} sprint{'s' if most > 1 else ''} for these {count} criteria - fewer "
        f"when the work is small. A plan with more is cut back to {most}, its later sprints "
        "folded into the last.\n\n"
    )


_NOT_A_TOPIC = frozenset({
    "the", "and", "with", "for", "from", "that", "this", "their", "them", "they", "into",
    "users", "user", "can", "should", "must", "will", "able", "allow", "allows", "each",
    "every", "work", "works", "working", "correctly", "properly", "functionality", "feature",
    "features", "support", "supports", "between", "when", "after", "before", "have", "has",
})


def _topics(text: str) -> set[str]:
    """The significant words of a text, cut to a short stem so forms of a word meet."""
    words = re.findall(r"[a-z][a-z0-9]+", str(text).lower())
    return {
        (word[:-1] if word.endswith("s") and len(word) > 4 else word)[:4]
        for word in words
        if len(word) >= 4 and word not in _NOT_A_TOPIC
    }


def _the_sprint_that_builds_it(sprints: list[Any], criterion: str) -> int | None:
    """The earliest sprint whose own words share the most topics with a criterion.

    A shared word counts by how few sprints say it, and a word a sprint puts
    out of its scope counts against it. The product's own nouns are in every
    sprint and tell them apart by nothing: one run's "Edit a task's title" went
    to the sprint that adds tasks with a title - and says editing is out of its
    scope - over the sprint whose goal was editing.
    """
    wanted = _topics(criterion)
    if not wanted:
        return None
    said = [
        _topics(" ".join(
            [str(getattr(sprint, "goal", "") or ""), str(getattr(sprint, "user_value", "") or "")]
            + [str(item) for item in getattr(sprint, "in_scope", None) or []]
            + [str(item) for item in getattr(sprint, "acceptance_criteria", None) or []]
        ))
        for sprint in sprints
    ]
    excluded = [
        _topics(" ".join(str(item) for item in getattr(sprint, "out_of_scope", None) or []))
        for sprint in sprints
    ]

    def weight(topic: str) -> float:
        return 1 / max(1, sum(1 for other in said if topic in other))

    best, best_score = None, 0.0
    for index, topics in enumerate(said):
        score = sum(weight(topic) for topic in wanted & topics) - sum(
            weight(topic) for topic in wanted & excluded[index]
        )
        if score > best_score:
            best, best_score = index, score
    return best


def _the_ids_it_names(sprint: Any, known: list[str]) -> list[Any]:
    """The criteria a sprint claims: its `criteria`, or else the ids its `acceptance_criteria` name.

    Measured on one run: the planner left every sprint's `criteria` empty and
    listed the ids under `acceptance_criteria` instead - sprint 2 "AC-2, AC-3,
    AC-4". Read from `criteria` alone, all nine were assigned by their words,
    and "Edit a task's title" went to sprint 1, whose scope says editing is not
    in it.
    """
    from app.acceptance.junit import tags_in

    claimed = list(getattr(sprint, "criteria", None) or [])
    if claimed:
        return claimed
    named: list[str] = []
    for item in getattr(sprint, "acceptance_criteria", None) or []:
        # A bare number too, as `_as_a_criterion_id` reads one: the next run's
        # planner listed sprint 3's as "3".
        ids = list(tags_in(str(item))) or [_as_a_criterion_id(item, known)]
        named += [tag for tag in ids if tag in known and tag not in named]
    return named


def _as_a_criterion_id(item: Any, known: list[str]) -> str:
    """`item` as a criterion id: `ac_3`, `AC\u20113` and a bare `3` all read as `AC-3` when it exists.

    Measured on one run: the plan named its criteria `1` to `8`; every one was
    dropped as "not a criterion" and the sprints were re-assigned from their
    goals' words, which can differ from what the plan meant.
    """
    from app.acceptance.junit import tags_in

    text = str(item).strip()
    tagged = tags_in(text)
    if len(tagged) == 1:
        return tagged[0]
    bare = text.lstrip("#").rstrip(".").strip()
    if bare.isdigit() and f"AC-{int(bare)}" in known:
        return f"AC-{int(bare)}"
    return text.upper().replace("_", "-")


def scope_a_later_sprint_delivers(plan: Any, criteria_texts: dict[str, str]) -> list[str]:
    """One line per scope item that builds what only a later sprint's criteria need.

    One run's plan assigned editing, deleting and filtering to sprint 2's
    criteria and put them in sprint 2's scope - and in sprint 1's, as "inline
    edit flow with Edit/Save buttons per task, Delete button per task, filter
    button handlers". The lead wrote sprint 1's work orders from that scope, its
    builders built every sprint's features in the first, and nothing was left
    for sprint 2 but to build them again. Before it, another run's sprint 1 did
    the same unprompted, and its milestone review had the revision delete the
    work over the size limit.

    A sprint's own text is its goal and the criteria due by it, earlier sprints'
    included; a later sprint's is its goal and its criteria. See
    `app.analysis.integration_checks.work_a_later_sprint_delivers`.
    """
    from app.analysis.integration_checks import work_a_later_sprint_delivers

    sprints = list(getattr(plan, "sprints", None) or [])

    def text_of(sprint: Any) -> list[str]:
        return [
            str(getattr(sprint, "goal", "") or ""),
            *(criteria_texts.get(str(item), "") for item in getattr(sprint, "criteria", None) or ()),
        ]

    notes: list[str] = []
    for index, sprint in enumerate(sprints):
        later = sprints[index + 1:]
        if not later:
            break
        due = "\n".join(part for earlier in sprints[: index + 1] for part in text_of(earlier))
        coming = "\n".join(part for each in later for part in text_of(each))
        for item in getattr(sprint, "in_scope", None) or ():
            actions = work_a_later_sprint_delivers(str(item), due, coming)
            if not actions:
                continue
            owners = [
                str(cid)
                for each in later
                for cid in getattr(each, "criteria", None) or ()
                if work_a_later_sprint_delivers(str(item), due, criteria_texts.get(str(cid), ""))
            ]
            notes.append(
                f"Sprint {index + 1}'s scope builds {', '.join(actions)}, which only a later "
                f"sprint's criteria need{' (' + ', '.join(owners) + ')' if owners else ''}: "
                f"\"{' '.join(str(item).split())[:200]}\""
            )
    return notes


def _built_ahead(notes: list[str]) -> str:
    """The section asking for work built ahead of its sprint to be moved, or ""."""
    if not notes:
        return ""
    return (
        "YOUR LAST PLAN BUILT THESE BEFORE THE SPRINT THAT NEEDS THEM:\n"
        + "\n".join(f"- {note}" for note in notes)
        + "\nReturn the complete plan again with that work in the scope of the sprint "
        "whose criteria need it, or with those criteria moved into the earlier sprint "
        "together with the work. A sprint's scope builds its own criteria and nothing "
        "a later sprint delivers.\n\n"
    )


def with_every_criterion_assigned(
    plan: Any, criteria_ids: list[str], texts: dict[str, str] | None = None
) -> tuple[Any, list[str]]:
    """The plan with every criterion assigned to exactly one sprint, and what was changed.

    Unknown ids are dropped and an id claimed twice stays with the first
    sprint. An id no sprint claims goes to the sprint whose goal and scope name
    it best (`texts` holds each criterion's words) - one run's planner filled
    no `criteria` at all, and with every id on the last sprint, four of six
    sprints had nothing the suite could measure. Failing that, the last sprint,
    which answers for every criterion anyway. A walking skeleton with nothing to
    show is given the first criterion a later sprint holds.
    """
    sprints = list(getattr(plan, "sprints", None) or [])
    if not sprints or not criteria_ids:
        return plan, []
    known = list(dict.fromkeys(criteria_ids))
    notes: list[str] = []
    seen: set[str] = set()
    cleaned: list[list[str]] = []
    for number, sprint in enumerate(sprints, 1):
        mine: list[str] = []
        for item in _the_ids_it_names(sprint, known):
            item = _as_a_criterion_id(item, known)
            if item not in known:
                notes.append(f"sprint {number} named {item}, which is not a criterion")
            elif item in seen:
                notes.append(f"{item} was claimed by an earlier sprint than {number}")
            else:
                mine.append(item)
                seen.add(item)
        cleaned.append(mine)
    unassigned = [item for item in known if item not in seen]
    matched: list[str] = []
    for item in list(unassigned):
        index = _the_sprint_that_builds_it(sprints, (texts or {}).get(item, ""))
        if index is not None:
            cleaned[index].append(item)
            unassigned.remove(item)
            matched.append(f"{item} to sprint {index + 1}")
    if matched:
        notes.append("by what each sprint says it builds: " + ", ".join(matched))
    if unassigned:
        cleaned[-1].extend(unassigned)
        notes.append(f"{', '.join(unassigned)} assigned to the last sprint, which no sprint claimed")
    if len(cleaned) > 1 and not cleaned[0]:
        for later in cleaned[1:]:
            if later:
                cleaned[0].append(later.pop(0))
                notes.append(f"{cleaned[0][0]} moved to sprint 1, which had nothing to show")
                break
    updated = [sprint.model_copy(update={"criteria": ids}) for sprint, ids in zip(sprints, cleaned)]
    return plan.model_copy(update={"sprints": updated}), notes


def with_each_criterion_where_its_tests_can_pass(plan: Any, tests: list[list[str]]) -> tuple[Any, list[str]]:
    """The plan with each criterion moved to the earliest sprint in which one of its tests can pass, and what moved.

    A locked test carries every criterion it proves (`tests` holds each test's
    criterion ids, from its name). One that also proves a later sprint's
    criterion cannot pass before that sprint. Measured on a Measure run: the
    plan gave sprint 1 "accounts and items survive a restart" and sprint 2 the
    item routes; its only test, carrying both, signs up, creates an item,
    restarts and lists items. Sprint 1 spent two fix rounds - about 75 minutes
    - on a criterion that could not pass, and was planned again. A criterion
    with no test, or one of whose tests can pass where it is, stays.
    """
    sprints = list(getattr(plan, "sprints", None) or [])
    if len(sprints) < 2 or not tests:
        return plan, []
    where = {item: number for number, sprint in enumerate(sprints) for item in (getattr(sprint, "criteria", None) or [])}
    moves: dict[str, int] = {}
    for item, number in where.items():
        carrying = [[t for t in test if t in where] for test in tests if item in test]
        if not carrying:
            continue
        # The sprint by which each test's every criterion is built; the earliest of those.
        earliest = min(max(where[t] for t in test) for test in carrying)
        if earliest > number:
            moves[item] = earliest
    if not moves:
        return plan, []
    cleaned = [[i for i in (getattr(sprint, "criteria", None) or []) if i not in moves] for sprint in sprints]
    for item, number in moves.items():
        cleaned[number].append(item)
    if not cleaned[0]:
        return plan, []
    updated = [sprint.model_copy(update={"criteria": ids}) for sprint, ids in zip(sprints, cleaned)]
    notes = [f"{item} to sprint {number + 1}, where a test of it can first pass" for item, number in moves.items()]
    return plan.model_copy(update={"sprints": updated}), notes


_SYSTEM_PROMPT = f"""You are the Scrum Master for this workflow.

Your role is to turn an approved technical specification into an implementation
plan made of independently verifiable sprints.

Responsibilities:
- Break the approved specification into sprints that each deliver real user
  value on their own, rather than one sprint per technical layer.
- Never make setup a sprint of its own, and never make an open question one.
  Every sprint must end with behaviour a user can observe that they could not
  observe before. "Address open questions", "prepare for future scalability",
  "investigate alternatives" and "document the design" are not sprints:
  `open_questions` is a field on your response and is where a question goes.
  Observed: a sprint reading "Address open questions and prepare for future
  scalability" was turned by the Technical Lead into a
  milestone whose entire scope was "Update docs/architecture_review.md", a file
  the workflow writes and the tools refuse, so the milestone could not deliver
  anything at all.
  The workspace, its project directory
  and the `docs/` folder already exist and the workflow maintains them, so
  "create the project directory", "copy the documentation" and "initialise the
  manifest" deliver nothing a user could use. Observed: with a first sprint
  reading "Create project directory and basic documentation", the run
  spent a full milestone, a test round, a security review, a milestone review
  and two remediation rounds on it, and the product had no application code at
  the end. The first sprint must ship working behaviour; any manifest or
  directory it needs is part of that sprint, not instead of it.
- For every sprint, define goal, user value, in-scope and out-of-scope work,
  dependencies on other sprints, acceptance criteria, test strategy, security
  checks, documentation work, risks, and rollback or recovery notes.
- Sequence sprints so each one is verifiable before the next begins.
- When numbered acceptance criteria are given, every sprint lists in
  `criteria` the ids it makes pass, and every id belongs to exactly one
  sprint. The first sprint already delivers at least one of them end to end.
- List open questions instead of guessing when the specification is silent.

{SCOPE_DISCIPLINE}

Constraints:
- Do not modify application source code.
- Do not change repo files except through the approved artifact tool.
- Only plan against the already-approved specification; do not introduce new
  architecture decisions here.
- Do not write a document. The workflow renders `docs/sprint_plan.md` from the
  structured response you return, so your sprint plan reaches its readers
  either way - and only through that response. Writing it yourself
  produces the same work twice from one understanding, and the two
  copies then disagree.
- Sprint sizing: plan no more sprints than the request allows for its number
  of acceptance criteria, and fewer when the work is small.
- Keep the output structured and concise.

Return the response in the required output schema only.

{STRUCTURED_RESPONSE_RULE}
"""


def create_scrum_master_agent(
    model: str | BaseChatModel | None = None,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    repo_root: str | Path | None = None,
        allow_subdirectories: bool = True,
) -> Any:
    """Create the Scrum Master role worker."""
    return create_role_agent(
        name=_NAME,
        stage=_STAGE,
        system_prompt=_SYSTEM_PROMPT,
        response_format=SprintPlanOutput,
        model=model,
        checkpointer=checkpointer,
        repo_root=repo_root, allow_subdirectories=allow_subdirectories,
        # Its document is rendered from the structured response, so it needs no
        # write tool - see `app.agents.artifact_document`.
        can_write=False,
    )


__all__ = [
    "SprintDefinition",
    "SprintPlanOutput",
    "build_sprint_planning_request",
    "create_scrum_master_agent",
    "max_sprints_for_criteria_count",
    "with_capped_sprint_count",
]
