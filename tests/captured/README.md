# Captured outputs

Real output, copied verbatim from runs, for the tests of the harness's parsers and readers. A parser pinned to a
hand-made input passes on a shape the real tool never prints (the LF.1399 lesson; deep review of the parsers,
2026-11-25). Each file here is named for the tool, its version where known, and what the output shows.

## How to capture one

- **A command's output whole:** the journal keeps every output cut for the model, under the worker's
  `/app/data/journal/<reference>` (the reference is in the tool result: "full output saved as ..."). Copy it out with
  `docker cp langchain-worker-1:/app/data/journal/<reference> tests/captured/<tool>-<version>-<what>.log`.
- **A tool result as the model got it:** read the run's transcript (`/app/data/transcripts/<run>*.jsonl`, kind
  `tool_result`), parse its `content` as JSON, and keep only what the tool printed (`stdout`, `stderr`,
  `returncode`, and `command` where it matters) - not the harness's own notes.
- **A saved test result or source file:** copy it from the run's workspace
  (`/app/data/workspaces/default/workspace-<run>/`), for example `.harness/acceptance-result.json`.
- **Versions:** read from the workspace (`node_modules/<package>/package.json`, the runner's header line).

## Rules

- Never edit what the tool printed. The one exception: run ids in the harness's own journal references are replaced
  with `deadbeef` (`tests/test_no_run_ids_in_the_source.py`).
- No secrets: check the file for keys, tokens and passwords before committing it.
- Keep a file only as large as its test needs, unless the size is the point (a long output cut for the model).
- When a pack's runner is upgraded, capture its new output beside the old, so a format change fails a test instead of
  reading as zero.
