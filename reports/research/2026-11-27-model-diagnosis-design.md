# A model diagnosis that fits the harness to any model: audit, research and design

Date: 2026-11-27 (JST). Research and design only. Nothing in `src/`, `tests/`, the settings or the model servers was
changed, nothing was committed, and **no request was sent to any model server** (no completion, no diagnosis run).
The evidence is the code, the eleven diagnoses kept in the worker (`/app/data/model-fitness/`), the run transcripts
(`/app/data/transcripts/`, 891 files, read-only), the documents and reports in this repository, and published sources
(section 3; each marked as opened or not).

**Correction (checked after writing):** the reply-size comparison in section 1 ("1,855 against 280 to 300", "about ten
times the seconds per step") rests on a few runs. Over 40 recent transcripts the previous model's median reply ranges
from about 120 to 2,300 output tokens by run; this model's from about 1,650 to 2,300 (five runs). By mean reply the new
model writes about 1.5 to 2 times as much, not 6 times. The point that tokens per reply must be measured stands.

## 0. Recommendation

**Rebuild the diagnosis around one question per harness setting: "which value of this setting makes this model do a
real stage's work best, and how sure are we?"** Today's diagnosis mostly asks "can the model do X at all?" on toy
questions, three tries each. It gets the protocol facts right (how to force a structured answer, whether a reasoning
budget is enforced). It does not measure the things that cost the most time this week: how much a model reasons on a
real stage, how fast it is, how the endpoint behaves under two requests, and what its replies look like at stage size.

The design in section 4 has five parts:

1. **One model profile, one setting per field.** Each field has a value, where it came from (owner, server, measured,
   default), the evidence (tries, passes, an interval), and whether it is applied. The profile is keyed by a
   fingerprint of what was measured (model file, quantisation, chat template, server build, endpoint layout, probe-set
   version), not by the served name alone.
2. **Probes that are replays of real stage requests.** The transcripts already hold every request in full. A fixed,
   scrubbed, versioned set of them, a few per stage kind and from several product families and stacks, is replayed
   against the new model and scored by deterministic checks (schema valid, tool offered, edit applies, role kept).
   No hidden test is ever used.
3. **Calibration sweeps, each ending in a decision rule.** Reasoning effort, reasoning budget, reply cap, context
   size, concurrency, session scope, edit format, tool-list size and guidance lines are each tried at two to four
   values on the same items, paired. A value is adopted only when the gain is larger than the noise at that sample
   size, and never when anything else gets worse.
4. **Two tiers.** A quick tier (about 10 to 15 minutes, about 50 requests) before a model's first run, which sets
   everything that can lose a run. A full tier (20 to 90 minutes depending on the model's speed) between runs, which
   runs the sweeps.
5. **A feedback loop.** Every run already records what the model did. The same quantities the probes measure are
   counted in live runs, compared with the profile, and a drift or a change in the fingerprint asks for a new
   diagnosis.

**The first three things to build** (section 6):

1. **Make the present diagnosis's results true** (four small fixes): a server error is "not measured", not a failed
   try; a guidance line is kept only if nothing else fell; two checks that nearly every model fails are taken out of
   the tier score; "usable" needs a reply that proves it. Add the fingerprint and a probe-set version to what is kept.
2. **A speed and concurrency profile**: tokens per second, prompt speed, cache reuse, and whether two requests at once
   really run side by side. It sets the timeout floor, the parallel cap and the session scope. Nothing measures these
   today.
3. **A reasoning dose-response measured on replayed stage requests**: how many tokens the model reasons on a step, a
   review and a design request at each effort and budget, and whether the answer stays right. It sets effort, budget
   and reply cap per stage kind on the first day.

Each of today's losses would have been caught by items 2 or 3, or flagged by item 1 (section 1).

## 1. Today's facts, explained by gaps in the diagnosis

| Fact | Why the diagnosis did not catch it | What a general diagnosis measures instead |
|---|---|---|
| The reasoning-effort effect was "not measurable"; no effort was kept although the chat template defaults to 0.9 | The reasoning probe is one fixed puzzle asked once per way (`diagnostics.py:71`, `:276`). On this model it cost 145 output tokens as served, under the 200-token floor (`diagnostics.py:79`, `:703`), so nothing was kept. The seven ways measured 124 to 229 tokens, one sample each: that spread is noise. The template default (0.9) was read from `/props` and written as advice only; no code reads `template_default_effort` to choose an effort. | The question must be long enough for this model. Use a ladder of real stage requests and climb until the model reasons at least about 1,000 tokens as served, then compare efforts with repeats. A known template default is itself a finding: "nothing sent means high". |
| Design replies ran 30,000 to 44,000 tokens until a budget worked | No probe is stage sized for reasoning. The one stage-sized check, "an answer within a stage's reply", only asks whether a plan finishes under 32,768 tokens (`deep_diagnosis.py:354`); this model passed 3/3. The budget probe proved the server ends reasoning at a bound but tried only 64 and 0 tokens on a digit-sum question; "usable" was then set to true without a reply to prove it (`diagnostics.py:399`: no moderate reply means usable). | Measure reasoning tokens on a replayed design request, a review request and a step, at each effort and at two or three budgets. Set a budget per stage kind from that. This is what LF.1588 and LF.1593 then did by hand, from live runs. |
| Two one-slot servers behind a balancer queued both runs on one server | The profile counts slots correctly since LF.1579 (`server_profile.py:157-184`) but nothing measures how the balancer spreads requests. Session scope is an environment setting (`session_header.py:60`). | A concurrency probe: send as many requests at once as there are slots, under distinct sessions as two runs would, and see whether total throughput rises. If it does not, use per-request sessions or lower the parallel cap. |
| Generation speed about 35% below the previous model | Speed is never measured. The timeout floor is a constant, 30 tokens a second, or an environment value (`models/__init__.py:60-90`). From the transcripts (replies of 1,500 tokens or more, wall clock, the same endpoint): this model's median is 62 tokens a second, the previous model's 102 to 122. | Measure tokens per second and prompt tokens per second. More important: **tokens per reply**. This model's median reply is 1,855 output tokens, the previous model's 280 to 300. Six times the tokens at 0.6 times the speed is about ten times the seconds per step. That one number predicts run time. |
| A run lost hidden tests to a duplicated accessible label | The diagnosis checks whether the model follows the request's form. It never looks at what the model writes into a product. The fault was a habit of the model's output (a label given the same name as the control inside it), and the harness's own suite did not see it either. | Not a model setting. The general lesson is for the probes that score output: replay a small "write this part" request and run the harness's own deterministic product checks on the result (after LF.1590 the page probe has this one). It shows which known faults a model produces unprompted. Doubtful value, so behind a switch and in the full tier only (4.3, P11). |

## 2. Audit of the current diagnosis

### 2.1 What runs, and when

A model with no kept record is diagnosed at its first run segment (`server/tasks.py:771-805`) or when the server is
seen to serve another model mid-run (`call_gate.py:160-185`), one run at a time (`diagnosis_flight.py`). Four parts:
the tool and reasoning diagnosis (`diagnostics.py`), reply salvage (`reply_salvage.py`), the deep diagnosis and
steering profile behind `MODEL_GUIDANCE` (`deep_diagnosis.py`, `guidance.py`), and capabilities (`capabilities.py`).
The settings page can run all of it again (`steering_job.py`), refused while a run is live. `loop.sh diagnose`,
`fitness` and `ready` run parts by hand. A hosted model with its own client is skipped entirely
(`tasks.py:778-784`, `diagnostics.speaks_chat_completions`).

### 2.2 Each check: what it sets, whether that is read, whether it changed an outcome

"Read" means some code other than a report or the settings page uses the value.

**Tool and reasoning diagnosis (`diagnostics.py`), 3 tries a check, passes at 2 of 3 (`:47-49`).**

| Check | Sets | Read by | Changed an outcome? |
|---|---|---|---|
| tools offered; a tool required; one tool named; a named tool the request does not fit; one tool named, thinking off | `structured_answers` (forced, required, offered), `force_only_without_thinking` (`settled`, `:621-692`) | `_NAMED_CHOICE_BECOMES_REQUIRED` and `_NO_FORCED_TOOL_WHILE_THINKING` (`models/__init__.py:765-768`), `named_answer.HONOURED` (`named_answer.py:52`) | **Yes.** It changes the request form. On the newest model a named choice was read as `auto` (forced 0/3, required 3/3), found by the "does not fit" check added in LF.1582. On the LM Studio server the named form is a 400 and `required` is sent. The first forced call of a run once failed for want of this. No on/off run pair exists, but the failure it prevents is a failed stage. |
| a structured answer forced / offered / required; forced after a long request | the same settings, on a stage-shaped request | the same | **Yes**, same evidence. The most useful checks in the file: they use the real answer schema and a real tool list. |
| only offered names | advice about tool aliases | nothing | No. |
| the right one of many tools | nothing (`settled` does not use it) | nothing | No. Every kept record read passes 3/3: it tells models apart not at all. |
| two calls in one reply | advice; capability `parallel_tool_calls` | shown only (`capabilities.py:348`) | No. |
| a fact in a long request | advice | nothing | No. One try, at 24,000 tokens, on servers whose slots are 93,000 to 231,000. Every local model passes. The one "fail" (a hosted model) was a 413 "request too large", kept as "a fact ... was not read". |
| the five tool-fitness probes (`fitness.py:51`) | a count; a verdict fit/usable/unfit | printed by `loop.sh fitness` and `ready`; never a gate | No. |
| find-and-replace edits well formed (`fitness.py:131-179`) | `edit` and `whole` rates; `registry.edit_preference` | **Only `registry.describe`, a line of `loop.sh ready`** (`registry.py:172-186`). No stage reads it. | No. The newest model measured 83% and an earlier one 67% and nothing changed for either. The sample is 6 edits of three-to-seven-line files, so 83% is one miss. |
| reasoning switches (`_reasoning_cost`, `:276`) | `least_reasoning_effort`, `effort_route`, `template_thinking_switch`, `reasoning_measurable` | `thinking.measured` (`diagnostics.py:792`, `agents/thinking.py:349`), used by the calls that must answer without reasoning | **Partly.** On the Qwen builds it found "none" (146 tokens to 3). On the newest model it kept nothing, so every "answer without reasoning" mechanism was inert there. One sample per way; the 70% rule (`:81`) is applied to single numbers. |
| reasoning budget (`_budget_probe`, `:320`) | `reasoning_budget`, `reasoning_budget_usable`, `zero_budget_answers` | `reasoning_budget.learnt` (`reasoning_budget.py:78-90`), behind `REASONING_BUDGET`; `step_budget.py` behind `STEP_SIZED_REASONING_BUDGET` | **Yes, in time.** After the budget worked, one run went from design to release in about 20 minutes where design alone had taken about 3 hours (`reports/product-reviews/2026-11-27-web-todo-inkling-1.md`). But the budget sizes (cap less answer room; 8,000 a step) came from live runs and transcripts, not from the diagnosis. `docs/measuring.md` lists both switches as not measured. |
| template default effort (from `/props`) | `template_default_effort` | nothing but the advice line | No. |

**Deep diagnosis (`deep_diagnosis.py`), 12 checks, 3 tries each, then each guide tried on the checks it is for.**

| Output | Read by | Changed an outcome? |
|---|---|---|
| guides chosen (`guidance.chosen_by`, `guidance.py:127-141`) | `model_guidance.guidance_key` in the instruction middleware (`plugins/middleware.py:612`), behind `MODEL_GUIDANCE` and one `GUIDE_*` switch each | **Unknown.** `docs/measuring.md` lists all eight `GUIDE_*` switches as on in 488 scored runs, off in 0, "no signal". No guide has a firing record or an off arm. |
| end-of-request reminder | `STEERING_AT_THE_TAIL` | **Probably yes**: hidden 0.92 on, 0.70 off, but on 2 off runs. |
| tier (strong from 0.9, standard from 0.65; `guidance.py:43-44`) | acceptance batch size (`graph/acceptance_batches.py:26`), lean prompts for strong models (`agents/lean_prompts.py:76`), the support matrix (`stacks/support_matrix.py:68,134`: weak makes every stack experimental) | **Doubtful, see 2.3.** No kept model has ever scored 0.9, so "strong" has never been assigned from a diagnosis. |
| reply ceiling when a check looped (`:452`, 40,000) | `model_guidance.ceiling_for` (`models/__init__.py:731`) | Rarely. The ceilings that mattered were set from runs (`loop.sh ceiling`: 24,000 on one model) or by hand (12,000 on another), not by the diagnosis. |

**Capabilities (`capabilities.py`).** `reads_images` is read (`vision.py`) and has prevented failed stages.
`context_window` from the server is read by every budget. `knowledge_cutoff` and `researches` are read behind switches
that are off or unmeasured. `json_schema_answers`, `native_tool_calls`, `multilingual`, `forced_tool_enforced`,
`continues_a_begun_reply`, `thinking_switch`, `reasons` and `parallel_tool_calls` have no reader outside the settings
page.

**Server facts.** `server_profile.py` (slots, per-slot context, quantisation, the pool behind a balancer) is read by
the parallel cap and by `request_fit.py`, and has prevented refused requests and under-used servers. This is the part
of the present system that works best, and it costs no model call.

**Never measured:** generation speed, prompt speed, cache reuse, queueing under concurrency, how the balancer spreads
sessions, tokens per reply, reasoning at stage size, effective context beyond 24,000 tokens, edit quality on files of
real size, the effect of tool-list size, sampling (derived from the model card, never measured), any quality of
written output.

### 2.3 What the eleven kept diagnoses show about the diagnosis itself

Read from `/app/data/model-fitness/*.json`.

| Finding | Evidence | Consequence |
|---|---|---|
| **Two checks fail on nearly every model.** | "the answer as a call, not as text": 0/3 on 9 of 11 records, 1/3 on the other two. "a refusal heeded": 0/3 on 9 of 11. Yet these models give their answers in runs. In "the answer as a call" the request already holds a passing test run and then "Give your answer now"; most models run one more command first. In "a refusal heeded" most models read the file before editing it, which is counted as a failure. | The probes measure their own wording. Six of 36 tries are lost by everyone, so the highest tier score ever kept is 0.806 and no model can be "strong". |
| **Server errors are scored as the model's failures.** | `deep_diagnosis.py:403`: "a failed call is a failed try". One hosted model's 413 "request too large" and 400 tool-validation errors made it "weak" (0.583) with a tail reminder. One local diagnosis lost 2 of 3 tries to a proxy timeout of 30 seconds; another lost several to 503s. | The tier, the guides and the support matrix follow from outages and rate limits. |
| **"Helped" is mostly noise.** | A guide is kept when the pass count over 3 tries rises by one (`deep_diagnosis.py:435`). For a line with no effect and a base rate of 0.5, a rise happens 39% of the time (computed; 34% at a base rate of 0.33). | About one in three useless lines is kept. |
| **No harm check.** | With its kept guidance, one model's "a long list without repeating itself" fell from 3/3 to 0/3, another's from 3/3 to 1/3, the newest model's "a rule kept after a long request" from 3/3 to 2/3. The profile kept the lines in all three. `with_guidance` is recorded and never read. | A line that breaks something else stays on. |
| **The same model gets different settings on different days.** | One model family has four records under four names, three of them diagnosed. Structured answers: forced, forced only with thinking off, required. Guides chosen: one, none, two. Some of that is the server (LM Studio against llama.cpp), which is right; the rest is 3-try noise, which is not. | The record is keyed by the served name (`registry._slug`), with no record of the server, template or probe version it was measured on. Nothing re-diagnoses when those change (`diagnose_if_new`, `:829`: only when there is no record). |
| **"Usable" without proof.** | The newest model: budget 64 answered wrong, budget 0 answered wrong, the moderate budget was never asked because the question reasoned too little, and `reasoning_budget_usable` is true. | The setting happened to be right. The rule that set it is not evidence. |

### 2.4 What earlier models taught that the diagnosis did not catch

| Model | What the runs showed | Was it in the diagnosis? |
|---|---|---|
| Qwen builds | 16,000-token-plus replies hold 18 to 46% of all output tokens; design, lead and review stages reason 20,000 to 48,000 tokens; reviews are mostly reasoning (`docs/measuring.md` M9) | No. Found in runs; answered by reply caps, salvage and `REVIEWS_WITHOUT_REASONING`. |
| Qwen on a 4-slot pool | Requests refused at 20,000 to 48,000 tokens because the context is per slot; sessions hashed to one server | The first is now a server fact (free). The second was found in runs twice (LF.1407, LF.1576) and again today. |
| gpt-oss-20b | Small brief 9/9, large brief 1/10; a 79,000-token reply repeating one word; fails when it must invent the toolchain | Only "edits 67%" and "one call a reply" were measured, and neither is read. Its ceiling was set by hand. Nothing measures how success falls with the size of the work. |
| LFM2.5 | Plans as near misses of their schema; 107,596 tokens of one repeated string; product code written from the wrong role through a shell | These became the deep diagnosis's checks, after the runs. The repetition check passes 3/3 on every kept model, including that one. |
| A 1-bit build | Invented tool names, one query sent 27 times, 101 minutes over a plan | The five fitness probes were written for it; they are printed, not acted on. |
| All of them | Quantisation and the server engine change the result as much as the model | The record does not key on either. |

The pattern: each new model taught one lesson through a failed run; a check was then written for that lesson in the
shape of that failure. The checks are a list of past incidents. They do not span what a stage needs, and they are not
sized to tell a rate of 0.6 from a rate of 0.9.

## 3. Published research

Gathered on 2026-11-27 with generic queries (no project details). **[V]** = the page was opened and the numbers come
from it. **[S]** = from a search result's summary only, **not verified**. Several [S] items carry paper numbers I did
not open; treat them as leads, not facts.

| Topic | Finding | Source | What it means here |
|---|---|---|---|
| Harness and model fit | Two models under three harnesses on 50 tasks: pass rates within a model differed 0 to 8 points, tokens per solved task up to 40 times; each harness had its own failure signature. | [V] https://arxiv.org/abs/2607.22585 | Score fit on tokens and time per solved item, and keep a failure-mode count per model. |
| | 21,730 rollouts, 9 models, 9 benchmarks: higher reasoning effort lowered accuracy in most runs. | [V] https://arxiv.org/abs/2510.11977 | Never assume more effort is better; sweep it. |
| | Same-model swings of tens of points across scaffolds. | [S] https://arxiv.org/abs/2605.23950 ; [S] https://www.tbench.ai/leaderboard/terminal-bench/2.1 | Supports per-model fitting; the size is unverified. |
| Per-model profiles | Aider keeps one record per model: edit format, weak model, repo map, lazy, overeager, reminder, examples as system message, temperature use, system prompt use, streaming, reasoning tag, accepted settings, extra parameters. | [V] https://aider.chat/docs/config/adv-model-settings.html | The closest published shape for the profile in 4.2. Aider's is hand-kept; here it is measured. |
| | Capability maps (flags for tool calling, reasoning, caching; context limits). | [S] https://docs.litellm.ai/docs/provider_registration/add_model_pricing ; [S] https://github.com/anomalyco/models.dev | Priors only. The diagnosis measures and overrides. |
| Edit formats | The polyglot leaderboard reports "percent using correct edit format" per model: 91.6% to 100% over 12 rows read; models are run on different formats. | [V] https://aider.chat/docs/leaderboards/ | Measure malformed-edit rate per format; pick per model. |
| | Describe-then-apply raised every model: 79.7 to 85.0, 77.4 to 80.5, 71.4 to 75.2, 61.1 to 71.4. | [V] https://aider.chat/2024/09/26/architect.html | A two-step edit is a candidate for a model with a poor edit rate. |
| | Unified diffs cut "lazy" elisions for one model and hurt another; the best format depends on model and task. | [S] https://aider.chat/docs/unified-diffs.html ; [S] https://arxiv.org/abs/2510.12487 | Include an elision probe on a long file. |
| Tool calling | llama.cpp: native handlers for some templates, else a generic format that costs more tokens; parallel calls off unless asked; template capabilities at `/props`; an aggressively quantised KV cache degrades tool calling. | [V] https://raw.githubusercontent.com/ggml-org/llama.cpp/master/docs/function-calling.md | Read `/props` first; record native or generic. |
| | Report the chance that all of k tries succeed, not only the mean: one model 61% once, 25% eight times running. | [S] https://arxiv.org/abs/2406.12045 | A stage makes many calls in a row; per-call rates of 0.9 are not good enough. |
| | Tool selection falls as the tool count grows. | [S] https://arxiv.org/abs/2607.15593 ; [S] https://arxiv.org/abs/2505.10570 | Probe the harness's own short and long tool lists. |
| Structured output | Strict formats can hurt reasoning; a rebuttal says that was the prompt; constrained decoding is faster and slightly better across about 10,000 schemas. | [S] https://arxiv.org/abs/2408.02442 ; [S] https://blog.dottxt.ai/say-what-you-mean.html ; [S] https://arxiv.org/abs/2501.10868 | Disputed. Compare the two forms per model on the same items. |
| Reasoning effort and budget | Effort affects all output including tool calls; most of the gain is present at "high"; the top level can overthink structured work; the advice is to sweep effort on your own evals; changing effort mid-conversation can drop the prompt cache. | [V] https://platform.claude.com/docs/en/build-with-claude/effort | Sweep per model; hold effort fixed inside one conversation. |
| | llama.cpp: `--reasoning-budget` -1, 0 or N; reasoning formats; per-request template arguments. | [V] https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md | The controls differ per server; verify each by its effect. |
| | A reported case of an effort argument with no effect. | [S] https://github.com/ggml-org/llama.cpp/issues/15130 | Never trust a flag; measure reasoning tokens. Matches IK.2 here. |
| | Accuracy rises with thinking tokens, then falls (82.2% to 87.3% to 70.3% at about 16,000). | [S] https://arxiv.org/abs/2506.04210 ; [S] https://arxiv.org/abs/2508.13141 | A budget can raise quality as well as save time. |
| | Temperature 0 does not make code generation deterministic. | [S] https://arxiv.org/abs/2308.02828 | Repeats are needed whatever the sampling. |
| Context length | 18 models, 194,480 calls: results degrade with length even on trivial work; distractors compound; focused input beat full input for every model. | [V] https://www.trychroma.com/research/context-rot | Measure the same item at several padded lengths with on-topic distractors. |
| | "Effective length" defined as the longest input keeping 85% of the short-input score; at 32,000 tokens 11 of 13 models were under half. | [S] https://arxiv.org/abs/2502.05167 | A ready definition for the compaction threshold. |
| | Tool results are about 84% of an agent turn's tokens; masking old results halves cost and matches summarising. | [S] https://arxiv.org/abs/2508.21433 | Agrees with what `request_fit.py` and the old-reads stubs already do. |
| Speed and concurrency | llama.cpp: slots, shared KV buffer, `cache_prompt` on by default, `id_slot`, slot similarity; `/slots`, `/props`, `/metrics`; replies carry timings (prompt tokens, cached tokens, tokens per second). | [V] https://raw.githubusercontent.com/ggml-org/llama.cpp/master/tools/server/README.md | Read timings from each reply; read `/slots` for the real per-slot context. |
| | Without a shared KV buffer the context is divided by the slot count. | [S] https://github.com/ggml-org/llama.cpp/issues/11681 | Matches what `server_profile` already reads. |
| | Balancer strategies (priority, round-robin, least connections); cache-aware routing claims large gains on shared prefixes. | [S] https://thushan.github.io/olla/concepts/load-balancing ; [S] https://docs.litellm.ai/docs/routing ; [S] https://developers.redhat.com/articles/2026/01/13/accelerate-multi-turn-workloads-llm-d | Nothing was found on sticky sessions in olla's documents. Measure sticky against spread on the owner's endpoint. |
| | Load tools sweep from one request to full rate and report time to first token, time between tokens, requests per second, and "goodput" (requests meeting a target). | [S] https://github.com/vllm-project/guidellm ; [S] https://docs.nvidia.com/aiperf/latest/tutorials/metrics-analysis/benchmark-goodput-with-ai-perf | Use the same quantities; a ladder of 1, 2, up to the slots is enough. |
| Statistics | Sample size for a difference; 3 points at 80% power needs about 969 questions; with 198 questions, 10 repeats each cut the detectable difference from 13.2 to 7.5 points; paired comparison and clustered errors. | [V] https://arxiv.org/abs/2411.00640 | With 10 to 20 items only large effects can be seen. Always pair. Repeat items before adding items. |
| | 60,000 agent trajectories: one run moves pass rate 2.2 to 6.0 points; spread above 1.5 points even at temperature 0. | [V] https://arxiv.org/abs/2602.07150 | One run proves nothing about a setting. |
| | Sequential tests and anytime-valid comparisons for evals. | [S] https://aclanthology.org/2026.findings-acl.43.pdf ; [S] https://neurips.cc/virtual/2026/172171 | Stop early only under a rule made for stopping early. |
| | Prompt formatting alone moves accuracy by many points. | [S] https://arxiv.org/abs/2310.11324 | A guidance line must beat that noise floor. |
| Cheap probes | About 100 well-chosen items estimate a full benchmark within about 2%. | [S] https://arxiv.org/abs/2402.14992 | Keep a small anchor set of items that tell models apart. |
| | Success against task length fits a curve; the length at 50% success is a model's "horizon". | [S] https://arxiv.org/abs/2503.14499 | Size the probes in tiers (step, stage, sprint) and find where success crosses a half. |
| | Scoring the next step from a recorded state; replaying from recorded prefixes; a warning that exact-match scoring under-counts valid paths. | [S] https://arxiv.org/abs/2610.10478 ; [S] https://arxiv.org/abs/2608.22960 ; [S] https://arxiv.org/abs/2501.16150 | Supports replay probes scored by outcome (does the edit apply), not by matching the recorded reply. |
| Cost | Token counting before sending is free and accepts tools and thinking; counts differ by model. | [V] https://platform.claude.com/docs/en/build-with-claude/token-counting | Count every probe first; refuse a sweep over the ceiling. |
| | Cached input is read at about a tenth of the price; batch requests are half price. | [V] https://developers.openai.com/api/docs/guides/prompt-caching ; [S] https://platform.claude.com/docs/en/about-claude/pricing ; [S] https://developers.openai.com/api/docs/guides/batch | Put the shared probe prefix first; batch the probes that need no reply at once. |

**Not found:** a published cross-model table of find-and-replace failure rates beyond Aider's one column; anything on
olla's sticky sessions and prompt caches; a direct measurement of agent success against tool-history length.

## 4. The proposed design

### 4.1 Principles

1. **A probe exists only for a setting.** Every probe names the harness setting it controls and the rule that turns
   its number into a value. A measurement with no reader is not run (today: recall at 24,000 tokens, two calls a
   reply, the edit rates).
2. **Probes are stage shaped and replayed, never invented.** A probe is a recorded request of a real stage with the
   real tool list and answer schema. It is scored by what the reply does (valid schema, offered tool, an edit that
   applies), never by matching the recorded reply and never by a hidden test.
3. **Not tuned to one model, stack or product.** The probe set draws from at least three product families and three
   stacks per stage kind. Decision rules name no model. A value specific to a stack still lives only in a pack or
   `plugins/seed.py`.
4. **A number has a sample size and an interval, or it is "not measured".** Three outcomes for every field: measured,
   not measured (and why), not applicable. A server error is never a failed try.
5. **Default unless proven.** A setting leaves its default only when the paired gain clears the rule for its sample
   size and nothing else got worse. Quality settings need a clear gain; efficiency settings need no loss (the owner's
   "quality first" rule), and stay behind their switch until a run pair confirms.
6. **The servers are the owner's.** The diagnosis reads, and sends ordinary requests. It never loads, stops or
   reconfigures a server, never sends more requests at once than the slots the server reports, and never sends
   sampling the owner has not turned on (ADR-0008).

### 4.2 The profile

One record per fingerprint, in `DATA_DIR/model-fitness/` as now, with a history.

- **Fingerprint:** served model file or name; quantisation; a hash of the chat template; the server's build string;
  the endpoint layout (addresses behind a balancer, slots each, per-slot context); the provider for a hosted model;
  the probe-set version; the harness's decision-rule version. All but the last two are read without a model call.
- **Each setting:** value; source (owner, server, measured, default); evidence (items, tries, passes, interval, median
  tokens and seconds); confidence (sure, likely, not measured); whether applied; the switch that guards it if any.
- **The owner's value always wins**, as in `capabilities.py` today.
- **A change of fingerprint** makes the old record a prior, not the truth: its settings are used until the quick tier
  has run again, and the run's provenance says so.

Settings the profile controls, with where each lives today:

| Setting | Today | From the profile |
|---|---|---|
| structured answer form (forced, required, offered) | diagnosis | kept; stage-sized items only |
| reasoning effort per stage kind (step, review, design, answer-now) and its route | one run setting (`thinking.DEFAULT_EFFORT`, medium); least effort from a puzzle | measured dose-response |
| reasoning budget per stage kind | cap less answer room; 8,000 a step, both constants | measured p90 of reasoning in passing replies |
| reply cap per stage kind; looping ceiling | deployment setting; ceiling by hand or `loop.sh ceiling` | measured |
| timeout floor (tokens per second) | constant 30 or an environment value | measured p10 speed |
| parallel cap; session scope | slots; `.env` | measured throughput at each concurrency |
| input room and compaction point | slot less reserve | the smaller of the slot and the measured effective context |
| edit tool by file size | none (rate unread) | measured per format and size |
| tool list (short or full) | switches for every model | measured |
| guides and end reminder | 3-try rise | paired, with a harm check |
| tier (batch size, lean prompts, support matrix) | share of 36 tries | stage-kind pass rates on replay items, with intervals |
| images, cutoff, lookups, salvage shape | as now | as now |
| sampling | card and family, sent only if the owner says | advice only; an optional sweep behind a switch |

### 4.3 The probe stages

Sizes are for the full tier; the quick tier is in 4.6. "Items" are replayed requests; "tries" are repeats of one item.
Time is for a model at about 60 output tokens a second on two slots; a faster model takes less.

| # | Probe | Measured quantity | Setting it controls | Decision rule | Sample | Budget |
|---|---|---|---|---|---|---|
| P0 | **Server facts** (no model call): `/props`, `/slots`, the balancer's status page, the template text, model lists | slots, per-slot context, template capabilities (tools, effort levels, default effort, thinking switch read or not), quantisation, vision part, engine and build | fingerprint; priors for P3 and P4 (which efforts and routes to try); parallel cap ceiling | facts, no rule. A template default effort above medium is flagged: "nothing sent means high". | 3 to 6 GETs | seconds, 0 tokens |
| P1 | **Speed**: one short request and one long-prefix request sent twice | output tokens a second; prompt tokens a second; time to first token; share of the prompt read from cache on the second send (server timings where given, else wall clock on a streamed reply) | timeout floor; time estimates shown to the owner; whether a conversation's cache is worth keeping | floor = slowest of 5; cache "works" if the second send's prompt time is under 30% of the first | 5 + 2 requests | 2 min, about 3,000 output, 40,000 input |
| P2 | **Concurrency and spread**: k requests at once, k = 1, 2, up to the reported slots, each under its own session as separate runs would be; then the same with per-request sessions | total tokens a second at each k; queue time; for a pool, whether k sessions ran side by side | parallel cap; session scope | cap = largest k whose total throughput is at least 1.3 times that of k-1. Per-request sessions if they give at least 1.3 times the throughput of conversation sessions at k = slots; else conversation sessions (the cache is kept). | 3 rounds per k and scope | 3 to 5 min, about 8,000 output |
| P3 | **Protocol**: the present tool and structured-answer checks on stage-sized requests only | pass rate of each request form | structured answer form; named-answer use; one call or several a reply | a protocol fact is the server's: 3 agreeing tries settle it, any disagreement asks 5 more; then the present `settled` logic | 8 forms, 3 to 8 tries | 3 min, about 8,000 output |
| P4 | **Reasoning dose-response**: three replayed requests (a step after tool results, a review, a design or plan), climbing in size until the as-served reply reasons at least 1,000 tokens; each asked at every effort the server lists, by field and by template argument, and at three budgets | reasoning tokens (server count, else reasoning text); output tokens; seconds; whether the answer passes its item's checks; whether the reply hit its cap | effort per stage kind and its route; whether a budget is enforced; budget per stage kind; reply cap per stage kind; the "answer now" form | a control "works" if median reasoning falls below 70% of as-served over 5 tries each (not single replies). Effort for a stage kind = the lowest whose pass count is within 1 of the best over 10 paired tries. Budget = p90 of reasoning tokens in the passing replies at that effort, rounded up, never above cap less answer room. Cap = budget plus the largest passing answer times 1.25. | 3 kinds, up to 4 efforts and 3 budgets, 5 tries | the largest cost: 25 to 40 min, 150,000 to 250,000 output |
| P5 | **Stage replays**: 8 to 12 recorded requests per stage kind (plan, design, review, suite author, builder step, fixer step, final answer) from delivered runs of several families and stacks | per kind: schema-valid answer; a call to an offered tool with valid arguments; path inside the role; one program a command; stops when its checks pass; no repetition; not cut at its cap; tokens and seconds per reply | tier per stage kind (batch sizes, lean prompts, support matrix); which guides are candidates (P9); the predicted minutes per stage | sequential test per behaviour: works at 0.9 against fails at 0.6, error rates 0.1, at most 16 tries (5 to 9 on average); "unsure" keeps the default and is watched in runs (4.7) | about 70 items, 1 to 2 tries each | 15 to 25 min, about 140,000 output |
| P6 | **Context ladder**: the same 6 questions at the end of four padded requests (8,000, 24,000, 64,000 tokens and 0.8 of the slot); the padding is recorded project memory with on-topic distractors and is the same for every question at one length, so the server reads each length once and answers the rest from its cache | score at each length: a fact recalled, a rule kept, a forced answer valid | input room and compaction point | effective context = the longest length whose score is at least 85% of the 8,000-token score; room = the smaller of that and the slot | 4 lengths, 6 questions | 5 to 10 min; 4 long prompt reads, about 5,000 output |
| P7 | **Edit formats**: 12 recorded edits on files of three sizes (under 50, about 150, over 400 lines), each asked as a whole-file write, a find-and-replace and a line-range replace | the edit applies; the file equals the target after normalising space; nothing else lost; an elision left in ("rest unchanged"); output tokens per edit | which edit tool is offered first by file size (today `WHOLE_FILE_LINES`, unread) | per size band: the cheapest format whose clean-apply rate is within 1 of the best over 12 | 36 requests | 5 to 8 min, about 40,000 output |
| P8 | **Tool-list size**: 10 recorded steps asked with the role's short list and the full list | right tool chosen; arguments valid | `LEAN_TOOL_LISTS`, `TOOL_LISTS_BY_ROLE_KIND` for this model | short list unless the full list is better by 3 of 10 | 20 requests | 2 min |
| P9 | **Guidance lines**: only for behaviours P5 found short; each line tried on the items that failed and, once chosen, the whole set tried on the items that passed | paired pass counts with and without the line | the model's guides and end reminder | keep a line if it gains at least 3 of 10 paired tries (a useless line passes this about 12% of the time; a line worth 40 points passes about 78%) **and** no behaviour that passed falls by 2 or more with the whole set | up to 8 lines, 10 pairs each | 0 to 15 min |
| P10 | **Capabilities**, as now: an image, a schema, lookups, cutoff from the card, salvage shape | as now | images shown or not; web tools; API cards; salvage | as now; a refusal is "no", no answer is "not measured" | as now | 2 min |
| P11 | **Output habits** (doubtful; behind a switch; full tier only): 3 to 5 replayed "write this part" requests of different product kinds, the reply's files run through the harness's own deterministic product checks | which known product faults the model writes unprompted | which product-side reminders (general, pack-neutral rows) are shown to this model's builders | a reminder is on if its fault appears in 2 of 5 | 5 requests | 5 to 10 min |

How the replay set is built (P4 to P9, P11):

- **Source:** `model_request` records (messages, tools, blocks) with the `model_response` that followed, from runs
  that ended delivered. Requests are chosen at points where the next step has a property a program can check.
- **Spread:** per stage kind, at least three product families and three stacks, and three sizes of request.
- **Scrubbed:** run ids, host paths and names removed. A test asserts that no probe holds text from a hidden-test file
  and that none holds a run id.
- **Frozen and versioned:** kept as fixtures with their checks and a set hash. Changing the set changes the probe-set
  version in the fingerprint, so profiles made with the old set are marked.
- **Maintained by evidence:** after four or more models, an item everyone passes or everyone fails is moved out of the
  scored set (kept as a cheap sentinel at one try). A probe whose rate disagrees with the same behaviour's live rate
  (4.7) is retired. That is the rule the two checks in 2.3 fail today.

### 4.4 Calibration sweeps in one place

| Sweep | Values tried | Fixed while sweeping | Outcome compared | Where it runs |
|---|---|---|---|---|
| effort | each level the server lists, and "nothing sent" | budget off, cap high | pass count, median output tokens, seconds | P4 |
| reasoning budget | none, the p50 and the p90 of unbounded reasoning | chosen effort | pass count, replies cut, tokens | P4 |
| reply cap | derived, then checked: no passing reply within 10% of the cap | chosen effort and budget | replies cut at the cap | P4, P5 |
| context size | 8,000, 24,000, 64,000, 0.8 of the slot | question set | score against the shortest | P6 |
| concurrency | 1 up to the slots | request size | total tokens a second, queue time | P2 |
| session scope | conversation, request | concurrency at the slots | total tokens a second, cache share | P2 |
| edit format | whole file, find-and-replace, line range | the edits | clean applies, tokens | P7 |
| tool-list size | role list, full list | the steps | right tool, valid arguments | P8 |
| guidance lines | each line on, off; then the kept set | the failing and the passing items | paired pass counts | P9 |
| sampling (doubtful, switch, only if the owner sends sampling) | the card's value and one step either side for temperature | everything else | pass count, repetition, variance across tries | full tier, optional |

Sweeps run one setting at a time in the order above, each using the values already chosen. A full grid is not
affordable and the settings are nearly independent, except effort and budget, which are swept together in P4.

### 4.5 Sample sizes and confidence

Computed for this report (plain binomial arithmetic and a simulation; no model involved).

| Rule | What it can tell | Its error |
|---|---|---|
| today: passes at 2 of 3 | almost nothing | a behaviour that works half the time "passes" 50% of the time; one at 0.7, 78% |
| today: a guide helped if 3 tries rose by one | almost nothing | a useless line is kept 34 to 47% of the time |
| 3 of 3 | the true rate is above 0.44 (95%) | fine for a server fact, not for a behaviour |
| 10 of 10 | above 0.72 | |
| 20 of 20 | above 0.84 | |
| sequential, 0.6 against 0.9, at most 16 tries | works, fails or unsure | wrong about 10% each way; 5 to 9 tries on average; a true 0.75 is "unsure" about half the time, which is the honest answer |
| paired, gain of 3 in 10 | effects of about 40 points | false keep 12 to 13%; finds a 40-point gain 77 to 79% of the time |
| paired, gain of 4 in 12 | the same | false keep 6 to 8%; power 73 to 74% |

What follows:

- The diagnosis can settle **large** effects only: a control that does or does not work, a behaviour at 0.9 or at
  0.6, a line worth 40 points. That is what a new model needs on its first day.
- **Small** effects (a few points of hidden score) cannot be settled by any probe set this size; the published
  figure is about a thousand questions for three points. They stay with the run-pair measurements in
  `docs/measuring.md`. The diagnosis nominates candidates for those pairs and does not replace them.
- Continuous quantities (tokens, seconds) use the median of at least 5, with the lowest for floors and the 90th
  percentile for budgets.
- Every item is used in both arms of a comparison. Unpaired comparisons at these sizes are not made.
- A stage makes many calls in a row. The profile therefore also reports the chance that 10 in a row succeed (rate to
  the tenth power), because 0.9 a call is 0.35 for ten.

### 4.6 Quick and full tiers

| | Quick | Full |
|---|---|---|
| When | automatically, before the first run on a new fingerprint; a run waits for it, as now | on the settings page or `loop.sh diagnose --full`, between runs; offered when the quick tier ends; never started while a run is live unless the owner says |
| Probes | P0; P1; P2 at k = slots only; P3 at 3 tries; P4 with two request sizes, as served against the lowest effort and one budget, 2 tries, replies capped at 4,000; P5 with 2 items per stage kind; P10 | everything, at the sizes in 4.3 |
| Requests | about 50 | 300 to 450, fewer with early stopping |
| Output tokens | about 50,000 | 400,000 to 600,000 |
| Time, a model at 60 tokens a second on two slots | 10 to 15 minutes | 60 to 90 minutes |
| Time, a model at 100 tokens a second on four slots | about 5 minutes | 20 to 30 minutes |
| Hard stops | 20 minutes or 80,000 output tokens | 120 minutes or 800,000 output tokens; resumable from the last finished probe |
| Sets | structured answer form; the answer-now form; a first effort and budget per stage kind ("likely"); timeout floor; parallel cap; session scope; images; a first tier | every field, with intervals; replaces "likely" with "sure" or "not measured" |

The quick tier's reasoning result is deliberately coarse: it answers "does this model reason past 4,000 tokens on a
design request as served, and does a lower effort or a budget stop that with the answer still valid?" That question
alone would have saved about three hours on each of this morning's first two runs.

### 4.7 The feedback loop: drift checks and re-diagnosis

The transcripts already record, per reply: output tokens, reasoning characters, finish reason, salvage, invalid tool
calls, cached input, the model that answered, and the time. So each quantity a probe measures has a live twin.

| Live counter, per run and stage kind | Compared with | Action when it disagrees |
|---|---|---|
| median and p90 output tokens a reply; share of replies at their cap or budget | P4's budget and cap | more than 10% of replies cut at the budget with nothing but reads: raise that stage kind's budget one step (as `step_budget.py` does within a run), and mark the field for the full tier |
| tokens a second (replies over 1,500 tokens) | P1 | more than 25% slower over a run: re-run P1 and P2 at the next run boundary; the server or its load changed |
| invalid or not-offered tool calls; answers given as text; refused commands repeated | P5's rates | outside the probe's interval over 200 calls: the probe item is wrong (retire it) or the model changed (re-run the quick tier) |
| cached share of input | P1, P2 | below half of the probe's: the session scope is costing the cache; re-run P2 |
| requests refused for size | P0, P6 | already learnt by `request_fit.py`; also written to the profile |
| a guide's target behaviour with the guide on | P9 | no better than the probe's baseline over 3 runs: the guide goes to an off-arm pair or is dropped |

Re-diagnosis triggers:

| Trigger | What runs |
|---|---|
| no profile for the fingerprint | quick tier, before the run |
| fingerprint changed in a server fact (template, build, quantisation, slots, context, endpoint count) | P0 always; quick tier at the next run boundary; the old profile is used meanwhile and the run says so |
| probe-set or decision-rule version changed | the affected probes only, at the next idle time |
| a drift counter fired | the probe named in the table above |
| the owner asks | either tier |
| age (30 days) with runs since | quick tier, to catch silent server changes |

`loop.sh effects` and the 10-minute audit already read these transcripts; the counters belong there, one line per
field that disagrees.

### 4.8 Storage, the settings page, versions

- **Stored** in the model's fitness file as now, under one new key holding the profile, with the probe replies'
  numbers (not their text) and a history of earlier profiles. Each run's `provenance` record names the profile's
  fingerprint and version, so a scored run can be tied to the settings it ran with.
- **Shown** on Settings, Models, as one card per served model:
  - a headline in plain words: predicted seconds per step and minutes per small run; what is set away from the
    default and why; what is not measured;
  - a table: setting, value, source, evidence ("9 of 10; at least 0.60"), confidence, an Auto / fixed control (the
    present per-guide control, widened to every field);
  - the dose-response as a small chart (reasoning tokens and pass rate against effort and budget);
  - a diff against the previous profile after a re-diagnosis;
  - two actions, "Quick check" and "Full calibration", each showing its expected time and, for a hosted model, its
    cost ceiling before it starts.
- **Versions:** the probe-set hash, the decision-rule version and the harness commit are in every profile. A profile
  from older rules is shown as such, as `diagnostics.recorded` already does for one field.

### 4.9 Endpoint safety

- Only GETs of the server's own status pages, and ordinary chat requests. No load, unload, restart or setting change
  on any server or balancer.
- Never more requests at once than the slots P0 read, and never more than `HARNESS_MAX_PARALLEL`.
- The full tier does not start while a run is live (the present rule); the quick tier holds the run that needs it and
  takes the one-at-a-time lock (`diagnosis_flight.py`). A run that starts on the same model waits and uses the result.
- The concurrency probe never goes above the reported slots, so it cannot starve the owner's other use of the server
  beyond what one run in parallel mode already does.
- Hard stops on time and tokens (4.6). A server that stops answering ends the diagnosis as "not measured", keeps what
  was finished, and writes nothing as the model's failure (the `the_model_answers` rule, applied to every probe).
- Sampling is not sent unless the owner has turned "send sampling" on.
- Every probe request carries the session header as a measurement would (`session_header.py`: a fresh session
  outside a run), except P2, which sets it on purpose.

### 4.10 Hosted, paid models

- **Only when the owner starts it** or has approved it, as for hosted runs.
- **One client path:** the probes are written against the harness's own model interface, not the OpenAI root client,
  so a provider with its own client is diagnosed too (today it is skipped). Probes for server facts (P0, the
  llama.cpp-only controls) are "not applicable", not failed.
- **Counted before sent:** each tier's requests are token-counted first (the provider's free counter where there is
  one, else the calibrated characters-per-token rate) and priced from the harness's price table
  (`observability/cost_tracker.py`). A tier whose estimate passes its ceiling does not start; the page says what it
  would cost.
- **Ceilings:** proposed defaults of 1 USD for the quick tier and the run ceiling (`MAX_RUN_COST_USD`, 8) for the full
  tier, both the owner's to set. Worked example, with made-up prices of 1 USD per million input tokens and 5 per
  million output: the full tier's 600,000 output and 3 million input tokens cost about 6 USD uncached and about 3.50
  with the shared prefixes read from cache. A real estimate uses the price table.
- **Cheaper by design:** the shared prefix first and identical across items so it is cached; P6's long reads once per
  length; the probes that need no reply at once sent through the provider's batch route where one exists; P2 skipped
  (the provider's rate limits are read from its response headers instead); the top context rung skipped unless the
  owner asks.
- **A rate limit is not a failure:** a 429 or a 413 pauses and retries, then ends the probe as "not measured".
- The diagnosis's spend is recorded against a diagnosis id in the cost tracker, apart from any run.

## 5. Proving the diagnosis predicts run outcomes

A diagnosis that does not predict runs is decoration. Five checks, cheapest first; the first three need no new run.

1. **Test-retest.** Diagnose the same model on the same server twice. At least 90% of fields must agree, and every
   field marked "sure" must. Today's three-try rules fail this on the evidence in 2.3. This is a unit of the
   decision rules and can be simulated in tests from recorded reply counts.
2. **Probe against live rate.** For every behaviour in P5 there is a live counter (4.7). For the models already run
   (eleven profiles, 891 transcripts), compute the live rate of each behaviour and compare it with what the saved
   diagnosis said. A check whose verdict disagrees with the live rate is a bad probe. "The answer as a call" and "a
   refusal heeded" are expected to fail this at once; the forced-answer checks are expected to pass.
3. **Back-test against the fix log.** For each past model, list the fixes its first runs forced (reply ceilings by
   hand, a session scope, a budget, an effort route, a tool-choice form). Ask of each: would a field of the new
   profile have set it before the first run? Target: every one that is a property of the model or its endpoint.
   This morning's four are the first test case, and the design is not allowed to name the model to pass it.
4. **Predicted against actual time.** The profile predicts seconds per reply per stage kind (tokens per reply times
   seconds per token). After each run, compare with the run's stage times. Target: within a factor of 1.5 for 80% of
   stages. A model whose prediction is off is a model whose probes are the wrong size.
5. **Setting by setting, in runs.** A setting the diagnosis changed from the default is one arm; the default is the
   other; two runs per family on one frozen version, scored by hidden tests and the KPIs, exactly as
   `docs/measuring.md` prescribes, using the per-run switch override that exists. One switch,
   `PROFILE_FROM_DIAGNOSIS`, turns every newly controlled field back to its default for the off arm; per-field
   overrides allow single-field pairs later. Keep rule: no hidden or quality score falls, and active minutes or model
   calls fall; else park.

Across models (only about eight distinct ones so far, few of them with many scored runs) the rank agreement between a profile's stage-kind pass rates and
the models' hidden scores is reported but not relied on: eight points make no correlation. The honest claim the
evidence can support is narrower and more useful: **each setting, chosen by its probe, is no worse than the default
in runs, and the settings that were found by hand in the past are now found by the diagnosis.**

One KPI for the owner: **fixes forced by a new model in its first three runs.** Today that was at least six (LF.1580
to LF.1588, LF.1593, the session scope). The target is zero that a profile field could have set.

## 6. Build plan

Effort: S = under a day, M = one to three days, L = about a week. "Always on" items are fixes to wrong results;
"switch" items change what a run is sent and are measured first (owner's switch policy).

### Phase 0: make today's results true (always on)

| Item | What | Expected value | Effort | A test that fails on the old code |
|---|---|---|---|---|
| DX.1 | A try that ended in a server error (5xx, 413, 429, a timeout, a dropped connection) is "not measured"; a check with under two measured tries has no verdict and is left out of the tier | High: stops outages and rate limits from setting tiers and guides | S | A deep-diagnosis measure whose calls raise a 503 yields no failed tries and no tier; the old code scores 0/3 and "weak". Use the captured error texts. |
| DX.2 | A guide is kept only on a paired gain that clears the rule, and the kept set is dropped back, line by line, while any passing check falls by 2 or more | High: removes lines kept by chance and lines that break something else | S | From a captured record where the kept set took a check from 3/3 to 0/3, the profile keeps no line that causes it; the old `chosen_by` keeps all. |
| DX.3 | A check is "calibrating" (run, shown, not scored) until its verdicts agree with live rates; the two checks of 2.3 start there; tier thresholds are over scored checks only | Medium: the tier starts to mean something; "strong" becomes reachable | S | A profile passing every scored check is "strong" although the two calibrating checks fail; the old score is 0.83, "standard". |
| DX.4 | "Usable" and "a zero budget answers" are true only from a reply that shows it; otherwise "not measured", and the budget question climbs until it reasons past the bound | Medium: no setting without evidence | S | A budget probe with no moderate reply gives usable "not measured"; the old code gives true. |
| DX.5 | The fingerprint and versions are kept with every record; `recorded` treats a record whose template hash, build, quantisation or slots differ from the server's as stale | High: ends "same name, different server, old settings"; enables every trigger in 4.7 | M | Two server-fact fixtures with one name and different templates: the second is not served the first's settings; the old code returns them. |

### Phase 1: measure what loses runs (measurements always on; new settings behind `PROFILE_FROM_DIAGNOSIS`)

| Item | What | Expected value | Effort | A test that fails on the old code | Switch |
|---|---|---|---|---|---|
| DX.6 | P1 and P2: speed, cache, concurrency, spread; the profile feeds the timeout floor, the parallel cap and the session scope | High: today's queueing and the 30-tokens-a-second constant | M | With a stub pool where two sessions land on one server, the profile chooses per-request sessions; with a stub server at 20 tokens a second, the timeout floor follows it. The old code keeps the constants. | scope and cap changes behind the switch; the timeout floor always on (it only lengthens patience) |
| DX.7 | P4 on a minimal replay set (one step, one review, one design request, from three families); effort, route, budget and cap per stage kind | Highest: three hours a run this morning; 18 to 46% of all output tokens on earlier models were in replies over 16,000 tokens | L | From recorded reply sizes of a model that reasons 30,000 tokens on a design request as served and 6,000 at a lower effort with valid answers, the profile sets that effort and a budget; the old diagnosis keeps nothing ("not measurable"). | effort per stage kind behind the switch (a quality risk); the budget joins `REASONING_BUDGET` |
| DX.8 | The replay-set builder: pick, scrub, freeze and version requests from transcripts; the deterministic scorers; the hidden-test and run-id guard | Enables P5 to P9 | L | The guard: a fixture holding a run id or a hidden-test line fails the build. The builder is new, so its tests are its own. | none |

### Phase 2: the rest of the sweeps

| Item | What | Expected value | Effort | A test that fails on the old code | Switch |
|---|---|---|---|---|---|
| DX.9 | The sequential rule and intervals for every behaviour check; "unsure" as a third verdict | High: every later number rests on it | M | Simulated reply sequences at a true rate of 0.5 "work" under 5% of the time; the old 2-of-3 rule passes them half the time. | none |
| DX.10 | P5 at full size; the tier per stage kind | Medium | M | A model strong on steps and weak on plans gets a plan batch size for "weak" and step settings for "strong"; the old single tier cannot. | tier use behind the switch |
| DX.11 | P7; the edit tool offered first by file size reads the profile (`edit_preference` gets a reader) | Medium: 67% and 83% edit rates were measured and ignored | M | A profile with find-and-replace under the bar on long files makes the write stage offer the line-range or whole-file tool first there; the old code offers the same tools. | switch |
| DX.12 | P6; input room from effective context | Medium for long runs; unknown for small ones | M | A profile whose score falls at 64,000 tokens sets the room below the slot; the old room is the slot. | switch |
| DX.13 | P8; P9 at full size | Low to medium | M | As DX.2, at ten pairs. | switch |

### Phase 3: the loop, the page, hosted models, the proof

| Item | What | Expected value | Effort | A test that fails on the old code | Switch |
|---|---|---|---|---|---|
| DX.14 | Live counters and the triggers of 4.7 in `loop.sh effects` and the audit | High: catches a changed server or a bad probe without a failed run | M | A transcript whose replies are 30% slower than the profile produces a "re-run speed" line; the old audit says nothing. | none |
| DX.15 | The settings card of 4.8 | Medium: the owner sees why each setting is what it is | M | None (a page; per the owner's rule a plain UI change needs no test; the API behind it is tested). | none |
| DX.16 | The hosted path: the harness's model interface, counting first, ceilings, batch and cache | Medium; needed before any hosted comparison | M | A hosted client without the OpenAI root client gets a profile with "not applicable" server probes; the old code skips it. An estimate over the ceiling does not start. | none |
| DX.17 | `loop.sh diagnosis-validity`: checks 1 to 4 of section 5 from kept profiles and transcripts | High: the proof | M | Report code; its own tests. | none |
| DX.18 | P11, output habits | Doubtful | M | A reply whose page gives two elements one accessible name turns the matching reminder on. | switch, off until measured |
| DX.19 | The sampling sweep | Doubtful; the owner's setting | S | - | switch, off; only where the owner sends sampling |

**Doubtful, so behind a switch and measured before it stays on:** effort lowered per stage kind (DX.7), session scope
and parallel cap chosen automatically (DX.6), the edit tool by size (DX.11), input room below the slot (DX.12), the
tool list by model (DX.13), output habits (DX.18), sampling (DX.19). **Sure, so always on:** every Phase 0 item, the
measurements themselves, the timeout floor, the fingerprint, the counters and the validity report.

**Order and bundles** (the owner's bundle rule): Phase 0 as one bundle at the next run boundary, then a re-diagnosis
of the model under test. DX.6 and DX.7 in parallel worktrees, DX.8 beside them. Phase 2 after the first profile made
by Phase 1 has been through checks 1 to 3 of section 5.

## 7. Open questions for the owner

1. **Time for the full tier.** It needs 20 to 90 minutes of the model server with no run live. When may it run: when
   a model is added, overnight, or only when started from the settings page?
2. **May the diagnosis apply what it finds, or only recommend?** Effort per stage kind and the session scope are
   today a run setting and an `.env` line. Proposed: applied automatically behind `PROFILE_FROM_DIAGNOSIS`, with every
   field overridable on the settings page. Is reasoning effort the owner's in the way sampling is (ADR-0008)?
3. **Slots during a diagnosis.** May the concurrency probe use every slot the server reports for a few minutes, or
   should it keep one free?
4. **Hosted ceilings.** Are 1 USD for the quick tier and 8 USD for the full tier right, and does each hosted
   diagnosis need an explicit yes, as a hosted run does?
5. **Which transcripts may become probes.** Proposed: only the loop's benchmark runs (their briefs are in the
   repository), never the owner's own runs, and never anything from the hidden tests. Is that the right line?
6. **A stale profile at a run's start.** If the fingerprint changed and the quick tier has not run, should a run wait
   for it (10 to 15 minutes), or start on the old settings and say so? Proposed: wait, as a new model does today.
7. **The weak tier's reach.** A weak tier makes every stack experimental. Given 2.3, should that rule be suspended
   until DX.1 and DX.3 are in, or kept?
8. **The model under test now.** After Phase 0, may the loop re-diagnose it (several minutes of its server) before
   runs resume, so its guides and tier are no longer the three-try ones?
9. **Output habits (P11).** Is a model's unprompted product faults something the owner wants in the profile at all,
   or should that stay with the product probes inside each run?

## 8. Method and limits

- Code read in full or in outline: `src/app/models/` (`diagnostics.py`, `deep_diagnosis.py`, `guidance.py`,
  `model_guidance.py`, `fitness.py`, `capabilities.py`, `registry.py`, `server_profile.py`, `balancer.py`,
  `reasoning_budget.py`, `step_budget.py`, `session_header.py`, `request_fit.py`, `sampling_modes.py`,
  `window_probe.py`, `steering_job.py`, `call_gate.py`), `src/app/agents/thinking.py`, `src/app/server/tasks.py`,
  `scripts/loop/model_diagnose.py`, `model_ready.py`, `model_fitness.py`.
- Data read: the eleven kept diagnoses; the last 26 transcripts for reply sizes, speed, finish reasons and cache share
  (speed is wall clock from request to reply, so it includes prompt reading; the comparison between models is on the
  same endpoint but not at the same load).
- "Changed an outcome" in 2.2 rests on run reviews and the measuring register, not on controlled pairs; where no pair
  exists the table says so.
- The statistics in 4.5 are exact binomial sums and a 20,000-draw simulation of the sequential rule.
- Published sources marked [S] were not opened. Several carry paper numbers that could not be checked; none of the
  design's rules depends on an [S] number.
- Nothing here was tried against a model. Every budget in 4.3 and 4.6 is an estimate from transcript sizes and must be
  re-measured by the first real quick tier.
