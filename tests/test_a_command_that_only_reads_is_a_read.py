"""A command that only reads a file is a read, decided as `read_file` is (LF.1525).

Measured on a medium run (`tests/captured/builder-reads-a-file-through-the-shell.json`): a database builder needed a
593-line `routes.py` another work order owned. With `read_file` withheld it read the file through the command tool -
`head -100`, `head -200`, `cat`, `wc -l`, `sed -n 200,400p` (refused: "To change a file, use `edit_artifact`"),
`sed -n 200,350p`, `head -100` again, and Python one-liners printing slices of its lines, the first failing on the
path and two asking for the same lines. 49 calls, 22% failing. Withholding the reader did not stop the reading.

The stage here is the captured fixer whose reads are decided file by file (TR.2,
`tests/captured/fixer-reads-withheld-after-two-summaries.json`), sent the builder's captured commands.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agents import project_memory, stage_memory
from app.agents.settled_answer import build_settled_answer_middleware
from app.observability import transcript
from tests.test_a_withheld_read_is_decided_per_file import CAPTURED, HELD, Answer, _message, _Request

SHELL = json.loads((Path(__file__).parent / "captured" / "builder-reads-a-file-through-the-shell.json")
                   .read_text(encoding="utf-8"))
BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)
ROUTES = "task-management-dashboard/task_management_dashboard/routes.py"
REQUIREMENTS = "task-management-dashboard/requirements.txt"
RAN = "the command ran"
RUN = "run-deadbeef"


def _captured(*words: str) -> dict:
    """The first captured command call whose arguments carry every one of `words`."""
    return next(c["args"] for c in SHELL["calls"]
                if c["tool"] == "run_terminal_command" and all(w in json.dumps(c["args"]) for w in words))


SED_200_400 = _captured("sed", "200,400p")
CAT_REQUIREMENTS = _captured("cat", "requirements.txt")
SLICE_100_250 = _captured("lines[100:250]", "'task_management_dashboard/routes.py'")
SLICE_100_250_FROM_THE_ROOT = _captured("lines[100:250]", "'task-management-dashboard/task_management_dashboard")
SLICE_250_400 = _captured("lines[250:400]")
SLICE_400_590 = _captured("lines[400:590]")


def _line(n: int) -> str:
    return f"    route_{n} = handler_for({n})"


@pytest.fixture
def the_builder(tmp_path, monkeypatch):
    """Its memory, the command reads and its answer guard in one stage, in the order its agent has them; reads decided
    file by file after the captured fixer's conversation."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("PROJECT_MEMORY", "on")
    monkeypatch.setenv("STABLE_TOOLS", "on")
    monkeypatch.setenv("FIRST_REREAD_ANSWERED", "off")
    monkeypatch.setenv("FIX_STAGE_CALL_CAP", "off")
    repo = tmp_path / "repo"
    (repo / "tasks-api" / "tasks_api").mkdir(parents=True)
    for path in HELD:
        (repo / path).write_text(f'"""{Path(path).stem}"""\n')
    (repo / "task-management-dashboard" / "task_management_dashboard").mkdir(parents=True)
    (repo / REQUIREMENTS).write_text("fastapi>=0.115\nuvicorn>=0.30\n")
    from app.agents.shell_reads import build_shell_read_middleware

    with stage_memory.remembering("the-builder-thread"), transcript.asked_for("specialist_database_0", RUN):
        memory = project_memory.build_project_memory_middleware(str(repo))
        memory.wrap_model_call(_Request(messages=[HumanMessage(content="Build the database layer")], model=None),
                               lambda request: None)
        # Written after the memory was taken, as another work order's file the memory does not hold.
        (repo / ROUTES).write_text("\n".join(_line(n) for n in range(1, 594)) + "\n")
        shell = build_shell_read_middleware(str(repo))
        guard = build_settled_answer_middleware(Answer, "specialist_database", 40)
        builder = SimpleNamespace(memory=memory, shell=shell, guard=guard)
        _a_model_call(builder, [])
        yield builder
    stage_memory.forget_everything()


def _a_model_call(builder, then: list) -> None:
    """One model call carrying the captured conversation, then `then`."""
    conversation = [HumanMessage(content="Build the database layer"), *(_message(m) for m in CAPTURED["conversation"]),
                    *then]
    request = _Request(messages=conversation, tools=[SimpleNamespace(name=name) for name in CAPTURED["offered"]],
                       model=None, model_settings={})
    builder.shell.wrap_model_call(request, lambda sent: builder.guard.wrap_model_call(sent, lambda final: None))


def _command(builder, args: dict, call_id: str = "c1") -> ToolMessage:
    """One command through all three, the memory outermost, as the agent orders them; the command itself stubbed."""
    call = SimpleNamespace(tool_call={"name": "run_terminal_command", "id": call_id, "args": args})

    def the_sandbox(request):
        return ToolMessage(content=RAN, tool_call_id=call_id)

    return builder.memory.wrap_tool_call(
        call, lambda request: builder.shell.wrap_tool_call(request, lambda inner: builder.guard.wrap_tool_call(inner, the_sandbox)))


def _numbered(text: str) -> list[int]:
    return [int(n) for n in re.findall(r"(?m)^ *(\d+)  ", text)]


def test_a_print_only_sed_is_answered_with_those_lines_numbered(the_builder):
    said = str(_command(the_builder, SED_200_400).content)

    assert said != RAN
    assert _numbered(said) == list(range(200, 401))
    assert _line(200) in said and _line(401) not in said
    assert "edit_artifact" not in said


def test_a_python_line_printing_a_slice_is_answered_with_those_lines(the_builder):
    said = str(_command(the_builder, SLICE_100_250).content)

    assert _numbered(said) == list(range(101, 251))


def test_the_slice_named_from_the_workspace_s_root_is_read_too(the_builder):
    """The captured call that failed on its path in the sandbox: the folder named again from the root."""
    said = str(_command(the_builder, SLICE_100_250_FROM_THE_ROOT).content)

    assert _numbered(said) == list(range(101, 251))


def test_a_file_the_memory_holds_is_refused_by_name_and_where_it_is(the_builder):
    answer = _command(the_builder, CAT_REQUIREMENTS)

    said = str(answer.content)
    assert answer.status == "error"
    assert f"'{REQUIREMENTS}'" in said and project_memory.HELD_POINTER in said
    assert not BANNED.search(said.replace(REQUIREMENTS, "")), "the harness's own words (the product's path aside)"


def test_the_same_lines_asked_again_are_refused_while_the_first_answer_is_held(the_builder):
    """The captured builder sent `lines[250:400]` twice running."""
    first = _command(the_builder, SLICE_250_400, "c1")
    _a_model_call(the_builder, [AIMessage(content="", tool_calls=[{"name": "run_terminal_command", "id": "c1",
                                                                    "args": SLICE_250_400}]),
                                ToolMessage(content=first.content, tool_call_id="c1", name="run_terminal_command")])

    again = _command(the_builder, SLICE_250_400, "c2")
    other = _command(the_builder, SLICE_400_590, "c3")

    assert again.status == "error" and "read earlier in this conversation" in str(again.content)
    assert _numbered(str(other.content)) == list(range(401, 591))


def test_each_decision_is_recorded_with_the_command_tool(the_builder):
    _command(the_builder, SED_200_400)
    _command(the_builder, CAT_REQUIREMENTS)

    records = [(r.get("how"), r.get("path"), r.get("tool")) for r in transcript.read_transcript(RUN)
               if r.get("kind") == "read_while_withheld"]

    assert records == [("ran", ROUTES, "run_terminal_command"),
                       ("held whole", REQUIREMENTS, "run_terminal_command")]


def test_with_reading_offered_the_same_command_sent_again_is_answered_from_the_first(tmp_path, monkeypatch):
    """Reading not withheld: the captured raw answer to `lines[250:400]` is still in the conversation."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.agents.shell_reads import build_shell_read_middleware

    with stage_memory.remembering("a-reading-thread"):
        shell = build_shell_read_middleware(str(tmp_path))
        conversation = [HumanMessage(content="Build the database layer"),
                        AIMessage(content="", tool_calls=[{"name": "run_terminal_command", "id": "c1",
                                                           "args": SLICE_250_400}]),
                        ToolMessage(content=SHELL["printed_250_400"], tool_call_id="c1", name="run_terminal_command")]
        shell.wrap_model_call(_Request(messages=conversation, model=None), lambda request: None)
        calls = [SimpleNamespace(tool_call={"name": "run_terminal_command", "id": i, "args": args})
                 for i, args in (("c2", SLICE_250_400), ("c3", SLICE_400_590))]
        again, other = (shell.wrap_tool_call(call, lambda request: ToolMessage(content=RAN, tool_call_id="x"))
                        for call in calls)
        again, other = str(again.content), str(other.content)
    stage_memory.forget_everything()

    assert "read earlier in this conversation" in again
    assert other == RAN


def test_the_sandbox_calls_a_print_only_sed_a_read(tmp_path):
    """Captured: "'sed' is not permitted for role 'database_specialist'. To change a file, use `edit_artifact`"."""
    from app.tools.sandbox import CommandNotAllowed, validate_command

    with pytest.raises(CommandNotAllowed) as refused:
        validate_command(["sed", "-n", "200,400p", "task_management_dashboard/routes.py"], SHELL["role"], tmp_path)

    said = str(refused.value)
    assert "edit_artifact" not in said and "To change a file" not in said
    assert "only reads lines 200-400" in said and "`offset` 199" in said and "`limit` 201" in said
    assert not BANNED.search(said.replace("task_management_dashboard/routes.py", ""))


def test_an_editor_that_changes_a_file_is_still_pointed_at_the_edit_tool(tmp_path):
    from app.tools.sandbox import CommandNotAllowed, validate_command

    with pytest.raises(CommandNotAllowed) as refused:
        validate_command(["sed", "-i", "s/a/b/", "app.py"], SHELL["role"], tmp_path)

    assert "edit_artifact" in str(refused.value)


def test_a_judge_of_the_suite_is_refused_the_product_s_code_by_a_command_too():
    """LF.1531's rule for `read_file`, whatever tool reads."""
    from app.agents.reads_of_the_product import refused

    assert ROUTES in refused("run_terminal_command", SED_200_400)
    assert refused("run_terminal_command", {"command": ["npx", "playwright", "test"]}) == ""


@pytest.mark.parametrize("command, path, lines", [
    (["head", "-100", "a/app.py"], "a/app.py", (0, 100)),
    (["head", "-n", "20", "app.py"], "app.py", (0, 20)),
    (["tail", "-n", "30", "app.py"], "app.py", (-30, 30)),
    (["tail", "-n", "+40", "app.py"], "app.py", (39, 0)),
    (["sed", "-n", "5p", "app.py"], "app.py", (4, 1)),
    (["awk", "NR>=3 && NR<=9", "app.py"], "app.py", (2, 7)),
    (["nl", "app.py"], "app.py", (0, 0)),
    (["node", "-e", "console.log(require('fs').readFileSync('src/app.js', 'utf8'))"], "src/app.js", (0, 0)),
])
def test_the_commands_that_only_read_say_which_lines(command, path, lines):
    from app.agents.shell_reads import a_shell_read

    read = a_shell_read(command, "")

    assert (read.path, read.offset, read.limit) == (path, *lines)


@pytest.mark.parametrize("command", [
    ["sed", "-i", "s/a/b/", "app.py"], ["sed", "s/a/b/", "app.py"], ["head", "-c", "20", "app.py"],
    ["cat", "a.py", "b.py"], ["cat", "/etc/hosts"], ["python3", "-c", "import app; print(app.run())"],
    ["tail", "-f", "server.log"],
])
def test_a_command_that_does_more_than_read_one_file_is_not_a_read(command):
    from app.agents.shell_reads import a_shell_read

    assert a_shell_read(command, "") is None


def test_the_answer_s_own_words_carry_no_product_word(the_builder):
    said = str(_command(the_builder, SED_200_400).content)

    assert not BANNED.search(re.sub(r"(?m)^ *\d+  .*$", "", said).replace(ROUTES, ""))
