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
    `unaccounted_success_measures`.
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
        + f"**CRITICAL INSTRUCTION**: All application code lives in ONE project directory at the workspace root. Run `ls` FIRST: if a project directory already exists, write into that exact directory, spelled exactly as it already is. Only create one if none exists, naming it after this product in lowercase-with-hyphens. Never scaffold directly in the workspace root, never use a generic name like 'nest-app', and never create a second project directory. Documentation that ships with the product goes inside that project directory beside the code it describes. `docs/` is the workflow's own directory and writing anything into it is refused.\n"
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
        "no later than the sprint that claims it.\n\n"
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
    """The earliest sprint whose own words share the most topics with a criterion."""
    wanted = _topics(criterion)
    if not wanted:
        return None
    best, best_score = None, 0
    for index, sprint in enumerate(sprints):
        said = " ".join(
            [str(getattr(sprint, "goal", "") or ""), str(getattr(sprint, "user_value", "") or "")]
            + [str(item) for item in getattr(sprint, "in_scope", None) or []]
            + [str(item) for item in getattr(sprint, "acceptance_criteria", None) or []]
        )
        score = len(wanted & _topics(said))
        if score > best_score:
            best, best_score = index, score
    return best


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
        for item in getattr(sprint, "criteria", None) or []:
            item = str(item).strip().upper().replace("_", "-")
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
- Every write_artifact call pauses for a human decision before anything is
  saved; never claim the artifact is saved until a tool result confirms it.
- **Write the complete artifact in ONE single write_artifact call.** Do NOT
  make follow-up edit calls to refine, fix typos, or improve the document after
  the initial write. The document must be complete and correct before you write
  it. Once the write is confirmed, immediately return your structured response.
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
]
