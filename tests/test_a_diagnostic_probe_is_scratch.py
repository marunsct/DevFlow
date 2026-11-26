"""A fixer's diagnostic probe named `diag*` is a throwaway, not the product (LF.1529).

Measured on a page product: three fixers left `diag.js`, `diag.mjs`, `diag2.mjs` and `diag-filter.js` at the project
root; the cross-file check raised `diag.js`'s `require` under `"type": "module"` as the product's defect, and it took
a fix round.
"""
from __future__ import annotations

from app.analysis.file_kinds import is_scratch


def test_the_probes_the_fixers_left_are_scratch() -> None:
    for name in ("simple-to-do-list-app/diag.js", "simple-to-do-list-app/diag.mjs",
                 "simple-to-do-list-app/diag2.mjs", "simple-to-do-list-app/diag-filter.js"):
        assert is_scratch(name), name


def test_a_product_file_that_starts_so_is_not() -> None:
    for name in ("src/diagram.js", "src/diagnostics.ts", "app/diagnosis.py"):
        assert not is_scratch(name), name
