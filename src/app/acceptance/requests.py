"""What the QA stage, the test rounds and the reviews are told about the suite."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence

from app.acceptance import actions_within_a_view, suite
from app.acceptance.api_reference import api_reference
from app.acceptance.criteria import Criterion
from app.agents import brief_over_spec
from app.stacks import contract
from app.plugins.seed import JUNIT_REPORTS

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


#: Said to the writer of a suite that runs against one service for its whole
#: session. Measured on a gate run: a test asserted a signed-in account's list
#: was empty after signing in to an account an earlier test had filled; it
#: could pass for no product, the suite was reopened and reviewed twice.
#: One pack said it; the others start their service the same way.
SHARED_STORE = (
    "The service keeps its data for the whole run of the suite, shared by every test, so a test "
    "must not assume it starts empty: create what it reads under names no other test uses (a "
    "username of its own, say), and look for its own records rather than counting all of them."
)
#: Said to the writer of a suite that drives a page. Measured on runs: a test saved an entry and typed the next one
#: at once; the page emptied its form when the save finished and erased what the test had typed, and the test failed
#: a product that was right.
WAIT_FOR_THE_SAVE = (
    "After a test sends a form - an entry saved, a sign-in - it waits for what the page shows once that is done "
    "(the new entry listed, the form emptied) before it types into the form again: a page may empty its form when "
    "the save completes, and erase whatever was typed in the meantime."
)
#: Said to the suite's writer and its reviewer, true on every stack. It said each test ran alone against an empty
#: product, beside `SHARED_STORE`, which says the opposite for a service the suite starts once; the
#: reviewer had only the first, and a test counting a shared table read as right to both.
TESTS_ASSUME_ONLY_WHAT_THEY_MADE = (
    "- Each test assumes nothing it did not make: what it acts on or reads, it creates first, through the "
    "product as a user would, under names no other test uses. Other tests' records may be there too - on a "
    "service the suite starts once they are - so a test looks for its own records and never counts them all. "
    "A test that acts on something it never created can pass only on a product that ships with that data. "
    # Measured on two full-stack runs in a row: a test read the kept start script and asserted its lines; found only
    # after the build, each cost a suite reopen and a repair.
    "And a test never reads the text of a file the harness keeps - its start script, its configuration: that "
    "text is not the product's to change. What such a file must do, the test shows on the running product.\n"
    # Measured on two runs in a row, both arms of a measurement: a locked test expected 24 characters for a string of
    # 23 (or 25), counted by hand; each cost two fix rounds on a product that counted right.
    "- A count or length of text the test writes itself - its characters, lines or bytes - is worked out in the test "
    "from that text (its length, its lines), never written as a number: a number counted by hand is often one off, "
    "and the test then fails a product that counts right.\n"
    # Measured on one run, a false acceptance: the brief said a function leaves "the whitespace exactly as it was",
    # every test used spaces alone, the product split words on spaces only, and a hidden test with a tab failed.
    "- Where a criterion speaks of a kind of input - whitespace, punctuation, separators, digits, letters of any "
    "case - its tests use more than one member of that kind (a space and a tab, a comma and a full stop), so a "
    "product that handles only the first one fails.\n"
    # Measured on two runs, both false acceptances of one brief: it gave a mode an output of its own in place of
    # another's; the test checked only that its own part was there, and a product printing both passed.
    "- Where the brief gives one mode an output in place of another's - \"instead\", \"only\", \"rather than\", "
    "or \"with this, it prints ...\" - a test of that mode also checks the other output is absent: it compares the "
    "whole set of keys or lines with the ones the brief shows for that mode. A product that prints both passes a test "
    "that looks only for its own part.\n"
)
#: The kinds of product whose suite runs against one long-lived service.
_A_SHARED_SERVICE = frozenset({"http_api", "fullstack"})
#: The kinds of product whose suite drives a page.
_DRIVES_A_PAGE = frozenset({"browser_app", "fullstack"})


def shares_one_service(repo_root: str | Path) -> bool:
    """Whether this workspace's suite runs against one service started once and shared by every test."""
    found = contract.the_pack(repo_root)
    return found is not None and getattr(found[0], "kind", "") in _A_SHARED_SERVICE


def _how_to_write_them(repo_root: str | Path, project: str, acceptance_dir: str, stack: Any) -> str:
    found = contract.the_pack(repo_root)
    if found is not None:
        pack, record = found
        command = " ".join(record.get("acceptance_test") or pack.acceptance_test)
        guide = pack.filled(pack.acceptance_guide, project, record.get('title') or project, record.get('package'))
        if getattr(pack, "kind", "") in _A_SHARED_SERVICE and "starts empty" not in guide:
            guide = guide.rstrip() + "\n" + SHARED_STORE
        if getattr(pack, "kind", "") in _DRIVES_A_PAGE:
            guide = guide.rstrip() + "\n" + WAIT_FOR_THE_SAVE
        return (
            f"{guide}\n"
            f"Run the suite with `{command}` in `{project}/`."
        )
    testing = str(getattr(stack, "testing_framework", "") or "the stack's testing framework")
    return (
        f"No project setup exists for this stack, so the suite's runner is yours to set up. "
        f"Use {testing}. Write the tests in `{project}/{acceptance_dir}/`, and write "
        f"`{project}/{acceptance_dir}/{suite.DECLARED_COMMAND_FILE}` saying how they run: "
        '{"command": ["<executable>", "<argument>", ...], "report": "<path>"} - the command '
        f"is run in `{project}/`, and must write a JUnit XML report at `report` (a path "
        f"relative to `{project}/`). When the suite needs several runners, list each with its own report instead: "
        '{"runs": [{"command": [...], "report": "<path>"}, ...]} - no script of your own to combine them; each runs in '
        "turn and the harness reads each report as it finishes. Test the product the way its user meets it: a page "
        "through a browser, a service over HTTP, a program as a process, a library through "
        "its public functions. Each test's name carries the id of the criterion it proves, "
        "`[AC-3]` in a title or `ac3` in an identifier.\n"
        # Measured on one run: a browser runner was asked for its report in a form it does not read, and five rounds
        # failed on a report that was never written; the writers had never been told how each runner writes one.
        f"How each runner writes that report:\n{JUNIT_REPORTS}"
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


#: The most of the example test the request carries.
MOST_EXAMPLE_CHARACTERS = 4_000


def _a_test_that_ran_here(repo_root: str | Path, acceptance_dir: str) -> str:
    """The acceptance smoke test that passed when the project was set up, as the shape to copy.

    Measured on one run: QA spent 149 minutes and 182 calls on its suite, a
    third of them malformed or refused, writing every file from nothing. The
    setup had already proven one acceptance test in this project's own runner -
    its imports, how it starts the product, how it names a test - and removed it.
    """
    try:
        from app.stacks import contract

        found = contract.the_pack(repo_root)
    except Exception:  # noqa: BLE001 - the request without an example
        return ""
    if not found:
        return ""
    pack, record = found
    example = str(((record or {}).get("setup") or {}).get("acceptance_example") or "")
    if not example:
        example = next(
            (str(text) for name, text in (getattr(pack, "smoke_files", None) or {}).items()
             if str(name).startswith(f"{acceptance_dir}/")),
            "",
        )
    if not example.strip():
        return ""
    return (
        "--- A test that ran and passed in this project's own runner ---\n"
        "It proved the setup and was then removed. Copy its shape - its imports, how it starts "
        "the product, how it names and structures a test - and replace what it checks with "
        "the criteria:\n"
        f"```\n{example.strip()[:MOST_EXAMPLE_CHARACTERS]}\n```\n\n"
    )


def _the_interface_contract(lines: Sequence[str]) -> str:
    """The architect's interface contract as a section of the brief, or "" when there is none."""
    kept = [" ".join(str(line).split()) for line in lines or () if str(line).strip()]
    if not kept:
        return ""
    return (
        "--- The interface contract ---\n"
        + "\n".join(f"- {line}" for line in kept)
        + "\nThe architect fixed these routes, page controls and commands, and the release checks "
        "each one. Where a test reaches one, it uses exactly this path, role and name.\n\n"
    )


def build_author_request(
    repo_root: str | Path,
    criteria: Sequence[Criterion],
    stack: Any = None,
    feedback: Sequence[str] = (),
    change_requests: dict[str, str] | None = None,
    brief: str = "",
    testability: Sequence[str] = (),
    interface_contract: Sequence[str] = (),
    specification: Any = None,
    batch_note: str = "",
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
        f"{batch_note}"
        f"{_how_each_was_made_testable(testability)}"
        f"{requests_text}"
        f"{feedback_text}"
        f"--- How to write them ---\n{_how_to_write_them(repo_root, project, acceptance_dir, stack)}\n\n"
        f"{_a_test_that_ran_here(repo_root, acceptance_dir)}"
        + (f"--- The brief, as the customer wrote it ---\n{brief.strip()[:BRIEF_CHARS]}\n\n" if brief.strip() else "")
        + _the_names_the_brief_gives(brief)
        + _the_interface_contract(interface_contract)
        + api_reference(specification, brief)
        + "--- What to build them against ---\n"
        "Where the brief states the interface - the labels on controls, endpoints, commands, "
        "names - the tests use exactly those words: they are what the customer will check. "
        "Where it says what kind of thing a record is shown as - an item of a list, a row of a "
        "table, an element of a returned array - the tests find each record that way, so a "
        "product that shows them some other way fails. "
        "For anything it leaves open, read `docs/technical_specification.md`, which names the "
        "rest, and test in the words a user would see, matching each name exactly as given.\n\n"
        "--- Rules ---\n"
        "- At least one test for every criterion; a test may prove several. Every criterion's id "
        "appears in the name of at least one test, written as the naming rule above says, and a "
        "test that proves several criteria carries every one of their ids. A criterion whose id "
        "is in no test's name cannot be tracked or credited. A criterion is proven by checking "
        "the result a user observes, not by calling internal code.\n"
        "- A test checks what the brief or the interface contract says, and no more. Where they give a "
        "status code, a field or an exact message, the test checks that. Where they give no wording for an "
        "error or a message, the test checks that it is an error - the status, the shape - and not the "
        "words the specification happened to choose. A product built to the brief fails a test that "
        "asserts wording nobody required, and the suite is locked with that failing.\n"
        + brief_over_spec.qa_rule()
        + TESTS_ASSUME_ONLY_WHAT_THEY_MADE
        + "- A test that a product keeps its data checks every kind of change it offers - not only "
        "creating a record, but each way one can be changed or removed - survives a reload or a "
        "restart. A product that keeps only what was created passes a weaker test and loses its "
        "user's changes.\n"
        "- Where a view shows only the records in some state, a test also changes a record's "
        "state while that view is shown and checks the record leaves it - or joins it - at "
        "once, not only after the view is chosen again. A product that updates a view only "
        "when it is re-chosen passes every check made on a fresh view and fails its user.\n"
        + actions_within_a_view.author_rule()
        + "- Where the user adds records through a page, one test adds two, one after the other, "
        "from the same page without reloading it, and checks both are shown. A page that works "
        "only once - a control left disabled, or a form left in its first state, after the first "
        "save - passes every test that adds one record and fails its user at the second. The test "
        "waits until the first is shown before it types the second, as a person does: a page that "
        "empties its form once a save has finished would otherwise empty what the test typed.\n"
        + f"- Write only inside `{project}/{acceptance_dir}/`. Product code is not yours.\n"
        "- Never start a product that keeps running - a service, or the server a page is served "
        "from - yourself, in a test or by a command: the suite's own setup starts it before the "
        "tests and stops it after. A test that runs its start script or its server waits for a "
        "process that never ends, and the whole suite stops there with no result for any test. "
        "A criterion about how it starts is proven by the running product the setup gives you. "
        "A program that runs and exits is run by its tests, as its user runs it.\n"
        "- Run the suite once. The tests must RUN and FAIL now, because nothing is built: "
        "what the project holds now is the stack's starting skeleton - a health check, an "
        "empty entry point, a manifest - and the builders write the product after this suite "
        "is locked. Finishing it is not yours, not even to see one test pass; "
        "failing because a control, endpoint, command or function does not exist yet is "
        "right.A syntax error, an import that does not resolve, \"no tests found\", or an "
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


def _where_a_file_left_out_is() -> str:
    """What a suite file left out of the request says about where it is.

    Measured on one run: a 58,000-character suite showed 24,000 here and told
    the reviewer to read the rest; the project memory held all ten files
    whole, every one of the five reads came back "is in the project memory",
    and the stall rule then withheld the reviewer's tools - a model call and
    five tool calls spent finding what it already had. With the memory on, the
    memory is where the file is.
    """
    from app.agents import project_memory

    if project_memory.enabled():
        return "(not shown here: it is in the project memory; read it only if the memory names it as not included)"
    return "(not shown - read it with your tools)"


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
            parts.append(f"### {path.relative_to(root).as_posix()}\n{_where_a_file_left_out_is()}\n")
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
