"""A `require` in a file Node loads as an ES module is reported with its exact correction.

Measured on one run: the check told QA to "use `import` (`import { test, expect } from '@playwright/test';`)" about a
`require('./service.cjs')` inside one test, in a file whose top already imported that name from that module; QA kept
the line through three review rounds and the suite was locked with it.
"""
from __future__ import annotations

import json
import re

from app.stacks.packs import _javascript as js

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)


def _found(tmp_path, code):
    (tmp_path / "package.json").write_text(json.dumps({"type": "module"}))
    return js.module_system_mismatch(tmp_path, tmp_path / "a.spec.js", code)


def test_a_require_of_a_name_already_imported_is_a_line_to_delete(tmp_path):
    code = ("import { test, expect } from '@playwright/test';\n"
            "import { startService } from './service.cjs';\n"
            "test('[AC-1] restarts', async () => {\n"
            "  const { startService } = require('./service.cjs');\n"
            "  await startService();\n"
            "});\n")
    [(line, why)] = _found(tmp_path, code)
    assert line == 4
    assert "Delete the line" in why and "line 2 already imports `startService`" in why
    assert "test around it fails" in why and "@playwright/test" not in why
    assert not BANNED.search(why)


def test_a_require_of_a_name_not_imported_is_the_import_to_write(tmp_path):
    code = "const { readFileSync } = require('node:fs');\nimport { test } from '@playwright/test';\n"
    [(line, why)] = _found(tmp_path, code)
    assert line == 1 and "throws before its tests run" in why
    assert "`import { readFileSync } from 'node:fs';` at the top" in why


def test_a_require_it_cannot_read_still_says_to_import(tmp_path):
    [(_, why)] = _found(tmp_path, "import { test } from '@playwright/test';\nrequire('./setup.cjs');\n")
    assert "`import` at the top of the file" in why
