# Skipped and expected-to-fail tests, and who owns each kind (plan CH.3)

Every skip and xfail in `tests/` states its reason in the call; `tests/test_every_skip_names_its_reason.py`
fails on one that does not. Each falls in one of these kinds:

| Kind | Example reason | Owner | What makes it run |
|---|---|---|---|
| A tool the machine lacks | `needs node`, `git is not installed`, `needs /proc`, `needs fork()`, the TypeScript compiler, Pyright | the environment | the worker image and the CI runner have them; a bare host may not |
| An optional package | `pytest.importorskip("deepagents")`, `httpx`, `tree_sitter_language_pack` | `pyproject.toml` `[test]` extras | `uv pip install ".[test]"` |
| Data a run leaves | `no corpus harvested on this host yet`, `not a git checkout` | the loop (`loop.sh corpus harvest`, a git clone) | a run's harvest; a checkout |
| A credential the host lacks | `OPENAI_API_KEY` (the agent smoke test), S3 (the three seeding tests, failing rather than skipped) | the owner | the key or bucket being configured |
| A route a build may not have | `no local-model route on this build` | the server | the route being present |

**Flaky, not skipped:** a few tests depend on test order and fail only beside others in the parallel
run (seen: `test_text_tool_calls`, `test_the_start_form_remembers_how_runs_are_started`,
`test_the_model_server_s_health_is_read_without_a_model_call`, `test_the_sprints_are_served_as_figures`).
`loop.sh suite` runs every failure once more, alone, and reports it as `flaky (passed alone)` or
`FAILED alone too`; only the second is a failure.
