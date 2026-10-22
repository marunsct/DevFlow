"""Where things go, decided once, so every stage puts them in the same place.

Each stage builds its own agent and none can see what an earlier one chose, so
without a stated convention each invents a layout and they disagree. Measured
across this project's runs:

- one run put `test_auth.py` and `auth.test.js` in one `tests/` directory,
  beside an `__init__.py` and a `requirements.txt` and a `package.json`. Two
  languages, two test runners, one directory: each file sensible on its own,
  and nothing able to run the set.
- one run wrote `css/style.css` first, so `css` became the project.
- one run wrote the workspace's own host path as a directory inside itself.
- one run finished with two `tests/` directories holding three files of
  the same names.

The convention below is deliberately not one fixed skeleton. A single-language
product is better flat - one run shipped `task-manager/` with five files
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
      task-manager/<entry file>
      task-manager/<module files>
      task-manager/<test files>
      task-manager/<the language's manifest>
- More than one tier, or more than one language? One directory per tier, all
  inside the project:
      task-dashboard/backend/      server code and its manifest
      task-dashboard/frontend/     the interface and its manifest
      task-dashboard/db/           migrations and schema
- ONE LANGUAGE PER DIRECTORY. A directory is what a manifest and a test runner
  address: two languages' manifests in the same folder means neither runner
  sees a complete project, and two languages' test files side by side means
  no single command runs the tests. Put each language in
  its own directory, with its own manifest and its own tests.
- Tests live beside the code they test, inside the project. A suite at the
  workspace root is one the project's runner never collects.
- Documentation that ships with the product - a README, a guide for whoever
  maintains it - goes inside the project, beside the code it describes.
- `docs/` already exists and the workflow maintains it. `product_intake.md`,
  `technology_stack.md`, `technical_specification.md`, `sprint_plan.md`,
  `milestone_plan.md`, `architecture_review.md`, `security_review.md`,
  `milestone_review.md` and `tools_and_models.md` are each rendered from a
  stage's structured response, once that stage has run - early in a run some
  are not there yet. Read the ones that exist; never write, copy, move or
  recreate them, and never copy `docs/` into the project. A second copy is stale the
  moment that stage runs again, and writing one is refused."""

_KEPT_FROM_THE_GENERAL_LAYOUT = PROJECT_LAYOUT[PROJECT_LAYOUT.index("- ONE LANGUAGE PER DIRECTORY."):]


def scaffolded_layout(project: str, served: list[str]) -> str:
    """The layout section for a project a stack pack scaffolded: where it is served from, settled.

    The general section's "one directory per tier - `backend/`, `frontend/`"
    was in every specialist's prompt on a scaffolded full-stack run whose
    product is served from `src/` and the package's `main.py`. The run drafted
    the page in `frontend/src/` and the service in `backend/app/`, beside the
    served files; nothing built or ran them, and fixes landed in both. Once a
    pack has scaffolded the project, where the product lives is a fact, not a
    convention to choose from.
    """
    names = ", ".join(f"`{project}/{path}`" for path in served)
    return (
        "WHERE FILES GO - settled by the scaffold; follow it:\n\n"
        f"- The project is `{project}/`. The product is served from {names}. Build it there: in\n"
        "  those files, or in files beside them that they import. Code anywhere else is\n"
        "  never built or run.\n"
        "- Never start a second copy of a served folder elsewhere in the project - a\n"
        "  `frontend/` or `backend/` beside the folder that is served. Change the served one.\n"
        + _KEPT_FROM_THE_GENERAL_LAYOUT
    )


def for_this_workspace(text: str, repo_root: object) -> str:
    """`text` with the general layout section replaced by the scaffold's, when a pack scaffolded `repo_root`."""
    if PROJECT_LAYOUT not in text or not repo_root:
        return text
    try:
        from app.stacks.scaffold import _served_entrypoints

        project, served = _served_entrypoints(repo_root)
    except Exception:  # noqa: BLE001 - the general section stands
        return text
    if not project or not served:
        return text
    return text.replace(PROJECT_LAYOUT, scaffolded_layout(project, served))


#: What to tell an agent about where it is, instead of where the workspace is
#: on the host. `product_manager` has carried this reasoning in a comment since
#: one run and was the only caller that acted on it; five other briefs
#: opened with `Repository root: /app/data/workspaces/<label>-<run-id>` and the
#: agents used it. Measured across the stored run histories: 15 of 24 runs
#: carry that string into tool calls, and the calls fail - one run, which
#: completed cleanly, still spent six calls on it and five came back
#: `not found` or `path_not_found`; one run spent 432 and 254 approval
#: gates before dying of gate exhaustion.
#:
#: Telling an agent the path and then telling it not to use the path does not
#: work. The reliable fix is not to show it.
WORKSPACE_ROOT_NOTE = (
    "The workspace is rooted at '/'; every path you use is relative to it.\n\n"
)

__all__ = ["PROJECT_LAYOUT", "WORKSPACE_ROOT_NOTE"]


#: Where the product lives, as a stage that plans it is told. The code-writing
#: stages' version says to run `ls` and write into the directory; told that,
#: one run's architect on a local model took itself to be writing the product
#: and spent its attempts listing an empty directory. A stage that plans
#: writes no file of the product: every path it names is inside the directory.
PLANNED_PROJECT_DIRECTORY = (
    "**CRITICAL INSTRUCTION**: The product's code lives in ONE project directory at the workspace "
    "root: the one that already exists, spelled exactly as it is, or - if none does - one named "
    "after this product in lowercase-with-hyphens. Every path you plan is inside it: never the "
    "workspace root, never a generic name like 'nest-app', never a second project directory. "
    "Documentation that ships with the product goes inside it beside the code it describes; "
    "`docs/` is the workflow's own directory. This stage writes none of the product's files: "
    "its result is its answer.\n"
)
