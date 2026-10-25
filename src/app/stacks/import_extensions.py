"""A relative import names the file Node will load: the harness adds the `.ts` the model leaves off.

The `node-hono-native-api` pack runs `.ts` files with Node itself, which resolves a relative import exactly as written:
`from './routes/notes'` is `ERR_MODULE_NOT_FOUND` where `./routes/notes.ts` exists. Measured on the first run of that pack:
its guide says to name the extension, the model wrote `./middleware/bodyLimit` anyway, and the service did not start in
three rounds. Which file an extensionless import means is not a judgement: if `<spec>.ts` (or `<spec>/index.ts`) exists, that
is the file. So this rewrites it before the harness measures the product, as it puts back a kept configuration file.
TypeScript's own advice for the same error is `.js`, which would not load here; a `.js` import whose `.ts` file exists is
rewritten too.
"""
from __future__ import annotations

import re
from pathlib import Path

#: `from './x'`, `import './x'`, `import('./x')`, `export ... from './x'`: the opening, the quote, the relative path.
_RELATIVE = re.compile(r"""(\bfrom\s*|\bimport\s*\(?\s*)(['"])(\.{1,2}(?:/[^'"\n]*)?)\2""")
_KEEPS_ITS_NAME = (".ts", ".json", ".mjs", ".cjs", ".node", ".mts", ".cts")


def _named(importer: Path, spec: str) -> str:
    """The specifier with the extension Node needs, or the same one when no `.ts` file is what it means."""
    if spec.endswith(_KEEPS_ITS_NAME):
        return spec
    base = spec[:-3] if spec.endswith(".js") else spec
    target = (importer.parent / base)
    if Path(f"{target}.ts").is_file():
        return f"{base}.ts"
    if target.is_dir() and (target / "index.ts").is_file():
        return f"{base.rstrip('/')}/index.ts"
    return spec


def put_the_extensions_on(project_root: Path, extension: str = ".ts") -> list[str]:
    """Rewrite the relative imports of the project's TypeScript files; one line saying what was done, or []."""
    if extension != ".ts" or not project_root.is_dir():
        return []
    changed_files = 0
    changed_imports = 0
    for folder in ("src", "test"):
        for path in sorted((project_root / folder).rglob("*.ts")) if (project_root / folder).is_dir() else []:
            if "node_modules" in path.parts:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            count = 0

            def fix(match: re.Match) -> str:
                nonlocal count
                spec = match.group(3)
                named = _named(path, spec)
                if named == spec:
                    return match.group(0)
                count += 1
                return f"{match.group(1)}{match.group(2)}{named}{match.group(2)}"

            rewritten = _RELATIVE.sub(fix, text)
            if count:
                try:
                    path.write_text(rewritten, encoding="utf-8")
                except OSError:
                    continue
                changed_files += 1
                changed_imports += count
    if not changed_imports:
        return []
    return [f"{changed_imports} relative import(s) in {changed_files} file(s) now name the `.ts` file they mean, as Node "
            "needs; the harness added the extension."]
