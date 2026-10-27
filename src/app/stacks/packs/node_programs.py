"""A command-line program or a library in JavaScript or TypeScript, on Node alone.

No framework and no build: Node runs TypeScript itself (type stripping, so only
erasable syntax - no `enum`, no `namespace`, no parameter properties), and its
own test runner writes JUnit. Unit tests import the code; acceptance tests meet
the product the way its user does - a program run as its own process in an
empty directory, a library imported by its package name through `exports`, so
only its public interface is reachable.
"""

from __future__ import annotations

from app.stacks import StackPack
from app.stacks.packs import _javascript as js

TYPESCRIPT = "~6.0.2"
TYPES_NODE = "^24.0.0"


def _script(directory: str, report: str, extension: str) -> str:
    return (
        f"mkdir -p test-results && node --test {js.TEST_TIMEOUT} --test-reporter=spec --test-reporter-destination=stdout "
        f"--test-reporter=junit --test-reporter-destination=test-results/{report} "
        f"'{directory}/**/*.test.{extension}'"
    )


TSCONFIG = """{
  "compilerOptions": {
    "target": "es2024",
    "module": "nodenext",
    "moduleResolution": "nodenext",
    "strict": true,
    "noEmit": true,
    "allowImportingTsExtensions": true,
    "erasableSyntaxOnly": true,
    "verbatimModuleSyntax": true,
    "skipLibCheck": true,
    "types": ["node"]
  },
  "include": ["bin", "src", "tests", "acceptance"]
}
"""

CLI = """import { parseArgs } from 'node:util';

/**
 * Runs the program. `argv` is what follows the program's name; the result is
 * its exit status. Output goes to `io.stdout` and `io.stderr`, so a unit test
 * can pass its own.
 */
export async function main(argv%(argv_type)s, io%(io_type)s = { stdout: process.stdout, stderr: process.stderr })%(result_type)s {
  const { values } = parseArgs({
    args: argv,
    options: { version: { type: 'boolean' }, help: { type: 'boolean', short: 'h' } },
    allowPositionals: true,
    strict: false,
  });
  if (values.version) {
    io.stdout.write('{{project}} 0.1.0\\n');
    return 0;
  }
  if (values.help) {
    io.stdout.write('Usage: {{project}} [options]\\n');
    return 0;
  }
  return 0;
}
"""

BIN = """#!/usr/bin/env node
import { main } from '../src/cli.%(ext)s';

process.exitCode = await main(process.argv.slice(2));
"""

RUN_CLI = """// Kept by the harness: acceptance tests run the program through this, the way a user does.
import { spawnSync } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const program = fileURLToPath(new URL('../bin/{{project}}.%(ext)s', import.meta.url));

/**
 * Runs the program with `args` as its own process, in a new empty directory
 * (also its HOME) unless `cwd` names one, and returns
 * `{ code, stdout, stderr, dir }`. Pass `dir` back as `cwd` to run it again
 * in the same place - that is how a test proves something persists.
 */
export function runCli(args%(args_type)s = [], options%(options_type)s = {}) {
  const dir = options.cwd ?? mkdtempSync(path.join(tmpdir(), '{{project}}-'));
  const finished = spawnSync(process.execPath, [program, ...args], {
    cwd: dir,
    input: options.input,
    env: { ...process.env, HOME: dir, ...options.env },
    encoding: 'utf8',
    timeout: 60_000,
  });
  return { code: finished.status, stdout: finished.stdout, stderr: finished.stderr, dir };
}
"""

LIBRARY = """/** {{title}}: everything exported here is the library's public interface. */

export const VERSION = '0.1.0';
"""

SMOKE_CLI_UNIT = """import { test } from 'node:test';
import assert from 'node:assert/strict';
import { main } from '../src/cli.%(ext)s';

test('the version option exits cleanly', async () => {
  let out = '';
  const code = await main(['--version'], { stdout: { write: (text%(text_type)s) => { out += text; return true; } }, stderr: process.stderr }%(cast)s);
  assert.equal(code, 0);
  assert.match(out, /0\\.1\\.0/);
});
"""

SMOKE_CLI_ACCEPTANCE = """import { test } from 'node:test';
import assert from 'node:assert/strict';
import { runCli } from './run-cli.%(ext)s';

test('the program runs', () => {
  const finished = runCli(['--version']);
  assert.equal(finished.code, 0, finished.stderr);
  assert.match(finished.stdout, /{{project}}/);
});
"""

SMOKE_LIBRARY_UNIT = """import { test } from 'node:test';
import assert from 'node:assert/strict';
import { VERSION } from '../src/index.%(ext)s';

test('the library says its version', () => {
  assert.equal(VERSION, '0.1.0');
});
"""

SMOKE_LIBRARY_ACCEPTANCE = """import { test } from 'node:test';
import assert from 'node:assert/strict';
import { VERSION } from '{{project}}';

test('the library is imported by its name', () => {
  assert.equal(VERSION, '0.1.0');
});
"""

NAMING = """Name each test after the criterion it proves, with the id in its title:
`test('[AC-3] adds an item', ...)` (a test proving two: `[AC-3][AC-4]`). A test
with no criterion id in its name proves nothing the harness can count."""

TS_NOTE = """ Node runs the TypeScript itself, stripping the types: import files with
their `.ts` extension, and use only syntax that erases - no `enum`, `namespace` or
constructor parameter properties (use a union of literals and plain fields)."""


def _package_json(kind: str, typescript: bool) -> str:
    ext = "ts" if typescript else "js"
    unit, acceptance = _script("tests", "unit.xml", ext), _script("acceptance", "acceptance.xml", ext)
    entry = (
        f'  "bin": {{ "{{{{project}}}}": "bin/{{{{project}}}}.{ext}" }},\n' if kind == "cli"
        else f'  "exports": "./src/index.{ext}",\n'
    )
    dev = (
        f'  "devDependencies": {{\n    "@types/node": "{TYPES_NODE}",\n    "typescript": "{TYPESCRIPT}"\n  }},\n'
        if typescript else ""
    )
    return (
        "{\n"
        '  "name": "{{project}}",\n'
        '  "version": "0.1.0",\n'
        '  "private": true,\n'
        '  "type": "module",\n'
        f"{entry}"
        f'  "engines": {{ "node": ">={js.NODE_MAJOR}" }},\n'
        '  "scripts": {\n'
        f'    "test": "{unit}",\n'
        f'    "test:acceptance": "{acceptance}"\n'
        "  },\n"
        f"{dev}"
        '  "dependencies": {}\n'
        "}\n"
    ), unit, acceptance


def _pack(kind: str, typescript: bool) -> StackPack:
    ext = "ts" if typescript else "js"
    language = "typescript" if typescript else "javascript"
    named = "TypeScript" if typescript else "JavaScript"
    types = {
        "argv_type": ": string[]" if typescript else "",
        "io_type": ": { stdout: { write(text: string): unknown }; stderr: { write(text: string): unknown } }" if typescript else "",
        "result_type": ": Promise<number>" if typescript else "",
        "args_type": ": string[]" if typescript else "",
        "options_type": ": { cwd?: string; input?: string; env?: Record<string, string> }" if typescript else "",
        "text_type": ": string" if typescript else "",
        "cast": "",
        "ext": ext,
    }
    manifest, unit_script, acceptance_script = _package_json(kind, typescript)
    files = {"package.json": manifest, ".gitignore": js.GITIGNORE}
    if typescript:
        files["tsconfig.json"] = TSCONFIG
    if kind == "cli":
        files.update({
            f"bin/{{{{project}}}}.{ext}": BIN % types,
            f"src/cli.{ext}": CLI % types,
            f"acceptance/run-cli.{ext}": RUN_CLI % types,
        })
        kept = (f"acceptance/run-cli.{ext}",)
        smoke = {
            f"tests/scaffold-smoke.test.{ext}": SMOKE_CLI_UNIT % types,
            f"acceptance/scaffold-smoke.test.{ext}": SMOKE_CLI_ACCEPTANCE % types,
        }
        guide = (
            f"The program is {named} on Node alone. Its entry point is `main(argv, io)` in "
            f"`src/cli.{ext}`, which returns the exit status; `bin/{{{{project}}}}.{ext}` runs it. "
            "Parse options with `parseArgs` from `node:util`, write output through `io.stdout` "
            "and errors through `io.stderr`, and return a non-zero status on failure. Unit "
            f"tests go in `tests/`, named `<module>.test.{ext}`, using `node:test` and "
            "`node:assert/strict`; a test calls `main([...], io)` with an `io` that collects "
            "what is written. Run them with `npm test`. Install a dependency with "
            "`npm install <name>`." + (TS_NOTE if typescript else "")
        )
        acceptance_guide = (
            f"Acceptance tests go in `acceptance/`, named `<feature>.test.{ext}`, using `node:test` "
            f"and `node:assert/strict`. Import `runCli` from `./run-cli.{ext}` and run the program "
            "exactly as a user would: `const finished = runCli(['add', 'Buy milk'])`, then check "
            "`finished.code`, `finished.stdout` and `finished.stderr`. Each call runs in a new "
            "empty directory, which is also the program's HOME; to prove something persists, "
            "run it again with `{ cwd: finished.dir }`. Never import the program's modules here.\n"
            + NAMING
        )
        frameworks = ("commander", "yargs", "parseargs", "node", "standard library")
        testing = "node:test for unit tests, node:test running the program as a process for acceptance tests"
    else:
        files[f"src/index.{ext}"] = LIBRARY
        kept = ()
        smoke = {
            f"tests/scaffold-smoke.test.{ext}": SMOKE_LIBRARY_UNIT % types,
            f"acceptance/scaffold-smoke.test.{ext}": SMOKE_LIBRARY_ACCEPTANCE % types,
        }
        guide = (
            f"The library is {named} on Node alone. Its public interface is what "
            f"`src/index.{ext}` exports (the package's `exports`); other modules in `src/` are "
            f"internal. Unit tests go in `tests/`, named `<module>.test.{ext}`, using `node:test` "
            "and `node:assert/strict`, and import the modules directly. Run them with `npm test`. "
            "Install a dependency with `npm install <name>`." + (TS_NOTE if typescript else "")
        )
        acceptance_guide = (
            f"Acceptance tests go in `acceptance/`, named `<feature>.test.{ext}`, using `node:test` "
            "and `node:assert/strict`. Import the library by its package name, exactly as a user "
            "would - `import { parse } from '{{project}}'` - never from a path into `src/`: only "
            "what the package exports is its interface.\n" + NAMING
        )
        frameworks = ("node", "standard library")
        testing = "node:test for unit tests, node:test importing the package by its name for acceptance tests"
    title = "Command-line program" if kind == "cli" else "Library"
    return StackPack(
        name=f"{'typescript' if typescript else 'node'}-{kind}",
        title=f"{title} in {named} on Node",
        kind=kind,
        language=language,
        frameworks=frameworks,
        files=files,
        install=js.INSTALL,
        unit_test=js.UNIT_TEST,
        acceptance_test=js.ACCEPTANCE_TEST,
        unit_report="test-results/unit.xml",
        acceptance_report="test-results/acceptance.xml",
        unit_dir="tests",
        acceptance_dir="acceptance",
        acceptance_pattern=f"*.test.{ext}",
        unit_pattern=f"*.test.{ext}",
        kept_files=kept,
        kept_scripts={"test": unit_script, "test:acceptance": acceptance_script},
        smoke_files=smoke,
        guide=guide,
        acceptance_guide=acceptance_guide,
        stack={
            "language": named,
            "framework": "None (Node.js standard library)",
            "frontend_framework": "",
            "testing_framework": testing,
        },
        check_families=frozenset({"javascript", *({"typescript"} if typescript else set())}),
        code_runs_in="node",
        ci_setup=js.CI_SETUP,
    )


NODE_CLI = _pack("cli", typescript=False)
NODE_LIBRARY = _pack("library", typescript=False)
TYPESCRIPT_CLI = _pack("cli", typescript=True)
TYPESCRIPT_LIBRARY = _pack("library", typescript=True)
