"""The image, the sandbox, the packs' CI and release files run one Node.

The runtime copies Node from the image's front-end build stage, and the packs
write `_javascript.NODE_MAJOR` into each product's CI setup and container
definition: a product is built and tested on the Node it will run on. Node 20
reached its end of life, and the current Angular CLI refuses to start on it.

The move to Node 24 changed what `node --test` does with its arguments: a
directory is loaded as a module and fails before any test runs, so every
pack's unit command names its files by a pattern Node expands itself.
Measured in the candidate image: the three packs whose unit command named
`tests/` failed their smoke tests that way, and passed once it named a pattern.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.stacks.packs import ALL_PACKS
from app.stacks.packs import _javascript as js

ROOT = Path(__file__).resolve().parent.parent


def test_the_image_runs_the_node_the_packs_name() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert re.search(rf"^FROM node:{js.NODE_MAJOR}-slim AS frontend-builder$", dockerfile, re.M)
    runtime = dockerfile[dockerfile.index("AS runtime"):]
    assert "COPY --from=frontend-builder /usr/local/bin/node /usr/local/bin/node" in runtime


def test_the_sandbox_s_own_node_image_is_the_same_release() -> None:
    from app.tools.sandbox import _image_for

    assert _image_for("node") == f"node:{js.NODE_MAJOR}-slim"


def test_no_pack_gives_node_test_a_directory(tmp_path: Path) -> None:
    from app.analysis.integration_checks import (
        _directories_node_will_not_search,
        _paths_named_after_the_test_flag,
    )

    (tmp_path / "tests").mkdir()
    for pack in ALL_PACKS:
        for name, script in (pack.kept_scripts or {}).items():
            if "node --test" not in script and "--test " not in script:
                continue
            named = _paths_named_after_the_test_flag(script)
            assert named, f"{pack.name} `{name}` names no test files"
            assert _directories_node_will_not_search(named, tmp_path) == [], (
                f"{pack.name} `{name}` gives node --test a directory: {script}"
            )
