"""What the QA stage, the test rounds and the reviews are told about the suite."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from app.acceptance import suite
from app.acceptance.criteria import Criterion
from app.stacks import contract

#: How much of the brief QA is handed. Briefs are short; this is a ceiling.
BRIEF_CHARS = 12_000

#: How much of the suite's text a reviewer is handed inline. It can read the
#: files itself; this is so the common case needs no tool call.
SUITE_TEXT_CHARS = 24_000


def criteria_text(criteria: Sequence[Criterion], deferred: dict[str, str] | None = None) -> str:
    deferred = deferred or {}
    lines = []
    for criterion in criteria:
        line = f"- {criterion.id}: {criterion.text}"
        if criterion.id in deferred:
            line += f" (deferred: {deferred[criterion.id]})"
        lines.append(line)
    return "\n".join(lines)


def _how_to_write_them(repo_root: str | Path, project: str, acceptance_dir: str, stack: Any) -> str:
    found = contract.the_pack(repo_root)
    if found is not None:
        pack, record = found
        command = " ".join(record.get("acceptance_test") or pack.acceptance_test)
        return (
            f"{pack.filled(pack.acceptance_guide, project, record.get('title') or project, record.get('package'))}\n"
            f"Run the suite with `{command}` in `{project}/`."
        )
    testing = str(getattr(stack, "testing_framework", "") or "the stack's testing framework")
    return (
        f"No project setup exists for this stack, so the suite's runner is yours to set up. "
        f"Use {testing}. Write the tests in `{project}/{acceptance_dir}/`, and write "
        f"`{project}/{acceptance_dir}/{suite.DECLARED_COMMAND_FILE}` saying how they run: "
        '{"command": ["<executable>", "<argument>", ...], "report": "<path>"} - the command '
        f"is run in `{project}/`, and must write a JUnit XML report at `report` (a path "
        f"relative to `{project}/`). Test the product the way its user meets it: a page "
        "through a browser, a service over HTTP, a program as a process, a library through "
        "its public functions. Each test's name carries the id of the criterion it proves, "
        "`[AC-3]` in a title or `ac3` in an identifier."
    )


def _how_each_was_made_testable(testability: Sequence[str]) -> str:
    """The adopted testability advice, for whoever writes or reviews the suite, or ""."""
    lines = [" ".join(str(line).split()) for line in testability or () if str(line).strip()]
    if not lines:
        return ""
    return (
        "--- How each criterion is to be made testable (the testing specialist's advice, "
        "adopted by the specification) ---\n"
        + "\n".join(f"- {line}" for line in lines)
        + "\nWrite the tests to it: the names to find each control by, the data each test "
        "creates first, what is held still, and what is asserted.\n\n"
    )


def _the_names_the_brief_gives(brief: str) -> str:
    """The names the brief gives its controls, each to be found by exactly that name, or ""."""
    from app.analysis.interface_checks import controls_the_brief_names

    names = controls_the_brief_names(brief)
    if not names:
        return ""
    return (
        "--- The names the brief gives its controls ---\n"
        + "\n".join(f'- "{name}"' for name in names)
        + "\nSome test finds each of these by exactly that name, through a locator that "
        "refuses two matches. The review sends back a suite that finds any of them another "
        "way.\n\n"
    )


def build_author_request(
    repo_root: str | Path,
    criteria: Sequence[Criterion],
    stack: Any = None,
    feedback: Sequence[str] = (),
    change_requests: dict[str, str] | None = None,
    brief: str = "",
    testability: Sequence[str] = (),
) -> dict[str, list[dict[str, str]]]:
    """The QA stage's brief: write the acceptance suite before anything is built.

    `testability` is the testing specialist's advice the specification adopted,
    one "TS-n: ..." line each. See `app.agents.specialist_advice`.

    `brief` is the customer's own document. It is where a product's interface
    is stated - the labels on its controls, its endpoints, its commands - and
    a test written against anything else tests a product nobody asked for.
    """
    where = suite.location(repo_root) or ("<project>", "acceptance")
    project, acceptance_dir = where
    deferred = suite.deferred(repo_root)
    requests_text = ""
    if change_requests:
        requests_text = (
            "--- Change requests to prove as well ---\n"
            + "\n".join(f"- {cid}: {text}" for cid, text in change_requests.items())
            + "\nEach needs a test whose name carries its id, exactly like a criterion. "
            "Change an existing test only where a request changes what it must check.\n\n"
        )
    feedback_text = ""
    if feedback:
        # Only what is wrong with the tests is QA's. One run's suite repair was
        # handed three findings about the product - a class the page did not
        # use, a save that did nothing - under "Fix each of these first", and
        # QA spent five calls trying to edit the page, refused each time.
        feedback_text = (
            "--- What the last review of this suite found ---\n"
            + "\n".join(f"- {item}" for item in feedback)
            + "\nFix each of these that is about the tests first. One about the product - "
            "something it lacks or does wrong - is not yours to fix: the product's own stages "
            "fix it, and your tests stay as the criteria require.\n\n"
        )
    # A suite reopened for repair is repaired against a product that exists.
    built = bool((suite.last_result(repo_root) or {}).get("passed"))
    state_of_the_product = (
        "The product is partly built and the suite is being repaired: change only what the "
        "review names. "
        if built
        else "Nothing of the product's features is built yet. Write its acceptance suite now: "
        "the tests that decide whether it is done. "
    )
    content = (
        "The workspace is rooted at '/'; all paths you use are relative to it.\n\n"
        "You are the QA engineer. " + state_of_the_product + "Once "
        "reviewed, the suite is locked, and the product is finished when it passes.\n\n"
        f"--- Acceptance criteria ---\n{criteria_text(criteria, deferred)}\n\n"
        f"{_how_each_was_made_testable(testability)}"
        f"{requests_text}"
        f"{feedback_text}"
        f"--- How to write them ---\n{_how_to_write_them(repo_root, project, acceptance_dir, stack)}\n\n"
        + (f"--- The brief, as the customer wrote it ---\n{brief.strip()[:BRIEF_CHARS]}\n\n" if brief.strip() else "")
        + _the_names_the_brief_gives(brief)
        + "--- What to build them against ---\n"
        "Where the brief states the interface - the labels on controls, endpoints, commands, "
        "names - the tests use exactly those words: they are what the customer will check. "
        "Where it says what kind of thing a record is shown as - an item of a list, a row of a "
        "table, an element of a returned array - the tests find each record that way, so a "
        "product that shows them some other way fails. "
        "For anything it leaves open, read `docs/technical_specification.md`, which names the "
        "rest, and test in the words a user would see.\n\n"
        "--- Rules ---\n"
        "- At least one test for every criterion; a test may prove several. A criterion "
        "is proven by checking the result a user observes, not by calling internal code.\n"
        "- Each test runs alone, against a product that holds no data: nothing another test "
        "created is there. A test that acts on something - an item, a record, an entry - "
        "creates it first, through the product as a user would; otherwise it can pass only "
        "on a product that ships with that data.\n"
        "- Where a view shows only the records in some state, a test also changes a record's "
        "state while that view is shown and checks the record leaves it - or joins it - at "
        "once, not only after the view is chosen again. A product that updates a view only "
        "when it is re-chosen passes every check made on a fresh view and fails its user.\n"
        f"- Write only inside `{project}/{acceptance_dir}/`. Product code is not yours.\n"
        "- Run the suite once. The tests must RUN and FAIL now, because nothing is built: "
        "failing because a control, endpoint, command or function does not exist yet is "
        "right. A syntax error, an import that does not resolve, \"no tests found\", or an "
        "error the test's own code throws - a helper called with the wrong arguments, a name "
        "the test never defined - is yours to fix before you finish: read why each test "
        "failed, not only that it did.\n"
        "- A criterion no automated test can check - a human judgement, an uptime promise, "
        "a third party's approval - gets no test. Put one line in `blockers` for it: "
        "`AC-n: <why no test can check it>`.\n"
        "- Report every test file in `tests`."
    )
    return {"messages": [{"role": "user", "content": content}]}


def not_automatable(blockers: Sequence[str]) -> dict[str, str]:
    """`AC-n: reason` lines from the QA stage's blockers."""
    from app.acceptance.junit import tags_in

    found: dict[str, str] = {}
    for line in blockers or ():
        text = str(line)
        ids = [tag for tag in tags_in(text) if tag.startswith("AC-")]
        if not ids:
            continue
        reason = text.split(":", 1)[1].strip() if ":" in text else text.strip()
        for criterion_id in ids:
            found.setdefault(criterion_id, reason or "no automated test can check it")
    return found


def suite_text(repo_root: str | Path) -> str:
    root = Path(repo_root)
    parts: list[str] = []
    total = 0
    for path in suite.suite_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        block = f"### {path.relative_to(root).as_posix()}\n{text}\n"
        if total + len(block) > SUITE_TEXT_CHARS:
            parts.append(f"### {path.relative_to(root).as_posix()}\n(not shown - read it with your tools)\n")
            continue
        parts.append(block)
        total += len(block)
    return "\n".join(parts) or "(the suite has no files)"


def acceptance_block(result: suite.AcceptanceResult | None, due: Sequence[str] | None = None) -> str:
    """The harness's own run of the suite, for a test round or a review."""
    if result is None:
        return ""
    due_note = ""
    if due is not None:
        # Only what is due. One run's first sprint was shown every criterion's
        # failure, reported a later sprint's filter as a defect, and spent its
        # whole fix budget on work its plan gave to sprint 3.
        due_note = (
            "Criteria this sprint must deliver (with every earlier sprint's): "
            + (", ".join(due) or "none")
            + ". Criteria later sprints build are left out: they are expected to fail "
            "until then and are not defects now.\n"
        )
    return (
        "--- The acceptance suite, run by the harness just now ---\n"
        f"{due_note}{result.summary(due)}\n"
        "This is the record of what passes; it is not open to interpretation. A failing "
        "criterion that is due is a defect in the product, never in the locked suite.\n\n"
    )
