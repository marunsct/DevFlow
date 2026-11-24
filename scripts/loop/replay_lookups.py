"""Score the stuck lookup on past stuck defects whose fix is known: does the note a fixer is shown name it (plan HK.4).

    PYTHONPATH=src python scripts/loop/replay_lookups.py [--through fixer|lookup] [--empty-workspace] [--only id,id]
                                                         [--pace 7]
                                                         [--data data/lookup-replay] [--cases benchmarks/lookup-replay.json]

No model and no run: each case of the replay set (`benchmarks/lookup-replay.json`) is looked up as the harness would -
by default through the stuck lookup a fixer gets (`app.graph.stuck_lookup.section`, its first trigger: a defect a fix
already left open, whose server printed the case's error), or with `--through lookup` straight through
`app.tools.lookups.look_up` - and the note is searched for any of the case's patterns for its known fix. Through the
fixer, each case is asked in the workspace its project had (the case's `workspace`: the dependency gate's record, the
stack facts and the installed package's files its error needs), laid out in an empty one first, so the lookup's
local-truth step and its library and release line fire as on a run; `--empty-workspace` asks in an empty one, as the
replay did before, to compare. The report
gives, for each case, named or not and what the note held, and the share named among the public cases (those whose
line states a cause) against the set's target (60%). It calls only the public functions, so it scores the lookup as it
stands, before and after a rebuild of it.

What it sends leaves the machine: each case's error and stack, through the one outbound gate, to the sources a lookup
asks. The lookup's own week-long cache and its daily counters live under `--data` (default `data/lookup-replay`), so a
second scoring within the week asks nothing again and the live harness's counters are not touched; `--pace` waits
between cases (GitHub's search allows 10 a minute without a token). Exits 0; reports only.
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
CASES = ROOT / "benchmarks" / "lookup-replay.json"

#: The note a fixer would be shown for one case ("" when none).
LookUp = Callable[[dict[str, Any]], str]


def load(path: Path = CASES) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def names_the_fix(case: dict[str, Any], note: str) -> str:
    """The first of the case's patterns the note holds, or "" when it names no known fix."""
    for pattern in case.get("names_the_fix") or []:
        if re.search(pattern, str(note or ""), re.I):
            return pattern
    return ""


def lay_out(case: dict[str, Any], root: str | Path) -> None:
    """The case's workspace under `root`: each of its files at its path from the workspace root - its text, or a JSON
    value written as JSON. A path that would leave the workspace is refused."""
    base = Path(root).resolve()
    for path, content in (case.get("workspace") or {}).items():
        target = (base / path).resolve()
        if base not in target.parents:
            raise ValueError(f"{case['id']}: {path} is not inside the workspace")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content if isinstance(content, str) else json.dumps(content, indent=1) + "\n",
                          encoding="utf-8")


def through_the_fixer(case: dict[str, Any], *, workspace: bool = True) -> str:
    """The note the stuck lookup gives the fixer of a defect a fix left open whose server printed the case's error,
    asked in the case's workspace (`lay_out`), or in an empty one with `workspace` false."""
    from app.acceptance.what_went_wrong import THE_SERVER_PRINTED
    from app.graph import stuck_lookup

    defect = SimpleNamespace(description="The product fails on a request it should answer.", source="replay",
                             owner="replay", actual_behavior=f"{THE_SERVER_PRINTED} {case['error']}",
                             attempts=[{"stage": "defect_fix_1_0", "outcome": "left open"}])
    stack = SimpleNamespace(language=case.get("language", ""), framework=case.get("framework", ""))
    with tempfile.TemporaryDirectory(prefix="workspace-replay-") as root:
        if workspace:
            lay_out(case, root)
        return stuck_lookup.section(root, defect, stack)


def through_the_lookup(case: dict[str, Any]) -> str:
    """The note `app.tools.lookups` gives for the case's error and stack words."""
    from app.tools import lookups

    answer = lookups.look_up(case["error"], f"{case.get('language', '')} {case.get('framework', '')}".strip())
    return lookups.as_a_section(answer)


def score(cases: list[dict[str, Any]], look_up: LookUp, *, pace: float = 0.0,
          sleep: Callable[[float], None] = time.sleep) -> list[dict[str, Any]]:
    """Each case with its note and the pattern it named ("" for none); a case whose lookup raised says why."""
    scored = []
    for at, case in enumerate(cases):
        if at and pace:
            sleep(pace)
        try:
            note, failed = str(look_up(case) or ""), ""
        except Exception as exc:  # noqa: BLE001 - one case that cannot be looked up is scored as not named
            note, failed = "", f"{type(exc).__name__}: {str(exc)[:120]}"
        scored.append({"id": case["id"], "public": bool(case.get("public", True)), "named": names_the_fix(case, note),
                       "note": note, **({"failed": failed} if failed else {})})
    return scored


def _share(named: int, of: int) -> str:
    return f"{named} of {of} ({round(100 * named / of) if of else 0}%)"


def report(scored: list[dict[str, Any]], target: float) -> list[str]:
    """The lines of the scoring: the share among the public cases against the target, then one line a case."""
    public = [s for s in scored if s["public"]]
    named = sum(1 for s in public if s["named"])
    met = bool(public) and named / len(public) >= target
    lines = [f"lookup replay: {_share(named, len(public))} public cases name the known fix; target "
             f"{round(100 * target)}% - {'met' if met else 'not met'}",
             f"  all cases: {_share(sum(1 for s in scored if s['named']), len(scored))}"]
    for s in scored:
        leads = len(re.findall(r"^- ", s["note"], re.M))
        state = (f"named ({s['named']})" if s["named"] else f"failed ({s['failed']})" if s.get("failed")
                 else f"not named ({leads} lead(s))" if s["note"] else "nothing found")
        lines.append(f"  {s['id']:<52} {state}" + ("" if s["public"] else "  [no public cause]"))
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--cases", default=str(CASES))
    parser.add_argument("--through", choices=("fixer", "lookup"), default="fixer")
    parser.add_argument("--empty-workspace", action="store_true",
                        help="ask each case in an empty workspace, as the replay did before its fixtures")
    parser.add_argument("--only", default="", help="case ids, comma-separated")
    parser.add_argument("--pace", type=float, default=7.0, help="seconds between cases")
    parser.add_argument("--data", default=str(ROOT / "data" / "lookup-replay"))
    parser.add_argument("--json", action="store_true", help="print each case's note and score as JSON as well")
    args = parser.parse_args(argv)
    os.environ["DATA_DIR"] = args.data
    os.environ.setdefault("WEB_LOOKUP_WHEN_STUCK", "on")
    os.environ.setdefault("RUN_TRANSCRIPT", "false")
    replay = load(Path(args.cases))
    only = {part.strip() for part in args.only.split(",") if part.strip()}
    cases = [case for case in replay["cases"] if not only or case["id"] in only]
    fixer = functools.partial(through_the_fixer, workspace=not args.empty_workspace)
    scored = score(cases, fixer if args.through == "fixer" else through_the_lookup, pace=args.pace)
    print("\n".join(report(scored, float(replay.get("target") or 0.6))))
    if args.json:
        print(json.dumps(scored, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "src"))
    raise SystemExit(main())
