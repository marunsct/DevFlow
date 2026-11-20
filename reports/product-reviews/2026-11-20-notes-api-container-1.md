# End-of-run product review: notes-api container 1 (2026-11-20)

Run run-fba53958-99ce-4c84-bb34-6b51ed446e7d, notes-api in Python/FastAPI, unsloth/Qwen3.6-35B-A3B-MTP-GGUF on :8888, 17:04-18:29 JST. Switches on: `WEB_LOOKUP_WHEN_STUCK`, `WEB_TOOLS_AFTER_TWO_FAILED_FIXES`.

**Score:** hidden 9 of 9, quality 8 of 8, **delivered**, handoff 1.0, no false acceptance. 70 active minutes, 156 model calls, mutation score 0.75. All 19 locked acceptance tests passed from 17:42 on.

**KPI flag:** defects left open 10 (5-run mean 1) - two defects, both fixed before release:
- the edge probe's `GET /notes/{id}` at a 20-digit id answering 500 (the same SQLite integer overflow as tasks-api 6): left open 4 times, fixed 17:54 after the stuck lookup searched it;
- 16 creates sent at once not all kept: left open 7 times, fixed 18:19 (about 40 minutes).

## What the run showed about the harness
- The stuck lookup fired for the first time on a real defect, but searched the defect's own wording and later the harness's "The unit tests fail. It says: ..." preamble; the server's captured line was uvicorn's header, not the exception. Fixed during the run: LF.1194 (the exception line, not a framework header) and LF.1195 (search from the error name).
- The registry-version lookup asked PyPI for the specification's library call `fastapi.Depends` whole and found an unrelated package of that name; the drafting stage did not pin it. Fixed: LF.1193.

## Recurring
- The very-large-id 500 on Python services: tasks-api 6 and this run. The Python pack now knows its cause (LF.1185) and the fixer now sees the real exception line (LF.1194).
- Concurrent writes not each kept: worth a known cause if it recurs (SQLite under concurrent requests needs one connection per request and a write lock or a serialised writer).

## Added value
A clean delivery in 70 minutes, and the run that made the stuck lookup's query and the server-error capture right.
