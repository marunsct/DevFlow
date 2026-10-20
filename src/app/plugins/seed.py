"""Seed data for the `plugin_instructions` table: framework and language guidance.

This is the only place language- or framework-specific instructions for the
agents belong. `PluginStore` writes these rows at start-up and
`app.plugins.middleware` appends the rows that match the run's technology stack
to every agent's system prompt, so an agent building in Go reads Go guidance
and never JavaScript's.

The code that builds prompts stays language-agnostic: when a rule needs a
concrete tool, command or file name, the concrete part lives here, under the
language or framework it belongs to.

Keys are the lower-case names the stack extractor produces from
`docs/technology_stack.md` - a language (`javascript`, `python`, `go`) or a
framework (`react`, `django`). Editing a row in the database is safe: seeding
refreshes a row only while it still holds exactly the text it was seeded with,
so a manual edit is never overwritten. See `PluginStore`.
"""

from __future__ import annotations

SEED_INSTRUCTIONS: dict[str, str] = {
    "typescript": (
        "You are working in a TypeScript/JavaScript environment.\n"
        "- Dependency Management: Use `npm`, `pnpm` or `yarn` (ensure you respect lockfiles if present).\n"
        "- Linting & Formatting: Rely on standard tools like ESLint and Prettier to enforce styling and catch CommonJS vs ES Modules compatibility issues.\n"
        "- Compilation: Use `tsc` (TypeScript Compiler) for type checking. Ensure strict mode is enabled where possible.\n"
        "- Do not guess import syntax errors statically; run tests or the linter to reveal them."
    ),
    "python": (
        "You are working in a Python environment.\n"
        "- Dependency Management: Use `pip`, `poetry`, or `uv`. Ensure dependencies are pinned appropriately.\n"
        "- Environments: Do not install globally. Always use a virtual environment (`venv`, `.venv`, or Poetry's env).\n"
        "- Linting & Formatting: Rely on tools like `ruff`, `flake8`, `black`, and `mypy` for static analysis and type checking.\n"
        "- Execution: Run code locally via standard entrypoints (e.g., `python -m pytest` for testing)."
    ),
    "react": (
        "You are working with React.\n"
        "- Component Patterns: Follow functional component patterns exclusively. Use Hooks (useState, useEffect, custom hooks, useMemo, useCallback) for state management.\n"
        "- Architecture: Separate state logic from presentation. Avoid deeply nested prop-drilling by utilizing Context API or dedicated state libraries where appropriate.\n"
        "- Effects: Ensure cleanup functions are returned in `useEffect` where subscriptions or timers are used to prevent memory leaks.\n"
        "- Performance: Avoid unnecessary re-renders. Use `React.memo` where required for heavy components."
    ),
    "node": (
        "You are working with Node.js.\n"
        "- Async Flow: Use `async/await` extensively. Avoid raw Promises or callbacks unless absolutely necessary.\n"
        "- Error Handling: Always wrap async route handlers with `try/catch` or use an async wrapper to pass errors to the global error middleware.\n"
        "- Module System: Be explicit about `require()` vs `import`. The default environment may be CJS unless `type: module` is in package.json."
    ),
    "postgres": (
        "You are working with PostgreSQL.\n"
        "- Connection Management: Connections must be pooled. Ensure every connection borrowed from the pool is returned gracefully in a `finally` block.\n"
        "- Transactions: Wrap write operations in transactions. If an error occurs, explicitly `rollback()` the transaction before closing or returning the connection.\n"
        "- Safety: Never construct SQL strings via f-strings or string concatenation. Always use bound parameters (`%s` or `$1` depending on driver) to prevent SQL injection.\n"
        "- Indexing: Ensure foreign keys and heavily queried columns are indexed.\n"
        "- Here: no PostgreSQL server runs while the product is built and tested. Keep data access behind an adapter, "
        "default to the embedded file database under `DATA_DIR`, and take PostgreSQL from one connection setting only "
        "when the brief names it."
    ),
    "go": (
        "You are working in a Go environment.\n"
        "- Dependency Management: Use `go mod` for dependency tracking.\n"
        "- Error Handling: Explicitly check `err != nil`. Do not swallow errors. Return descriptive errors wrapping the original error using `fmt.Errorf` with `%w`.\n"
        "- Concurrency: Use goroutines and channels carefully. Watch out for race conditions; utilize `sync.Mutex` or `sync.WaitGroup` appropriately. Ensure channels are closed properly to prevent memory leaks."
    ),
    "rust": (
        "You are working in a Rust environment.\n"
        "- Dependency Management: Use `cargo` for package management and builds.\n"
        "- Memory Safety: Follow strict ownership and borrowing rules. Avoid `unsafe` blocks unless interfacing with FFI.\n"
        "- Error Handling: Use `Result` and `Option` types with pattern matching or the `?` operator instead of panics.\n"
        "- Best Practices: Follow `clippy` suggestions for idiomatic Rust code."
    ),
    "vue": (
        "You are working with Vue.js.\n"
        "- Composition API: Prefer the Composition API (`<script setup>`) over the Options API for better TypeScript support and logic reuse.\n"
        "- State Management: Use Pinia instead of Vuex for global state.\n"
        "- Components: Keep components scoped and modular. Use scoped CSS or CSS Modules."
    ),
    "angular": (
        "You are working with Angular.\n"
        "- Architecture: Follow strict modular architecture. Use standalone components if working with Angular 14+.\n"
        "- RxJS: Manage asynchronous streams using RxJS observables. Always unsubscribe (e.g., using `takeUntil` or the `AsyncPipe`) to prevent memory leaks.\n"
        "- Services: Keep business logic in injectable services rather than components."
    ),
    "nextjs": (
        "You are working with Next.js.\n"
        "- App Router: If using the App Router (`app/` directory), default to Server Components. Use `'use client'` only for interactive components.\n"
        "- Data Fetching: Leverage Next.js built-in `fetch` with caching configurations (`force-cache`, `no-store`, `revalidate`) instead of client-side fetching where possible.\n"
        "- Optimization: Always use `next/image` and `next/link` for optimized assets and routing."
    ),
    "django": (
        "You are working with Django.\n"
        "- Architecture: Follow the MTV (Model-Template-View) pattern strictly. Keep views thin and models fat (put business logic on model methods or services).\n"
        "- ORM: Use Django's ORM securely. Beware of N+1 query problems; utilize `select_related` and `prefetch_related`.\n"
        "- Migrations: Never manually alter the database schema; always use `makemigrations` and `migrate`."
    ),
    "flask": (
        "You are working with Flask.\n"
        "- Architecture: Use Blueprints to organize your application into distinct modules.\n"
        "- Application Factory: Implement the application factory pattern for better testing and configuration management.\n"
        "- Contexts: Understand and properly utilize application and request contexts. Avoid global state."
    ),
    "fastapi": (
        "You are working with FastAPI.\n"
        "- Type Hints: Strictly use Pydantic models and Python type hints for request/response validation.\n"
        "- Async Flow: Use `async def` for async I/O operations (like database calls). For synchronous blocking tasks, use standard `def` so they run in a threadpool.\n"
        "- Dependency Injection: Use FastAPI's `Depends` for reusable logic like authentication and database sessions."
    ),
    "java": (
        "You are working in a Java environment.\n"
        "- Build Tools: Use Maven or Gradle to manage dependencies and build life cycles.\n"
        "- Object-Oriented Design: Adhere to SOLID principles. Prefer composition over inheritance.\n"
        "- Modern Features: Utilize Streams, Lambdas, and Optional types introduced in Java 8+ instead of legacy patterns.\n"
        "- Concurrency: Prefer the `java.util.concurrent` package (e.g., `ExecutorService`, `CompletableFuture`) over manual thread management."
    ),
    "spring": (
        "You are working with Spring Boot.\n"
        "- Architecture: Use the layered architecture (Controller -> Service -> Repository).\n"
        "- Dependency Injection: Prefer constructor injection over field injection (`@Autowired`) for better testability and immutability.\n"
        "- Data Access: Use Spring Data JPA/JDBC. Avoid raw SQL strings where repositories provide the necessary interface.\n"
        "- Configuration: Favor Java-based configuration or `application.yml`/`application.properties` over XML."
    ),
    "ruby": (
        "You are working in a Ruby environment.\n"
        "- Dependency Management: Use Bundler (`Gemfile` and `Gemfile.lock`).\n"
        "- Idioms: Write idiomatic Ruby (e.g., use blocks, `map`, `select`, `reduce` instead of `for` loops).\n"
        "- Linting: Rely on `RuboCop` for static analysis and style guidelines."
    ),
    "rails": (
        "You are working with Ruby on Rails.\n"
        "- Architecture: Strictly follow MVC and the \"Skinny Controller, Fat Model\" design.\n"
        "- ActiveRecord: Protect against SQL injection by using parameterized queries. Fix N+1 queries using `.includes()`.\n"
        "- Conventions: Favor \"Convention over Configuration\". Stick to Rails standard naming and routing conventions."
    ),
    "csharp": (
        "You are working in a C# environment.\n"
        "- Dependency Management: Use NuGet and `dotnet` CLI.\n"
        "- Asynchronous Programming: Heavily utilize `async` and `await` with `Task`. Avoid blocking calls like `.Result` or `.Wait()`.\n"
        "- Features: Use modern C# features like records, pattern matching, and nullable reference types."
    ),
    "dotnet": (
        "You are working with .NET (ASP.NET Core).\n"
        "- Dependency Injection: Use the built-in Microsoft.Extensions.DependencyInjection container.\n"
        "- Configuration: Rely on `appsettings.json` and the Options pattern.\n"
        "- Entity Framework Core: Keep tracking behavior in mind. Use `.AsNoTracking()` for read-only queries."
    ),
    "php": (
        "You are working in a PHP environment.\n"
        "- Dependency Management: Use Composer (`composer.json`).\n"
        "- Types: Utilize strict typing (`declare(strict_types=1);`) and robust type hinting (including union and intersection types) for all functions.\n"
        "- Standards: Follow PSR-12 coding standards and PSR-4 for autoloading."
    ),
    "laravel": (
        "You are working with Laravel.\n"
        "- Architecture: Follow MVC. Place business logic in Services or Action classes rather than bloating Controllers.\n"
        "- Eloquent ORM: Avoid N+1 issues using eager loading (`with()`). Guard against mass-assignment vulnerabilities using `$fillable`.\n"
        "- Routing: Keep web routes distinct from API routes. Use Form Requests for validation."
    ),
    "kotlin": (
        "You are working in a Kotlin environment.\n"
        "- Build Tools: Use Gradle (Kotlin DSL preferred) or Maven.\n"
        "- Concurrency: Prefer Kotlin Coroutines (`suspend`, `launch`, `async`) over raw threads or RxJava for asynchronous programming.\n"
        "- Null Safety: Leverage Kotlin's null safety. Avoid the `!!` operator; use safe calls (`?.`) and the Elvis operator (`?:`)."
    ),
    "swift": (
        "You are working in a Swift environment.\n"
        "- Dependency Management: Use Swift Package Manager (SPM).\n"
        "- Concurrency: Use modern Swift concurrency (`async`/`await`, Actors, and Task groups) instead of GCD or completion handlers.\n"
        "- Safety: Leverage optionals and `guard` statements to handle missing values gracefully. Avoid force unwrap (`!`)."
    )
}


#: Where a project's notes on setting its test runners up are kept: under the
#: same key with this on the end. A project a stack pack scaffolded has its
#: runners, configuration and scripts set up and kept by the harness, so
#: `app.plugins.middleware` leaves these rows out there - they told one run's
#: agents to install Playwright, declare a `webServer` and never use jsdom,
#: beside a pack that had done the first two and provided the third.
SETUP = ":setup"

#: How a page that runs in a browser is tested. Attached to every key that means
#: "this product renders a page". Moved here from `TESTABILITY_RULE` and
#: `TESTING_DEPENDENCY_RULE`, where it was appended to every run whatever its
#: stack, so a Go service's agents were told how to configure Playwright.
_BROWSER_PAGE_TESTING = """Testing a page that runs in a browser:
- The thing that breaks a headless test is a module that reads or writes the DOM
  while it is being loaded. It reaches for `document`, `window` or `localStorage`
  at module scope, so the import itself runs that code and throws before any of
  your assertions are reached.
- Do the DOM wiring in one `init()` that the page calls, guarded so importing the
  file does not run it: `if (typeof document !== 'undefined') init();`. A bare
  `init();` at the end of the file is the whole problem.
- THE LOGIC MUST LIVE IN A FILE A TEST CAN OPEN. JavaScript inside a `<script>`
  tag in your HTML is unreachable: no runner can import it, so the only way to
  test it is to copy it, and a copy passes whatever your code does. One `app.js`
  beside `index.html` is still a single-page application with no build step.
- Prove what a user does on the page end-to-end with Playwright
  (`@playwright/test`) - a real headless browser runs here. A DOM inside Node,
  such as jsdom, serves unit tests of one module at a time: it lays nothing out
  and no user drives it, so passing there does not show the page works.
- Do NOT run a static server as a command of its own - it never exits, it is
  refused, and nothing connects to it.
- EVERY PLAYWRIGHT TEST ALREADY STARTS WITH EMPTY STORAGE: each gets a fresh
  browser context. Do not clear `localStorage` yourself, and never in
  `page.addInitScript` - that script runs before EVERY navigation, reloads
  included, so a test that reloads to check persistence wipes the data it is
  checking and fails however the app behaves.
- `toBeVisible()` fails on an element with no size, such as an empty placeholder
  `<div>`. For an element that may be empty, assert `toBeAttached()` or
  `toHaveCount(1)` instead."""

#: How a project's browser tests are set up, where the harness did not.
_BROWSER_PAGE_SETUP = """Setting up a page's tests:
- Install Playwright with `npm i -D @playwright/test` and
  `npx playwright install chromium`, run it with `npx playwright test`, and use a
  BUILT-IN reporter - `--reporter=line` or `--reporter=list`. Do NOT pass
  `--reporter=tap`: Playwright resolves that to an npm package called `tap`,
  which is not installed, and the suite dies with "Cannot find module 'tap'".
- A unit test that needs a DOM gets a real one from its runner - jsdom installed
  with `-D` and set up once for every test file - never a `global.document`
  written by hand.
- A PLAYWRIGHT TEST CANNOT OPEN THE PAGE WITH `file://`. Chromium blocks an ES
  module script loaded from a `file://` URL on CORS grounds, so the page loads,
  the script never runs, and the test times out. Load it over
  `http://localhost:<port>` and let Playwright manage the server: declare a
  `webServer` in `playwright.config.ts` and one `npx playwright test` starts
  it, runs the suite and stops it:
      webServer: {
        command: 'npx serve .',       // or `node server.mjs`
        url: 'http://localhost:3000',
        reuseExistingServer: false,
      }
  Its `cwd`, if you give one, is relative to the config file, not to where you
  ran the command. With the config inside the project directory, leave `cwd`
  out: `cwd: '<project-dir>'` points at a folder inside itself that does not
  exist, and Node reports that as `spawn /bin/sh ENOENT` - naming the shell,
  which is present - so the suite looks unrunnable when one line is wrong."""

#: How JavaScript and TypeScript modules are tested, and where their test-only
#: packages go. Moved here from `TESTABILITY_RULE` and `TESTING_DEPENDENCY_RULE`.
_JAVASCRIPT_TESTING = """Testing JavaScript and TypeScript:
- A TEST SCRIPT MUST EXIT. `vitest` on its own starts watch mode and never
  returns; the script is `vitest run`. Likewise `jest --watch` is for a
  terminal, not for `npm test`. A command that never exits is killed at the
  time limit and reports nothing.
- IF YOU USE `export`, DECLARE IT. A `.js` file is CommonJS unless something says
  otherwise, so a test importing it gets "does not provide an export named ...".
  Ship a `package.json` containing `{"type": "module"}` beside it, or name the
  files `.mjs`. Neither installs anything, and `export` is not a dependency.
- THE SAME `package.json` MUST SAY HOW TO RUN THE TESTS, with the unit runner
  this project's stack names and no other: `"scripts": {"test": "..."}`. Without
  it `npm test` answers "missing script: test" and the project reads as having
  no tests. One unit runner per project: a test written for a second one throws
  under the first, and changing the script to suit it strands the rest.
- WHAT EACH UNIT RUNNER NEEDS TO RUN ES MODULES (`import`/`export`):
  - Node's own, `node --test <your test files>`: nothing. It ships with Node -
    nothing to install, no dependency, no lines of product code - and runs ES
    modules as they are. Tests import `test` from 'node:test' and `assert`
    from 'node:assert'.
  - Vitest, `vitest run`: nothing. It runs ES modules as they are.
  - Jest: a flag, and it is Node's. Jest loads test files as CommonJS, so in a
    project with `"type": "module"` every `import` in a test is "SyntaxError:
    Cannot use import statement outside a module" until Jest is started as
        "test": "node --experimental-vm-modules node_modules/jest/bin/jest.js"
    with `"transform": {}` in Jest's configuration. `experimentalVmModules`,
    `extensionsToTreatAsEsm` and `globals` in jest.config do NOT do this, and
    `babel-jest` is not needed. Under that flag `jest.fn()` needs
    `import { jest } from '@jest/globals'`; `test` and `expect` are already
    there. A DOM under Jest is a separate package, `jest-environment-jsdom`.
- TWO RUNNERS MUST NOT LOAD EACH OTHER'S FILES. Jest, Vitest and Playwright all
  collect `*.test.js` and `*.spec.js` unless told where to look, so a unit
  runner left to itself loads the browser specs and fails on every one. Keep
  the browser specs in a directory of their own (`e2e/`) and say so once: the
  unit script names its files (`node --test 'tests/**/*.test.js'` - Node takes
  a quoted pattern, never a directory - or `vitest run tests`) or
  its configuration ignores the other (`testPathIgnorePatterns: ['/e2e/']` for
  Jest, `exclude: ['e2e/**', 'node_modules/**']` for Vitest), and Playwright's
  configuration sets `testDir: 'e2e'`."""

#: How JavaScript tests are written, whoever set the runner up.
_JAVASCRIPT_TEST_WRITING = """Writing JavaScript tests:
- A static page that ships to a browser is still tested on the machine that
  builds it - deployment constrains what you ship, not what you can run while
  building it.
- A test-only package goes in `devDependencies` (`npm i -D ...`); it ships to
  nobody and breaks no constraint on the product's dependencies.
- An assertion like `typeof mod.parse === 'function'` checks that an export
  exists, not what it does; and `assert.doesNotThrow(() => save(x))` passes
  whether the function saved anything or not. Assert on what it returned."""

#: The test runner each language ships with or conventionally uses, and where a
#: test-only dependency goes. Moved here from the per-ecosystem table that
#: `TESTING_DEPENDENCY_RULE` carried in every prompt.
_TESTING_BY_LANGUAGE = {
    "python": (
        "- Testing: `unittest` ships with Python and installs nothing; `pytest` is the "
        "common choice. A test-only package goes in a dev/test dependency group "
        "(`[dependency-groups]`, `[project.optional-dependencies]`, or a test extra).\n"
        # Measured on one gate run: an async service's tests failed to set up
        # round after round ("requested an async fixture"), and the fix tried
        # was the configuration - a file the harness keeps. Strict mode is
        # pytest-asyncio's default and the one that leaves anyio and trio
        # tests to their own plugin, so the markers are the answer.
        "- Async tests: pytest-asyncio runs in its default strict mode - mark each async "
        "test `@pytest.mark.asyncio` and each async fixture `@pytest_asyncio.fixture`; "
        "a test run by anyio is marked `@pytest.mark.anyio` instead."
    ),
    "go": "- Testing: `go test ./...` is part of the toolchain; test code needs no dependency declaration.",
    "rust": "- Testing: `cargo test`; test-only crates go in `[dev-dependencies]`.",
    "java": "- Testing: JUnit, declared with Maven `<scope>test</scope>` or Gradle `testImplementation`.",
    "kotlin": "- Testing: JUnit or kotest, declared with Gradle `testImplementation`.",
    "spring": "- Testing: `spring-boot-starter-test` in test scope (`<scope>test</scope>` / `testImplementation`).",
    "php": "- Testing: PHPUnit; test-only packages go in `require-dev`.",
    "laravel": "- Testing: `php artisan test` (PHPUnit or Pest); test-only packages go in `require-dev`.",
    "ruby": "- Testing: Minitest ships with Ruby; RSpec is common. Test-only gems go in `group :test`.",
    "rails": "- Testing: `bin/rails test` (Minitest) or RSpec; test-only gems go in `group :test`.",
    "csharp": "- Testing: `dotnet test` with xUnit, NUnit or MSTest; test packages belong to the test project only.",
    "dotnet": "- Testing: `dotnet test`; test packages are `PackageReference`s of the test project only.",
    "swift": "- Testing: `swift test` with XCTest.",
}

SEED_INSTRUCTIONS["javascript"] = (
    "You are working in a JavaScript environment.\n"
    "- Modules: prefer ES modules (`import`/`export`).\n"
    "- Dependency Management: respect a lockfile if one is present.\n\n"
    + _JAVASCRIPT_TEST_WRITING
)
SEED_INSTRUCTIONS["html"] = (
    "You are building a page that runs in a browser.\n"
    "- Keep behaviour in script files the page loads, not inline in the markup.\n\n"
    + _BROWSER_PAGE_TESTING
)
for _key in ("typescript", "node"):
    SEED_INSTRUCTIONS[_key] += "\n\n" + _JAVASCRIPT_TEST_WRITING
for _key in ("javascript", "typescript", "node"):
    SEED_INSTRUCTIONS[_key + SETUP] = _JAVASCRIPT_TESTING
SEED_INSTRUCTIONS["html" + SETUP] = _BROWSER_PAGE_SETUP
for _key in ("react", "vue", "angular", "nextjs"):
    SEED_INSTRUCTIONS[_key] += "\n\n" + _BROWSER_PAGE_TESTING
    SEED_INSTRUCTIONS[_key + SETUP] = _JAVASCRIPT_TESTING + "\n\n" + _BROWSER_PAGE_SETUP
for _key, _line in _TESTING_BY_LANGUAGE.items():
    SEED_INSTRUCTIONS[_key] += "\n" + _line

#: Password hashing in Python. Measured on one gate run: a service declared
#: `passlib[bcrypt]` and `bcrypt>=4.0.0`, the install took bcrypt 5.0.0, and
#: every hash failed - passlib 1.7.4, its last release, hashes a 255-byte secret
#: in its own start-up check and bcrypt 5 refuses one over 72 bytes - so the
#: unit tests that hash a password failed while the fixer read it as a version
#: mismatch to work around.
_PYTHON_PASSWORDS = (
    "- Password hashing: `passlib` 1.7.4, its last release, fails on every hash with `bcrypt` 5 "
    "(\"password cannot be longer than 72 bytes\", from passlib's own start-up check). Hash with "
    "`bcrypt` directly - `bcrypt.hashpw(password.encode(), bcrypt.gensalt())` and "
    "`bcrypt.checkpw(password.encode(), hashed)` - or, keeping passlib, declare `bcrypt<5` beside it."
)
SEED_INSTRUCTIONS["python"] += "\n" + _PYTHON_PASSWORDS

#: Installing a Python application set up without a pack. Measured on one run:
#: a setup declared `pip install -e .` over a `pyproject.toml` with setuptools at
#: a project root that also held its tests, its data and `node_modules`, and the
#: install failed on "Multiple top-level packages discovered in a flat-layout".
_PYTHON_SETUP = """Setting up a Python project's install:
- An editable install (`pip install -e .`) with setuptools must say what it installs when the
  project root holds more than the package: `[tool.setuptools] py-modules = ["<module>"]` for a
  single module, or `packages = ["<package>"]`. Otherwise tests, data or a `node_modules`
  folder beside it make setuptools refuse: "Multiple top-level packages discovered in a
  flat-layout".
- An application that is never imported from elsewhere can install only its dependencies
  instead: `pip install -r requirements.txt`, or the project's dependency group."""
for _key in ("python", "fastapi", "flask", "django"):
    SEED_INSTRUCTIONS[_key + SETUP] = (SEED_INSTRUCTIONS.get(_key + SETUP, "") + "\n\n" + _PYTHON_SETUP).strip()

#: Playwright, wherever a stack names it. Before this a generated note stood
#: here, telling every stage to run `npx playwright install` and download three
#: browser engines - in a project whose browser the harness had installed and
#: matched to its pinned Playwright, where `--with-deps` is refused. QA ran it
#: in every run, and one run twice before writing a test.
SEED_INSTRUCTIONS["playwright"] = (
    "Playwright:\n"
    "- End-to-end tests run in a real headless browser with `@playwright/test`,\n"
    "  through `npx playwright test`.\n"
    "- Where the harness set the project up, the browser its Playwright version\n"
    "  needs is already installed: install nothing. `npx playwright install\n"
    "  --with-deps` is refused here - it installs system packages as root.\n"
    "- Use a built-in reporter, `--reporter=line` or `--reporter=list`; never\n"
    "  `tap`, which Playwright resolves to an npm package that is not installed."
)


__all__ = ["SEED_INSTRUCTIONS", "SETUP"]
