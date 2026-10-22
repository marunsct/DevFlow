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

import pytest

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


def _product(root, *names):
    for name in names:
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("x = 1\n")
    return root


def test_the_excerpt_keeps_the_product_s_frame_and_the_line_it_ran(tmp_path):
    problem = the_product_did_not_start(OUTPUT, _product(tmp_path, "shop/shop_pkg/main.py",
                                                        "shop/.venv/lib/python3.12/site-packages/sqlalchemy/engine/part7.py"))

    assert 'File "shop/shop_pkg/main.py", line 31, in lifespan' in problem
    assert "async with engine.begin() as conn:" in problem
    assert "part7.py" not in problem
    assert "unable to open database file" in problem


def test_a_data_file_that_would_not_open_is_explained_in_the_setup_s_own_words(tmp_path, monkeypatch):
    from app.stacks import contract

    monkeypatch.setattr(contract, "the_pack", lambda root: (SimpleNamespace(
        data_store="A service keeps its data under the directory in `DATA_DIR`."), {}))

    problem = the_product_did_not_start(OUTPUT, tmp_path)

    hint = problem[problem.index("The product could not open its data file"):]
    assert "creates that folder" in hint and "This setup says: A service keeps its data under the directory in `DATA_DIR`." in hint
    assert not BANNED.search(hint)


def test_the_fix_rewrites_the_product_s_frame_not_the_warning_s_file(tmp_path):
    for name in ("shop/shop_pkg/main.py", "shop/shop_pkg/routers/items.py", "shop/shop_pkg/database.py"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("x = 1\n")
    defect = SimpleNamespace(description="The product does not start for the acceptance suite, so no test can reach it.",
                             affected_files=[])

    found = files_to_fix(defect, the_product_did_not_start(OUTPUT, tmp_path), tmp_path, lambda path: True)

    assert found == ["shop/shop_pkg/main.py"]


#: The same start failure as other runtimes print it, frames in the product among frames that are not.
TRACES = {
    "go": ("shop/cmd/server/main.go", "goroutine 1 [running]:\nmain.openStore(...)\n\t{root}/shop/cmd/server/main.go:41 +0x1d\n"
           "github.com/mattn/go-sqlite3.(*SQLiteDriver).Open(...)\n\t/go/pkg/mod/github.com/mattn/go-sqlite3@v1.14.22/sqlite3.go:1450 +0x8f"),
    "jvm": ("shop/src/main/java/shop/Store.java", "\tat org.sqlite.core.DB.open(DB.java:174)\n\tat shop.Store.open(Store.java:28)\n"
            "\tat java.base/java.lang.Thread.run(Thread.java:1583)"),
    "node": ("shop/src/store.js", "    at Database.open ({root}/shop/node_modules/better-sqlite3/lib/database.js:65:11)\n"
             "    at openStore ({root}/shop/src/store.js:9:14)"),
    "ruby": ("shop/app/store.rb", "{root}/shop/vendor/bundle/ruby/3.3.0/gems/sqlite3-2.0.2/lib/sqlite3/database.rb:150:in 'open'\n"
             "{root}/shop/app/store.rb:12:in 'connect'"),
}


@pytest.mark.parametrize("runtime", sorted(TRACES))
def test_the_product_s_frame_is_found_in_any_runtime_s_trace(tmp_path, runtime):
    """Owner, 2026-10-20: a fix works for every language. The first version knew Python's
    and Node's frames and their dependency folders; a frame is now the product's when it
    names one of the product's own files, whatever prints it."""
    mine, trace = TRACES[runtime]
    trace = trace.replace("{root}", str(tmp_path))
    _product(tmp_path, mine, "shop/node_modules/better-sqlite3/lib/database.js")
    output = ("Error: Process from config.webServer was not able to start. Exit code: 1\n"
              + "[WebServer] starting\n" * 3 + trace + "\n" + "[WebServer] padding\n" * 3
              + "unable to open database file\n" + "[WebServer] exiting\n" * 8)

    problem = the_product_did_not_start(output, tmp_path)

    assert mine.rsplit("/", 1)[-1] in problem
    assert "go-sqlite3@v1.14.22/sqlite3.go" not in problem and "lib/database.js" not in problem
    assert "DB.java" not in problem and "gems/sqlite3" not in problem
