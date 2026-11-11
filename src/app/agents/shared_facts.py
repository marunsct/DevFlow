"""One account of the facts a sprint's work is built under, for the stages that build it and the stages that judge it (plan CM.1).

Of fifteen failures traced to agents missing something, about eleven were one
stage lacking a fact another stage or the harness already had, each patched for
one stage at a time: a review undid the file-database fallback the architect
had been told to plan (LF.42), the security review demanded a secret the
product then could not start without (LF.90). Measured again on one run: every
fixer was told which code the product does not run, and the milestone review
that accepted the release was not - it passed a product whose planned modules,
59% of its lines, nothing imported.

So the facts come from one function, read from the workspace and the pack it is
set up with, and every builder and judge request appends the same block. A
judge sees what the builder was given; it never sees the builder's reasoning
or transcript (CM.5).
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

#: Group 2 of the plan is measured before and after (ADR-0010): built while a
#: gate run measures the code without it, so it stays off until that run ends.
#: `SHARED_FACTS` set to on or off overrides this.
ON_BY_DEFAULT = False


def enabled() -> bool:
    """Whether builder and judge requests end with the facts (plan CM.1)."""
    from app.switches import is_on

    return is_on("SHARED_FACTS", ON_BY_DEFAULT)

#: The heading every builder and judge reads the block under.
HEADING = "--- The facts this work is built and judged under ---"


def layout_facts(pack: Any, project: str, package: str | None) -> list[str]:
    """The pack's layout and data store for this project, one line each.

    The architect wrote the file plan knowing the stack, not the layout the
    harness would set up for it. Measured on one run: the plan put the service
    in `backend/app/` and the page in `frontend/src/` while the scaffold served
    the package's `main.py` and `src/App.tsx`; 28 files were drafted where
    nothing served them.
    """
    served = [pack.filled(e, project, "", package) for e in (pack.entrypoint, *pack.entrypoints) if e]
    prefix = f"{project}/" if project else ""
    lines = [f"- The project lives in `{prefix or './'}`."]
    if served:
        lines.append("- What the product serves, and the acceptance suite runs through: "
                     + ", ".join(f"`{prefix}{path}`" for path in served)
                     + ". Plan the product in these files, or in modules they import.")
    modules = [path[:-3].replace("/", ".") for path in served if path.endswith(".py") and "/" in path]
    if modules and project:
        # Measured on two full-stack runs whose project directory and package share a name: one wrote a second
        # `main.py` at the project's root, the other's tests imported `bookmarks.bookmarks.main`.
        lines.append(f"- The service is imported as `{modules[0]}`, from inside `{prefix}`: the project directory is "
                     f"where it runs from, not part of the name - `{project.replace('-', '_')}.{modules[0]}` "
                     "resolves to nothing.")
    lines.append(f"- Unit tests: `{pack.unit_pattern}` in `{prefix}{pack.unit_dir}/`; acceptance tests: "
                 f"`{pack.acceptance_pattern}` in `{prefix}{pack.acceptance_dir}/`.")
    if getattr(pack, "data_store", ""):
        lines.append("- Where the data lives: " + " ".join(str(pack.data_store).split()))
    started = str((getattr(pack, "files", None) or {}).get("start.sh") or "")
    if started:
        # The setup's own start script, already proven by its smoke test. Both
        # Measure gate runs' specifications designed a start.sh of their own,
        # and one - `exec python tasks_api/app.py`, a Python without the
        # product's dependencies - was drafted over the working one: every
        # locked test passed and the service did not start for anyone else.
        command = next((line.strip() for line in pack.filled(started, project, "", package).splitlines()
                        if line.strip() and not line.startswith("#")), "")
        lines.append(f"- `{prefix}start.sh` is already set up and starts the service as the brief asks"
                     + (f" (`{command}`)" if command else "")
                     + ": the file plan keeps it as it is, and changes it only for something the brief "
                     "asks that it does not do.")
    kept = [path for path in pack.kept_files if path not in served]
    if kept:
        lines.append("- Kept by the harness, not the product's to write: "
                     + ", ".join(f"`{prefix}{path}`" for path in kept[:8]) + ".")
    ready = _the_route_the_suite_waits_on(pack)
    if ready:
        # Measured on two full-stack runs: the builders rewrote the service without the setup's own readiness route,
        # the suite waited on it, and the first test round found "the product does not start".
        lines.append(f"- The acceptance suite starts the product and waits until `GET {ready}` answers before any test "
                     "runs: keep that route answering 200 - the setup's own code has it - whatever else is rewritten.")
    for path in _kept_code_to_show(pack, kept):
        code = _code_lines(pack.filled(str(pack.files[path]), project, "", package))
        lines.append(f"- What `{prefix}{path}` does now, in full (comments left out):\n```\n" + "\n".join(code) + "\n```")
    scripts = sorted((getattr(pack, "kept_scripts", None) or {}))
    if scripts:
        # Measured on two runs: told nothing of them, both fixers of a failing unit run rewrote `package.json`'s test
        # script and added another runner's configuration; the harness put the script back, and neither fix worked.
        lines.append("- The manifest's " + ", ".join(f"`{name}`" for name in scripts)
                     + f" script{'s are' if len(scripts) > 1 else ' is'} the harness's too, kept as "
                     + ("they are" if len(scripts) > 1 else "it is")
                     + ": a change to " + ("them" if len(scripts) > 1 else "it") + " is put back, so a fix goes in "
                     "the code or the tests, never there.")
    for path, text in list((getattr(pack, "proven_code", None) or {}).items())[:2]:
        # Measured on a stack no pack covers: the specification, written before the setup existed, created the
        # application another way; the builders followed it and the product no longer started.
        code = _code_lines(str(text))
        lines.append(f"- What `{prefix}{path}` did when the setup was proven - it started and answered the smoke test "
                     "(comments left out):\n```\n" + "\n".join(code) + "\n```\n  Build on it: keep how it creates "
                     "the application and how the server loads it. Where the specification does those another way, "
                     "this way is the one proven to start, and it stands.")
    if kept or started:
        # Measured on three runs: the specification put creating the data directory and checking the port in the
        # pack's `start.sh`, and signal handling in its kept start file; the reviews then sent the sprint back for
        # behaviour no work order may write there.
        lines.append("- Those files do what they do now and nothing more: put whatever else the product must do - "
                     "at start, at shutdown, with its settings or its data directory - in the product's own files.")
    return lines


#: A kept file of code is shown whole when it is this short, so the design stages read what it does and leaves undone.
#: Measured on four runs: told only that a start file was kept, the specification gave it behaviour it does not have
#: - creating the data directory, checking the port, handling signals - and the review blocked on it.
KEPT_CODE_LINES = 20
_CODE_SUFFIXES = (".ts", ".mts", ".js", ".mjs", ".cjs", ".py", ".go", ".rs", ".java", ".kt", ".cs", ".rb", ".php")
_NOT_PRODUCT_CODE = re.compile(r"config|setup|conftest|test|spec|/acceptance/|^acceptance/", re.I)
_A_COMMENT = re.compile(r"^\s*(?://|#|/\*|\*)")


_THE_READY_URL = re.compile(r"url:\s*`https?://[^`/]*\$\{port\}(/[^`\s]+)`")


def _the_route_the_suite_waits_on(pack: Any) -> str:
    """The path the kept test configuration waits on before the suite runs, when it is not the page itself."""
    for path in getattr(pack, "kept_files", ()) or ():
        found = _THE_READY_URL.search(str((getattr(pack, "files", None) or {}).get(path) or ""))
        if found and found.group(1) != "/":
            return found.group(1)
    return ""


def _code_lines(text: str) -> list[str]:
    return [line.rstrip() for line in str(text).splitlines() if line.strip() and not _A_COMMENT.match(line)]


def _kept_code_to_show(pack: Any, kept: list[str]) -> list[str]:
    """The kept files that run the product - its start file, its server - short enough to show whole, at most two."""
    files = getattr(pack, "files", None) or {}
    chosen = []
    for path in kept:
        if (path.endswith(_CODE_SUFFIXES) and not _NOT_PRODUCT_CODE.search(path) and path in files
                and len(_code_lines(str(files[path]))) <= KEPT_CODE_LINES):
            chosen.append(path)
    return chosen[:2]


def what_the_setup_decides(pack: Any, project: str, package: str | None) -> list[str]:
    """What the pack has settled that a specification might otherwise choose, one line each, for the stages designing it.

    Measured on several runs: the review ended on blocking findings about the harness's own files after six revisions
    each - a kept start file given signal handlers, a file plan's other unit runner, a tool added to run the language.
    Every builder has the pack's guide, so this goes only to the stages that write and judge the specification.
    """
    prefix = f"{project}/" if project else ""

    def command(argv: Any) -> str:
        return pack.filled(" ".join(argv), project, "", package)

    lines = []
    runners = str((getattr(pack, "stack", None) or {}).get("testing_framework") or "")
    if runners:
        lines.append(f"- The tests' runners are the setup's: {runners}. `{command(pack.unit_test)}` runs the unit tests "
                     f"and `{command(pack.acceptance_test)}` the acceptance tests. Every section that mentions testing "
                     "names these, and no other runner.")
    start = str((getattr(pack, "kept_scripts", None) or {}).get("start") or "")
    if start or "start.sh" in (getattr(pack, "files", None) or {}):
        how = f"`{start}`" if start else f"`{prefix}start.sh`"
        lines.append(f"- The product is started by {how} and in no other way: no other way of running it, and no "
                     "dependency or tool for one.")
    for path, names in (getattr(pack, "required_exports", None) or {}).items():
        listed = ", ".join(f"`{name}`" for name in names)
        called = (" and call it with no arguments, so it needs none and reads its settings from the environment"
                  if getattr(pack, "required_exports_called_bare", False) else "")
        lines.append(f"- `{prefix}{path}` is the product's entry and exports {listed} under that name, as a named "
                     f"export: the setup's own files import it so{called}.")
    if pack.kept_files:
        lines.append("- The specification names the files the harness writes and keeps as given. It may say what they "
                     "provide, and gives no step, signature or behaviour inside them.")
    # The module system the setup's manifest already declares. Measured on one run: the first design review blocked
    # a specification for not saying how Node loads ES modules, while the setup's `package.json` declared it.
    try:
        import json as _json

        manifest = _json.loads(pack.filled(str((getattr(pack, "files", None) or {}).get("package.json") or "{}"),
                                           project, "", package))
    except (ValueError, TypeError):
        manifest = {}
    kind = manifest.get("type") if isinstance(manifest, dict) else None
    if kind in ("module", "commonjs"):
        lines.append(f'- `{prefix}package.json` is the setup\'s and already declares `"type": "{kind}"`: its `.js` files are '
                     + ("ES modules (`import` / `export`)" if kind == "module" else "CommonJS modules (`require`)")
                     + ". The specification needs no other module setting.")
    lines.extend(_what_the_setup_already_writes(pack, project, package))
    return lines


#: Dependency manifests whose runtime lines the setup's design stages are told; a development one is left out.
_A_RUNTIME_MANIFEST = re.compile(r"(?:^|/)(?:requirements(?:\.txt|/base\.txt)|package\.json)$")


def _what_the_setup_already_writes(pack: Any, project: str, package: str | None) -> list[str]:
    """The files the setup writes beside the kept ones, and the runtime dependencies it declares; [] when none.

    Measured on one run: the design review blocked on "missing wsgi.py" and "gunicorn not declared" - the setup had
    written both `wsgi.py` and a requirements file declaring gunicorn, but the review was told only of the kept files,
    and the specification went back twice and escalated.
    """
    files = getattr(pack, "files", None) or {}
    kept = set(getattr(pack, "kept_files", None) or ())
    prefix = f"{project}/" if project else ""
    written = [pack.filled(path, project, "", package) for path in files
               if path not in kept and not path.startswith(".") and "/." not in path]
    if not written:
        return []
    # Measured on two runs after this line said "has already written": the architect, told so before the setup had
    # run, read the starter files and was told no such file exists yet. The words hold at every stage.
    lines = [f"- The setup writes {_at_most(written, MOST_NAMED, prefix)} when the build starts: none of them is "
             "missing, and the product may fill or change them. Before the build they are not on disk, so no "
             "call reads them."]
    declared: list[str] = []
    for path, text in files.items():
        if not _A_RUNTIME_MANIFEST.search(path):
            continue
        body = pack.filled(str(text or ""), project, "", package)
        if path.endswith(".json"):
            try:
                import json as _json

                declared += list((_json.loads(body) or {}).get("dependencies") or {})
            except (ValueError, TypeError, AttributeError):
                continue
        else:
            declared += [line.strip() for line in body.splitlines() if line.strip() and not line.strip().startswith(("#", "-"))]
    if declared:
        lines.append(f"- The setup declares the runtime dependencies {_at_most(declared, MOST_NAMED)}: "
                     "no step adds them.")
    return lines


#: Names one setup line lists before it says how many more: each line goes into every design request.
MOST_NAMED = 6


def _at_most(names: list[str], most: int, prefix: str = "") -> str:
    shown = ", ".join(f"`{prefix}{name}`" for name in names[:most])
    return shown + (f" and {len(names) - most} more" if len(names) > most else "")


def facts_from_the_workspace(root: str | Path | None, *, built: bool = True) -> list[str]:
    """The layout, a served stub and the code the product does not run, as measured now; [] before a pack is set up. Never raises.

    `built` is False for the stages still writing the product: until the work
    orders are done the scaffold's stub is still served and the modules
    written so far are not yet imported, which is how building goes, not a
    finding. They get the layout alone.
    """
    if not root:
        return []
    try:
        from app.stacks import contract
        from app.stacks.scaffold import code_the_product_does_not_run, entrypoint_is_still_the_stub

        # `contract.the_pack`, not `pack_named`: a stack no pack covers has a proven setup's pack, and its stages read
        # the same layout facts a code pack's do (SF.0a; `pack_named` knows only the code packs).
        found = contract.the_pack(root)
        if found is None:
            return []
        pack, record = found
        lines = layout_facts(pack, str(record.get("project") or ""), str(record.get("package") or "") or None)
        if not built:
            return lines
        stub = entrypoint_is_still_the_stub(root)
        if stub:
            lines.append(f"- `{stub}` is still byte for byte the scaffold's stub: nothing drafted elsewhere is served.")
        lines.extend(f"- Code the product does not run: {problem}" for problem in code_the_product_does_not_run(root))
        return lines
    except Exception:  # noqa: BLE001 - a request without the facts is the request as it was
        logger.debug("Could not read the workspace's facts", exc_info=True)
        return []


def the_facts_section(root: str | Path | None, *, built: bool = True) -> str:
    """The block a builder or judge request ends with; "" when there are no facts yet or it is off."""
    from app.agents.specification_rulings import the_rulings_section

    # The rulings follow their own switch: a decision taken for the run binds whichever facts are on.
    from app.agents.start_breaks import the_section as the_start_breaks

    # Both follow no switch: a decision taken for the run, and fixes undone for a start that broke, bind every stage.
    rulings = the_rulings_section(root) + the_start_breaks(root)
    facts = facts_from_the_workspace(root, built=built) if enabled() else []
    if not facts:
        return rulings
    return f"\n\n{HEADING}\n" + "\n".join(facts) + "\n" + rulings


def with_the_facts(request: dict[str, Any], root: str | Path | None, *, built: bool = True) -> dict[str, Any]:
    """`request` with the facts block appended to its last message. Never raises."""
    try:
        section = the_facts_section(root, built=built)
        if section and request.get("messages"):
            last = request["messages"][-1]
            if isinstance(last, dict) and isinstance(last.get("content"), str):
                last["content"] += section
    except Exception:  # noqa: BLE001 - as above
        logger.debug("Could not add the facts to a request", exc_info=True)
    return request
