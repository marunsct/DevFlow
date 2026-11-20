# End-of-run product review: web-todo-react container 2 (2026-11-21)

Run run-a83705e2-9676-4ff4-bd10-daa0ff773bc7, web-todo-react (React page product), unsloth/Qwen3.6-35B-A3B-MTP-GGUF on :8888, 23:49-01:10 JST. Switches on: `FIX_ORDER_CRITERIA_FIRST`, `WEB_LOOKUP_WHEN_STUCK`.

**Score:** hidden 10 of 10, **quality 5 of 6**, delivered, handoff 1.0, no false acceptance. **73 active minutes**, 165 model calls, 2 fixes reverted (mean 0.6), 6 defects left open, mutation score 0.625. The quality test lost: "an edit to an empty title leaves a titled task" - editing a task's title to empty must be refused or leave the old title; the product accepted it.

## What the run showed
- All 17 acceptance tests were green at 01:03 JST, 1 hour 14 minutes in, after three sprint attempts and two disputes. The same brief on the :1234 model (container 1) is still on its three edit and refresh criteria after about 5 hours: the models differ much more than the harness.
- `FIX_ORDER_CRITERIA_FIRST`: no `fix_order` record was written - the criteria were already raised first, so there was nothing to reorder. This arm did not test the switch. It needs a run where unit-test defects are raised before the criteria.
- The edit-with-empty-title case was the product's own fault and is not covered by the locked acceptance suite (the quality tests are independent). The contract probes did not find it either: they check the interface's lines, not each field's empty edit.

## Switches
- `WEB_LOOKUP_WHEN_STUCK`: no case.

## Added value
A fast, accepted page product on the faster model; the one quality loss is a product edge the suite and probes both missed. A check that sends an empty title to an edit control, in the page probe, would have caught it: worth building (below).
