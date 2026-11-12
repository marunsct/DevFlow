"""The release never removes a module Python runs by itself, and undoes a removal that broke the product.

Measured on one run: the release removed an untouched `__main__.py` as a template "nothing loads"; `python -m` then
failed 19 of 19 locked tests, and a product that had passed them all shipped failing every hidden test.
"""
from __future__ import annotations

import inspect

from app.graph import delivery
from app.stacks import scaffold


def test_main_and_init_are_loaded_by_python_itself():
    assert scaffold._the_ways_a_file_is_named("wordstats/__main__.py") == []
    assert scaffold._the_ways_a_file_is_named("wordstats/__init__.py") == []
    assert scaffold._the_ways_a_file_is_named("wordstats/cli.py")


def test_a_removal_that_broke_the_suite_is_put_back_and_measured_again():
    source = inspect.getsource(delivery._measured_again_if_it_changed)
    assert "put_back_templates(root, list(left_out))" in source and "again = suite.run(root)" in source
    assert "_measured_again_if_it_changed(root, left_out)" in inspect.getsource(delivery)
