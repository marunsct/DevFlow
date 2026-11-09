"""A command line of the contract that says what it prints is read, and what it printed is checked at release.

Measured on a library's run: all seven contract lines were `AC-n command python -c "..." -> stdout 'x' exit 0`, a
form the contract did not have, so none was checked and the README, which lists the contract's commands as examples,
said nowhere how to use the library. Lines saying it in words (`-> prints JSON counts and exits 0`) are read for
their exit code, the words kept as the line's note.
"""
from __future__ import annotations

from app.acceptance import interface_contract

LINE = """AC-6 command python -c "from textkit import slugify; print(slugify('Hello, World!'))" -> stdout 'hello-world' exit 0"""


def _one(line: str):
    checks, unreadable = interface_contract.parse([line])
    assert unreadable == [], unreadable
    return checks[0]


def test_the_printed_text_and_the_exit_code_are_read():
    check = _one(LINE)
    assert check.kind == "command" and check.exit_code == 0 and check.stdout == "hello-world"
    assert check.command == """python -c "from textkit import slugify; print(slugify('Hello, World!'))\""""


def test_words_before_the_exit_code_are_its_note():
    check = _one("AC-3 command wordstats --json sample.txt -> prints JSON counts and exits 0")
    assert (check.command, check.exit_code, check.stdout, check.note) == ("wordstats --json sample.txt", 0, "", "prints JSON counts")
    check = _one("AC-4 command wordstats missing.txt -> writes an error to stderr and exit 2")
    assert check.exit_code == 2


def test_the_plain_form_is_read_as_before():
    check = _one("AC-1 command textkit --help -> exit 0")
    assert (check.command, check.exit_code, check.stdout) == ("textkit --help", 0, "")


def _release(check, printed: str, code: int = 0):
    failed: list[str] = []
    unchecked: list[str] = []
    interface_contract._run_each_command(
        [check], "proj", lambda argv, category, where: {"returncode": code, "stdout": printed}, failed, unchecked)
    return failed, unchecked


def test_the_release_checks_what_it_printed():
    check = _one(LINE)
    assert _release(check, "hello-world\n") == ([], [])
    failed, _ = _release(check, "Hello-World\n")
    assert failed and "it printed 'Hello-World'" in failed[0]
    failed, _ = _release(check, "hello-world\n", code=1)
    assert failed and "it exited 1" in failed[0]


def test_a_saved_contract_without_the_field_still_loads():
    from dataclasses import asdict

    item = asdict(_one("AC-1 command textkit --help -> exit 0"))
    item.pop("stdout")
    assert interface_contract.Check(**item).stdout == ""


# Measured on one release (LF.769): `stdout "words: <n>\nlines: <n>\ncharacters: <n>"` was failed against a product
# printing `words: 9`, and four more lines whose output was described, not given, were reported as broken contracts.
def test_a_placeholder_stands_for_any_value():
    printed = interface_contract._it_printed
    assert printed("words: 9\nlines: 2\ncharacters: 40\n", r"words: <n>\nlines: <n>\ncharacters: <n>")
    assert not printed("words: 9\nlines: 2\n", r"words: <n>\nlines: <n>\ncharacters: <n>")
    assert printed("the 3\ncat 2\n", r"<word> <count>\n...")


def test_output_described_not_given_is_unchecked_not_broken():
    check = _one(r'AC-3 command wordstats sample.txt --json -> stdout "{\"words\": n, \"lines\": n}" exit 0')
    failed, unchecked = _release(check, '{"words": 9, "lines": 2}\n')
    assert failed == [] and unchecked and "described, not given" in unchecked[0]


def test_literal_text_that_differs_still_fails():
    failed, unchecked = _release(_one(LINE), "Hello-World\n")
    assert failed and unchecked == []


# LF.773, measured on one release: `--top N <file>` ran with those words and was reported as a broken contract.
def test_a_command_naming_a_placeholder_is_unchecked_not_run():
    ran = []
    failed, unchecked = [], []
    for line in ("AC-8 command python -m wordstats --top N <file> -> exit 0",
                 "AC-9 command python -m wordstats --json sample.txt ... -> exit 0"):
        interface_contract._run_each_command(
            [_one(line)], "proj", lambda argv, c, w: ran.append(argv) or {"returncode": 2}, failed, unchecked)
    assert ran == [] and failed == []
    assert len(unchecked) == 2 and all("names a placeholder" in u for u in unchecked)


def test_a_command_with_real_values_still_runs():
    ran = []
    interface_contract._run_each_command(
        [_one("AC-1 command python -m wordstats --top 3 sample.txt -> exit 0")], "proj",
        lambda argv, c, w: ran.append(argv) or {"returncode": 0}, [], [])
    assert ran == [["python", "-m", "wordstats", "--top", "3", "sample.txt"]]
