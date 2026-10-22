"""How strong is a run's own locked acceptance suite? Break the product and see.

Runs inside the worker (it has the toolchains and the harness importable):

    python mutate.py <workspace> <result.json> [mutants]

A locked suite that passes says the product does what the tests check; it does
not say the tests check much. One run's suite passed 8 of 9 while the product
scored 2 of 10 on the hidden tests. This copies the workspace, makes one small
change to the product's source at a time - a comparison turned round, a
condition flipped, a constant changed - and runs the suite exactly the way the
harness does (`app.acceptance.suite.run`). A change the suite does not notice
is a behaviour no test holds the product to.

Every change is textual and works on any language whose source uses these
operators; a site inside a comment or a string literal is left alone. A change
can also be equivalent (behaves the same) - those survive by right, so the
score is a floor on suite strength, never a ceiling. A change that makes every
test fail usually broke the program outright; it counts as caught, and is
marked so the reader can discount it.

The result: the baseline (tests that pass unmutated), each change with the
tests it turned red, and the score (changes caught / changes tried).
"""

from __future__ import annotations

import json
import re
import shutil
import sys
import time
from pathlib import Path

# The changes and where they apply are the harness's own: `app.acceptance.mutation`
# runs the same probe at release, over fewer changes.
from app.acceptance.mutation import (  # noqa: E402 - run inside the worker, where `app` imports
    OPERATORS,
    apply,
    passing as _passing,
    source_files,
    sites,
    spread,
)


def mutate(workspace: Path, out: Path, count: int = 12) -> dict:
    from app.acceptance import suite
    from app.stacks import contract

    copy = Path(f"/tmp/mutate-work/{workspace.name}-{int(time.time())}")
    shutil.copytree(workspace, copy, symlinks=True)
    found = contract.the_pack(copy)
    project_name = str(found[1].get("project")) if found else (suite.location(copy) or ("",))[0]
    project = copy / project_name if project_name else copy

    baseline = suite.run(copy, save=False)
    held = _passing(baseline)
    result: dict = {"workspace": str(workspace), "baseline_passing": sorted(held), "mutants": []}
    if not held:
        result["problem"] = "no test passes on the unchanged product, so no change can be caught"
        out.write_text(json.dumps(result, indent=2))
        return result

    kept = set(found[0].kept_files) if found else set()
    for site in spread(sites(source_files(project, kept), project), count):
        original = apply(project, site)
        try:
            after = suite.run(copy, save=False)
        finally:
            (project / site["file"]).write_bytes(original)
        turned_red = sorted(held - _passing(after))
        result["mutants"].append({
            **site,
            "caught": bool(turned_red),
            "everything_failed": bool(turned_red) and len(turned_red) == len(held),
            "turned_red": turned_red,
        })
    tried = len(result["mutants"])
    caught = sum(m["caught"] for m in result["mutants"])
    specific = sum(m["caught"] and not m["everything_failed"] for m in result["mutants"])
    result.update({
        "tried": tried,
        "caught": caught,
        "score": round(caught / tried, 3) if tried else None,
        "caught_by_a_specific_test": specific,
    })
    out.write_text(json.dumps(result, indent=2))
    shutil.rmtree(copy, ignore_errors=True)
    return result


if __name__ == "__main__":
    workspace, out = Path(sys.argv[1]), Path(sys.argv[2])
    count = int(sys.argv[3]) if len(sys.argv) > 3 else 12
    result = mutate(workspace, out, count)
    if "problem" in result:
        print(result["problem"])
        raise SystemExit(1)
    print(
        f"locked suite caught {result['caught']} of {result['tried']} changes "
        f"(score {result['score']}); {result['caught_by_a_specific_test']} by a specific test "
        "rather than by everything failing"
    )
    for m in result["mutants"]:
        if not m["caught"]:
            print(f"  SURVIVED {m['file']}:{m['line']}  {m['original']} -> {m['replacement']}")
