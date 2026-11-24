# Product review: notes-api-hono container 11 (run-10b376e2-ac02-4845-8948-a8b7a89751a0)

**Result (started 18:41 JST 11-24 on :8888, finished 19:56; paused 24 minutes at the owner's word, about 51 minutes active; mixed versions - LF.1282 deployed into it): delivered, hidden 9 of 9, quality 8 of 8, handoff 1.0, mutation 0.58 (0.75 with the unit tests); locked suite 11 of 11.**

- **What happened.** Planning, three suite-authoring passes and one sprint.
  - The first fix round left one defect open: two locked tests share a title prefix, so earlier tests' records pollute later ones. A dispute reclassified one locked test (AC-13/AC-18).
  - Drafting was paused by a deploy at 19:25 and ran in full on resume (LF.1276): 7 drafts accepted at the first pass.
- **The empty body held.** The product kept an empty `body`, and the hidden quality test that lost in five families today passed.
- **But the kept-when-empty probe (LF.1273) asked nothing.** It read "Create request body - title: ..., non-empty" and an example `{"error": "Title is required and must not be empty"}` as holding `body` to a floor, though the specification said "body: any string value including empty is accepted". **LF.1283** (pushed, suite green, deploying at the medium run's next boundary) reads a field's name as a message ("request body") and a quoted sentence as no rule.
- **Cost:** the tool-failure rate was 3.4% (5-run mean 1.5%), from a builder's `rm -rf` and edits to text the files did not hold.
