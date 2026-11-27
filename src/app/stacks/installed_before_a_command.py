"""A stage's build and test commands see the dependencies its manifest names.

The harness installs the project's dependencies again when a manifest changed (`contract.install_if_the_manifests_changed`),
but only before its own measurements. A stage's commands run without a network - only an install has one - so a
dependency a draft or a stage added to the manifest was on disk only after the next measurement. Measured on a Rust
run: drafting wrote `Cargo.toml` with `rusqlite` in it, the first unit-testing work order then ran every `cargo build`,
`check` and `test` against it before any measurement, each failed "Could not resolve host: index.crates.io" (and, with
`--offline`, "no matching package named `rusqlite` found"), and the stage spent nine minutes on retries, offline flags,
the binary and shell redirects without ever seeing a compile result.

So the same install runs, with the network and through the same egress and dependency gates, before a stage's command
that runs one of the project's own programs, once per change of the manifests. An install that fails is not tried
again for the same manifests before a stage's command (the harness's measurements still try it each time), and its
note is handed to each failed command that could not reach a registry, with what that failure means: the command had
no network by design, and retrying it, or running it offline, cannot change that.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any, Sequence

from app.stacks import contract

logger = logging.getLogger(__name__)

#: The manifests an install before a stage's command last failed on, and what it said.
TRIED_FILE = f"{contract.HARNESS_DIR}/install-tried.json"

#: A command failing to reach a package registry, in each package manager's words: name resolution (cargo, curl, git,
#: glibc, Node's `EAI_AGAIN`/`ENOTFOUND`, Go's `dial tcp: lookup`), pip's connection error, NuGet's `NU1301`, and a
#: package an offline resolver does not have (cargo `--offline`, npm's `ENOTCACHED`, Maven's offline mode).
_COULD_NOT_REACH_A_REGISTRY = re.compile(
    r"Could not resolve host\b|Temporary failure in name resolution|\bEAI_AGAIN\b|getaddrinfo ENOTFOUND|"
    r"dial tcp: lookup\b|Failed to establish a new connection|\bNU1301\b|\bENOTCACHED\b|"
    r"no matching package named `[^`]+` found[^\n]*\n(?:[^\n]*\n){0,3}[^\n]*offline|"
    r"offline mode[^\n]*(?:not|no) (?:been )?(?:downloaded|available)|Cannot access [^\n]+ in offline mode",
    re.IGNORECASE,
)

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _the_lock_for(repo_root: str | Path) -> threading.Lock:
    """One install at a time per workspace: two stages that find the same change install it once."""
    key = os.path.realpath(str(repo_root))
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.Lock())


def _the_program(command: Sequence[str]) -> str:
    """The program a command runs, past a leading `cd <dir> &&`."""
    words = [str(word) for word in command]
    if words[:1] == ["cd"] and "&&" in words:
        words = words[words.index("&&") + 1:]
    return os.path.basename(words[0]) if words else ""


def _the_project_s_programs(record: dict[str, Any]) -> set[str]:
    """The programs the project's recorded commands run, and its language's toolchain."""
    programs = {_the_program(argv) for key in ("install", "warm_up") for argv in record.get(key) or [] if argv}
    programs |= {_the_program(record[key]) for key in ("unit_test", "acceptance_test") if record.get(key)}
    try:
        from app.stacks import pack_named
        from app.tools.sandbox import TOOLCHAINS, _toolchain_key

        pack = pack_named(record.get("pack"))
        key = _toolchain_key(getattr(pack, "language", "") or "") if pack else None
        programs |= set(TOOLCHAINS.get(key or "", ()))
    except Exception:  # noqa: BLE001 - the recorded commands' programs alone
        logger.debug("Could not read the pack's toolchain", exc_info=True)
    return programs - {""}


def _tried(repo_root: str | Path) -> dict[str, Any]:
    try:
        found = json.loads((Path(repo_root) / TRIED_FILE).read_text(encoding="utf-8"))
        return found if isinstance(found, dict) else {}
    except (OSError, ValueError):
        return {}


def _keep_tried(repo_root: str | Path, manifests: str, said: str) -> None:
    try:
        path = Path(repo_root) / TRIED_FILE
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"manifests": manifests, "said": said[:2000]}) + "\n", encoding="utf-8")
    except OSError:
        pass


def _the_install_in_words(record: dict[str, Any]) -> str:
    return ", ".join(f"`{' '.join(str(part) for part in argv)}`" for argv in record.get("install") or [] if argv)


def before(repo_root: str | Path, command: Sequence[str], runner: Any = None) -> str:
    """Install the project's dependencies before a stage's command when a manifest changed; the note for the
    command's result, or "". Never raises."""
    try:
        record = contract.read(repo_root)
        if record is None or not record.get("install") or _the_program(command) not in _the_project_s_programs(record):
            return ""
        with _the_lock_for(repo_root):
            now = contract.the_manifests_now(repo_root)
            if not now or now == contract.the_manifests_installed(repo_root) or _tried(repo_root).get("manifests") == now:
                return ""
            notes = contract.install_if_the_manifests_changed(repo_root, runner)
            if not notes:
                return ""
            if contract.the_manifests_installed(repo_root) == now:
                return (f"Before this command the harness installed the project's dependencies with the network "
                        f"({_the_install_in_words(record)}), as it does once whenever a manifest changes; this "
                        "command, like every command but an install, ran without a network on what that install "
                        "fetched.")
            said = "\n".join(str(note) for note in notes)
            _keep_tried(repo_root, now, said)
            return ("Before this command the harness ran the project's install with the network, as it does once "
                    f"whenever a manifest changes, and it did not succeed: {said}\nA build or test command runs "
                    "without a network, so a package that install did not fetch is not there for it. The install "
                    "runs again, before the next command, once a manifest changes.")
    except Exception:  # noqa: BLE001 - the command runs as it would have
        logger.debug("Could not install before a stage's command", exc_info=True)
        return ""


def why_it_could_not_reach_a_registry(repo_root: str | Path, outcome: Any, *, install_said: bool = False) -> str:
    """For a stage's failed command that had no network and could not reach a package registry: what happened, and
    what changes it; "" otherwise. `install_said`: the install before this command already said how it went. Never
    raises."""
    try:
        if not isinstance(outcome, dict) or str(outcome.get("network") or "") != "none":
            return ""
        if str(outcome.get("returncode", "0")) in ("0", "None", ""):
            return ""
        said = "\n".join(str(outcome.get(key) or "") for key in ("stdout", "stderr", "error"))
        if not _COULD_NOT_REACH_A_REGISTRY.search(said):
            return ""
        opening = ("This command had no network, by design: in this sandbox only an install (the package manager's "
                   "install, add or fetch command) is given one. It failed looking for a package that is not on disk. "
                   "Running it again, or with an offline flag, cannot change that. ")
        if install_said:
            return opening.strip()
        record = contract.read(repo_root)
        if record is None or not record.get("install"):
            return opening + "Run the package manager's install or fetch command for the manifest first, then this one."
        now = contract.the_manifests_now(repo_root)
        tried = _tried(repo_root)
        if now and tried.get("manifests") == now and now != contract.the_manifests_installed(repo_root):
            return (opening + "The harness's install of the manifest as it is now did not succeed: "
                    f"{tried.get('said', '')}\nChange the manifest so it installs; the harness installs it again before "
                    "the next command once it changes.")
        if now and now == contract.the_manifests_installed(repo_root):
            return (opening + f"The harness installed what the manifest names ({_the_install_in_words(record)}) after "
                    "its last change, so the package this command looked for is one the manifest does not name, or "
                    "names differently from the code: name it in the manifest and the harness installs it before the "
                    "next command.")
        return opening + (f"The harness installs what the manifest names ({_the_install_in_words(record)}) before the "
                          "next command that runs the project's programs, and before each of its own measurements.")
    except Exception:  # noqa: BLE001 - the result goes as it was
        logger.debug("Could not explain a command that reached no registry", exc_info=True)
        return ""
