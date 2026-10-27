"""A throwaway named in camelCase (`tmpCheckMultiple.js`) is scratch, not the product.

Measured on one run: a fixer wrote `notes-api/tmpCheckMultiple.js` to probe an import, the revert gate read the
language service's error in it as the fix breaking the product, and the whole fix was put back. The scratch pattern
knew `tmp_check.js` and `tmp-inline-1.cjs`, not the camelCase spelling. Only `tmp` and `scratch` take it: the sweeper
deletes what matches, and `tempConverter.js` or `debugLogger.ts` can be the product's own.
"""
from __future__ import annotations

import pytest

from app.analysis.file_kinds import is_scratch


@pytest.mark.parametrize("name", ["tmpCheckMultiple.js", "tmpTest.mjs", "scratchPad.ts", "notes-api/tmpProbe.cjs"])
def test_a_camel_case_throwaway_is_scratch(name):
    assert is_scratch(name)


@pytest.mark.parametrize("name", ["tempConverter.js", "debugLogger.ts", "template.js", "tmpl.js", "tmpfile.ts", "temperature.ts"])
def test_a_product_file_that_starts_alike_is_not(name):
    assert not is_scratch(name)
