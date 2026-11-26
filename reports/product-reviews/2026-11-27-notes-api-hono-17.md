# Product review: L notes-api-hono container 17 (run-f6502d06-22f4-4abf-b049-a4592bcdd51f)

**Result: delivered - hidden 9 of 9, quality 0.75 (data 1.0, service 0.5), handoff 1.0; locked suite 10 of 10.** The owner's
model under test, inkling-2-mini (Q4_K_M, two llama.cpp servers of one slot each behind olla); parallel mode; 02:06 to ~07:45
JST 11-27, with two diagnosis pauses and several deploys. 110 tool calls, 0.9% failed; no invented tools.

- **Time:** about 3 hours went to design replies of 30-44k tokens before the reasoning limit worked (from 05:14, IK.3,
  LF.1588); from the acceptance tests to release took about 2.5 hours, including calls queued on one server until per-request
  sessions (06:38).
- **Quality 0.75, re-scored 1.0 after LF.1591 (deployed 08:53):** the two lost checks are "one error shape" and "the error shape the specification states". The product
  answers every error as `{error}`; the other "shapes" counted are an internal TypeScript result type in
  `src/validation.ts` (`{ok: false; status; error}`), not a response. Likely a false finding, to be fixed in the scorer.
- **Gaps:** 32, most of them QA-lead findings about weak assertions left open when fast delivery locked the suite.
