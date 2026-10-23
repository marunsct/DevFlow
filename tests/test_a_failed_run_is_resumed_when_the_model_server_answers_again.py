"""A run that failed on a stopped model server is resumed the moment the server answers.

Measured: the owner's server stopped at 07:28 JST, the run failed with a connection error, and every minute until
someone looked was model time lost. Resuming is refused while the model is unreachable, so polling is safe.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("resume_when_ready_t", ROOT / "scripts" / "loop" / "resume_when_ready.py")
watcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watcher)


class _Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


def test_it_waits_while_the_server_is_down_and_resumes_on_the_first_answer():
    clock, answers, resumed = _Clock(), iter([False, False, False, True]), []

    result = watcher.wait_and_resume("run-x", lambda: next(answers), lambda run: resumed.append(run) or True,
                                     sleep=clock.sleep, clock=clock, say=lambda text: None)

    assert result == "resumed" and resumed == ["run-x"] and clock.now == 180.0


def test_it_gives_up_after_the_time_it_was_given():
    clock = _Clock()

    result = watcher.wait_and_resume("run-x", lambda: False, lambda run: True, sleep=clock.sleep, clock=clock,
                                     every=60, give_up_after=300, say=lambda text: None)

    assert result == "gave up" and clock.now >= 300


def test_a_server_that_answers_but_refuses_the_resume_twice_ends_it_without_hammering():
    clock, tries = _Clock(), []

    result = watcher.wait_and_resume("run-x", lambda: True, lambda run: tries.append(run) and False,
                                     sleep=clock.sleep, clock=clock, say=lambda text: None)

    assert result == "refused" and len(tries) == 2


def test_the_loop_script_has_the_two_commands():
    text = (ROOT / "scripts" / "loop" / "loop.sh").read_text()
    assert "\nresume)" in text and "resume-when-ready)" in text
