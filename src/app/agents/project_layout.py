"""Where things go, decided once, so every stage puts them in the same place.

Each stage builds its own agent and none can see what an earlier one chose, so
without a stated convention each invents a layout and they disagree. Measured
across this project's runs:

- py` and `auth.test.js` in one `tests/` directory,
  beside an `__init__.py` and a `requirements.txt` and a `package.json`. Two
  languages, two test runners, one directory: each file sensible on its own,
  and nothing able to run the set.
- css` first, so `css` became the project.
- 
- 

The convention below is deliberately not one fixed skeleton. A single-language
product is better flat -  What must hold in both shapes is the last rule: one
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
- Documents go in the workspace's `docs/`, never inside the project.
- `docs/` already exists and the workflow maintains it. `product_intake.md`,
  `technology_stack.md`, `technical_specification.md`, `sprint_plan.md`,
  `milestone_plan.md`, `architecture_review.md`, `security_review.md`,
  `milestone_review.md` and `tools_and_models.md` are each rendered from a
  stage's structured response. Read them; never write, copy, move or recreate
  them, and never copy `docs/` into the project. A second copy is stale the
  moment that stage runs again, and writing one is refused."""

#: What to tell an agent about where it is, instead of where the workspace is
#: on the host. `product_manager` has carried this reasoning in a comment since
#: opened with `Repository root: /app/data/workspaces/<label>-<run-id>` and the
#: agents used it. Measured across the stored run histories: 15 of 24 runs
#: completed cleanly, still spent six calls on it and five came back
#: gates before dying of gate exhaustion.
#:
#: Telling an agent the path and then telling it not to use the path does not
#: work. The reliable fix is not to show it.
WORKSPACE_ROOT_NOTE = (
    "The workspace is rooted at '/'; every path you use is relative to it.\n\n"
)

__all__ = ["PROJECT_LAYOUT", "WORKSPACE_ROOT_NOTE"]
