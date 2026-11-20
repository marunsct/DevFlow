# Prompt-side and model-side methods for instruction adherence in small/medium open-weight agent models

Context: LFM2.5-24B-A2B in a coding-agent harness ignores refusals, repeats refused calls, answers in prose where a tool answer is required, and re-reads files it was already given. Evidence strength is marked as [strong] (peer-reviewed or large controlled study), [moderate] (preprint with a clear method or numbers), [weak] (vendor claim, docs, blog or secondary summary).

## 1. Instruction placement and repetition (system vs user role, recency, prompt repetition, lost-in-the-middle, IFScale, primacy/recency)

### Takeaway
Repeating the operative request verbatim is the best-measured cheap prompt intervention for non-reasoning models: 47 wins, 0 losses over 70 tests, and very large gains on position-sensitive tasks for the smallest model tested. It is roughly neutral for reasoning-mode models, and LFM2.5-24B-A2B always reasons. Adherence collapses as instructions pile up, and smaller models collapse earliest: llama-4-scout, a MoE with about 17B active parameters, drops to 54% at 50 simultaneous instructions. Multi-turn drift is mostly *unreliability*, not lost capability. So keep the live rule set short and restate the one rule that matters in the latest turn, rather than relying on a long system prompt.

### Cited Findings
- **Prompt repetition (Google Research, Leviathan, Kalman, Matias, Dec 2025)** [moderate]. The method turns `<QUERY>` into `<QUERY><QUERY>`. Without reasoning it won 47 of 70 benchmark-model pairs with 0 losses (McNemar, p<0.1). Models: Gemini 2.0 Flash and Flash-Lite, GPT-4o and 4o-mini, Claude 3 Haiku and 3.7 Sonnet, DeepSeek V3. Benchmarks: ARC, OpenBookQA, GSM8K, MMLU-Pro, MATH, NameIndex, MiddleMatch — [arXiv 2512.14982](https://arxiv.org/html/2512.14982v1)
  - The biggest gain was on NameIndex, where Gemini 2.0 Flash-Lite rose from 21.33% to 97.33%. Repeating the query three times ("×3") often beat a single repeat on NameIndex and MiddleMatch. A "verbose" variant inserts "Let me repeat that:" between copies — [arXiv 2512.14982](https://arxiv.org/html/2512.14982v1)
  - **Control:** padding the input with periods to the same length gave no gain, so the effect comes from semantic repetition, not length — [arXiv 2512.14982](https://arxiv.org/html/2512.14982v1)
  - **With reasoning (step-by-step):** 5 wins, 1 loss, 22 ties out of 28, i.e. neutral to slightly positive. The authors suggest reasoning models already restate the request themselves — [arXiv 2512.14982](https://arxiv.org/html/2512.14982v1)
  - **Cost and mechanism:** output length and latency did not grow in most cases; the extra work is prefill only. The stated mechanism is that causal attention cannot look ahead, so a second copy lets every token attend to the whole request. Options-first prompts benefited more than question-first ones — [arXiv 2512.14982](https://arxiv.org/html/2512.14982v1)
- **LFM2.5-24B-A2B always reasons.** It is "a pure reasoning model that always thinks before it answers"; the chat template opens every assistant turn with `<think>`, and there is no separate instruct variant — [HF model card](https://huggingface.co/LiquidAI/LFM2.5-24B-A2B)
- **IFScale (Distyl AI, NeurIPS 2025)** [moderate-strong]. The task is a business report that must include N keywords, with N from 10 to 500. Accuracy (%) at 10 / 50 / 100 / 250 / 500 instructions — [arXiv 2507.11538](https://arxiv.org/html/2507.11538v1):

  | Model | 10 | 50 | 100 | 250 | 500 |
  |---|---|---|---|---|---|
  | llama-4-scout | 100 | 54.4 | 27.2 | 9.3 | 6.7 |
  | claude-3.5-haiku | 98 | 78.0 | 43.4 | 16.6 | 8.5 |
  | gpt-4o-mini | 94 | 65.6 | 41.8 | 18.3 | 10.4 |
  | gpt-4.1-nano | 94 | 72.8 | 51.6 | 25.7 | 16.2 |
  | qwen3-235b-a22b | 100 | 92.8 | 77.6 | 36.4 | 20.9 |
  | o3 (high) | 100 | 99.6 | 98.2 | 97.8 | 62.8 |
  | gemini-2.5-pro | 100 | 99.6 | 98.4 | 84.8 | 68.9 |

- **IFScale decay shapes:** reasoning models show "threshold" decay, gpt-4.1 and claude-sonnet-4 decay linearly, and gpt-4o and llama-4-scout decay exponentially — [arXiv 2507.11538](https://arxiv.org/abs/2507.11538)
- **IFScale primacy.** Every model violates later instructions more than earlier ones. Primacy is measured as error-rate(last third) / error-rate(first third), and it peaks around 100-200 instructions: gpt-4.1-mini 3.37 and gpt-4.1-nano 2.17 at 100. It falls back toward 1.0-1.5 at 300 or more instructions. The authors' advice: put the most important instructions first, but do not rely on this at extreme densities — [arXiv 2507.11538](https://arxiv.org/html/2507.11538v1)
- **IFScale error type.** At high density small models mostly *omit* instructions rather than half-follow them. Omission:modification ratios at 500 instructions: llama-4-scout 34.9, claude-3.5-haiku 31.7, versus o3 6.3. The authors recommend programmatic compliance checks with retry — [arXiv 2507.11538](https://arxiv.org/html/2507.11538v1)
- **AgentIF (Tsinghua/Zhipu, NeurIPS 2025 D&B)** [strong]. It has 707 instructions drawn from 50 real agentic apps, averaging 1,723 words and 11.9 constraints each. The best model follows fewer than 30% of instructions perfectly. Performance falls sharply beyond about 3,000 tokens and about 40 constraints. Tool specifications and complex constraint structures (conditional, nested) are the weakest categories — [arXiv 2505.16944](https://arxiv.org/html/2505.16944v1)
- **"LLMs Get Lost in Multi-Turn Conversation" (Laban et al., 2025)** [strong; more than 200k simulated conversations]. Top open- and closed-weight LLMs average a 39% drop from single-turn to multi-turn across six generation tasks. The drop decomposes into "a minor loss in aptitude and a significant increase in unreliability". Models make early assumptions and "when LLMs take a wrong turn in a conversation, they get lost and do not recover" — [arXiv 2505.06120](https://arxiv.org/abs/2505.06120)
- **Multi-turn adherence decays.** In Multi-IF, adherence decays with turn count; o1-preview fell from 88% to 71% between turns 1 and 3 (secondary summary in search results). A multi-turn instruction-hierarchy paper finds degradation is worst when user turns contradict the system prompt twice, because the dialog history reinforces the user's format — [arXiv 2511.03508](https://arxiv.org/pdf/2511.03508); [IHDec, arXiv 2606.29960](https://arxiv.org/pdf/2606.29960) [weak-moderate; read through search summaries only]
- **Monitoring only partly helps.** In multi-turn ideation, models "recall what they violate": they can state the constraint they are breaking. Automated checkpointing and external monitoring recover adherence only partially — [arXiv 2604.28031](https://arxiv.org/pdf/2604.28031) [weak-moderate; abstract-level]
- **Lost in the middle (Liu et al., TACL 2024)** [strong]. Retrieval and QA accuracy follows a U-shape over context position: best at the start and end, worst in the middle — [arXiv 2307.03172](https://arxiv.org/abs/2307.03172)
- **Vendor guidance (Anthropic).** For long inputs, put the long documents first and the query or instructions at the end; Anthropic reports this can improve response quality by up to 30% on their models — [Anthropic long-context tips](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/long-context-tips) [weak for small open models; vendor claim]

### Inferences
- The failure classes look like late-context unreliability: re-reading files already given, repeating a refused call, answering in prose. The rule usually *is* in the prompt (cf. "models recall what they violate"); it loses to recent context. The best-supported prompt lever is to restate the single binding rule *adjacent to the point of decision*, i.e. at the end of the latest user or tool-result turn: "the call X was refused because Y; the next reply must be one tool call other than X." IFScale and lost-in-the-middle together argue against appending more rules to the system prompt.
- Prompt repetition is measured on non-reasoning models. Because LFM2.5 always thinks, the paper's own reasoning-mode result (5 wins, 1 loss, 22 ties) predicts a small gain at best. Repeating only the *binding constraint* (not the whole prompt) at the end is a cheaper variant, but it is untested in the paper.
- IFScale suggests a small model handles about 10 active rules at near 100%, but falls off fast by 50. Rules that only matter in one stage or state should be injected per turn, not kept globally. This fits the harness's dynamic agent-instruction injection.
- Since omission dominates for small models, a deterministic post-check plus a targeted re-prompt converts silent omission into a recoverable error. IFScale itself used retry logic. This is likely higher-yield than prompt wording.

### Gaps
- I found no controlled study of placing a rule in the system role versus in the latest user turn for small open models in tool loops. Evidence is indirect: lost-in-the-middle, primacy/recency, multi-turn drift.
- I found no measurement of prompt repetition on 1-30B open-weight models or on agentic or tool-calling tasks. The paper covers QA and math with API models only.
- I did not retrieve the mitigation numbers in Laban et al.: recap, "snowball" restatement, and lower temperature. Check the full paper.
- The IFScale model list has no ~2B-active MoE such as LFM2.5 or Qwen3-30B-A3B.

## 2. Positive vs negative phrasing, concise vs long prompts, compact variants, few-shot (incl. error-recovery few-shot)

### Takeaway
Evidence favours short prompts and positive phrasing for small models, but it is mostly indirect. Negated or "don't" constraints backfire through priming: naming the forbidden thing raises its probability. Cline ships a "compact prompt" about 90% smaller for local models, and says most models under 30B fail with its full prompt. I found no controlled study of few-shot *error-recovery* examples in prompts. The recovery evidence is on the training side (section 4).

### Cited Findings
- **Negative constraints backfire mainly through priming** [moderate; single-author mechanistic preprint]. Naming the forbidden token in "do not use X" raises its probability; a smaller share of failures traces to late-layer FFN contributions. The paper suggests phrasings that avoid naming the forbidden item — [arXiv 2601.08070](https://arxiv.org/html/2601.08070v1)
- **Open-source models break prohibitions more under negation** [moderate]. Across 16 models and 14 ethical scenarios, open-source models endorsed prohibited actions far more often under negated prompts than under affirmative ones, and models agreed with each other less. This held under deterministic decoding — [arXiv 2601.21433](https://arxiv.org/pdf/2601.21433)
- **Cline compact prompt** [weak; vendor docs]. Cline's local-model docs recommend "Use Compact Prompt", which "reduces the prompt size by 90% while maintaining core functionality". They state that most models under 30B parameters fail with Cline (broken tool-use output, refusing to run commands, losing context). The recommended local model is Qwen3 Coder 30B — [Cline docs: running models locally](https://docs.cline.bot/running-models-locally); [Cline local overview](https://docs.cline.bot/running-models-locally/overview.md)
- **Compact prompt trade-off** [weak, anecdotal]. AMD-tested guidance turns the compact prompt off on 64 GB machines and reports "noticeably more nuanced" responses with the full prompt. The trade-off depends on model size — [Cline blog: local models on AMD](https://cline.bot/blog/local-models-amd)
- **Context truncation hides prompts** [weak]. A practical failure is Ollama's default context silently truncating a long agent system prompt; users raise `num_ctx` — [llmconfigurator Cline guide](https://llmconfigurator.com/en/guides/coding-agents/cline-with-local-llms)
- **Long agentic system prompts fail.** AgentIF shows that real agent prompts average about 1.7k words and 12 constraints, and that compliance drops sharply past about 3k tokens and 40 constraints. This is direct evidence that long agent system prompts cost adherence — [arXiv 2505.16944](https://arxiv.org/html/2505.16944v1) [strong]
- **The model card gives no prompt guidance.** The LFM2.5 card offers only a generic system prompt ("a helpful assistant trained by Liquid AI"). For the Hermes harness it suggests enabling `agent.tool_use_enforcement`, which makes the harness force a tool call rather than accept prose — [HF model card](https://huggingface.co/LiquidAI/LFM2.5-24B-A2B)

### Inferences
- For "don't repeat the refused call", positive operative phrasing that never names the refused payload is predicted to work better than "do not call X again". An example is "Next: choose one of {A, B, C}" or "the next step is a write to a new path". This rests on the priming result; it is untested in agent loops.
- Prose where a tool answer is required is better fixed structurally than by wording. Use tool-use enforcement (`tool_choice=required` or grammar-constrained decoding), as the model card's harness note implies. Vendors expose this because prompt wording alone is unreliable.
- A per-model compact prompt, as in Cline, is consistent with IFScale and AgentIF. The gain is plausibly from fewer competing constraints, not fewer tokens as such.

### Gaps
- I found no controlled head-to-head of "do X" versus "don't do Y" across many tasks on small open models; the cited papers are narrow (lexical bans, ethics).
- I found no study measuring few-shot demonstrations of *recovering after a refusal or tool error* inside the prompt. The nearest evidence is training-time (FISSION-GRPO, learning-from-failure).
- I could not confirm Cline's source variant naming ("xs") or its file contents; the GitHub tree URL returned 404. Only the "Compact Prompt" feature and its ~90% figure are documented.
- I did not retrieve numeric results comparing few-shot and zero-shot for tool-calling small models on BFCL or τ-bench.

## 3. Instruction hierarchy and system-prompt adherence benchmarks; how small models score

### Takeaway
Benchmarks show system-prompt adherence degrading over turns, and agent-style instruction following far below single-turn IFEval scores. A model can post IFEval ≈97 (LFM2.5's vendor number) and still fail agent constraints, because IFEval tests short, verifiable, single-turn format constraints. The instruction hierarchy is a *trained* property (OpenAI), not something a prompt reliably adds.

### Cited Findings
- **OpenAI Instruction Hierarchy (Wallace et al., 2024)** [strong]. LLMs treat system prompts with the same priority as user and third-party text. Synthetic data that teaches the model to "selectively ignore lower-privileged instructions" (applied to GPT-3.5) substantially increased robustness, including to unseen attacks, "with minimal degradation on standard capabilities" — [arXiv 2404.13208](https://arxiv.org/abs/2404.13208)
- **SysBench** [moderate]. It has 500 system messages, each followed by 5 user turns. It measures constraint complexity, misalignment between the system message and user instructions, and multi-turn stability, scored per constraint, per instruction and as session stability. v1 evaluated 14 LLMs; a secondary review says GPT-4o was best and that attention paid to the system message correlates with adherence — [arXiv 2408.10943](https://arxiv.org/html/2408.10943v2); [Moonlight review](https://themoonlight.io/review/sysbench-can-large-language-models-follow-system-messages) (secondary)
- **AgentIF.** The best model achieves fewer than 30% perfect instruction success; an aggregator shows the top constraint success rate at about 59.8% and instruction success at about 26.9%. Tool-spec and conditional constraints are hardest — [arXiv 2505.16944](https://arxiv.org/html/2505.16944v1); [benchmarklist AgentIF](https://benchmarklist.com/benchmarks/agentif/) (secondary)
- **LFM2.5-24B-A2B vendor scores**, versus Qwen3.6-35B-A3B — [HF model card](https://huggingface.co/LiquidAI/LFM2.5-24B-A2B) [weak; vendor-reported, mixed eval temperatures]:
  - Instruction following: IFEval 96.75 vs 93.06; IFBench 74.69 vs 64.21; Multi-IF 84.38 vs 81.53.
  - Tool use: BFCLv4 65.01 vs 65.00; ToolSandbox 80.71 vs 75.02; LiveClaw 48.09 vs 38.19; τ³-Bench Banking 8.04 vs 7.63.
  - Trails on SWE-Bench Verified 51.00 vs 66.20, WebArena Verified 26.75 vs 37.62, and GPQA-D 74.42 vs 83.69.
  - Third parties flag these as Liquid's own measurements — [benchmarklist LFM2.5](https://benchmarklist.com/models/liquid-lfm-2.5-24b-a2b/)
- **Cline's practitioner report.** Most models under 30B fail in Cline through broken tool output, refusing commands and losing context. Qwen2.5-Coder-7B often emits malformed tool calls — [Cline docs](https://docs.cline.bot/running-models-locally/overview.md); [modelfit.io](https://modelfit.io/tools/cline/) [weak]

### Inferences
- High IFEval and IFBench scores do not predict multi-turn agent adherence. LFM2.5's comparative weakness is long-horizon agentic work (SWE-Bench Verified −15 points and WebArena −11 points versus Qwen3.6-35B-A3B), which matches the observed harness behaviour better than its IF scores do.
- The harness's refusals arrive as tool results, i.e. a lower-priority channel in instruction-hierarchy terms. Models trained to give tool output low priority (an anti-injection design) may be predisposed to discount harness refusals carried in tool messages. One option is to deliver the binding refusal or rule as a user or system-role turn, or to have the harness prevent the repeat (block, dedupe) rather than ask. This is an inference, not measured.

### Gaps
- I found no published SysBench or AgentIF score for LFM2.5 or for any ~2B-active MoE.
- I did not retrieve the OpenAI hierarchy paper's per-attack numbers or over-refusal figures (abstract only).
- I found no independent BFCL or τ-bench leaderboard entries for LFM2.5-24B-A2B.

## 4. Model-side: fine-tuning/LoRA on agent trajectories (incl. failure and recovery traces), DPO/RL, QLoRA feasibility, quantization and checkpoint choice

### Takeaway
Agent-trajectory SFT reliably lifts small models: FireAct reports +77% on HotpotQA for Llama2-7B with 500 trajectories, and SWE-smith takes Qwen2.5-Coder-32B to 40.2% on SWE-bench Verified. Training specifically on failure and recovery addresses the observed "repeat the invalid call" loop: FISSION-GRPO lifts Qwen3-8B BFCL-v4 multi-turn accuracy from 42.75% to 46.75%. Liquid officially supports LoRA SFT, DPO and GRPO for LFM2.5 via TRL and Unsloth. 4-bit weight quantization usually costs a few instruction-following points at most, and costs more on smaller models.

### Cited Findings
- **FireAct (2023)** [moderate]. LoRA fine-tuning Llama2-7B on 500 GPT-4 ReAct trajectories gave a 77% HotpotQA improvement (relative vs absolute is not stated in the abstract). Evaluation used 500 dev examples, scored by EM/F1 — [arXiv 2310.05915](https://arxiv.org/abs/2310.05915v1)
  - A replication with LLaMA2-70B was mixed: 162 examples scored 27.8, below few-shot ReAct at 32.4; 512 examples scored 30.0. Small trajectory sets may underperform prompting — [arXiv 2401.14016](https://arxiv.org/pdf/2401.14016)
- **Learning From Failure (2024)** [moderate]. Keep failed trajectories and add a prefix or suffix marking success or failure instead of discarding them. This improved agent tuning on math, multi-hop QA and strategic QA — [arXiv 2402.11651](https://arxiv.org/abs/2402.11651v2)
- **FISSION-GRPO (Jan 2026)** [moderate; preprint].
  - It targets exactly "smaller models often fall into repetitive invalid re-calls after a tool error".
  - Each failed trajectory becomes a new training instance with error-simulator feedback, and recovery rollouts are resampled on-policy.
  - On BFCL v4 Multi-Turn, Qwen3-8B's error-recovery rate rose 5.7 points and overall accuracy went from 42.75% to 46.75%. Gains on TAU-Bench and TAU2-Bench are reported at up to 17.4% — [arXiv 2601.15625](https://arxiv.org/pdf/2601.15625)
- **SWE-smith (NeurIPS 2025 D&B)** [strong]. 50k task instances from 128 repositories; Claude 3.7 Sonnet SWE-agent trajectories, filtered to resolved instances (rejection-sampling fine-tuning). Students were Qwen2.5-Coder-Instruct 7B and 32B; SWE-agent-LM-32B reached 40.2% Pass@1 on SWE-bench Verified. Data, trajectories and models are released — [arXiv 2504.21798](https://arxiv.org/pdf/2504.21798); [HF papers](https://huggingface.co/papers/2504.21798)
- **LFM2.5 officially supports fine-tuning.** Liquid "recommends fine-tuning for specific use cases". Supported recipes: Unsloth continued pre-training (CPT) and SFT-LoRA, TRL SFT-LoRA, TRL DPO-LoRA, and TRL GRPO-LoRA, with Colab notebooks. A `LFM2.5-24B-A2B-Base` checkpoint is published — [HF model card](https://huggingface.co/LiquidAI/LFM2.5-24B-A2B)
- **QLoRA and MoE memory** [weak-moderate; vendor docs].
  - Unsloth reports Qwen3-30B-A3B fine-tuning in about 17.5 GB VRAM. QLoRA needs the full 16-bit weights downloaded and quantized on the fly, so it needs extra RAM and disk.
  - Unsloth disables router-layer training by default.
  - Unsloth's later Qwen3.5 MoE docs say "MoE QLoRA 4-bit is not recommended due to BitsandBytes limitations" and recommend bf16 LoRA instead.
  - Sources: [Unsloth Qwen3 docs](https://unsloth.ai/docs/models/qwen); [Unsloth Qwen3 blog](https://unsloth.ai/blog/qwen3); [Unsloth Qwen3.5 fine-tune](https://unsloth.ai/docs/models/qwen3.5/fine-tune.md)
- **Quantization and instruction following** [moderate].
  - In instruction-tuned models up to 405B, 4-bit (especially GPTQ) can cause significant drops in *smaller* models, while about 70B models usually hold up. AWQ degrades less than GPTQ — [arXiv 2409.11055](https://arxiv.org/html/2409.11055v1)
  - On long-context constraint satisfaction, FP8 and BNB-nf4 dropped about 1.8 and 1.0 points, while AWQ-int4 and GPTQ-int4 slightly beat BF16. Drops grow at higher constraint counts — [arXiv 2505.20276](https://arxiv.org/pdf/2505.20276)
  - KV-cache quantization (not weights) at 6-bit collapsed IFEval for Qwen-2.5-7B-Instruct — [arXiv 2606.09864](https://arxiv.org/pdf/2606.09864)
  - A Jan 2026 study benchmarks llama.cpp K-quants (3-8 bit) on Llama-3.1-8B-Instruct, including instruction following; its numbers were not retrieved — [arXiv 2601.14277](https://arxiv.org/pdf/2601.14277)
- **Sampling.** The LFM2.5 card recommends temperature 0.1, top_k 50 and repetition_penalty 1.05, but the benchmarks were run mostly at temperature 0.6 (1.0 for LiveClaw, 0 for some tool tests) — [HF model card](https://huggingface.co/LiquidAI/LFM2.5-24B-A2B)

### Inferences
- **Feasibility for a local 24B MoE:**
  - At 24B total parameters, bf16 weights are about 48 GB, so bf16 LoRA needs roughly 48 GB or more of VRAM plus activations. 4-bit QLoRA would need about 13-15 GB of weights, but Unsloth now discourages QLoRA for MoE. This is arithmetic from parameter count, not a measured figure.
  - The 2.45B active parameters make training steps cheap relative to total size. A DPO-LoRA on a few hundred to a few thousand harness-specific preference pairs is plausible on one 48-80 GB GPU or a rented one. The pairs: chosen = tool call after a refusal; rejected = repeated refused call, prose answer, or re-read.
- **The harness's own logs are a ready dataset.** Every refused or repeated call, prose answer and redundant read already logged is a natural "rejected" sample. The harness's correction is the "chosen" sample. This is the FISSION-GRPO and learning-from-failure recipe, applied offline.
- **Quantization is unlikely to be the main cause** of these behavioural failures if the weights are at least about 4-5 bit (Q4_K_M or higher). KV-cache quantization in llama.cpp (e.g. `-ctk q4_0`) is a plausible and checkable culprit given the KV-cache-quantization IFEval collapse result.
- **Checkpoint choice:** LFM2.5-24B-A2B has no non-reasoning instruct variant, so "switch to instruct" is not available within the family. The card's temperature of 0.1 differs from the 0.6 used for benchmarks; adherence may differ between the two.

### Gaps
- I found no numeric result for IFDPO or other tool-use DPO papers on small models in this pass; I could not retrieve them within budget.
- I found no published SWE-Gym numbers in this pass.
- I found no AgentTuning (AgentInstruct) numbers in this pass.
- I found no measured VRAM figure for LoRA on LFM2.5-24B-A2B specifically; Liquid's notebooks may state it.
- I found no GGUF-quant IFEval numbers for LFM2.5 or for any hybrid conv/attention model. Its 30 conv plus 10 GQA layers may respond to quantization differently from pure transformers; this is untested.

## 5. Dense vs MoE with few active parameters: do low-active MoEs follow instructions worse?

### Takeaway
I found no direct evidence that low-active-parameter MoEs follow instructions worse than dense models of equal total size. The one controlled study found that MoE matches or beats dense under equal total parameters, compute and data. Weak circumstantial evidence exists. In IFScale, llama-4-scout (MoE, about 17B active) is the worst model at high instruction density. LFM2.5 trails a 3B-active MoE on long-horizon agentic benchmarks while leading it on IFEval and IFBench.

### Cited Findings
- **Controlled MoE vs dense study (ICLR 2026 oral)** [strong]. An MoE with activation rate in an optimal region outperforms its dense counterpart under the same total parameters, training compute and data. More data is needed as a trade-off. General benchmarks only, not instruction following — [arXiv 2506.12119](https://arxiv.org/html/2506.12119v1)
- **IFScale, high density.** llama-4-scout, a MoE, scores 54.4% at 50 instructions and 6.7% at 500, with the highest omission bias (34.9). Its sibling llama-4-maverick, also a MoE, scores 76.4% at 50. qwen3-235b-a22b, a MoE with 22B active, scores 92.8% at 50 and 20.9% at 500, below several dense or unknown-architecture API models — [arXiv 2507.11538](https://arxiv.org/html/2507.11538v1) [moderate; confounded by training recipe]
- **LFM2.5-24B-A2B architecture.** 24.0B total and 2.45B active parameters; 64 experts per block with top-4 routing; 40 layers (30 short-convolution, 10 GQA); 131k context; about 36T training tokens — [HF model card](https://huggingface.co/LiquidAI/LFM2.5-24B-A2B)
- **LFM2.5 versus Qwen3.6-35B-A3B** (vendor numbers) — [HF model card](https://huggingface.co/LiquidAI/LFM2.5-24B-A2B):
  - LFM2.5 leads: IFEval, IFBench, Multi-IF, ToolSandbox, LiveClaw.
  - LFM2.5 trails: SWE-Bench Verified 51.0 vs 66.2, WebArena Verified 26.75 vs 37.62, PinchBench 83.18 vs 89.93.
- **Expert dropping** under over-subscription "can introduce subtle inconsistencies" — [Decagon glossary](https://decagon.ai/glossary/what-is-mixture-of-experts) [weak; vendor glossary, no data]

### Inferences
- Within LFM2.5, the model is strong on short verifiable constraints but weaker on long-horizon agentic tasks. That points to a *long-context, multi-step* weakness rather than an instruction-parsing one. A hybrid design with only 10 attention layers out of 40 may contribute to that, given that recall across long tool histories depends on attention. This is speculative; I found no study isolating it.
- Practical implication: keep the effective context short. Summarise or compact old tool outputs, and re-inject the file contents and the active constraint near the end. Do not expect the model to retrieve them from far back. This targets the "re-reads files already given" symptom directly.

### Gaps
- I found no matched dense-vs-MoE pair (same data and recipe) evaluated on IFEval, IFBench, SysBench or AgentIF.
- I found no study of instruction following as a function of active-parameter count, nor of hybrid conv/attention models (LFM-style) versus pure transformers on long multi-turn adherence.
