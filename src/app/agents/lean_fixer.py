"""A fixer's own lean request: its own short system prompt, the tools it uses, and its failing tests printed once
each (plan FX.3, LF.1417-LF.1418; always on).

Measured on a medium run (eight fixers shown a defect): every fixer was built as its owner's builder - the builder's
role prompt with its build, documentation, testability and dependency rules, about 21,000 characters with the stack
guidance, and sixteen tools whose descriptions came to 23,564 characters. Over 54 runs of fix stages, five tools made
nearly all the calls: `read_file` 2,990, `run_terminal_command` 869, `edit_artifact` 507, `write_artifact` 120 and the
search; `move_artifact`, `read_docs` and `research` were never called in about 3,500 offers each. Together with the
request and its memory, the fixers opened at 26,400-34,000 tokens against a 43,020-token summary trigger and were
summarised twice in 16-19 calls; about a quarter of a 129,000-character opening bore on the defect. Six blocks of what
the failing tests printed said one thing five times.

So a fixer is given:

- `system_prompt`: how to fix one failure - find the cause from what the machine printed, work from the files held,
  read by range, change by exact passage, run the test again, answer once - with the rules that bind any change to
  the product (its owner's product rules, no logic removed, no route only for tests, the locked suite and `docs/`
  left alone) and the answer rules. The builder's rules for writing a product from nothing are not in it.
- `TOOLS`: read by range (`read_file`), search (`grep`), edit (`edit_artifact`), write (`write_artifact`, and
  `delete_artifact`, which a stack's guidance names to remove a lock file and which removes a fixer's own scratch file),
  run (`run_terminal_command`, with `read_command_output` for the rest of an output it cut, which the harness's own
  pointers name), and its answer; `module_exports` where the run offers it, since a stack's guidance names it. The web
  tools of a fixer whose defect failed twice stay offered with it.
- `failures_once`: each distinct failure its tests printed whole once, and every other test that failed the same way
  as one line naming where it stopped.

The guards are where they were: the write tools' rules (the locked suite, the harness's own files, a tests-only
attempt) refuse what they refused; the request's sections (what may be written, how the fix is settled) are its own.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Iterable

#: The tools a fixer is offered, beside its answer (and the web tools of a fixer whose defect failed twice).
TOOLS: frozenset[str] = frozenset({
    "read_file", "grep", "edit_artifact", "write_artifact", "delete_artifact", "run_terminal_command",
    "read_command_output",
})
#: Offered when the run offers it at all: a stack's own guidance tells a fixer to check an installed package's
#: exports with it before importing an unsure name.
WHEN_OFFERED: frozenset[str] = frozenset({"module_exports"})

#: How each owner is named in a fixer's prompt.
_TITLES = {
    "ui_ux": "UI and UX", "database": "Database", "backend": "Backend", "testing": "Testing",
    "documentation": "Documentation", "security_reliability": "Security and Reliability",
}

#: The first paragraph: who the fixer is (the summary of a long conversation reads it as the stage's role).
_WHO = ("You are the {title} specialist, fixing one failure in code that exists. The request names it and shows what "
        "the machine printed when it failed; the project memory holds the files it passes through, where they fit.")

#: What a fixer does with a locked test no right product can pass: it says so and stops, rather than bending the product
#: to it (LF.1616). Measured on one run: two fixers worked out that a locked test's locator found two of its own records,
#: wrote "but I can't change the test", spent every call reshaping a right page and gave no answer, so nothing reached
#: the QA lead until the attempt's rounds were spent.
LOCKED_TEST_THAT_CANNOT_PASS = (
    "- A locked test that no product meeting its criterion can pass - its own steps rule out what it asserts - is\n"
    "  not yours to make pass: change nothing for it, return at once, and put in `blockers` the test's name and the\n"
    "  line of it that cannot hold, word for word, with why. The QA lead judges it; the test stays as it is."
)

FIXING_RULES = (
    "How to fix it:\n"
    "- Find the cause before you change anything. Start from what the machine printed and the files the request\n"
    "  names; where they show no cause, run the failing test, or a short program that shows the error, with\n"
    "  `run_terminal_command`.\n"
    "- A file the project memory holds is in front of you, whole and current: work from it. Read any other file\n"
    "  with `read_file`, a long one by `offset` and `limit` around the lines you need, and find which file holds\n"
    "  a name or a message with `grep`.\n"
    "- Change a file with `edit_artifact`: one exact passage, copied from the file without its line numbers, to\n"
    "  its replacement. Write a new file, or a whole file again, with `write_artifact`, beside the code or tests\n"
    "  it belongs with in the project folder; remove a file you made only to try something with `delete_artifact`.\n"
    "  Change what this failure needs and nothing else.\n"
    "- After a change, run the failing test again.\n"
    "- `run_terminal_command` runs one program with its arguments, with no shell between them: `&&`, `|`, `;` and\n"
    "  `cd` do not work. Pass `working_directory` to run in the project directory. Where it cut an output,\n"
    "  `read_command_output` reads the rest.\n"
    "- Never remove or disable application logic to make a test pass, and never add a route or command that\n"
    "  exists only so tests can reset, seed or inspect data: everyone who can reach the product can call it.\n"
    "- The locked acceptance suite says what the product must do: read its tests, never change them. `docs/` is\n"
    "  the workflow's: read it, never write there. You already have permission to write; never ask for it.\n"
    + LOCKED_TEST_THAT_CANNOT_PASS + "\n"
    "- Return your answer once, through your answer tool: the files you changed, every command you ran with its\n"
    "  exit code, and the test you added. What you could not fix goes in `blockers`, with what you found.\n"
)



def _role_rules(role: str) -> str:
    """The rules of `role`'s builder that bind any change to the product, as its builder is given them."""
    from app.agents.normal_form import A_GROUP_IN_ITS_NORMAL_FORM
    from app.agents.own_store_rule import FOR_TEST_WRITERS as OWN_STORE
    from app.agents.stand_in_rule import FOR_TEST_WRITERS as STAND_INS

    if role == "backend":
        from app.agents.specialists import REFUSE_WHAT_IT_CANNOT_USE

        return REFUSE_WHAT_IT_CANNOT_USE + " " + A_GROUP_IN_ITS_NORMAL_FORM
    if role == "ui_ux":
        return A_GROUP_IN_ITS_NORMAL_FORM
    if role == "testing":
        return STAND_INS + " " + OWN_STORE
    return ""


def system_prompt(role: str) -> str:
    """A fixer's system prompt for a defect `role` owns."""
    from app.agents.role_agent import ARTIFACTS_ARE_NOT_THE_ANSWER, REASONING_IS_NOT_WORK
    from app.agents.structured_response import STRUCTURED_RESPONSE_RULE

    title = _TITLES.get(str(role), str(role).replace("_", " ").title())
    rules = _role_rules(str(role))
    return (_WHO.format(title=title) + "\n\n" + FIXING_RULES + "\n"
            + (rules + "\n\n" if rules else "")
            + REASONING_IS_NOT_WORK + "\n" + ARTIFACTS_ARE_NOT_THE_ANSWER + "\n" + STRUCTURED_RESPONSE_RULE + "\n")


def tools_for(also: Iterable[Any] = ()) -> frozenset[str]:
    """The names a fixer is offered: `TOOLS`, `WHEN_OFFERED` (where the run builds them) and the tools in `also`
    (the web tools of a fixer whose defect failed twice)."""
    return TOOLS | WHEN_OFFERED | {str(getattr(tool, "name", "") or "") for tool in also or ()} - {""}


# --- what its failing tests printed, each failure once -----------------------------------------------------------

#: A line of a test's message that states the failure: an error or exception and its message, what was expected and
#: what was received, an assertion, a cause.
_A_STATEMENT = re.compile(
    r"^\s*(?:[A-Za-z_][\w.]*(?:Error|Exception|Failure)\b|Error\b|Expected\b|Received\b|E\s{2,}|assert\b|"
    r"AssertionError\b|Caused by\b|panic\b|FAIL(?:ED)?\b)")
#: Where a test stopped: a stack frame's `at path:line` or `path:line:` in its own file.
_WHERE = re.compile(r"(?:\bat\s+\(?|^\s*)([\w./\\-]+\.[A-Za-z]{1,5}):(\d+)", re.M)
#: The most of the statement a repeated failure's line carries.
MOST_STATEMENT_CHARACTERS = 160


#: A path in a statement: a runner names each test's own evidence file in it, so two tests failing the same way differ
#: only there.
_A_PATH = re.compile(r"\S*/\S*")


def _statement(message: str) -> tuple[str, ...]:
    """The lines of `message` that state its failure, each without its paths and with its spaces closed up; a line
    left saying nothing past its label is not one."""
    said = (" ".join(_A_PATH.sub("", line).split()) for line in str(message).splitlines() if _A_STATEMENT.match(line))
    return tuple(line for line in said if not line.endswith(":"))


def _where_it_stopped(message: str) -> str:
    """The last `file:line` of `message` (the test's own frame, as runners print it last); "" for none."""
    found = list(_WHERE.finditer(str(message)))
    if not found:
        return ""
    path, line = found[-1].group(1), found[-1].group(2)
    return f"{path.replace(chr(92), '/').rsplit('/', 1)[-1]}:{line}"


def _blocks(output: str, names: str) -> tuple[str, list[tuple[str, str]], str]:
    """`output` split into what comes before the first test, each test's (name, message) and what follows the last
    (a page's own report). A test's block opens with a line `<name>:` at the margin whose name `names` (the list of
    the failing tests the command line gives) holds."""
    lines = str(output).split("\n")
    starts: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        if line.endswith(":") and line == line.lstrip() and len(line) > 4 and line[:-1] in names:
            starts.append((index, line[:-1]))
    if not starts:
        return output, [], ""
    head = "\n".join(lines[:starts[0][0]])
    blocks: list[tuple[str, str]] = []
    tail = ""
    for position, (index, name) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        body = "\n".join(lines[index + 1:end])
        if position + 1 == len(starts):
            # A report after the last test (the page's own, `When the page itself loaded`) is not that test's.
            cut = body.find("\n\nWhen the page itself loaded")
            if cut >= 0:
                body, tail = body[:cut], body[cut:]
        blocks.append((name, body.rstrip("\n")))
    return head, blocks, tail


def printed_once(output: str, names: str) -> str:
    """`output` (what a defect's failing tests printed) with each distinct failure whole once, in order, and each
    other test that failed the same way - the same statement of what failed - as one line; `output` as it is when
    no two failed the same way."""
    head, blocks, tail = _blocks(output, names)
    first_of: dict[tuple[str, ...], str] = {}
    whole: list[str] = []
    repeats: list[str] = []
    for name, body in blocks:
        statement = _statement(body)
        if statement and statement in first_of:
            where = _where_it_stopped(body)
            said = "; ".join(statement)[:MOST_STATEMENT_CHARACTERS]
            repeats.append(f"- {name}" + (f" (at {where})" if where else "") + f": {said}")
            continue
        if statement:
            first_of[statement] = name
        whole.append(f"{name}:\n{body}")
    if not repeats:
        return output
    text = (head.rstrip("\n") + "\n" if head.strip() else "") + "\n\n".join(whole)
    text += (f"\n\n{len(repeats)} more test(s) failed the same way as one shown above:\n" + "\n".join(repeats))
    return text + tail


def failures_once(observed: Any) -> Any:
    """`observed` (a fix request's "what its failing tests printed": command, output, title) with its output printed
    once each (`printed_once`); `observed` itself when there is nothing to fold. Never raises."""
    try:
        if not isinstance(observed, dict) or not observed.get("output"):
            return observed
        output = str(observed["output"])
        folded = printed_once(output, str(observed.get("command") or ""))
        return observed if folded == output else {**observed, "output": folded}
    except Exception:  # noqa: BLE001 - the output as it was
        return observed


# --- the standing sections that bear on a defect -----------------------------------------------------------------

def bearing_on(files: Iterable[str], routes: Iterable[str], criteria: Iterable[str]) -> Callable[[str], bool]:
    """Whether a standing section of a fix request bears on its defect: it names one of the defect's `files` (by path,
    or by a file name no shorter than five characters), a route its failing tests call (`routes`, as
    `fixer_request_shape.routes_called` gives them), or one of its `criteria`. A request past its target leaves out
    the others first (`request_budget.fit`, FX.3)."""
    paths = {str(f).strip().lstrip("./") for f in files or () if str(f).strip()}
    names = {p.rsplit("/", 1)[-1] for p in paths} - {""}
    words = [re.compile(rf"(?<![\w.-]){re.escape(w)}(?![\w-])") for w in sorted(paths | {n for n in names if len(n) >= 5})]
    resources = [re.compile(rf"{re.escape(str(r).lower())}(?![\w-])") for r in routes or () if str(r).strip()]
    tags = [re.compile(rf"(?<![\w-]){re.escape(str(c))}(?![\w])") for c in criteria or ()
            if str(c).startswith(("AC-", "CR-"))]

    def touches(section: str) -> bool:
        text = str(section or "")
        lowered = text.lower()
        return (any(w.search(text) for w in words) or any(r.search(lowered) for r in resources)
                or any(t.search(text) for t in tags))

    return touches


__all__ = ["FIXING_RULES", "MOST_STATEMENT_CHARACTERS", "TOOLS", "WHEN_OFFERED", "bearing_on", "failures_once",
           "printed_once", "system_prompt", "tools_for"]
