# Reasoning-cost subsystem: design review (2026-11-11)

Triggered by the step-back rule after four point fixes (LF.805, LF.819, LF.820, LF.821). Written by a designer agent from three independent readers (code map, transcript measurement over 25 runs, external practice with sources). Status: M1 and M2 built as LF.822 (always on, bug fixes). M3 (one ledger and the L3 cap behind `THINKING_OFF_REPLY_CAP`) and M4 (`REASONING_BUDGET`, per server) are queued and will be measured before they are kept.


Nothing in the repository was edited, deployed, started or stopped. I spot-checked these lines against the readers' claims and they hold: `src/app/models/__init__.py:719-748`, `src/app/models/reply_salvage.py:343-452` and `src/app/agents/settled_answer.py:1608-1704`. Git shows LF.805 was committed at 2026-11-10 17:49 JST and was not deployed into the frozen Measure batch.

## 1) Diagnosis

- **The stage cap only limits the first request.** `_generate_paced`'s `finally` clears `_REPLY_CAP.tokens` and `.deadline` (`__init__.py:746-748`) before `salvaged()` runs (`:700`, `:684`). The intended 16k salvage clamp (`reply_salvage.py:438`) writes `max_tokens` next to langchain-openai's `max_completion_tokens`, which stays at the model ceiling (35k on :1234, 32k on :8888). Each salvage request is limited only by the 1800 s timeout.
  - Worst case for one fix reply: about 82k tokens against a 12k cap.
  - Measured: 10 salvages ran to the ceiling, 302,299 tokens and 60.9 min wall over 25 runs.
  - The 23:19 UTC reply on run-45cef9f4 was 12,000 + 35,000 = 47,000 tokens in 408 s.
- **Salvage accepts any reply that has text.** The test `if content.strip() or calls` (`:443`) ignores `finish_reason=length` and prose reasoning. So 147,829 characters of "Let me trace…" were accepted as the answer and recorded as `salvaged=reasoning`. The middleware then counts it as a success, not a loss.
- **Turning thinking off does not stop the reasoning.** All 57 of 57 thinking-off fix replies that hit the cap were reasoning in prose: 17 to 143 reasoning turns each, against a threshold of 5.
  - Thinking off lowers the share of capped fix replies by about a third: 16.6% to 10.9% on :1234, 22.3% to 12.9% on :8888.
  - The replies that still hit the cap burn the full 12k: 344 min wall over 25 runs.
  - A server-side reasoning budget cannot catch this, because the empty `<think></think>` ends its forcing. Only `max_tokens` can.
  - LF.805 sends these replies to the answer-from-reasoning salvage path. Combined with the uncapped-salvage bug, that made 45cef9f4 worse, not better. The 46 continuations in the sample predate LF.805.
- **The token counts are undercounted.** Continuation calls are never added (`_with_the_text`). Shapes that were tried and rejected are never added either. Continuation rows show exactly 12,000 tokens but took 109 to 829 s. The thinking-off counters, `effects` and the audits all decide on these low numbers.
- **Several point rules answer one question.** Whether this visit is reasoning too much is decided in three places:
  - counted from the message history;
  - counters kept as replies come back (LF.819);
  - re-read from the transcript after a resume (LF.821).

  On top of that there are two stage-family switches (SALVAGED_REPLIES_TURN_THINKING_OFF for fix stages, LF.820's SALVAGED_PLANNING_THINKING_OFF for planning) and two cap functions. None of them acts on what is actually measured, which is tokens reasoned per useful reply. Replies that reasoned to the cap cost 878.9 min at 100 tok/s (994 min wall) over 25 runs, a mean of 35.2 min per run.

## 2) Mechanisms

**M1. One reply budget per logical reply (always on; bug fix)**
- **What:**
  - Move the `_REPLY_CAP` scope from `_generate_paced` to `_generate_once`, so the cap and the paced deadline cover the first request, its retries and every salvage request.
  - Add one helper, `_capped(payload, n)`, that lowers whichever of `max_tokens` / `max_completion_tokens` is present and removes the other. Use it in `_get_request_payload` (`__init__.py:582-610`) and in salvage. Delete the raw `payload["max_tokens"]` write at `reply_salvage.py:438`.
  - Cap each continuation request (Path B) at the stage cap.
  - Each salvage request gets a deadline from `paced_timeout(expected 16k)`, not 1800 s.
  - Add every request's usage to the reply's usage (`_with_the_text`, rejected shapes). Record `salvage_requests` and `salvage_output_tokens` in the transcript row.
- **Saving:** the 10 ceiling cases added 302,299 tokens. At 16k per attempt that is at most 160,000, so about 142k tokens are saved: about 23.7 min at 100 tok/s, or about 28.6 min wall pro rata (60.9 × 142/302) over 25 runs. The worst case per fix reply drops from about 82k to 12k + 2 × 16k = 44k, and to 28k with M2.
- **Quality risk:** none. 16k is the cap the code already intended, and its own comment says it fits a whole-file answer.
- **How to measure:** on fix stages, the number of salvaged rows above 28k should be 0. Recorded tokens divided by wall time should come back to the measured 110 to 125 tok/s, which shows the counting is honest.

**M2. One "reasoned to the cap" check, used everywhere (always on; bug fix)**
- **What:** add `reasoned_to_cap(text, reasoning, finish, calls)` in `reply_salvage.py`. It is true when finish is `length`, there is no tool call, and the reply has reasoning, or a reasoning tag left open, or `reasoning_in_prose`. It replaces the three separate entry checks and is applied in three places:
  - at entry, as today;
  - on each answer-from-reasoning reply: accept it only if the check is false. If the first shape reasoned again in prose, do not try the second shape, because prose reasoning does not depend on the shape. Try the second shape only when the first came back empty;
  - on each continuation chunk: stop when the chunk is prose reasoning.

  A rejected salvage returns the original reply marked `salvaged="failed"`, so it counts as lost, not as answered.
- **Saving:** each of the 10 cases costs at most 12k + 16k = 28k instead of 44k to 55k, about 16k to 27k less each (roughly 2.7 to 4.5 min at 100 tok/s per case). The 147k-character false answer, and the structured-extraction pass made on it, no longer go into the next call.
- **Quality risk:** a reply that hit `length` with no tool call and five or more "Let me" openers in an answer would be rejected. A reply like that is not usable in a fix stage anyway.
- **How to measure:** accepted salvages with `finish=length` and no calls should be 0. Count `failed` rows per stage.

**M3. One reasoning-cost ledger per stage visit, with a step-down ladder**
- **What:** add `reasoning_ledger(run, stage)` in `settled_answer.py`. It reads the transcript (the one source that survives compaction and resume) and classifies each reply of the visit with M2's check: ok, reasoned to cap with thinking on, reasoned to cap with thinking off, salvaged ok, or salvage failed. It is cached by row count. It replaces `lost_before`, `salvaged_before`, `last_salvaged`, `_salvaged_so_far`, `_salvaged_in` and the history-based counts in `_thinking_is_off_here`. The ladder per visit:
  - **L1:** after one reply reasoned to the cap, the next reply goes without thinking (today's rule).
  - **L2:** after two, thinking stays off for the visit (today's rule, `LOST_REPLIES_BEFORE_THINKING_STAYS_OFF`).
  - **L3 (new, behind switch `THINKING_OFF_REPLY_CAP`, off until measured):** once a thinking-off reply has reasoned to the cap, thinking-off replies in this visit get a lower cap. The cap is the model's measured p95 of uncapped thinking-off replies for that stage family, taken from transcripts and stored in the fitness file. It is set per model by measurement, never by name, with a floor of 2,000. Salvage then answers from the shorter prose.
  - **Optional at the same level, behind its own guide switch:** the model's measured non-thinking sampling profile (presence_penalty), chosen per model by diagnosis.
- The stage-family switches become rows of one table, one per family.
- **Saving (L3):** 57 capped thinking-off replies × (12k − C). With a placeholder C = 4k, that is 456k recorded tokens, about 76 min at 100 tok/s over 25 runs. Wall time is larger because continuations were uncounted: those 57 replies took 344 min wall, so expect roughly 200 min saved over 25 runs, about 8 min per run. The ledger itself saves no tokens; it removes three counters and their bugs.
- **Quality risk (L3):** it can cut prose reasoning that would have found the fix. That is why it stays behind the switch.
- **How to measure (L3):** a Measure A/B per model comparing:
  - hidden-test score;
  - fix-stage visits needed to reach green;
  - repeated-call rate (the 3% vs 22 to 35% metric in the `LOST_REPLIES_BEFORE_THINKING_STAYS_OFF` comment);
  - wall time per fix stage.

**M4. The server's reasoning budget as salvage in a single call (switch `REASONING_BUDGET`, measured per server)**
- **What:**
  - Fix the probe: `scripts/loop/reasoning_probe.py:36` sends `reasoning_budget`. It should send `reasoning_budget_tokens` (alias `thinking_budget_tokens`) plus `reasoning_budget_message`.
  - Record whether each server honours it in the model's fitness `Support` (`budget_field`). Honoured means reasoning of about 300 tokens or less and non-empty content at a budget of 256.
  - Where it is honoured, thinking-on capped stages send budget = cap − answer room (fix 12k − 4k; plan 20k − 6k), with ENOUGH as the message. The server closes the reasoning and answers in the same call.
  - Reply salvage stays as the fallback when the budget is not honoured or the reply still hits `length`. This is the same salvage the owner prefers, done on the server.
  - It does not help thinking-off prose; that is M3's job.
- **Saving:** 236 thinking-on salvages over 25 runs (about 9.4 per run). Each one avoids a second request: the prefill of up to 16k tokens of reasoning sent back, plus queueing. That is about 16 s per salvage with a prefix-cache hit at about 1k tok/s, and up to about 60 s on a cache miss, so about 2.5 to 9 min per run. This is an estimate; the probe and an A/B must confirm it.
- **Quality risk:** neutral to salvage, since it is the same cut at the same point. Upstream evidence (llama.cpp PR 25961) suggests an injected message can lower reliability, so test both an empty message and ENOUGH.
- **How to measure:** probe each front end (LM Studio and Unsloth Studio may drop the field). Then an A/B on hidden score, salvage count and wall time per capped reply.

## 3) Build plan, in order

1. **M1 cap scope and `_capped`.** Test: a fake client records payloads. The model is built with `max_tokens=35000` and the stage is `defect_fix_1_1`. The first reply has `finish=length` with reasoning. Assert every recorded payload's `max_completion_tokens` is at most 16,000 and none carries both keys. Today the salvage payload has 35,000 and fails this.
2. **M1 honest counting.** Test: the fake client returns a 12k cut text reply, then two 5k continuations. Assert output tokens = 22k and `salvage_requests == 2`. Today it reports 12k.
3. **M2 single check.** Test: the fake salvage reply has `finish=length`, content with 6 "Wait," turns and no calls. Assert exactly 1 salvage request and the result marked `salvaged="failed"`. Today it makes 2 requests and accepts the reply as `reasoning`.
4. **M3 ledger, then L3 behind its switch.**
   - Ledger test: the transcript rows for the stage are [a thinking-off reply reasoned to the cap and salvaged as `failed`, then a prose continuation], and the compacted messages are empty. Assert the next call goes without thinking. Today `_salvaged_so_far` counts only `salvaged=="reasoning"`, so this fails.
   - L3 test: switch on, a measured p95 of 3,000 in the fitness record. Assert the next payload's cap is 3,000. Today it is 12,000.
5. **M4 probe field and budget.** Tests: the probe's budget variant sends the key `reasoning_budget_tokens` (today it sends `reasoning_budget`). With the switch on and `support.budget_field` set, the fix-stage payload carries `reasoning_budget_tokens == 8000`.

## 4) Delete or simplify

- `reply_salvage.py:438`, the raw `max_tokens` write: replaced by `_capped`.
- The second-shape loop: keep it only for an empty reply, never after prose reasoning. Drop `_keep_the_long_shape` rewrites triggered by prose.
- `settled_answer.py`:
  - delete the `lost_before`, `salvaged_before` and `last_salvaged` parameters;
  - delete `_salvaged_so_far` (LF.821), `_salvaged_in` and the counting wrapper in the handler (LF.819);
  - replace the history counting in `_thinking_is_off_here` and `_a_fix_stage_s_salvaged_replies_turn_thinking_off` with one ledger read.
- `fix_stage_reply_cap` and `plan_review_reply_cap`: merge into one `stage_reply_cap(stage, ceiling)` table. The two existing switches stay as rows. LF.820's planning switch becomes a row of the ladder table.
- `reasoning_in_prose` and `reasoning_left_open`: no longer separate rules; they become inputs to `reasoned_to_cap`.
- Keep `_with_its_reasoning_kept_closed`. It is model-agnostic and driven by measurement, but it does nothing on both Qwen models, so do not count it as a mitigation.
- Known gap, left as is: clients with `max_retries != 0` skip `_generate_paced`, so they get no stage cap. The `_capped` / budget scope in `_generate_once` closes this for free if the scope is opened before that branch.
