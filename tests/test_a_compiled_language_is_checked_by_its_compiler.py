"""Code in a compiled language is checked by its compiler before its tests run.

JavaScript, TypeScript and Python had a language service reading each file as
it was written; Go, Rust, Java, Kotlin and C# had a parse and nothing more, so
a name nothing defines was first heard of as a failed build in a test round.
The compiler is those languages' language service: it is asked once for the
project when a stage that changed such code finishes, and again at the sprint's
gate. The outputs below were captured from the real compilers (Go 1.27, Rust
1.98 on the host; Maven and .NET 8 in the worker image).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.analysis import compiler_check
from app.analysis.compiler_check import errors_in, findings

GO = (
    "FAIL\tgoapp [build failed]\nFAIL\n# goapp [goapp.test]\n"
    "./main.go:6:14: undefined: greet\n./main_test.go:5:32: undefined: missing\n"
)
RUST = (
    "src/main.rs:2:9: warning: unused variable: `unused`\n"
    "src/main.rs:3:20: error[E0425]: cannot find value `undefined_name` in this scope: not found in this scope\n"
    "error: could not compile `rsapp` (bin \"rsapp\") due to 1 previous error\n"
)
MAVEN = (
    "[ERROR] COMPILATION ERROR : \n"
    "[ERROR] /work/japp/src/main/java/app/Main.java:[2,78] cannot find symbol\n"
    "  symbol:   method greet()\n  location: class app.Main\n"
    "[ERROR] Failed to execute goal org.apache.maven.plugins:maven-compiler-plugin:3.13.0:compile\n"
    "[ERROR] /work/japp/src/main/java/app/Main.java:[2,78] cannot find symbol\n"
    "[ERROR]   symbol:   method greet()\n"
)
DOTNET = (
    "An issue was encountered verifying workloads.\n"
    "/work/csapp/Program.cs(1,26): error CS0103: The name 'Greet' does not exist in the current context [/work/csapp/csapp.csproj]\n"
    "/work/csapp/Program.cs(2,5): warning CS0219: The variable 'unused' is assigned but its value is never used [/work/csapp/csapp.csproj]\n"
)
KOTLIN = "e: file:///work/ktapp/src/main/kotlin/Main.kt:1:22 Unresolved reference: greet\n"
PHPSTAN = "/work/php/app/Http/Kernel.php:12:Call to an undefined method App\\Http\\Kernel::boot().\n"


@pytest.mark.parametrize("project, output, expected", [
    ("goapp", GO, [("goapp/main.go", 6, "undefined: greet"), ("goapp/main_test.go", 5, "undefined: missing")]),
    ("rsapp", RUST, [("rsapp/src/main.rs", 3, "cannot find value `undefined_name` in this scope: not found in this scope")]),
    ("japp", MAVEN, [("japp/src/main/java/app/Main.java", 2, "cannot find symbol (symbol: method greet())")]),
    ("csapp", DOTNET, [("csapp/Program.cs", 1, "The name 'Greet' does not exist in the current context")]),
    ("ktapp", KOTLIN, [("ktapp/src/main/kotlin/Main.kt", 1, "Unresolved reference: greet")]),
    ("php", PHPSTAN, [("php/app/Http/Kernel.php", 12, "Call to an undefined method App\\Http\\Kernel::boot().")]),
])
def test_each_compiler_s_errors_are_read_and_its_warnings_are_not(project, output, expected):
    workspace = Path("/work")

    found = errors_in(output, workspace / project, workspace)

    assert [(f["file"], f["line"], f["message"]) for f in found] == expected


@pytest.mark.parametrize("files, command", [
    ({"go.mod": "module x\n"}, ["go", "test", "-count=1", "-run", "^$", "./..."]),
    ({"Cargo.toml": ""}, ["cargo", "check", "--quiet", "--all-targets", "--message-format=short"]),
    ({"pom.xml": ""}, ["mvn", "--quiet", "--batch-mode", "-DskipTests", "test-compile"]),
    ({"build.gradle.kts": ""}, ["gradle", "--quiet", "--console=plain", "testClasses"]),
    ({"api.csproj": ""}, ["dotnet", "build", "--nologo", "-v", "q", "-clp:NoSummary"]),
    ({"Package.swift": ""}, ["swift", "build"]),
    ({"vendor/bin/phpstan": "", "app/x.php": ""},
     ["vendor/bin/phpstan", "analyse", "--no-progress", "--error-format=raw", "--level=0", "app"]),
])
def test_the_project_s_own_build_decides_the_check(tmp_path, files, command):
    for name, text in files.items():
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text(text)

    assert compiler_check.checker_for(tmp_path)[1] == command


def test_ruby_and_a_php_project_without_a_checker_are_left_to_their_tests(tmp_path):
    (tmp_path / "Gemfile").write_text("")
    (tmp_path / "composer.json").write_text("{}")

    assert compiler_check.checker_for(tmp_path) is None


def _project(root: Path) -> None:
    (root / "goapp").mkdir()
    (root / "goapp" / "go.mod").write_text("module goapp\n")


def test_a_stage_that_changed_no_compiled_code_does_not_wait_for_the_compiler(tmp_path):
    _project(tmp_path)
    ran = []

    assert findings(tmp_path, "goapp", ["goapp/README.md"], run=lambda *a: ran.append(a) or {}) == []
    assert ran == []


def test_a_build_that_passes_or_cannot_run_says_nothing(tmp_path):
    _project(tmp_path)

    assert findings(tmp_path, "goapp", ["goapp/main.go"], run=lambda *a: {"returncode": "0", "stdout": GO}) == []
    assert findings(tmp_path, "goapp", ["goapp/main.go"], run=lambda *a: {"error": "'go' is not installed"}) == []


def test_errors_are_found_through_the_sandbox_s_build(tmp_path):
    _project(tmp_path)
    seen = []

    def run(argv, category, project):
        seen.append((category, project))
        return {"returncode": "1", "stdout": "", "stderr": GO}

    found = findings(tmp_path, "goapp", ["goapp/main.go"], run=run)

    assert seen == [("build", "goapp")]
    assert found[0]["file"] == "goapp/main.go"


# --- where it is asked -------------------------------------------------------------------

def test_a_stage_is_told_the_compiler_s_errors_in_what_it_touched_first(tmp_path, monkeypatch):
    from app.graph import workflow

    monkeypatch.setattr(compiler_check, "findings", lambda root, project, files: [
        {"file": "goapp/other.go", "line": 2, "message": "undefined: y"},
        {"file": "goapp/main.go", "line": 6, "message": "undefined: greet"},
    ])

    told = workflow._what_the_compiler_says_of(str(tmp_path), {"goapp/main.go"}, "defect_fix_1_0", "goapp")

    assert told == [
        "- In `goapp/main.go` line 6: undefined: greet (the compiler)",
        "- In `goapp/other.go` line 2: undefined: y (the compiler)",
    ]


def test_a_work_order_is_not_held_to_a_file_another_has_yet_to_write(tmp_path, monkeypatch):
    from app.graph import workflow
    from app.tools.repository import WORK_ORDER_FILES

    asked = []
    monkeypatch.setattr(compiler_check, "findings", lambda *a: asked.append(a) or [])
    (tmp_path / WORK_ORDER_FILES).write_text(json.dumps({
        "goapp/main.go": "specialist_backend_0", "goapp/store.go": "specialist_database_0",
    }))

    workflow._what_the_compiler_says_of(str(tmp_path), {"goapp/main.go"}, "specialist_backend_0", "goapp")
    assert asked == []

    (tmp_path / "goapp").mkdir()
    (tmp_path / "goapp" / "store.go").write_text("package main\n")
    workflow._what_the_compiler_says_of(str(tmp_path), {"goapp/main.go"}, "specialist_backend_0", "goapp")
    assert len(asked) == 1


def test_the_sprint_gate_raises_a_defect_for_each_error_and_closes_it_once_gone(tmp_path, monkeypatch):
    from app.graph import engineering

    monkeypatch.setattr(engineering.ci, "changed_since", lambda root, since: ["goapp/main.go"])
    errors = [{"file": "goapp/main.go", "line": 6, "message": "undefined: greet"}]
    monkeypatch.setattr(compiler_check, "findings", lambda *a, **k: list(errors))
    monkeypatch.setattr("app.tools.repository.pinned_project_directory", lambda root: "goapp")
    monkeypatch.setattr(engineering, "_owner_of", lambda state, work_order: "backend")
    _project(tmp_path)
    (tmp_path / "goapp" / "main.go").write_text("package main\n")

    defects = engineering._what_the_compiler_says({}, str(tmp_path), "abc", "goapp")

    assert [d.description for d in defects] == [f"goapp/main.go line 6: undefined: greet{engineering.FAILS_WHEN_IT_RUNS}"]
    assert engineering.no_longer_underlined(str(tmp_path), defects[0].description) == ""
    errors.clear()
    assert "compiler no longer reports it" in engineering.no_longer_underlined(str(tmp_path), defects[0].description)


def test_the_sandbox_lets_the_harness_run_phpstan():
    from app.tools.sandbox import TOOLCHAINS

    assert "phpstan" in TOOLCHAINS["php"]
