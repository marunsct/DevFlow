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
    rule read off the plan's own accounting instead of asked for in prose.

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
    return [k for k in range(1, sprint_count + 1) if k not in delivering]


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
    empty = [
        gap for gap in gaps
        if isinstance(gap, dict) and isinstance(gap.get("sprint"), int)
    ]
    gaps = [gap for gap in gaps if gap not in empty]
    if empty:
        named = "\n".join(
            f"  Sprint {gap['sprint']}: {str(gap.get('goal') or '').strip()}" for gap in empty
        )
        section += (
            "\nYOUR LAST PLAN HAD SPRINTS THAT DELIVER NONE OF THE MEASURES ABOVE - your own "
            "coverage lines assign nothing to them:\n"
            f"{named}\n"
            "A sprint like that ends with nothing a user can do and nothing the product "
            "is judged against, and it still costs a full build, test round and review. "
            "Setup is not a sprint: fold that work into the first sprint that needs it, "
            "so every sprint delivers at least one measure, and return the complete plan "
            "again with fewer sprints.\n"
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
) -> dict[str, list[dict[str, str]]]:
    """Build the Deep Agent input from the approved technical specification.

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
        + f"**CRITICAL INSTRUCTION**: All application code lives in ONE project directory at the workspace root. Run `ls` FIRST: if a project directory already exists, write into that exact directory, spelled exactly as it already is. Only create one if none exists, naming it after this product in lowercase-with-hyphens. Never scaffold directly in the workspace root, never use a generic name like 'nest-app', and never create a second project directory. Documentation that ships with the product goes inside that project directory beside the code it describes. `docs/` is the workflow's own directory and writing anything into it is refused.\n"
    )
    return {"messages": [{"role": "user", "content": brief}]}


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
