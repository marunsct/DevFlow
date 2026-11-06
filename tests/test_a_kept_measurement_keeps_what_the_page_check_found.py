"""A measurement kept because the product did not change keeps everything the page check found.

Measured on one run: at a phone's width the page scrolled 10px sideways, a defect was raised, and when the suite's
last run was kept as it stood ("the product is as the suite last measured it") the rebuilt result dropped the
page's layout - the overflow read 0, the defect closed as "the page check no longer finds it", and the run was
released with the page still scrolling sideways (a hidden test failed: a false acceptance).
"""
import inspect

from app.acceptance import measured_once, suite


def test_the_rebuilt_result_carries_every_page_finding_the_saved_run_has():
    source = inspect.getsource(measured_once.saved_run_if_unchanged)
    saved_fields = [name for name in ("phone_overflow", "overlaps", "small_targets", "accessibility",
                                      "runtime_problems", "shows")]
    for name in saved_fields:
        assert f"{name}=" in source, name


def test_each_field_the_result_saves_is_one_the_kept_run_restores():
    fields = set(suite.AcceptanceResult.__dataclass_fields__)
    source = inspect.getsource(measured_once.saved_run_if_unchanged)
    page = {"runtime_problems", "shows", "phone_overflow", "overlaps", "small_targets", "accessibility"}
    assert page <= fields
    assert all(f"{name}=" in source for name in page)
