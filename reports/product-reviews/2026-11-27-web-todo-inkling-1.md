# Product review: L web-todo container (inkling) 1 (run-e3acafda-458a-4a60-aaed-d85a5968de46)

**Result: delivered by the harness, hidden 7 of 10 - a silent loss and a false acceptance.** Quality 0.83 (interface 0.67,
service 1.0), handoff 1.0; locked suite 11 of 11. First finished run on the owner's model under test, inkling-2-mini (Q4_K_M,
olla, two servers of one slot each); parallel mode; 02:07 to ~07:00 JST 11-27, with two diagnosis pauses and six deploys.

- **The lost tests (3), one cause:** each task row has two elements labelled "Done": the checkbox (named by its wrapping
  label) and the label itself, given `aria-label="Done"`. The hidden tests find the control by its label and Playwright's
  strict mode fails on two matches. The harness's own suite found it by role (`getByRole('checkbox', {name: 'Done'})`),
  which sees only the checkbox, so it passed.
- **Fix (LF.1590, building):** a control the interface contract names by a label must be the only element carrying that
  label inside its record; the page probe raises a second one as a defect.
- **Time:** about 3 hours went to design replies of 30-44k tokens before the reasoning limit worked (IK.3, LF.1588, from
  05:14); after it, build to release took about 20 minutes. About 15 minutes went to four full browser-suite runs that
  could not finish (LF.1589).
- **Model notes:** 116 tool calls, 6.0% failed; no invented tools. Contradictions in the specification were left open at the
  design escalation (11 listed).
