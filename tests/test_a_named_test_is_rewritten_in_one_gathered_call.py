"""Behind `NAMED_TEST_REWRITE` (off until measured), a reopened suite has its named tests rewritten by one gathered call each.

Plan item 10 part 2. Reopening the locked suite for the tests the checks named restarted QA's agent loop on the whole
suite, and a repair after the lock took 5-10 minutes and 1.4-2.2M tokens to change one or two tests whose fault had
already been named. The harness holds the test's text, the failure message, the checks' finding and the criterion: it
asks for the replacement in one call, places it by title, repairs the tests that fail with the same message in the same
call, and goes straight to the review. A test it cannot place leaves the repair to the agent loop.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from app.acceptance import suite
from app.graph import acceptance_nodes, rewritten_tests
from app.stacks import contract, pack_named

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

HEAD = "import { test, expect } from '@playwright/test';\n\nconst base = 'http://localhost:3000';\n\n"
LISTS = "test('[AC-2] lists', async ({ request }) => {\n  expect(1).toBe(1);\n  expect(mine.length).toBe(2);\n});\n\n"
FETCHES = "test('[AC-3] fetches', async ({ request }) => {\n  expect(2).toBe(2);\n  expect(mine.id).toBe(1);\n});\n\n"
REMOVES = "test('[AC-4] removes', async ({ request }) => {\n  expect(3).toBe(3);\n});\n"
MESSAGE = "ReferenceError: mine is not defined"
FINDING = (f"`[AC-2] lists` fails because of an error in the test's own code, not because the product is unbuilt: "
           f"{MESSAGE}. Fix the test so that it can pass once the product works.")


def _fixed(title, before, after):
    return f"### {title}\n```js\n{before.replace('mine', after).rstrip()}\n```\n"


class _Model:
    def __init__(self, reply):
        self.reply, self.asked = reply, []

    def invoke(self, messages, **_):
        self.asked.append(messages)
        if isinstance(self.reply, Exception):
            raise self.reply
        return SimpleNamespace(content=self.reply)


def _suite(tmp_path):
    contract.write(tmp_path, pack_named("node-hono-native-api"), "notes", "Notes")
    folder = tmp_path / "notes" / "acceptance"
    folder.mkdir(parents=True, exist_ok=True)
    spec = folder / "api.spec.js"
    spec.write_text(HEAD + LISTS + FETCHES + REMOVES)
    suite.save_criteria(tmp_path, [SimpleNamespace(id="AC-2", text="The list shows every note", source="brief"),
                                   SimpleNamespace(id="AC-3", text="A note is fetched by id", source="brief")])
    suite.lock(tmp_path)
    suite.unlock(tmp_path)
    suite.repairing(tmp_path, ["[AC-2] lists"])
    saved = {"criteria": {
        "AC-2": {"id": "AC-2", "text": "The list shows every note", "status": "failed",
                 "tests": [{"name": "[AC-2] lists", "outcome": "failed", "message": MESSAGE + "\n  at api.spec.js:6"}]},
        "AC-3": {"id": "AC-3", "text": "A note is fetched by id", "status": "failed",
                 "tests": [{"name": "[AC-3] fetches", "outcome": "failed", "message": MESSAGE + "\n  at api.spec.js:12"}]},
        "AC-4": {"id": "AC-4", "text": "A note is removed", "status": "failed",
                 "tests": [{"name": "[AC-4] removes", "outcome": "failed", "message": "expect(received).toBe(expected)"}]},
    }}
    (tmp_path / suite.RESULT_FILE).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / suite.RESULT_FILE).write_text(__import__("json").dumps(saved))
    return spec


def _which(finding):
    return acceptance_nodes._which_test(finding)


def test_the_named_test_and_the_one_failing_the_same_way_are_rewritten_in_one_call(tmp_path):
    spec = _suite(tmp_path)
    model = _Model(_fixed("[AC-2] lists", LISTS, "ours") + _fixed("[AC-3] fetches", FETCHES, "ours"))

    done = rewritten_tests.repair(tmp_path, [FINDING], model, which_test=_which)

    assert done == {"files": ["notes/acceptance/api.spec.js"], "tests": ["[AC-2] lists", "[AC-3] fetches"], "calls": 1}
    assert len(model.asked) == 1
    text = spec.read_text()
    assert text == (HEAD + LISTS.replace("mine", "ours") + FETCHES.replace("mine", "ours") + REMOVES)
    assert suite.is_locked(tmp_path) is False
    # The test repaired for sharing the fault is under repair too, so the suite is locked again on the checks alone.
    assert suite.only_the_repaired_tests_changed(tmp_path) is True


def test_the_call_is_given_what_the_harness_gathered(tmp_path):
    _suite(tmp_path)
    model = _Model(_fixed("[AC-2] lists", LISTS, "ours"))

    rewritten_tests.repair(tmp_path, [FINDING], model, which_test=_which, reference="--- The API ---\nGET /notes",
                           reason="the test names a variable it never made")
    prompt = model.asked[0][1].content

    for gathered in ("expect(mine.length).toBe(2);", "ReferenceError: mine is not defined", FINDING,
                     "AC-2: The list shows every note", "`notes/acceptance/api.spec.js`", "--- The API ---",
                     "the test names a variable it never made", "const base = 'http://localhost:3000';",
                     "### [AC-3] fetches", "the very same fault"):
        assert gathered in prompt, gathered
    assert "[AC-4] removes" not in prompt, "a test that fails for another reason is not offered"
    assert not BANNED.search(prompt) and not BANNED.search(rewritten_tests.SYSTEM)


def test_a_test_that_cannot_be_placed_leaves_the_repair_to_the_agent_loop(tmp_path):
    spec = _suite(tmp_path)
    model = _Model("never asked")

    assert rewritten_tests.repair(tmp_path, ["`[AC-9] no such test` cannot pass"], model, which_test=_which) is None
    assert model.asked == [] and spec.read_text() == HEAD + LISTS + FETCHES + REMOVES


@pytest.mark.parametrize("reply", [
    "I could not tell what to change.",
    "### [AC-2] lists\n```js\ntest('[AC-2] lists', async ({ request }) => {\n  await request.get('/notes');\n});\n```\n",
    "### [AC-2] lists\n```js\ntest('[AC-2] renamed', async ({ request }) => {\n  expect(1).toBe(1);\n  expect(2).toBe(2);\n});\n```\n",
])
def test_a_reply_that_does_not_keep_the_test_leaves_every_file_as_it_was(tmp_path, reply):
    spec = _suite(tmp_path)

    assert rewritten_tests.repair(tmp_path, [FINDING], _Model(reply), which_test=_which) is None
    assert spec.read_text() == HEAD + LISTS + FETCHES + REMOVES


def test_a_failed_call_leaves_the_repair_to_the_agent_loop(tmp_path):
    spec = _suite(tmp_path)

    assert rewritten_tests.repair(tmp_path, [FINDING], _Model(RuntimeError("down")), which_test=_which) is None
    assert spec.read_text() == HEAD + LISTS + FETCHES + REMOVES


def test_a_sibling_the_reply_leaves_out_is_left_as_it_was(tmp_path):
    spec = _suite(tmp_path)

    done = rewritten_tests.repair(tmp_path, [FINDING], _Model(_fixed("[AC-2] lists", LISTS, "ours")), which_test=_which)

    assert done["tests"] == ["[AC-2] lists"]
    assert spec.read_text() == HEAD + LISTS.replace("mine", "ours") + FETCHES + REMOVES


def test_replies_are_read_by_title():
    reply = "Here:\n### [AC-2] lists\n```js\nline one\nline two\n```\nand\n### `other`\n```\nx\n```\n"
    assert rewritten_tests.blocks_in(reply) == {"[AC-2] lists": "line one\nline two\n", "other": "x\n"}


# --- the reopening -------------------------------------------------------------------------------------------

def _state(tmp_path):
    return {"repository": SimpleNamespace(root_path=str(tmp_path)), "suite_repairs": 0}


def test_with_the_switch_on_a_reopened_suite_goes_straight_to_the_review(tmp_path, monkeypatch):
    monkeypatch.setattr(acceptance_nodes, "_decide", lambda *a, **k: None)
    monkeypatch.setenv("NAMED_TEST_REWRITE", "on")
    spec = _suite(tmp_path)
    model = _Model(_fixed("[AC-2] lists", LISTS, "ours"))

    reopened = acceptance_nodes.reopen_the_suite_for(_state(tmp_path), [FINDING], model=model)

    assert reopened["stage"] == "acceptance_review" and reopened["acceptance_round"] == 1
    assert reopened["acceptance_feedback"] == [] and reopened["acceptance_return_to"] == "test_and_triage"
    assert reopened["suite_repairs"] == 1 and reopened["suite_repaired_tests"] == ["[AC-2] lists"]
    assert "ours.length" in spec.read_text() and len(model.asked) == 1
    # And it is the cheap lock's: the checks that let a repair be locked again read it as changing only its own tests.
    assert suite.only_the_repaired_tests_changed(tmp_path) is True


def test_with_the_switch_on_a_test_it_cannot_place_still_restarts_the_author(tmp_path, monkeypatch):
    monkeypatch.setattr(acceptance_nodes, "_decide", lambda *a, **k: None)
    monkeypatch.setenv("NAMED_TEST_REWRITE", "on")
    _suite(tmp_path)

    reopened = acceptance_nodes.reopen_the_suite_for(
        _state(tmp_path), [FINDING], model=_Model("### [AC-2] lists\nno block here"))

    assert reopened["stage"] == "acceptance_author" and reopened["acceptance_round"] == 0
    assert reopened["acceptance_feedback"][0] == FINDING and reopened["acceptance_feedback"][-1] == acceptance_nodes.REPAIR_RULE


def test_with_the_switch_off_the_author_restarts_and_the_model_is_not_asked(tmp_path, monkeypatch):
    monkeypatch.setattr(acceptance_nodes, "_decide", lambda *a, **k: None)
    monkeypatch.setenv("NAMED_TEST_REWRITE", "off")
    spec = _suite(tmp_path)
    model = _Model(_fixed("[AC-2] lists", LISTS, "ours"))

    reopened = acceptance_nodes.reopen_the_suite_for(_state(tmp_path), [FINDING], model=model)

    assert reopened["stage"] == "acceptance_author" and reopened["acceptance_round"] == 0
    assert model.asked == [] and spec.read_text() == HEAD + LISTS + FETCHES + REMOVES


def test_the_dispute_and_the_round_hand_the_judgement_model_to_the_reopening():
    import inspect

    from app.graph import workflow

    source = inspect.getsource(workflow)
    assert "reopen_the_suite_for(state, cannot_pass, model=judgement_model)" in source
    assert "reclassifying=True, model=judgement_model," in source
