"""A command-line program or a library in Rust, on the standard library.

Unit tests sit in a `#[cfg(test)]` module beside the code, as Rust's do.
Acceptance tests are Cargo's integration tests in `tests/`: for a program they
run the built binary (`CARGO_BIN_EXE_<name>`) as its own process in an empty
directory; for a library they use it as an outside crate, so only its public
interface is reachable. cargo-nextest writes JUnit for each.
"""

from __future__ import annotations

from app.stacks import StackPack

CARGO_TOML = """[package]
name = "{{package}}"
version = "0.1.0"
edition = "2021"

[dependencies]
"""

NEXTEST = """# Kept by the harness: the two test runs report through these profiles.
[profile.ci.junit]
path = "junit.xml"

[profile.acceptance.junit]
path = "junit.xml"
"""

UNIT_TEST = ("cargo", "nextest", "run", "--profile", "ci", "--lib", "--bins", "--no-fail-fast", "--no-tests=pass")
ACCEPTANCE_TEST = ("cargo", "nextest", "run", "--profile", "acceptance", "--test", "*", "--no-fail-fast")

CLI_LIB = """use std::io::Write;

/// The program: `args` are what follows its name, and the result is its exit
/// status. `src/main.rs` calls it; unit tests call it with their own writers.
pub fn run(args: &[String], out: &mut dyn Write, err: &mut dyn Write) -> i32 {
    match args.first().map(String::as_str) {
        Some("--version") => {
            let _ = writeln!(out, "{{project}} 0.1.0");
            0
        }
        Some(other) if other.starts_with('-') => {
            let _ = writeln!(err, "unknown option: {other}");
            2
        }
        _ => 0,
    }
}

#[cfg(test)]
mod tests {}
"""

CLI_MAIN = """fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let code = {{package}}::run(&args, &mut std::io::stdout(), &mut std::io::stderr());
    std::process::exit(code);
}
"""

CLI_COMMON = """// Kept by the harness: acceptance tests run the program through `run_cli`, the way a user does.
#![allow(dead_code)]

use std::io::Write;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicUsize, Ordering};

pub struct Finished {
    pub code: i32,
    pub stdout: String,
    pub stderr: String,
    pub dir: PathBuf,
}

static RUNS: AtomicUsize = AtomicUsize::new(0);

/// A new empty directory for one run of the program.
pub fn empty_dir() -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "{{project}}-{}-{}",
        std::process::id(),
        RUNS.fetch_add(1, Ordering::SeqCst)
    ));
    std::fs::create_dir_all(&dir).expect("a temporary directory");
    dir
}

/// Runs the program with `args` as its own process in `dir` (a new empty
/// directory, also its HOME, when `None`), with `input` on standard input.
/// Pass a run's `dir` again to prove something persists.
pub fn run_cli(dir: Option<&PathBuf>, input: &str, args: &[&str]) -> Finished {
    let dir = dir.cloned().unwrap_or_else(empty_dir);
    let mut child = Command::new(env!("CARGO_BIN_EXE_{{package}}"))
        .args(args)
        .current_dir(&dir)
        .env("HOME", &dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("the program to start");
    child.stdin.take().unwrap().write_all(input.as_bytes()).unwrap();
    let output = child.wait_with_output().expect("the program to finish");
    Finished {
        code: output.status.code().unwrap_or(-1),
        stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
        stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
        dir,
    }
}
"""

# A binary of its own in `src/bin/`, which Cargo finds without the library
# naming it: the smoke test is removed once it passes, and a module the library
# declared would then be missing.
CLI_SMOKE_UNIT = """fn main() {}

#[cfg(test)]
mod tests {
    #[test]
    fn the_version_option_exits_cleanly() {
        let (mut out, mut err) = (Vec::new(), Vec::new());
        assert_eq!({{package}}::run(&["--version".to_string()], &mut out, &mut err), 0);
        assert!(String::from_utf8(out).unwrap().contains("0.1.0"));
    }
}
"""

CLI_SMOKE_ACCEPTANCE = """mod common;

#[test]
fn the_program_runs() {
    let finished = common::run_cli(None, "", &["--version"]);
    assert_eq!(finished.code, 0, "{}", finished.stderr);
    assert!(finished.stdout.contains("{{project}}"));
}
"""

LIBRARY = """//! {{title}}. Everything `pub` here is the library's public interface.

/// The library's version.
pub const VERSION: &str = "0.1.0";

#[cfg(test)]
mod tests {}
"""

LIBRARY_SMOKE_UNIT = """fn main() {}

#[cfg(test)]
mod tests {
    #[test]
    fn the_library_says_its_version() {
        assert_eq!({{package}}::VERSION, "0.1.0");
    }
}
"""

LIBRARY_SMOKE_ACCEPTANCE = """#[test]
fn the_library_is_used_as_a_crate() {
    assert_eq!({{package}}::VERSION, "0.1.0");
}
"""

NAMING = """Name each test function after the criterion it proves: `fn ac3_adds_an_item()`
for AC-3 (two: `fn ac3_ac4_...`). A test with no criterion id in its name proves
nothing the harness can count."""

UNIT_GUIDE = """Unit tests go in the `#[cfg(test)] mod tests` at the bottom of the file whose code
they test, as `#[test]` functions. Run them with `cargo nextest run --lib --bins` (or
`cargo test --lib`). Add a crate with `cargo add <name>`."""

CI_SETUP = ("      - uses: dtolnay/rust-toolchain@stable\n      - uses: taiki-e/install-action@nextest",)


def _pack(kind: str) -> StackPack:
    if kind == "cli":
        files = {"Cargo.toml": CARGO_TOML, "src/lib.rs": CLI_LIB, "src/main.rs": CLI_MAIN, "tests/common/mod.rs": CLI_COMMON}
        kept = (".config/nextest.toml", "tests/common/mod.rs")
        smoke = {"src/bin/scaffold_smoke.rs": CLI_SMOKE_UNIT, "tests/scaffold_smoke.rs": CLI_SMOKE_ACCEPTANCE}
        guide = (
            "The program is Rust on the standard library. `run(args, out, err)` in `src/lib.rs` "
            "is the program - it returns the exit status - and `src/main.rs` calls it. Write "
            "output to `out` and errors to `err` with `writeln!`, and return a non-zero status "
            "on failure. " + UNIT_GUIDE
        )
        acceptance_guide = (
            "Acceptance tests go in `tests/`, one file per feature (`tests/<feature>.rs`), each "
            "starting with `mod common;`. Run the program exactly as a user would: "
            "`let finished = common::run_cli(None, \"\", &[\"add\", \"Buy milk\"]);` (directory, "
            "standard input, arguments), then check `finished.code`, `finished.stdout` and "
            "`finished.stderr`. `None` gives a new empty directory, also its HOME; to prove "
            "something persists, run it again with `Some(&finished.dir)`.\n" + NAMING
        )
        testing = "cargo nextest for unit tests, Cargo integration tests running the built program for acceptance tests"
        frameworks = ("clap", "rust", "standard library", "std")
    else:
        files = {"Cargo.toml": CARGO_TOML, "src/lib.rs": LIBRARY}
        kept = (".config/nextest.toml",)
        smoke = {"src/bin/scaffold_smoke.rs": LIBRARY_SMOKE_UNIT, "tests/scaffold_smoke.rs": LIBRARY_SMOKE_ACCEPTANCE}
        guide = (
            "The library is Rust on the standard library: what `src/lib.rs` makes `pub` is its "
            "public interface; keep internals in private modules. " + UNIT_GUIDE
        )
        acceptance_guide = (
            "Acceptance tests go in `tests/`, one file per feature (`tests/<feature>.rs`), using "
            "the library as an outside crate, exactly as a user would - `use {{package}}::parse;` - "
            "so only what it makes `pub` is reachable.\n" + NAMING
        )
        testing = "cargo nextest for unit tests, Cargo integration tests using the crate for acceptance tests"
        frameworks = ("rust", "standard library", "std")
    return StackPack(
        name=f"rust-{kind}",
        title=f"{'Command-line program' if kind == 'cli' else 'Library'} in Rust",
        kind=kind,
        language="rust",
        frameworks=frameworks,
        files={**files, ".config/nextest.toml": NEXTEST, ".gitignore": "target/\ntest-results/\n"},
        install=(("cargo", "build", "--all-targets"),),
        unit_test=UNIT_TEST,
        acceptance_test=ACCEPTANCE_TEST,
        unit_report="target/nextest/ci/junit.xml",
        acceptance_report="target/nextest/acceptance/junit.xml",
        unit_dir="src",
        acceptance_dir="tests",
        acceptance_pattern="*.rs",
        unit_pattern="*.rs",
        kept_files=kept,
        kept_scripts={},
        smoke_files=smoke,
        guide=guide,
        acceptance_guide=acceptance_guide,
        stack={"language": "Rust", "framework": "None (standard library)", "frontend_framework": "", "testing_framework": testing},
        check_families=frozenset({"rust"}),
        ci_setup=CI_SETUP,
    )


RUST_CLI = _pack("cli")
RUST_LIBRARY = _pack("library")
