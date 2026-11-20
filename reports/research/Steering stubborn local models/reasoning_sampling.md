# Controlling reasoning length and repetition loops in open-weight reasoning models (llama.cpp inference-time settings)

Context for the report writer: the target is LFM2.5-24B-A2B (24B total, about 2.45B active) on llama.cpp. It ignores `reasoning_effort` and the template's enable_thinking switch, and replies are uncapped. The failures are 80k-144k-token reasoning spirals and verbatim repetition loops. A second problem: when the model is given its own reasoning back as a prefilled assistant reply, it sometimes re-opens `<think>`.

Evidence-strength labels used below:
- **[S]**: peer-reviewed paper, or primary official docs/code.
- **[M]**: arXiv preprint, or a PR with measurements.
- **[W]**: anecdote, forum post, secondary summary or blog.

---

## Q1. Overthinking research: what does cutting reasoning length gain or cost?

### Takeaway
Across every source found, most long-reasoning tokens add little accuracy, especially on easy inputs. Cuts of about 20-80% (training-free early exit) or about 50% (RL pruning) cost roughly 0-2 points, and early exit sometimes gains. Hard cut-offs at very small budgets lose accuracy, and smooth budget-vs-accuracy curves exist (Qwen3). None of these papers studies spirals of 80k+ tokens; those are a different failure (looping/degeneration), not useful extra thinking.

### Cited Findings
- **Overthinking is real and mostly useless [S].** "Do NOT Think That Much for 2+3=?" (Chen et al., Tencent AI Lab/SJTU, Dec 2024, ICML 2025) found that o1-like models spend excessive compute on easy questions. One example: QwQ-32B-Preview produced 13 solutions to "2+3". The authors report that overthinking patterns "(1) contribute minimally to improving accuracy, (2) lack diversity in reasoning strategies, and (3) occur more frequently with simple problems." — [arXiv 2412.21187](https://arxiv.org/html/2412.21187v2); [PMLR v267](https://proceedings.mlr.press/v267/chen25bx.html)
  - A secondary summary gives the "about 1,953% more tokens than conventional models on 2+3" figure, and a 44.8% token reduction for their self-training fix (FCS+Reflection) with accuracy kept. Both numbers are from secondary summaries [W]; verify against the paper before quoting. — [search summary of arXiv 2412.21187](https://arxiv.org/pdf/2412.21187)
- **Budget forcing, s1 [S/M].** s1 (Muennighoff et al., Jan 2025) controls test-time compute in both directions:
  - Ceiling: it forcefully terminates thinking.
  - Floor: it appends "Wait" when the model tries to stop, which often makes the model fix wrong steps.
  - Result: s1-32B (Qwen2.5-32B-Instruct fine-tuned on 1,000 examples) beats o1-preview by up to 27% on MATH/AIME24, and budget forcing scales AIME24 from 50% to 57%.
  - The abstract does not cover extrapolation limits or loops.
  - Source: [arXiv 2501.19393](https://arxiv.org/abs/2501.19393)
- **Qwen3 thinking budget [S].**
  - Mechanism: when thinking reaches the user threshold, it is halted manually and this text is inserted: "Considering the limited time by the user, I have to give the solution based on the thinking directly now.\n</think>.\n\n". The model then answers from its partial reasoning.
  - The ability "emerges naturally as a result of applying Thinking Mode Fusion"; it was not explicitly trained.
  - Figure 2 (Qwen3-235B-A22B, four maths/coding/STEM benchmarks) shows "scalable and smooth" gains as the budget rises. The authors say gains may continue past 32K tokens.
  - Source: [Qwen3 Technical Report, arXiv 2505.09388](https://arxiv.org/html/2505.09388v1)
- **NoThinking [M].** Ma et al. (Apr 2025), "Reasoning Models Can Be Effective Without Thinking":
  - It skips explicit thinking with simple prompting.
  - At matched token counts it beats Thinking on 7 reasoning datasets, most at low budgets: "51.3 vs. 28.9 on ACM 23 with 700 tokens".
  - It becomes more competitive in pass@k as k grows.
  - Parallel NoThinking with best-of-N or verifiers matches Thinking that has "significantly longer latency (up to 9x)".
  - The prefill mechanism is not described in the abstract (see Gaps).
  - Source: [arXiv 2504.09858](https://arxiv.org/abs/2504.09858)
- **DEER, Dynamic Early Exit in Reasoning [M].**
  - Training-free. At transition points such as "Wait", it induces a trial answer and exits if confidence is high.
  - Across 11 reasoning LLMs it cuts CoT length by 19.1%-80.1% and *improves* accuracy by 0.3%-5.0%. A review reports -64.9% length and +2.1 pass@1 on programming benchmarks.
  - Baselines include NoThinking, Dynasor-CoT and SEAL.
  - Sources: [arXiv 2504.15895](https://arxiv.org/pdf/2504.15895); [GitHub iie-ycx/DEER](https://github.com/iie-ycx/DEER)
- **Dynasor / Certaindex [M].** Fu et al. (Dec 2024, rev. May 2025) observed "answer stabilization": intermediate answers stop changing and extra compute no longer alters the result. As a scheduler, Certaindex gives "up to 50% compute savings and 3.3x higher throughput in real workloads" "with no accuracy drop". — [arXiv 2412.20993](https://arxiv.org/abs/2412.20993)
- **ThinkPrune [S, TMLR 2026].**
  - Method: RL under a token limit, where unfinished thoughts get zero reward.
  - DeepSeek-R1-Distill-Qwen-1.5B on AIME24: about 15,484 tokens at 29.4% falls to 8,301 tokens at 29.0% (4k limit), 7,968 at 27.8% (3k) and 7,574 at 27.0% (2k). That is half the length for a 2% drop.
  - The model still produces long answers on hard problems.
  - Sources: [arXiv 2504.01296](https://arxiv.org/html/2504.01296v1); [TMLR 2026](https://mlanthology.org/tmlr/2026/hou2026tmlr-thinkprune)
- **L1 / LCPO [M].** L1 (CMU, Mar 2025) uses GRPO with a reward for meeting a length target written in the prompt. The authors report that it trades cost against accuracy smoothly, beats s1 budget forcing at length control, and that a 1.5B L1 model beats GPT-4o at equal reasoning lengths. Needs training, so it does not apply at inference. — [arXiv 2503.04697](https://arxiv.org/html/2503.04697v2)
- **Survey [S].** "Stop Overthinking" (Sui et al., TMLR 2025) sorts methods into three groups:
  - model-based (train concise models);
  - reasoning-output-based (cut steps dynamically at inference: early exit, budgets);
  - input-prompt-based (difficulty- or length-aware prompts).
  - Source: [arXiv 2503.16419](https://arxiv.org/abs/2503.16419)
- **Field caution [M].** A July 2025 survey, "Towards Concise and Adaptive Thinking in Large Reasoning Models", covers the same territory. — [arXiv 2507.09662](https://arxiv.org/pdf/2507.09662)

### Inferences
- Inference-only options (budget cut-off, DEER/Dynasor-style probe-and-exit, NoThinking prefill) fit a model whose effort and thinking switches are ignored. RL methods (ThinkPrune, L1, the Chen self-training) need retraining and are out of scope.
- A spiral of 80k-144k tokens is far beyond the 2k-32k ranges in the budget curves. Past the point where answers stabilise (Dynasor), extra tokens are almost certainly a loop. A budget of a few thousand to ~16k tokens plus a forced answer should lose little accuracy, judging by the ThinkPrune and Qwen3 curves. This is an extrapolation to LFM2.5, which none of these papers tested.
- A Dynasor/DEER-style probe can be built client-side: stop at N tokens, append an "answer now" sentence plus `</think>`, read the answer, and compare it with a second probe later.

### Gaps
- None of these papers tests LFM2.5 or other 2B-active MoE models.
- I found no source measuring accuracy loss when cutting a degenerate (looping) 100k-token trace, as opposed to a merely long one.
- Not verified: the exact NoThinking prefill text, DEER's thresholds, and Certaindex's probe mechanism. I read abstracts only.

---

## Q2. Ending thinking and forcing an answer at inference (llama.cpp, vLLM, Qwen3); failures and mitigations, including the prefill re-opening `<think>`

### Takeaway
Current llama.cpp has a real reasoning-budget sampler. You set `--reasoning-budget N` (server flag) plus `--reasoning-budget-message` (an "answer now" sentence). When the budget runs out, it forces the end-of-think tokens by sending every other logit to -inf. It runs a state machine that also reads the prefill. Known failures:
- a model told about a budget keeps reasoning past the injected cut;
- second and later think blocks were unbudgeted until a re-arm fix;
- build regressions and hangs.

For the "re-opens `<think>` after prefill" problem, the levers that hold are:
- token-level bans: `logit_bias` with `false` on the `<think>` token, or a grammar;
- a `stop` string;
- the budget sampler's re-arm, which caps a re-opened block instead of letting it run.

### Cited Findings
**llama.cpp server flags (master README) [S]**
- `--reasoning-budget`: "token budget for thinking: -1 for unrestricted, 0 for immediate end, N>0 for token budget (default: -1)". — [llama.cpp server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- `--reasoning-budget-message`: "message injected before the end-of-thinking tag when reasoning budget is exhausted (default: none)". — [README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- `-rea, --reasoning [on|off|auto]`: "Use reasoning/thinking in the chat ... default: 'auto' (detect from template)". — [README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- `--reasoning-format` (`none`, `deepseek`, `deepseek-legacy`; default `auto`): "controls whether thought tags are allowed and/or extracted from the response". — [README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- `--reasoning-preserve`: "preserve reasoning trace in the full history, not just the last assistant message (default: template default)". — [README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- `--chat-template-kwargs` is a server startup flag ("sets additional params for the json template parser"). — [README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- Assistant prefill: the README lists "Prefilling of assistant messages similar to the Claude API". It is on by default: if the last message is an assistant message, the reply continues it. The opt-out flag makes a final assistant message count as a complete message rather than a prefix. — [README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- Per-request options [S]:
  - `logit_bias`: setting a token's value to `false` "prevents it from being produced".
  - `grammar`: grammar-based sampling.
  - `stop`: array of stop strings, excluded from the output.
  - `n_predict`: default -1, i.e. infinite.
  - Source: [README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)

**How the llama.cpp budget sampler works (`common/reasoning-budget.h`) [S]**
- "State machine: IDLE -> COUNTING -> WAITING_UTF8 -> FORCING -> DONE". The states:
  - IDLE watches for `start_tokens`.
  - COUNTING counts down and watches for a natural `end_tokens`.
  - FORCING "forces forced_tokens token-by-token (all other logits -> -inf)".
  - DONE is "passthrough forever".
- Prefill sets the initial state: "COUNTING if they begin with start_tokens (but don't also end with end_tokens), IDLE otherwise. COUNTING with budget <= 0 is promoted to FORCING."
- Source: [reasoning-budget.h (mirror of llama.cpp)](https://huggingface.co/datasets/echodict/llama.cpp/blob/main/common/reasoning-budget.h)

**Related llama.cpp changes [S/W]**
- Re-arm fix #22323: the budget used to ignore a new think block after the first one closed, so later blocks ran unlimited on Qwen3.6-27B. The fix returns to COUNTING with a fresh budget on a new `<think>`. — [commit page](https://app.semanticdiff.com/gh/ggerganov/llama.cpp/commit/52e5f0a5c180248ffae41fe74060d21a07651a93)
- Flag history: the original `--reasoning-budget` flag came from PR #13771, which supported only -1 or 0. A refactor (#22233) moved the message into sampling params. Per #21870, the sampler is not created when the budget is unlimited, because its presence disabled GPU-side sampling. — [search summary of llama.cpp PRs](https://github.com/ggml-org/llama.cpp/issues/22717) [W]
- Regressions [W]:
  - Issue #22717 reports `--reasoning-budget` stopped working on a Windows build (Qwen3.5 with a custom message). — [issue 22717](https://github.com/ggml-org/llama.cpp/issues/22717)
  - A downstream issue reports that builds after 2026-04-10 register thinking tags for more models, after which the sampler defaults to an effectively unlimited budget. The reporter saw silent hangs and KV-cache growth; the workaround was `--reasoning-budget 0`. — [forge issue #54](https://github.com/antoinezambelli/forge/issues/54)

**Draft PR #25961, "thinking-budget mechanism" (Jul 2026, unmerged as of Sep 2026) [M]**
- Features, all behind a `--reasoning-budget-enable` master switch:
  - an intro message with a `{budget}` placeholder;
  - a soft warning at a fraction of the budget, inserted at a newline;
  - a grace period that waits up to N tokens for a paragraph break before the hard cut ("Natural </think> still wins").
- It changes how the budget message is tokenized ("as-is"), and fixes prefill tokens feeding the sampler once it is forcing (seen with a template that prefills `<think>\n`).
- **Measured failure:** JigSawPT benchmarked it.
  - The intro cut median reasoning from 742 to about 485-594 chars on DeepSeek.
  - But the cut became less reliable: Gemma hit `max_tokens` more often with intro and soft messages.
  - Quote: "the model, once told it has a budget, treats the injected cut sentence as part of its own plan and continues past it."
  - A reviewer noted there was no eval evidence the PR helps.
  - A later PR (#27578) dropped the intro message.
- Source: [llama.cpp PR #25961](https://github.com/ggml-org/llama.cpp/pull/25961)

**vLLM [S/W]**
- `thinking_token_budget` is a per-request sampling parameter and requires `--reasoning-parser`. Counting starts at the reasoning start string, and at the budget vLLM "forces the model to produce reasoning_end_str".
- `reasoning_end_str` can be a transition sentence that ends in `</think>`, i.e. a Qwen3-style "answer now" sentence.
- Source: [vLLM reasoning outputs docs](https://docs.vllm.ai/en/v0.19.0/features/reasoning_outputs/)
- Caveat [W]: one forum report says that on v0.18.0 the parameter passed via `extra_args` was silently ignored. — [vLLM forum](https://discuss.vllm.ai/t/thinking-token-budget-silently-ignored-when-passed-via-extra-args-in-vllm-0-18-0/2533)
- Alternative API: PR #37112 proposed `reasoning_budget` plus `reasoning_budget_message`; it was closed. — [vLLM PR 37112](https://github.com/vllm-project/vllm/pull/37112)
- TensorRT-LLM has its own `thinking_token_budget`, which needs a reasoning parser. — [TRT-LLM source](https://nvidia.github.io/TensorRT-LLM/latest/_modules/tensorrt_llm/llmapi/thinking_budget.html)

**Qwen3 practice [S]**
- The official forced-end sentence is "Considering the limited time by the user, I have to give the solution based on the thinking directly now.\n</think>.\n\n". — [arXiv 2505.09388](https://arxiv.org/html/2505.09388v1)
- The Qwen3 model card says multi-turn history "should only include the final output part and does not need to include the thinking content". — [Qwen3-8B model card](https://huggingface.co/Qwen/Qwen3-8B)

**LFM2.5-24B-A2B [S]**
- The model card calls it a pure reasoning model that "always thinks before it answers". The chat template adds `<think>` when an assistant response starts.
- The card does not mention `enable_thinking`, a thinking budget, or any way to turn thinking off.
- This is consistent with the owner's report that it ignores `reasoning_effort` and the enable_thinking switch.
- Source: [LiquidAI/LFM2.5-24B-A2B](https://huggingface.co/LiquidAI/LFM2.5-24B-A2B)

**Prefill and `<think>` re-opening [W]**
- No llama.cpp issue was found that reports exactly "prefilled own reasoning, then the model re-opens `<think>`".
- The closest evidence is that some models interleave several think blocks per reply (Qwen3.6, per #22323).
- Open WebUI documents that when it replays history to llama.cpp, reasoning is rebuilt as a top-level `reasoning_content` field, which can differ from how the model first emitted it. — [Open WebUI reasoning docs](https://docs.openwebui.com/features/chat-conversations/chat-features/reasoning-models)

### Inferences
**Why LFM2.5 re-opens `<think>` after a prefill**
- The template always starts an assistant turn with `<think>`. A prefilled assistant turn that holds reasoning text *outside* a closed think block, or holds a closed block, is a state the model was never trained on. Models trained like Qwen3 (history without thinking) expect `<think>` at the start of a reply.
- The likely result is that the model emits a fresh `<think>`, either because the template inserts one or because the model "restarts" its own pattern. This is inference from the template behaviour and the Qwen3 history guidance, not a measured result.

**Mitigations, roughly from most to least reliable (all available in llama.cpp per the README)**
1. Prefill a closed think block with the reasoning, then the forced-end sentence, then `</think>` and an answer header. Then:
   - ban the `<think>` token id with `logit_bias: [[<id>, false]]`, so it cannot be sampled at all (this is the README semantics); or
   - use a `grammar` whose root excludes `<think>` (if `<think>` is one special token, `logit_bias` is the simpler of the two).
2. Add `"<think>"` to `stop`, so a re-opening ends the reply and the client can re-prompt. This is cheaper than a ban but loses the reply.
3. Server-wide `--reasoning-budget N` with a `--reasoning-budget-message`. On a build that has the #22323 re-arm, a re-opened block is capped rather than unlimited.
   - Because the prefill sets the initial state, a prefill that starts `<think>` and is not closed begins in COUNTING.
   - With budget 0 it goes straight to FORCING, which is a clean "answer now" for a prefilled-reasoning call.
4. Always set `n_predict`/`max_tokens` as a backstop, since the default is infinite.

**Points to verify before relying on these levers**
- The budget is a *server* flag in the documented README; I found no documented per-request budget field. A harness that needs per-call budgets needs either a separate server or client-side stop-and-reprompt.
- The DONE state is "passthrough forever", so a model that ignores the forced `</think>` and writes reasoning as answer text is not stopped by the sampler. Pair the budget with `n_predict`.
- The JigSawPT result suggests keeping the budget message to one short "answer now" line plus the forced `</think>`, without intro or soft warnings. Models can treat a soft injected sentence as part of their plan and keep going.

### Gaps
- No documented per-request `reasoning_budget` / `thinking_budget_tokens` in llama.cpp's `/v1/chat/completions`. The README fetch was truncated before that section, so this is unconfirmed either way. Also not confirmed: whether `chat_template_kwargs` and `reasoning_format` are accepted per request.
- No source tested whether LFM2.5's `<think>` and `</think>` are single special tokens. This decides whether `logit_bias` alone can ban them; check with `/tokenize`.
- No measured study found of "reasoning returned as prefill, then the model re-opens thinking", for any model.
- I did not confirm whether the budget sampler counts prefilled reasoning tokens against the budget, or only newly generated ones.

---

## Q3. Sampling settings against repetition loops (temperature, top-p/k, min-p, penalties, DRY, XTC)

### Takeaway
Greedy or very low temperature invites endless repetition in reasoning models (Qwen3 says so explicitly). Classic repetition, presence and frequency penalties loop-proof poorly and cost accuracy. DRY is the one sampler with measured evidence:
- about 47-52% fewer verbatim loops;
- accuracy kept on a 70B model (MMLU and GSM8k within 0.1 point);
- available in llama.cpp per request.

LFM2.5's published recommendation (temperature 0.1) is unusually low for a reasoning model. That is a risk factor for loops and conflicts with the 0.6 the owner's brief cites.

### Cited Findings
**Qwen3 model card [S]**
- "DO NOT use greedy decoding, as it can lead to performance degradation and endless repetitions."
- Presence penalty can go "between 0 and 2 to reduce endless repetitions", but "a higher value may occasionally result in language mixing and a slight decrease in model performance".
- Recommended output length is 32,768 tokens, and 38,912 for hard maths/code.
- Source: [Qwen3-8B model card](https://huggingface.co/Qwen/Qwen3-8B)
- Report settings: thinking mode uses temperature 0.6, top-p 0.95, top-k 20. Non-thinking mode uses 0.7, 0.8, 20, with presence penalty 1.5. — [Qwen3 report](https://arxiv.org/html/2505.09388v1)

**LFM2.5-24B-A2B model card [S]**
- Recommended: temperature **0.1**, top_k 50, repetition_penalty 1.05.
- The benchmarks themselves used temperature 0.6 for most evals.
- **Conflict:** the owner's brief says the card recommends temperature 0.6, top_k 50, top_p 0.95, repetition_penalty 1.05. The live card lists 0.1, with 0.6 appearing only as the eval setting. Re-check the card and note which value is deployed.
- Source: [LiquidAI/LFM2.5-24B-A2B](https://huggingface.co/LiquidAI/LFM2.5-24B-A2B)

**llama.cpp sampler defaults (server, per request) [S]**
- Core sampling: `top_k` 40, `top_p` 0.95, `min_p` 0.05.
- Repetition penalties:
  - `repeat_penalty` 1.1 on the server (CLI 1.0);
  - `repeat_last_n` 64;
  - `presence_penalty` 0 and `frequency_penalty` 0.
- DRY:
  - `dry_multiplier` 0.0 (off);
  - `dry_base` 1.75;
  - `dry_allowed_length` 2;
  - `dry_penalty_last_n` 64 (0 disables; -1 means the whole context);
  - `dry_sequence_breakers` `['\n', ':', '"', '*']`.
- XTC: `xtc_probability` 0.0 (off), `xtc_threshold` 0.1 (values above 0.5 disable it).
- Sources: [llama.cpp server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md); [DRY merge #9702](https://cdn04132025.gitlink.org.cn/replica/llama.cpp/commit/ff252ea48e90e6552010fd74584334fb41bdd387)

**DRY design (p-e-w, text-generation-webui PR #5677) [S]**
- Penalty = `multiplier * base ^ (n - allowed_length)`, where n is the length of the repeated match, so it "grows exponentially as the repeated sequence gets longer". There is no penalty below `allowed_length`.
- Standard parameters are "2/0.8/1.75" (allowed length/multiplier/base).
- Sequence breakers stop matching, which is needed because chat templates contain long repeated strings. Names or sequences that must repeat verbatim may need to be added as breakers.
- The author's claim: "classical repetition penalties don't actually prevent looping reliably" and "distort the grammar".
- Source: [oobabooga PR #5677](https://github.com/oobabooga/text-generation-webui/pull/5677)

**DRY measured (Weidmann et al., arXiv 2608.22761, Aug 2026) [M]**
- Main benchmark: Qwen2.5-1.5B, Llama-3.2-3B and Qwen2.5-7B, 16,566 generations.
  - SER@4 (share of steps that extend a seen suffix of length 4 or more) fell from 0.124 to **0.065** with DRY, **-47%**.
  - Repetition penalty reached 0.083. Presence and frequency penalties "barely moved" it.
  - A placebo matched to DRY's intervention rate without suffix awareness stayed at 0.121.
- Accuracy on Llama-3-70B:

  | Setting | MT-Bench | MMLU | GSM8k |
  |---|---|---|---|
  | No intervention | 8.95 | 79.2% | 92.1% |
  | DRY | 8.97 | 79.1% | 92.0% |
  | Repetition penalty | 8.61 | 76.8% | 88.4% |
  | No-repeat n-gram | 8.12 | 71.4% | 81.2% |

- Sequence breakers matter: without them, false-positive penalties on structural tokens rose from 1.2% to 28.4%.
- Sampling interaction: temperature 0.7 with top-p 0.9 and no DRY *raised* SER@4 from about 0.105 to 0.136 on 1.5B/3B models; adding DRY brought it to 0.079.
- Tuned values: λ 0.8, β 1.75, L 2, default breakers, range 1024.
- Limitations: no reasoning models or think traces were evaluated, and DRY "addresses only surface-form continuation loops, not semantic or discourse-level repetition".
- Source: [arXiv 2608.22761](https://www.alphaxiv.org/abs/2608.22761.md)

**XTC [W]**
- It removes the top tokens above a threshold with some probability. It is off by default in llama.cpp. — [README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- No study was found measuring XTC on reasoning accuracy or loops.

### Inferences
**Suggested starting configuration for LFM2.5 on llama.cpp**
- `temperature` about 0.6, not 0.1, with `top_k` 50, `top_p` 0.95 and `min_p` about 0.05. This follows the evals and the Qwen guidance against near-greedy decoding.
- `repeat_penalty` 1.0-1.05. Classic penalties hurt accuracy (repetition penalty cost 3.7 GSM8k points on 70B, per Weidmann et al.).
- DRY enabled:
  - `dry_multiplier` 0.8, `dry_base` 1.75, `dry_allowed_length` 2-4;
  - `dry_penalty_last_n` 1024 to -1. The default 64 is far too short to catch loops in a 100k-token trace.
  - Add breakers for code and JSON (for example `"{"`, `"}"`, `"("`) so legitimate code repetition is not penalised.
- Always pair with the reasoning budget and `n_predict` caps from Q2.

**Cautions**
- DRY in long code output is untested. Code repeats legitimately (indentation, identifiers), and a large window can penalise required repetition. Raise `dry_allowed_length` for code-writing agents.
- Presence penalty up to about 1.5 is the Qwen-endorsed lever against repetition, with language-mixing risk. For a small-active MoE, try it only as a second step.
- The semantic loops in reasoning ("let me re-check... wait...") are not verbatim and will not be caught by DRY. Budget forcing or probe-and-exit (Q1/Q2) is the tool for those.

### Gaps
- No published evaluation of DRY or XTC on reasoning-model think traces or long agentic code generation.
- No LFM2.5-specific report on repetition rates under different temperatures.
- I did not verify p-e-w's 0.8 recommendation in the original PR thread text beyond the "2/0.8/1.75" mention. Weidmann et al. independently tuned to 0.8, which supports it.

---

## Q4. Quantization and repetition/overthinking

### Takeaway
The best controlled study found (COLM 2025) says W8A8 and W4A16 are about lossless for reasoning models. Lower bit-widths add significant accuracy risk. Quantized reasoning models did **not** produce longer outputs. Separately, the DRY paper says quantization noise "tends to worsen repetition", and it measured high loop rates in 4-bit AWQ models, but it ran no full-precision control.

### Cited Findings
- **"Quantization Hurts Reasoning?" (Liu et al., COLM 2025) [S]**
  - Models: DeepSeek-R1-Distill Qwen/LLaMA from 1.5B to 70B, QwQ-32B and Qwen3-8B.
  - Benchmarks: AIME, MATH-500, GPQA and LiveCodeBench.
  - Findings:
    - "lossless quantization can be achieved with W8A8 or W4A16";
    - "lower bit-widths introduce significant accuracy risks";
    - model size, origin and task difficulty are key factors;
    - "quantized models do not exhibit increased output lengths".
  - Source: [arXiv 2504.04823](https://arxiv.org/abs/2504.04823)
- **DRY paper [M].** It chose 4-bit AWQ because quantization noise "tends to worsen repetition". On AWQ-4bit, DRY cut SER@4 from 0.088 to 0.042 (Llama-3-70B, -52.2%) and from 0.076 to 0.039 (GPT-OSS-120B, -48.6%). There was no full-precision comparison at those sizes. — [arXiv 2608.22761](https://www.alphaxiv.org/abs/2608.22761.md)
- **LFM2.5 card [S].** The edge benchmarks used llama.cpp with Q4_K_M. — [LFM2.5-24B-A2B](https://huggingface.co/LiquidAI/LFM2.5-24B-A2B)

### Inferences
- From the Liu et al. result, a Q4_K_M-or-better GGUF is unlikely to be the main cause of 100k-token spirals on its own. Sampling (too-low temperature) and the lack of a budget are likelier causes. Moving to Q6_K/Q8_0 is a cheap test if VRAM allows, but the owner's rule forbids changing the model or settings without the owner.
- The 2B-active count may matter more than the quant level: Liu et al. name model size as a key factor, and small models loop more. This is not measured for MoE active-parameter counts.

### Gaps
- No study separates GGUF k-quants (Q4_K_M and others) from the GPTQ/AWQ-style quants in Liu et al.
- No study covers quantization of MoE models with about 2B active parameters.
- The claim that low-bit quants loop more is asserted (DRY paper) but not shown with a controlled full-precision baseline in any source found.
