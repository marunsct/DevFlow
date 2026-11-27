"""The diagnosis's probes are real stage requests from benchmark runs, and never hold a run id, a host path or a hidden
test (DX.8; owner 2026-11-27: only benchmark runs' transcripts become probes, never the owner's own runs, never
hidden tests).
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path

from app.models import replay_set, stage_kinds

ROOT = Path(__file__).resolve().parents[1]
CAPTURED = ROOT / "tests" / "captured" / "transcript-a-reading-stage-whose-second-request-carries-three-messages.jsonl"


def _records() -> list[dict]:
    return [json.loads(line) for line in CAPTURED.read_text(encoding="utf-8").splitlines()]


def test_the_shipped_set_holds_every_kind_from_several_families():
    items = replay_set.load()

    by_kind = {kind: {item.family for item in items if item.kind == kind} for kind in stage_kinds.KINDS}
    assert all(len(families) >= 2 for families in by_kind.values()), by_kind
    assert len({item.family for item in items}) >= 3


def test_no_shipped_item_holds_a_run_id_a_host_path_or_a_hidden_test_line():
    hidden = replay_set.hidden_lines(ROOT / "benchmarks")

    assert hidden, "the benchmarks' hidden tests were not read"
    assert {item.id: replay_set.leaks(item, hidden) for item in replay_set.load()} == \
        {item.id: [] for item in replay_set.load()}


def test_every_shipped_item_is_a_request_whose_tools_and_answer_the_harness_still_has():
    for item in replay_set.load():
        names = [tool["function"]["name"] for tool in item.tools]
        assert item.messages and names
        assert not item.answer_tool or item.answer_tool in names
        module, _, name = item.answer.partition(":")
        assert not item.answer or hasattr(importlib.import_module(module), name), item.answer


def test_a_request_is_rebuilt_whole_from_what_it_carried_and_scrubbed():
    """The second request of the captured stage records 3 new messages and carries 3: the probe holds all 6."""
    candidates = replay_set.candidates(_records(), "a-family")
    second = candidates[-1][1]

    assert len(second.messages) == 6
    assert second.kind == "reading" and second.answer_tool == "StackSelectorOutput"
    assert second.messages[3]["role"] == "assistant" and second.messages[3]["tool_calls"]
    assert second.messages[4]["role"] == "tool" and second.messages[4]["tool_call_id"]
    assert "run-deadbeef" not in json.dumps(second.messages)


def test_a_request_holding_a_hidden_test_line_is_refused():
    item = replay_set.candidates(_records(), "a-family")[0][1]
    line = next(text for message in item.messages for text in str(message["content"]).splitlines()
                if len(text.strip()) > 40).strip()

    assert replay_set.leaks(item, [json.dumps(line)[1:-1]])
    assert not replay_set.leaks(item, ["a line that is in no request at all, long enough"])


def test_only_runs_scored_against_their_family_s_own_brief_are_read(tmp_path):
    benchmarks = tmp_path / "benchmarks"
    (benchmarks / "a-family").mkdir(parents=True)
    (benchmarks / "a-family" / "brief.md").write_text("A brief.\n")
    bench = tmp_path / "bench"
    bench.mkdir()
    (bench / "run-a.json").write_text(json.dumps({"benchmark": "a-family", "brief_mismatch": False, "score": 1.0}))
    (bench / "run-b.json").write_text(json.dumps({"benchmark": "a-family", "brief_mismatch": True, "score": 1.0}))
    (bench / "run-c.json").write_text(json.dumps({"benchmark": "", "brief_mismatch": False, "score": 1.0}))
    (bench / "run-d.json").write_text(json.dumps({"benchmark": "a-family", "brief_mismatch": False, "score": 0.4}))

    assert replay_set.benchmark_runs(bench, benchmarks) == {"run-a": "a-family"}


def test_a_reply_is_scored_by_what_it_does_not_by_matching_the_recorded_one():
    item = replay_set.candidates(_records(), "a-family")[-1][1]

    def reply(name, arguments, finish="tool_calls"):
        return {"tool_calls": [{"function": {"name": name, "arguments": json.dumps(arguments)}}]}, finish

    assert replay_set.score(item, *reply("read_file", {"file_path": "docs/brief.md"}))[0]
    assert not replay_set.score(item, *reply("read_file", {}))[0]
    assert not replay_set.score(item, *reply("edit_file", {"path": "x"}))[0]
    assert not replay_set.score(item, *reply("StackSelectorOutput", {"technology_stack": "JavaScript"}))[0]
    assert not replay_set.score(item, {"content": "I would read the brief."}, "stop")[0]
    assert not replay_set.score(item, *reply("read_file", {"file_path": "a"}, finish="length"))[0]


def test_the_kind_of_a_call_is_read_from_its_tools_and_conversation():
    assert stage_kinds.kind(["read_file", "AnAnswer"], holds_tool_results=True) == "reading"
    assert stage_kinds.kind(["read_file", "write_artifact"], holds_tool_results=False) == "opening"
    assert stage_kinds.kind(["read_file", "run_terminal_command"], holds_tool_results=True) == "step"
    assert stage_kinds.kind(["write_artifact"], holds_tool_results=True, answer_only=True) == "opening"
