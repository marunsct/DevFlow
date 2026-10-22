"""A command-line program or a library in Go, on the standard library.

Unit tests sit beside the code, as Go's do. Acceptance tests live in
`acceptance/` behind the `acceptance` build tag, so `go test ./...` never runs
them: for a program they build it once and run it as its own process in an
empty directory; for a library they import it by its module path, so only what
it exports is reachable. gotestsum writes JUnit for both.
"""

from __future__ import annotations

from app.stacks import StackPack
from app.stacks.packs.go_http_api import GO_VERSION

GO_MOD = """module {{package}}

go %s
""" % GO_VERSION

UNIT_TEST = ("gotestsum", "--junitfile", "test-results/unit.xml", "--format", "standard-quiet", "--", "./...")
ACCEPTANCE_TEST = (
    "gotestsum", "--junitfile", "test-results/acceptance.xml", "--format", "standard-quiet", "--",
    "-tags", "acceptance", "-count=1", "./acceptance/...",
)

CLI_MAIN = """package main

import "os"

func main() {
	os.Exit(run(os.Args[1:], os.Stdin, os.Stdout, os.Stderr))
}
"""

CLI_RUN = """package main

import (
	"flag"
	"fmt"
	"io"
)

// run is the program: args are what follows its name, and the result is its
// exit status. Unit tests call it with their own readers and writers.
func run(args []string, stdin io.Reader, stdout, stderr io.Writer) int {
	flags := flag.NewFlagSet("{{project}}", flag.ContinueOnError)
	flags.SetOutput(stderr)
	version := flags.Bool("version", false, "print the version and exit")
	if err := flags.Parse(args); err != nil {
		return 2
	}
	if *version {
		fmt.Fprintln(stdout, "{{project}} 0.1.0")
		return 0
	}
	return 0
}
"""

CLI_HELPERS = """//go:build acceptance

// Kept by the harness: acceptance tests run the program through runCLI, the way a user does.
package acceptance

import (
	"bytes"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
)

var program string

func TestMain(m *testing.M) {
	dir, err := os.MkdirTemp("", "{{project}}-build-")
	if err != nil {
		panic(err)
	}
	program = filepath.Join(dir, "{{project}}")
	build := exec.Command("go", "build", "-o", program, "..")
	build.Stderr = os.Stderr
	if err := build.Run(); err != nil {
		panic("the program did not build: " + err.Error())
	}
	code := m.Run()
	os.RemoveAll(dir)
	os.Exit(code)
}

// Finished is one run of the program.
type Finished struct {
	Code           int
	Stdout, Stderr string
	Dir            string
}

// runCLI runs the program with args as its own process in dir (a new empty
// directory, also its HOME, when dir is ""). Pass a run's Dir to run it again
// in the same place - that is how a test proves something persists.
func runCLI(t *testing.T, dir string, input string, args ...string) Finished {
	t.Helper()
	if dir == "" {
		dir = t.TempDir()
	}
	command := exec.Command(program, args...)
	command.Dir = dir
	command.Env = append(os.Environ(), "HOME="+dir)
	command.Stdin = strings.NewReader(input)
	var stdout, stderr bytes.Buffer
	command.Stdout, command.Stderr = &stdout, &stderr
	err := command.Run()
	code := 0
	if exit, ok := err.(*exec.ExitError); ok {
		code = exit.ExitCode()
	} else if err != nil {
		t.Fatalf("the program did not start: %v", err)
	}
	return Finished{Code: code, Stdout: stdout.String(), Stderr: stderr.String(), Dir: dir}
}
"""

CLI_SMOKE_UNIT = """package main

import (
	"bytes"
	"strings"
	"testing"
)

func TestTheVersionOptionExitsCleanly(t *testing.T) {
	var out, errs bytes.Buffer
	if code := run([]string{"-version"}, strings.NewReader(""), &out, &errs); code != 0 {
		t.Fatalf("exit %d: %s", code, errs.String())
	}
	if !strings.Contains(out.String(), "0.1.0") {
		t.Fatalf("printed %q", out.String())
	}
}
"""

CLI_SMOKE_ACCEPTANCE = """//go:build acceptance

package acceptance

import (
	"strings"
	"testing"
)

func TestTheProgramRuns(t *testing.T) {
	finished := runCLI(t, "", "", "-version")
	if finished.Code != 0 || !strings.Contains(finished.Stdout, "{{project}}") {
		t.Fatalf("exit %d, printed %q, %q", finished.Code, finished.Stdout, finished.Stderr)
	}
}
"""

LIBRARY = """// Package {{package}}: {{title}}. Everything it exports is its public interface.
package {{package}}

// Version is the library's version.
const Version = "0.1.0"
"""

LIBRARY_SMOKE_UNIT = """package {{package}}

import "testing"

func TestTheLibrarySaysItsVersion(t *testing.T) {
	if Version != "0.1.0" {
		t.Fatalf("Version is %q", Version)
	}
}
"""

LIBRARY_SMOKE_ACCEPTANCE = """//go:build acceptance

package acceptance

import (
	"testing"

	"{{package}}"
)

func TestTheLibraryIsImportedByItsPath(t *testing.T) {
	if {{package}}.Version != "0.1.0" {
		t.Fatalf("Version is %q", {{package}}.Version)
	}
}
"""

NAMING = """Name each test function after the criterion it proves: `Test_AC3_AddsAnItem` for
AC-3 (two: `Test_AC3_AC4_...`) - the underscore before `AC` is what lets the id be
read. A test with no criterion id in its name proves nothing the harness can count."""

UNIT_GUIDE = """Unit tests sit beside the code they test, in `<name>_test.go` files of the same
package, using `testing`. Run them with `gotestsum -- ./...` (or `go test ./...`). Add a
module with `go get <module>`; keep `go.mod` and `go.sum` tidy with `go mod tidy`."""

CI_SETUP = (
    "      - uses: actions/setup-go@v5\n"
    "        with:\n"
    f'          go-version: "{GO_VERSION}"\n'
    "      - run: go install gotest.tools/gotestsum@v1.12.3",
)


def _pack(kind: str) -> StackPack:
    if kind == "cli":
        files = {"go.mod": GO_MOD, "main.go": CLI_MAIN, "run.go": CLI_RUN, "acceptance/helpers_test.go": CLI_HELPERS}
        kept = ("acceptance/helpers_test.go",)
        smoke = {"scaffold_smoke_test.go": CLI_SMOKE_UNIT, "acceptance/scaffold_smoke_test.go": CLI_SMOKE_ACCEPTANCE}
        guide = (
            "The program is Go on the standard library. `run(args, stdin, stdout, stderr)` in "
            "`run.go` is the program - it returns the exit status - and `main.go` calls it. "
            "Parse options with `flag` on a `FlagSet`, write output to `stdout` and errors to "
            "`stderr`, and return a non-zero status on failure. " + UNIT_GUIDE
        )
        acceptance_guide = (
            "Acceptance tests go in `acceptance/`, in `<feature>_test.go` files of package "
            "`acceptance` that start with the line `//go:build acceptance`. Run the program "
            "exactly as a user would with `finished := runCLI(t, \"\", \"\", \"add\", \"Buy milk\")` "
            "(directory, standard input, then arguments), and check `finished.Code`, "
            "`finished.Stdout` and `finished.Stderr`. Each run with directory \"\" gets a new "
            "empty directory, also its HOME; to prove something persists, run it again with "
            "`finished.Dir`.\n" + NAMING
        )
        testing = "go test (reported by gotestsum) for unit tests, go test running the built program for acceptance tests"
        frameworks = ("flag", "cobra", "go", "golang", "standard library", "stdlib")
    else:
        files = {"go.mod": GO_MOD, "{{package}}.go": LIBRARY, "acceptance/doc.go": "//go:build acceptance\n\n// Package acceptance holds the acceptance tests.\npackage acceptance\n"}
        kept = ()
        smoke = {"scaffold_smoke_test.go": LIBRARY_SMOKE_UNIT, "acceptance/scaffold_smoke_test.go": LIBRARY_SMOKE_ACCEPTANCE}
        guide = (
            "The library is Go on the standard library, package `{{package}}` at the module's "
            "root: what it exports (capitalised names) is its public interface; put internals "
            "in `internal/`. " + UNIT_GUIDE
        )
        acceptance_guide = (
            "Acceptance tests go in `acceptance/`, in `<feature>_test.go` files of package "
            "`acceptance` that start with the line `//go:build acceptance`. Import the library by "
            "its module path, exactly as a user would - `import \"{{package}}\"` - and call only "
            "what it exports.\n" + NAMING
        )
        testing = "go test (reported by gotestsum) for unit tests, go test importing the module for acceptance tests"
        frameworks = ("go", "golang", "standard library", "stdlib")
    return StackPack(
        name=f"go-{kind}",
        title=f"{'Command-line program' if kind == 'cli' else 'Library'} in Go",
        kind=kind,
        language="go",
        frameworks=frameworks,
        files={**files, ".gitignore": "test-results/\nbin/\n"},
        install=(("go", "build", "./..."),),
        unit_test=UNIT_TEST,
        acceptance_test=ACCEPTANCE_TEST,
        unit_report="test-results/unit.xml",
        acceptance_report="test-results/acceptance.xml",
        unit_dir=".",
        acceptance_dir="acceptance",
        acceptance_pattern="*_test.go",
        unit_pattern="*_test.go",
        kept_files=kept,
        kept_scripts={},
        smoke_files=smoke,
        guide=guide,
        acceptance_guide=acceptance_guide,
        stack={"language": "Go", "framework": "None (standard library)", "frontend_framework": "", "testing_framework": testing},
        check_families=frozenset({"go"}),
        ci_setup=CI_SETUP,
    )


GO_CLI = _pack("cli")
GO_LIBRARY = _pack("library")
