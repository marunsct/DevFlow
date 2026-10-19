"""A start that failed inside a dependency names the product's own frame, and the warning is not the fix's target.

Measured live: a service stopped at start-up on "unable to open database file".
The defect's excerpt kept only frames inside the installed packages, and the
one product file the output named was a deprecation warning's - which the fast
fix then rewrote, while the cause sat in the module that opens the database:
it ignored `DATA_DIR` for a relative `data/app.db`.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

from app.acceptance.suite import the_product_did_not_start
from app.graph.rewritten_fixes import files_to_fix

BANNED = re.compile(r"\b(?:task|tasks|to-do|todo|button|click|checkbox)\b", re.I)

DEPENDENCY_FRAMES = "".join(
    f'[WebServer]   File "shop/.venv/lib/python3.12/site-packages/sqlalchemy/engine/part{n}.py", line {n}, in step{n}\n'
    f"[WebServer]     return self._step{n}()\n"
    for n in range(14)
)
OUTPUT = (
    "Error: Process from config.webServer was not able to start. Exit code: 3\n"
    "[WebServer] shop/shop_pkg/routers/items.py:146: FastAPIDeprecationWarning: `regex` has been deprecated\n"
    '[WebServer]   view: str = Query("personal", regex="^(personal|team)$"),\n'
    "[WebServer] INFO:     Waiting for application startup.\n"
    "[WebServer] ERROR:    Traceback (most recent call last):\n"
    '[WebServer]   File "shop/.venv/lib/python3.12/site-packages/starlette/routing.py", line 694, in lifespan\n'
    "[WebServer]     async with self.lifespan_context(app) as maybe_state:\n"
    '[WebServer]   File "shop/shop_pkg/main.py", line 31, in lifespan\n'
    "[WebServer]     async with engine.begin() as conn:\n"
    + DEPENDENCY_FRAMES +
    "[WebServer] sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) unable to open database file\n"
    "[WebServer] (Background on this error at: https://sqlalche.me/e/21/e3q8)\n"
    "[WebServer] ERROR:    Application startup failed. Exiting.\n"
)


def test_the_excerpt_keeps_the_product_s_frame_and_the_line_it_ran():
    problem = the_product_did_not_start(OUTPUT)

    assert 'File "shop/shop_pkg/main.py", line 31, in lifespan' in problem
    assert "async with engine.begin() as conn:" in problem
    assert "part7.py" not in problem
    assert "unable to open database file" in problem


def test_a_data_file_that_would_not_open_is_explained():
    problem = the_product_did_not_start(OUTPUT)

    hint = problem[problem.index("The product could not open its data file"):]
    assert "`DATA_DIR`" in hint and "creates the folder" in hint
    assert not BANNED.search(hint)


def test_the_fix_rewrites_the_product_s_frame_not_the_warning_s_file(tmp_path):
    for name in ("shop/shop_pkg/main.py", "shop/shop_pkg/routers/items.py", "shop/shop_pkg/database.py"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x = 1\n")
    defect = SimpleNamespace(description="The product does not start for the acceptance suite, so no test can reach it.",
                             affected_files=[])

    found = files_to_fix(defect, the_product_did_not_start(OUTPUT), tmp_path, lambda path: True)

    assert found == ["shop/shop_pkg/main.py"]
