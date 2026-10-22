"""A corpus of real model output for the harness's readers, harvested from transcripts and replayed (plan RC).

Twelve-plus audit fixes were a reader misreading real model output - a file
plan read as its headings, tool arguments written in tag form, a JSON
specification read as one line, 32 of 58 contract lines set aside - each fixed
against the one sample that failed, with no way to know what the fix did to
every sample before it. So after a run every input one of these readers took
is kept with the reader's result, and the suite replays the whole corpus
through today's readers: a reader change that alters any earlier outcome
fails the suite until the change is accepted on purpose (`loop.sh corpus accept`).

The corpus is `DATA_DIR` state (`<DATA_DIR>/corpus/<kind>/<hash>.json`), never
committed. Samples are redacted at harvest: workspace paths and anything
shaped like a key or a token.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Iterable

_WORKSPACE = re.compile(r"/app/data/workspaces/[^/\s\"']+/workspace-[^/\s\"']+")
_SECRET_SHAPES = re.compile(
    r"sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._~+/=-]{8,}|eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9._-]{10,}"
)

#: Inputs of one kind kept from one run at most, the first ones seen.
MOST_PER_RUN = 200


def corpus_dir() -> Path:
    return Path(os.environ.get("DATA_DIR") or "data") / "corpus"


def redacted(value: Any) -> Any:
    """`value` with workspace paths and key- or token-shaped strings replaced, through lists and dicts."""
    if isinstance(value, str):
        return _SECRET_SHAPES.sub("<redacted>", _WORKSPACE.sub("<workspace>", value))
    if isinstance(value, list):
        return [redacted(v) for v in value]
    if isinstance(value, dict):
        return {k: redacted(v) for k, v in value.items()}
    return value


# --------------------------------------------------------------------- the readers, one per kind


def _structured_args(records: list[dict]) -> Iterable[dict]:
    for r in records:
        if r.get("kind") == "model_response":
            for call in r.get("tool_calls") or []:
                if isinstance(call.get("args"), dict):
                    yield call["args"]


def _contract_lines(records: list[dict]) -> Iterable[Any]:
    for args in _structured_args(records):
        for line in args.get("interface_contract") or []:
            if isinstance(line, str) and line.strip():
                yield line


def _read_contract_line(line: Any) -> Any:
    from dataclasses import asdict

    from app.acceptance.interface_contract import parse

    checks, unread = parse([line])
    return {"checks": [asdict(c) for c in checks], "unread": unread}


def _file_plans(records: list[dict]) -> Iterable[Any]:
    for args in _structured_args(records):
        plan = args.get("file_plan")
        if isinstance(plan, list) and plan:
            yield [str(entry) for entry in plan]


def _read_file_plan(plan: Any) -> Any:
    from app.graph.drafting import planned_files

    return planned_files(SimpleNamespace(file_plan=plan))


def _drafted_replies(records: list[dict]) -> Iterable[Any]:
    for r in records:
        if r.get("kind") == "model_response" and str(r.get("stage") or "") == "drafting" and r.get("text"):
            yield str(r["text"])


def _read_drafted_reply(text: Any) -> Any:
    from app.graph.drafting import the_content_in

    content = the_content_in(text)
    return {"chars": len(content), "sha": hashlib.sha1(content.encode("utf-8")).hexdigest()[:16]}


def _text_tool_calls(records: list[dict]) -> Iterable[Any]:
    offered: list[str] = []
    for r in records:
        if r.get("kind") == "model_request":
            offered = [str(t) for t in r.get("tools") or []]
        elif r.get("kind") == "model_response" and not r.get("tool_calls") and offered:
            text = str(r.get("text") or "")
            if "<tool_call" in text or '"name"' in text or "<function" in text:
                yield {"text": text, "offered": offered}


def _read_text_tool_calls(sample: Any) -> Any:
    from app.agents.text_tool_calls import tool_calls_in_text

    calls = tool_calls_in_text(sample.get("text"), set(sample.get("offered") or []))
    return [{"name": c.get("name"), "args": sorted((c.get("args") or {}).keys())} for c in calls]


#: Each kind: what to take from a transcript, and the reader whose result is kept.
KINDS: dict[str, tuple[Callable[[list[dict]], Iterable[Any]], Callable[[Any], Any]]] = {
    "contract_line": (_contract_lines, _read_contract_line),
    "file_plan": (_file_plans, _read_file_plan),
    "drafted_reply": (_drafted_replies, _read_drafted_reply),
    "text_tool_call": (_text_tool_calls, _read_text_tool_calls),
}


def _key(kind: str, sample: Any) -> str:
    return hashlib.sha1((kind + json.dumps(sample, sort_keys=True, default=str)).encode("utf-8")).hexdigest()[:16]


def _outcome(read: Callable[[Any], Any], sample: Any) -> Any:
    try:
        return json.loads(json.dumps(read(sample), default=str))
    except Exception as error:  # noqa: BLE001 - a reader that raises is an outcome too
        return {"raised": type(error).__name__}


def harvest(records: list[dict], directory: Path | None = None) -> dict[str, int]:
    """Keep each new input a reader took in this transcript, with the reader's result; how many per kind."""
    root = directory or corpus_dir()
    added: dict[str, int] = {}
    for kind, (extract, read) in KINDS.items():
        folder = root / kind
        count = 0
        for sample in list(extract(records))[:MOST_PER_RUN]:
            sample = redacted(sample)
            path = folder / f"{_key(kind, sample)}.json"
            if path.exists():
                continue
            folder.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"kind": kind, "input": sample, "result": _outcome(read, sample)}, indent=1),
                            encoding="utf-8")
            count += 1
        added[kind] = count
    return added


def replay(directory: Path | None = None, accept: bool = False) -> list[str]:
    """Every sample whose reader's result differs today, as `kind/hash`; with `accept`, today's result is kept instead."""
    root = directory or corpus_dir()
    changed = []
    for path in sorted(root.glob("*/*.json")):
        try:
            sample = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        entry = KINDS.get(str(sample.get("kind") or ""))
        if entry is None:
            continue
        now = _outcome(entry[1], sample.get("input"))
        if now != sample.get("result"):
            changed.append(f"{sample['kind']}/{path.stem}")
            if accept:
                path.write_text(json.dumps({**sample, "result": now}, indent=1), encoding="utf-8")
    return changed


def sizes(directory: Path | None = None) -> dict[str, int]:
    """Samples kept per kind (RC.3)."""
    root = directory or corpus_dir()
    return {kind: len(list((root / kind).glob("*.json"))) for kind in KINDS}


__all__ = ["KINDS", "corpus_dir", "harvest", "redacted", "replay", "sizes"]
