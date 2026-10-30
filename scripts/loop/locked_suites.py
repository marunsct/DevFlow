"""The static suite checks replayed over real locked suites, against what they found when last accepted.

Measured on one run: a check built that morning (`tests_that_filter_for_what_they_never_made`) had been tried on 40
locked suites, none of which sent a value through a helper, and its first false positive reopened a right suite in a
live run. The corpus is kept in `tests/fixtures/locked_suites/` - the final locked suites of runs that reached a full
hidden score - and `tests/test_the_suite_checks_replay_unchanged_on_real_suites.py` fails when any check's findings on
any of them change. Review the change, then accept it:

    .venv/bin/python scripts/loop/locked_suites.py accept
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tests" / "fixtures" / "locked_suites"
BASELINE = CORPUS / "baseline.json"

#: The checks that read a suite's files alone. The two that need the interface contract are left out: these suites
#: are kept without theirs.
CHECKS = (
    "assertions_that_do_not_exist", "requests_with_a_fetch_body", "responses_read_without_the_call",
    "contexts_made_from_the_fixture", "fetch_calls_written_like_the_fixture", "reads_of_what_the_test_does_not_have",
    "tests_that_restart_on_data_they_never_wrote", "tests_that_filter_for_what_they_never_made",
    "tests_with_module_system_mismatch", "tests_with_unawaited_async_helpers", "tests_that_assert_an_unstated_order",
    "tests_that_expect_what_they_never_gave", "tests_that_never_open_the_page", "locators_that_do_not_exist",
    "tests_that_sign_in_as_nobody",
)


def findings() -> dict[str, dict[str, list[str]]]:
    """{suite: {check: [each finding's first 200 characters]}} for every suite of the corpus, checks that found nothing left out."""
    from app.acceptance import suite
    from app.stacks import contract, pack_named

    found: dict[str, dict[str, list[str]]] = {}
    for kept in sorted(path for path in CORPUS.iterdir() if path.is_dir()):
        with tempfile.TemporaryDirectory() as workspace:
            root = Path(workspace)
            contract.write(root, pack_named("node-hono-native-api"), "notes", "Notes")
            shutil.copytree(kept / "acceptance", root / "notes" / "acceptance")
            each = {name: [str(item)[:200] for item in getattr(suite, name)(root)] for name in CHECKS}
        found[kept.name] = {name: items for name, items in each.items() if items}
    return found


def changes() -> list[str]:
    """Each suite and check whose findings differ from the accepted baseline."""
    accepted = json.loads(BASELINE.read_text()) if BASELINE.is_file() else {}
    now = findings()
    return sorted(
        f"{name}: {check}: was {len(accepted.get(name, {}).get(check, []))}, now {len(now.get(name, {}).get(check, []))}"
        for name in sorted(set(accepted) | set(now))
        for check in sorted(set(accepted.get(name, {})) | set(now.get(name, {})))
        if accepted.get(name, {}).get(check, []) != now.get(name, {}).get(check, [])
    )


if __name__ == "__main__":
    if sys.argv[1:] == ["accept"]:
        BASELINE.write_text(json.dumps(findings(), indent=1, sort_keys=True))
        print(f"accepted {BASELINE.relative_to(ROOT)}")
    else:
        print("\n".join(changes()) or "unchanged")
