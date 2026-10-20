"""Source files under a served folder that no import from its entrypoint reaches are code the product does not run.

Measured on one run: every acceptance and unit test passed while the service ran
from one `main.py` that redefined its models and routes, and the page from one
`App.tsx`. The planned modules beside them - 59% of the product's lines -
imported each other and nothing imported them, and nothing said so to a fixer
or at release.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.analysis.reachability import unreached_modules
from app.stacks import pack_named, scaffold


def _write(root: Path, files: dict[str, str]) -> None:
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


SERVICE = {
    "board/__init__.py": "",
    "board/main.py": (
        "from fastapi import FastAPI\nfrom board.store import connect\n"
        "def create_item(): ...\ndef list_items(): ...\napp = FastAPI()\n"
    ),
    "board/store.py": "def connect(): ...\n",
    "board/models.py": "class Item: ...\n",
    "board/routers/__init__.py": "",
    "board/routers/items.py": (
        "from board.models import Item\nfrom ..store import connect\n"
        "def create_item(): ...\ndef list_items(): ...\n"
    ),
    "board/migrations/versions/0001_first.py": "def upgrade(): ...\n",
    "tests/conftest.py": "from board.main import app\n",
    "tests/test_items.py": "def test_it(): ...\n",
}

PAGE = {
    "index.html": '<script type="module" src="/src/main.tsx"></script>',
    "tsconfig.json": '{\n  // the page\n  "compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}\n}',
    "src/main.tsx": "import { App } from './App';\nimport './styles.css';\n",
    "src/styles.css": "body {}\n",
    "src/App.tsx": (
        "import { Card } from './components/Card';\nimport { slug } from '@/lib/text';\n"
        "const Lazy = React.lazy(() => import('./pages/Settings'));\n"
        "export function App() {}\nexport function useAuth() {}\nexport function login() {}\n"
    ),
    "src/components/Card.tsx": "export function Card() {}\n",
    "src/lib/text.ts": "export function slug() {}\n",
    "src/pages/Settings.tsx": "export default function Settings() {}\n",
    "src/pages/Login.tsx": "import { useAuth } from '../contexts/Auth';\nexport function Login() {}\n",
    "src/contexts/Auth.tsx": "export function useAuth() {}\nexport function login() {}\n",
    "src/vite-env.d.ts": "",
    "src/App.test.tsx": "import { App } from './App';\n",
}


def test_a_service_s_modules_nothing_imports_are_found_with_the_copy_they_repeat(tmp_path):
    _write(tmp_path, SERVICE)

    (found,) = unreached_modules(tmp_path, ["board/main.py"])

    assert found.files == ("board/models.py", "board/routers/items.py")
    assert found.repeats == ("board/routers/items.py", "board/main.py", ("create_item", "list_items"))


def test_a_page_s_modules_are_followed_through_launchers_lazy_imports_and_aliases(tmp_path):
    _write(tmp_path, PAGE)

    (found,) = unreached_modules(tmp_path, ["src/App.tsx"], lambda name: name.endswith(".test.tsx"))

    assert found.files == ("src/contexts/Auth.tsx", "src/pages/Login.tsx")
    assert found.repeats == ("src/contexts/Auth.tsx", "src/App.tsx", ("login", "useAuth"))


def test_every_module_reached_is_no_finding(tmp_path):
    _write(tmp_path, {
        "board/main.py": "from board import models\nfrom .routers import items\n",
        "board/models.py": "", "board/routers/items.py": "",
    })
    assert unreached_modules(tmp_path, ["board/main.py"]) == []


def test_the_finding_reaches_fixers_and_the_release_for_a_pack_wired_by_imports(tmp_path):
    (tmp_path / ".harness").mkdir()
    (tmp_path / ".harness" / "stack-pack.json").write_text(json.dumps(
        {"pack": "fullstack-react-fastapi", "project": "app", "package": "board", "title": "Board"}))
    _write(tmp_path / "app", {**SERVICE, **PAGE})

    problems = [p for p in scaffold.code_the_product_does_not_run(tmp_path) if "imported by nothing" in p]

    assert len(problems) == 2
    assert "`app/board/routers/items.py` defines `create_item`, `list_items` again" in " ".join(problems)
    assert all("Keep one copy" in p for p in problems)


def test_a_pack_whose_framework_loads_modules_by_place_or_name_is_not_checked(tmp_path):
    _write(tmp_path, SERVICE)
    for name in ("fullstack-django", "fullstack-next"):
        pack = pack_named(name)
        assert pack is not None and not pack.wired_by_imports
        assert scaffold._modules_nothing_imports(tmp_path, "", ["board/main.py"], pack) == []
    assert pack_named("fullstack-react-fastapi").wired_by_imports
