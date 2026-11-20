# End-of-run product review: notes-api-go container 4 (2026-11-20)

Run run-639189c6-6b03-44d5-b5e5-40ec1d49df9b, notes-api in Go on the standard library, unsloth/Qwen3.6-35B-A3B-MTP-GGUF on :8888, 20:13-21:22 JST. Switch on: `WEB_LOOKUP_WHEN_STUCK`.

**Score:** hidden 9 of 9, quality 8 of 8, **delivered**, handoff 1.0, no false acceptance. **51 active minutes**, 159 model calls, no defect left open, mutation score 0.9 - the fastest delivery of the day. KPI flag: identical calls 3.9% (mean 1.7%).

## What cost time
- Round 0 ran no acceptance test: a backend work order had rewritten `go.mod` from the scaffold's `go 1.26` to `go 1.21`, and the standard library's routing by method and path needs 1.22, so every route answered 404. A fixer found it in one stage (about 5 minutes). LF.1199 (deployed 21:09) now keeps the Go service's `go` line at 1.22 or later at every round and at a stage's end.
- The specification took three architect passes before its review: written in parts at once, one part re-asked for a missing section, then two cross-check revisions. Normal, and cheap.

## Switches
- `WEB_LOOKUP_WHEN_STUCK`: no case - no defect stayed open.

## Added value
A clean Go delivery in under an hour, and the run that made the Go pack hold its module version.
