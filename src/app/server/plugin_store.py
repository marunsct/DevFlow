"""Postgres-backed persistence for plugin instructions."""

import os
import threading
from contextlib import contextmanager
from typing import Any, Optional, Dict

import psycopg2
from psycopg2.pool import ThreadedConnectionPool

from app.server.schema_lock import lock_schema

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS plugin_instructions (
    framework_name TEXT PRIMARY KEY,
    instructions TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

def database_url() -> str:
    return os.environ.get("DB_URL", "postgresql://postgres:postgres@localhost:5432/postgres")


class PluginStore:
    """Store for framework-specific plugin instructions."""

    _shared: Optional["PluginStore"] = None
    _shared_lock = threading.Lock()

    def __init__(self, db_url: str | None = None) -> None:
        self._pool = ThreadedConnectionPool(1, 10, db_url or database_url())
        self._ensure_schema()
        self._seed_default_instructions()

    @classmethod
    def shared(cls) -> "PluginStore":
        with cls._shared_lock:
            if cls._shared is None:
                cls._shared = cls()
            return cls._shared

    def _ensure_schema(self) -> None:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                lock_schema(cur)
                cur.execute(_CREATE_TABLE)
            conn.commit()

    @contextmanager
    def get_connection(self):
        conn = self._pool.getconn()
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            try:
                conn.rollback()
            except Exception:
                pass
            self._pool.putconn(conn)

    def _seed_default_instructions(self) -> None:
        """Seed the database with detailed, framework-agnostic harness instructions."""
        defaults = {
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
                "- Indexing: Ensure foreign keys and heavily queried columns are indexed."
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
        
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                for framework, instructions in defaults.items():
                    # Insert only if not exists so we don't overwrite user changes
                    cur.execute(
                        "INSERT INTO plugin_instructions (framework_name, instructions) VALUES (%s, %s) "
                        "ON CONFLICT (framework_name) DO NOTHING",
                        (framework, instructions)
                    )
            conn.commit()

    def get_instructions(self, framework_name: str) -> Optional[str]:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT instructions FROM plugin_instructions WHERE framework_name = %s", (framework_name.lower(),))
                row = cur.fetchone()
                if row:
                    return row[0]
        return None

    def get_all_framework_names(self) -> list[str]:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT framework_name FROM plugin_instructions")
                return [row[0] for row in cur.fetchall()]

    def update_instructions(self, framework_name: str, instructions: str) -> None:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO plugin_instructions (framework_name, instructions) VALUES (%s, %s) "
                    "ON CONFLICT (framework_name) DO UPDATE SET instructions = EXCLUDED.instructions, updated_at = CURRENT_TIMESTAMP",
                    (framework_name.lower(), instructions)
                )
            conn.commit()
