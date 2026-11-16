"""A pack's scaffold opens its own toolchain before its first command, and a failed step says why (found on a run).

Measured on one run (a C# service): the stack was pinned earlier from another stage's words and left no marker, so
the sandbox's allowlist did not hold `dotnet`; `dotnet restore` was refused four times in 50 ms, the run stopped as
"could not be proven after two full attempts", and the decision named the command but not the refusal.
"""
from __future__ import annotations

from app.stacks import pack_named
from app.stacks.scaffold import scaffold
from app.tools.sandbox import project_stack


def test_the_toolchain_is_pinned_before_the_first_command(tmp_path):
    seen = []

    def runner(argv, category, working_directory):
        seen.append(set(project_stack(tmp_path)))
        return {"returncode": "1", "stdout": "", "stderr": "refused: dotnet is not an allowed program here"}

    result = scaffold(tmp_path, pack_named("csharp-aspnet-api"), "demo", "Demo", run=runner)
    assert seen and {"csharp", "javascript"} <= seen[0]
    assert not result.ok and "refused: dotnet is not an allowed program here" in result.problem


def test_a_toolchain_already_pinned_is_kept(tmp_path):
    from app.tools.sandbox import pin_project_stack

    pin_project_stack(tmp_path, "go")
    scaffold(tmp_path, pack_named("csharp-aspnet-api"), "demo", "Demo",
             run=lambda *args: {"returncode": "1", "stdout": "", "stderr": "x"})
    assert {"go", "csharp"} <= set(project_stack(tmp_path))
