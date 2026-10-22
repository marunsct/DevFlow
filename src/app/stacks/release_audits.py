"""A secret scan, a licence listing and a dependency audit for the product at release (plan PN.1, behind `RELEASE_AUDITS`).

A release proved the product works and said nothing about what ships inside
it: a credential written into the code, a dependency whose licence binds the
product, a dependency with a known vulnerability. With the switch on:

- the secret scan reads every file the product tracks for credentials of
  shapes that are never placeholders (cloud and service keys, private key
  blocks); one found holds the release back like a failing criterion, then
  is a gap - a secret in the code is a code fix;
- the licence listing reads the installed packages' own metadata, per
  ecosystem (`_LICENCE_READERS`), writes `docs/third-party-licences.md` and
  records each strong-copyleft dependency as a gap - a licence is the
  owner's decision, not a fix;
- the dependency audit is the ecosystem's own command (`AUDIT_COMMANDS`, per
  language, a pack's `audit` overriding it), added as a step of the
  generated CI: the sandbox gives the network to installs only, so the audit
  runs where it can reach its advisory database.

No check asks a model.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

from app.switches import is_on

logger = logging.getLogger(__name__)

#: `RELEASE_AUDITS` set to on or off overrides this.
ON_BY_DEFAULT = False
#: Where the licence listing is written, in the workspace.
LISTING = "docs/third-party-licences.md"
#: The ecosystem's own audit, by pack language; a pack's `audit` attribute overrides it.
AUDIT_COMMANDS: dict[str, str] = {
    # The product's own environment: the system pip audits only itself.
    "python": ".venv/bin/python -m pip install pip-audit && .venv/bin/python -m pip_audit",
    "javascript": "npm audit --omit=dev --audit-level=high",
    "typescript": "npm audit --omit=dev --audit-level=high",
    "go": "go run golang.org/x/vuln/cmd/govulncheck@latest ./...",
    "rust": "cargo install cargo-audit --locked && cargo audit",
    "ruby": "gem install bundler-audit && bundle-audit check --update",
    "php": "composer audit",
    "java": "mvn -q -B org.owasp:dependency-check-maven:check",
    "csharp": "dotnet list package --vulnerable --include-transitive",
}
#: Credential shapes that are never a placeholder, by what they are.
SECRET_SHAPES: dict[str, re.Pattern[str]] = {
    "a private key": re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"),
    "a cloud access key": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "a source-host token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "a chat-service token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "a live payment key": re.compile(r"\b[rs]k_live_[0-9A-Za-z]{20,}\b"),
    "a cloud API key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
}
#: Licences that bind a product that links them, read from the identifier or name.
_STRONG_COPYLEFT = re.compile(r"\bA?GPL(?!-?2\.0-with)|\bSSPL\b|Affero|(?<!Lesser )General Public License", re.I)
_LESSER = re.compile(r"\bLGPL\b|Lesser General", re.I)
_MOST_BYTES = 1_000_000
#: A file that documents a setting's shape, never a credential.
_AN_EXAMPLE_FILE = re.compile(r"\.(?:example|sample|template|dist)$|^example\.|^sample\.", re.I)
_NOT_THE_PRODUCT = frozenset({".agent-home", ".harness", ".git", "node_modules", ".venv", "vendor", "target"})


def enabled() -> bool:
    return is_on("RELEASE_AUDITS", ON_BY_DEFAULT)


def audit_command(pack: Any) -> str:
    """The dependency audit CI runs for this pack, or ""."""
    own = getattr(pack, "audit", None)
    if isinstance(own, str):
        return own
    return AUDIT_COMMANDS.get(str(getattr(pack, "language", "") or ""), "")


def _tracked(root: Path) -> list[str]:
    try:
        result = subprocess.run(["git", "-C", str(root), "ls-files", "-co", "--exclude-standard"],
                                capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return [line for line in result.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.SubprocessError):
        pass
    return []


def _a_placeholder(found: str) -> bool:
    """A documented sample or a filler: one character repeated, `xxxx`, `your-`, `changeme`, `EXAMPLE`."""
    body = re.sub(r"^(?:AKIA|ASIA|gh[pousr]_|xox[abprs]-|[rs]k_live_|AIza)", "", found)
    if len(set(body.lower())) <= 1:
        return True
    return bool(re.search(r"(?i)xxxx|your[-_]|changeme|EXAMPLE|placeholder", found))


def secrets_found(repo_root: str | Path) -> list[str]:
    """One line per file holding a credential, saying what and where; [] when off or none. Never raises."""
    if not enabled():
        return []
    root, found = Path(repo_root), []
    for relative in _tracked(root):
        # The harness's and the toolchains' own folders, never the product: a
        # seeded workspace has no harness `.gitignore`, and a module cache holds
        # its libraries' test keys.
        parts = relative.split("/")
        if any(part in _NOT_THE_PRODUCT for part in parts) or _AN_EXAMPLE_FILE.search(parts[-1]):
            continue
        path = root / relative
        try:
            if not path.is_file() or path.stat().st_size > _MOST_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for what, shape in SECRET_SHAPES.items():
            match = next((m for m in shape.finditer(text) if not _a_placeholder(m.group(0))), None)
            if match:
                line = text.count("\n", 0, match.start()) + 1
                found.append(f"`{relative}` line {line} holds {what}: a credential must come from the "
                             "environment, never from the code. Remove it and read it from a variable.")
                break
    return found


def _python(project: Path) -> dict[str, str]:
    licences = {}
    for metadata in sorted(project.glob(".venv/lib/python*/site-packages/*.dist-info/METADATA")):
        try:
            text = metadata.read_text(encoding="utf-8", errors="replace").split("\n\n", 1)[0]
        except OSError:
            continue
        fields = [line.split(":", 1) for line in text.splitlines() if ":" in line]
        name = next((v.strip() for k, v in fields if k == "Name"), metadata.parent.name)
        expression = next((v.strip() for k, v in fields if k == "License-Expression"), "")
        classifier = next((v.rsplit("::", 1)[-1].strip() for k, v in fields
                           if k == "Classifier" and v.strip().startswith("License ::")), "")
        short = next((v.strip() for k, v in fields if k == "License" and 0 < len(v.strip()) <= 60), "")
        licences[name] = expression or classifier or short or "not stated"
    return licences


def _node(project: Path) -> dict[str, str]:
    licences = {}
    for manifest in sorted([*project.glob("node_modules/*/package.json"), *project.glob("node_modules/@*/*/package.json")]):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        licence = data.get("license")
        if isinstance(licence, dict):
            licence = licence.get("type")
        licences[str(data.get("name") or manifest.parent.name)] = str(licence or "not stated")
    return licences


#: How each ecosystem's installed packages state their licence, by the directory they are installed in.
_LICENCE_READERS: dict[str, Callable[[Path], dict[str, str]]] = {".venv": _python, "node_modules": _node}


def licences(repo_root: str | Path, project: str = "") -> dict[str, str]:
    """Installed package -> licence, from the packages' own metadata. Never raises."""
    base, found = Path(repo_root) / project, {}
    for directory, reader in _LICENCE_READERS.items():
        if (base / directory).is_dir():
            try:
                found.update(reader(base))
            except Exception:  # noqa: BLE001 - one ecosystem unread is not a failed release
                logger.debug("Could not read the licences under %s", directory, exc_info=True)
    return found


def licence_gaps(repo_root: str | Path) -> list[str]:
    """Write the listing; the strong-copyleft dependencies as gaps. [] when off. Never raises."""
    if not enabled():
        return []
    try:
        from app.stacks import contract

        project = str((contract.read(repo_root) or {}).get("project") or "")
        listed = licences(repo_root, project)
        if not listed:
            return []
        target = Path(repo_root) / LISTING
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# Third-party licences\n\nRead from each installed package's own metadata at release.\n\n"
                          "| Package | Licence |\n|---|---|\n"
                          + "".join(f"| {name} | {licence.replace('|', '/')} |\n" for name, licence in sorted(listed.items())),
                          encoding="utf-8")
        binding = sorted(name for name, licence in listed.items()
                         if _STRONG_COPYLEFT.search(licence) and not _LESSER.search(licence))
        if not binding:
            return []
        return [f"Ships {len(binding)} dependenc{'y' if len(binding) == 1 else 'ies'} under a strong-copyleft "
                f"licence, which binds the product's own licence: {', '.join(binding[:10])} (see `{LISTING}`)."]
    except Exception:  # noqa: BLE001
        logger.warning("Could not list the product's licences", exc_info=True)
        return []


__all__ = ["AUDIT_COMMANDS", "LISTING", "ON_BY_DEFAULT", "SECRET_SHAPES", "audit_command", "enabled",
           "licence_gaps", "licences", "secrets_found"]
