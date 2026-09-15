"""Where things go, decided once, so every stage puts them in the same place.

Each stage builds its own agent and none can see what an earlier one chose, so
without a stated convention each invents a layout and they disagree. Measured
across this project's runs:

- run-64df2b20 put `test_auth.py` and `auth.test.js` in one `tests/` directory,
  beside an `__init__.py` and a `requirements.txt` and a `package.json`. Two
  languages, two test runners, one directory: each file sensible on its own,
  and nothing able to run the set.
- run-7b11cb67 wrote `css/style.css` first, so `css` became the project.
- run-2f252e4e wrote the workspace's own host path as a directory inside itself.
- run-2b5def74 finished with two `tests/` directories holding three files of
  the same names.

The convention below is deliberately not one fixed skeleton. A single-language
product is better flat - run-da6c5e19 shipped `task-manager/` with five files
in it and a passing suite - and forcing `ui/`, `db/`, `model/` onto it invents
structure nobody needs. What must hold in both shapes is the last rule: one
language per directory, because a directory is what a manifest and a test
runner address.
"""

PROJECT_LAYOUT = """WHERE FILES GO - this is settled; follow it rather than inventing one:

- ONE top-level project directory, named after the product in
  lowercase-with-hyphens: `task-manager/`, `todo-app/`. Never `app/`, `src/`,
  `backend/` or `css/` - those name a part of a project, and a run that pins
  one as the whole project cannot then write the other parts.
- One language and a handful of files? Keep it FLAT. A five-file product needs
  no folders:
      task-manager/index.html
      task-manager/app.js
      task-manager/style.css
      task-manager/app.test.mjs
      task-manager/package.json
- More than one tier, or more than one language? One directory per tier, all
  inside the project:
      task-dashboard/backend/      server code and its manifest
      task-dashboard/frontend/     the interface and its manifest
      task-dashboard/db/           migrations and schema
- ONE LANGUAGE PER DIRECTORY. A directory is what a manifest and a test runner
  address: `requirements.txt` and `package.json` in the same folder means
  neither runner sees a complete project, and `test_auth.py` beside
  `auth.test.js` means no single command runs the tests. Put each language in
  its own directory, with its own manifest and its own tests.
- Tests live beside the code they test, inside the project. A suite at the
  workspace root is one the project's runner never collects.
- Documents go in the workspace's `docs/`, never inside the project."""

__all__ = ["PROJECT_LAYOUT"]
