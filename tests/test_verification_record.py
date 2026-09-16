"""The verification record accepts the shape this harness handed the model.

`run_terminal_command` returns {"stdout", "stderr", "returncode"}. A model
asked for "the command you ran with its exit code" pastes that record back, and
`extra="forbid"` with a required `exit_code` then rejected every key of it.

run-3ddd443f died of it. `specialist_testing_5` was refused three times over
verification.0.exit_code, .exitCode, .returncode, .stdout, .category and
.working_directory. Because the answer never validated, `settled_answer` could
not recognise one and end the stage, so the model wrote the same answer five
times and the run-level repeat guard stopped the run at 758 events.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.specialists import VerificationRun


def test_the_canonical_shape_still_works() -> None:
    record = VerificationRun.model_validate({"command": ["node", "--test"], "exit_code": 0})

    assert record.exit_code == 0


@pytest.mark.parametrize("key", ["returncode", "exitCode", "return_code"])
def test_the_exit_code_is_accepted_under_the_names_the_tool_uses(key: str) -> None:
    """`returncode` is what the sandbox returns; the others are what a model
    writes when it is paraphrasing rather than copying."""
    record = VerificationRun.model_validate({"command": ["node"], key: 1})

    assert record.exit_code == 1


def test_a_command_written_as_a_string_is_read_as_argv() -> None:
    """The tool takes argv, but a model writes the command the way a person
    would. Turning that into a list keeps the record; refusing loses the answer."""
    record = VerificationRun.model_validate(
        {"command": "node --test app.mjs", "exit_code": 0}
    )

    assert record.command == ["node", "--test", "app.mjs"]


def test_the_whole_tool_result_can_be_pasted_back() -> None:
    """Which is what the model actually does, and what used to fail."""
    record = VerificationRun.model_validate(
        {
            "command": ["node", "--test"],
            "returncode": 1,
            "stdout": "TAP version 13",
            "stderr": "",
            "category": "test",
            "working_directory": "simple-to-do-list-app",
        }
    )

    assert record.exit_code == 1
    assert record.command == ["node", "--test"]


def test_a_record_with_no_exit_code_is_still_refused() -> None:
    """Tolerating the surrounding noise must not tolerate a missing claim: an
    entry with no exit code is not evidence that anything ran."""
    with pytest.raises(ValidationError):
        VerificationRun.model_validate({"command": ["node", "--test"]})


def test_a_record_with_no_command_is_still_refused() -> None:
    with pytest.raises(ValidationError):
        VerificationRun.model_validate({"exit_code": 0})


def test_a_whole_specialist_answer_validates_with_the_tool_s_shape() -> None:
    """The end the stage could not reach: an answer that `settled_answer` can
    recognise, so the stage can finish instead of writing it again."""
    from app.agents.specialists import SpecialistOutput

    answer = SpecialistOutput.model_validate(
        {
            "changed_files": ["app.js"],
            "decisions": ["wrote the thing"],
            "tests": ["app.test.mjs"],
            "verification": [
                {"command": ["node", "--test"], "returncode": 0, "stdout": "ok"}
            ],
        }
    )

    assert answer.verification[0].exit_code == 0
