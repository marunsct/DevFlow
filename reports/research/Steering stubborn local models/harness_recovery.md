# Harness-side recovery from repeated refused/failing tool calls

Scope: what agent harnesses actually do when a model repeats a refused or failing action, ignores an actionable error, or loops. Mechanisms, where they live in source, thresholds, and evidence strength. Context: a small MoE (LFM2.5-24B-A2B, ~2B active) on llama.cpp in LangGraph keeps resending shell lines (`cd x && cat y | head`) to a no-shell command tool despite refusals, and re-reads files already in context.

Evidence labels: **[measured]** = ablation/experiment with numbers; **[design]** = shipped code or documented design choice with no published measurement; **[anecdote]** = blog or qualitative claim.

## 1. How do SWE-agent, OpenHands, Aider, Cline/Roo Code, Goose, smolagents, Continue (plus Gemini CLI) handle repeated identical or near-identical failing actions?

### Takeaway
The shipped harnesses share one pattern. They detect an exact repeat (canonical name+args, sometimes with an n-cycle check), send one short "you repeated X, change the arguments or the approach" message, and then stop or hand control to the user if the loop goes on. Thresholds sit at 3 to 5 repeats. SWE-agent alone does something different: it re-asks the model for a corrected action in a temporary branch, and when the retry succeeds the failed attempt is dropped from the history. That is the one mechanism aimed at the model conditioning on its own refused calls. The exact-match detectors in OpenHands and Roo miss near-identical repeats, such as the same shell line with a changed `head -n` value or different reasoning text.

### Cited Findings

**OpenHands (current SDK, `StuckDetector`) [design]**
- Detects five patterns in the events since the last user message (scan window 20 events): (1) the same action with the same observation, (2) the same action with an error each time, (3) a monologue of agent messages with no tool use, (4) alternating A/B action-observation cycles, and (5) a loop of context-window errors. The source comment says the window covers "4 repeats × 2 events per cycle = 8 events minimum, plus buffer". — [stuck_detector.py](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/conversation/stuck_detector.py)
- Default thresholds in `StuckDetectionThresholds`: `action_observation=4`, `action_error=3`, `monologue=3`, `alternating_pattern=6`. All of them can be configured. — [types.py](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/conversation/types.py)
- The response is graded. When the same action has errored exactly `action_error` (3) times in a row, `get_action_error_nudge()` injects one user-role message from the "environment": "You've called `{tool_name}` with the same arguments {threshold} times in a row and gotten the same error each time: {error}. Repeating the exact same call again will not work — review the error message and either correct the arguments or try a different approach." It nudges once per streak. If the streak reaches threshold+1, `is_stuck()` returns True and `_check_stuck_or_nudge()` sets `ConversationExecutionStatus.STUCK`, which stops the run loop. — [stuck_detector.py](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/conversation/stuck_detector.py), [local_conversation.py](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/conversation/impl/local_conversation.py)
- Equality is strict. `_event_eq` compares `source`, `thought`, `action` and `tool_name`, and ignores only ids and metrics. A model that rewords its reasoning or tweaks one argument resets the streak. — [stuck_detector.py](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/conversation/stuck_detector.py)
- The legacy controller (v0.59) used the same scenarios with hard-coded counts: the last 4 action/observation pairs, 3 identical errors, 3 monologue messages, 6-pair alternation, and 10 condensation events. It also had syntax-error-specific checks (`_check_for_consistent_invalid_syntax`), and `_eq_no_pid` ignored process ids. On detection, `AgentController` raised `AgentStuckInLoopError('Agent got stuck in a loop')`, so it stopped and did not recover. — [stuck.py v0.59.0](https://github.com/All-Hands-AI/OpenHands/blob/0.59.0/openhands/controller/stuck.py), [agent_controller.py v0.59.0](https://github.com/All-Hands-AI/OpenHands/blob/0.59.0/openhands/controller/agent_controller.py)

**SWE-agent [design + measured context]**
- `forward_with_handling()` catches `FormatError`, `_BlockedActionError` (command on the blocklist) and `BashIncorrectSyntaxError`. It does not execute the action. It requeries the model, up to `max_requeries = 3`. — [agents.py](https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/agent/agents.py)
- The key detail is in the `get_model_requery_history()` docstring: "This function adds temporary history based on the error template and queries the model. If the model is able to correct itself, the records of the mistakes will not be part of the history (but they are saved in the trajectory)." The temporary history is `self.messages + [bad assistant output, rendered error template]`. The permanent context therefore never accumulates refused attempts. — [agents.py](https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/agent/agents.py)
- After 3 failed requeries the run ends with `exit_format` ("Exit due to repeated format/blocklist/bash syntax errors") and tries an autosubmission. — [agents.py](https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/agent/agents.py)
- The default blocklist error template is short and generic: "Operation '{{action}}' is not supported by this environment." The `blocklist` holds prefixes (vim, nano, less, `tail -f`, `python -m venv`, make, ...), `blocklist_standalone` holds bare `python`, `bash`, `sh`, and `block_unless_regex` allows a command only with the required flags. — [tools.py](https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/tools/tools.py)
- History processors: `LastNObservations` replaces older observations with "Old environment output: (n lines omitted)", and `ClosedWindowHistoryProcessor` collapses outdated file-viewer windows ("Outdated window with N lines omitted"). Together they keep the model from leaning on stale file dumps. — [history_processors.py](https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/agent/history_processors.py)

**Gemini CLI (`LoopDetectionService`) [design]**
- Tool-call loop: hashes `name:JSON(args)` with sha256, ignoring the thought text. It flags any cycle of length k=1..5 that repeats `TOOL_CALL_LOOP_THRESHOLD = 5` times, so A,B,A,B... alternation is caught as well as AAAAA. There is also a content loop check (`CONTENT_LOOP_THRESHOLD = 10` chunks of 50 chars). — [loopDetectionService.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/services/loopDetectionService.ts)
- LLM-judged loop check: after `LLM_CHECK_AFTER_TURNS = 30` turns, a diagnostic prompt ("determines whether a conversational AI assistant is stuck in an unproductive loop") runs over the last 20 history items. The check interval adapts between 5 and 15 turns based on returned confidence. A loop counts only at confidence ≥ 0.9, and a second "double-check" model alias confirms it. — [loopDetectionService.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/services/loopDetectionService.ts)
- Escalation: on the first detection, `_recoverFromLoop()` aborts the current stream and recursively sends a feedback turn: "System: Potential loop detected. Details: Repeated tool call: {name} with arguments {args}. Please take a step back and confirm you're making forward progress. If not, take a step back, analyze your previous actions and rethink how you're approaching the problem. Avoid repeating the same tool calls or responses without new results." A second detection (`count > 1`) emits `LoopDetected` and ends the turn. — [client.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/core/client.ts)

**Roo Code (Cline fork) [design]**
- `ToolRepetitionDetector` serializes `{name, params, nativeArgs}` with safe-stable-stringify (sorted keys) and counts consecutive identical calls. When the count reaches the limit it returns `allowExecution: false`, so the call is not run, and it asks the user (`mistake_limit_reached`, `toolRepetitionLimitReached`). It then resets its counters "to allow recovery if user guides the AI past this point". — [ToolRepetitionDetector.ts](https://github.com/RooCodeInc/Roo-Code/blob/main/src/core/tools/ToolRepetitionDetector.ts)
- The limit is shared with `consecutiveMistakeLimit`, where `DEFAULT_CONSECUTIVE_MISTAKE_LIMIT = 3`. When `consecutiveMistakeCount >= consecutiveMistakeLimit`, the task blocks on a user ask, any user text is sent back as `tooManyMistakes` → `{"status":"guidance","feedback":...}`, and the counter resets. — [Task.ts](https://github.com/RooCodeInc/Roo-Code/blob/main/src/core/task/Task.ts), [provider-settings.ts](https://github.com/RooCodeInc/Roo-Code/blob/main/packages/types/src/provider-settings.ts)
- Error phrasing: `missingToolParameterError` = "Missing value for required parameter '{param}'. Please retry with complete response." plus a tool-instructions reminder. `noToolsUsed` = "[ERROR] You did not use a tool in your previous response! Please retry with a tool use." plus the reminder. — [responses.ts](https://github.com/RooCodeInc/Roo-Code/blob/main/src/core/prompts/responses.ts)

**Aider [design]**
- Reflection loop: `max_reflections = 3` on `Coder`. Lint errors, test errors, and malformed edit blocks (`ValueError` → "The LLM did not conform to the edit format.") are put in `self.reflected_message` and sent back as the next user message. Once 3 reflections are used it stops with "Only 3 reflections allowed, stopping." The counter resets for each user message. — [base_coder.py](https://github.com/Aider-AI/aider/blob/main/aider/coders/base_coder.py)

**Goose [design]**
- The tool shim is for models without reliable native tool calling. A separate local interpreter model (default `mistral-nemo` via Ollama; backends ollama, local, llama.cpp) turns the main model's text into structured tool calls. It is enabled with `GOOSE_TOOLSHIM=true` and marked experimental. — [Goose tool-shim guide](https://goose-docs.ai/docs/guides/tool-shim)
- Goose also published a post on fine-tuning a dedicated toolshim model, following its "vibe check" benchmark, which found weak results for models without good tool support. — [finetuning toolshim](https://goose-docs.ai/blog/2025/04/11/finetuning-toolshim), [Goose benchmark](https://goose-docs.ai/blog/2025/03/31/goose-benchmark)

**smolagents**
- Tool errors are raised as `AgentToolCallError`, and the error text goes into the next observation of the memory step. I found no repeat detector in `agents.py`. — [agents.py](https://github.com/huggingface/smolagents/blob/main/src/smolagents/agents.py)

### Inferences
- Exact-match detectors (OpenHands includes `thought` in the comparison, Roo compares the whole param object) are likely to miss our failure. A small model that resends `cd x && cat y | head` with slightly different reasoning or a different `head -n` defeats them. A normalized key works better, for example the refusal reason class plus the leading program, or "same refusal code N times". Gemini CLI's name+args-only hash with an n-cycle check is closer to that, but still exact on args.
- Every harness surveyed escalates the same way: inject one nudge, then stop or ask a human. None of them silently retries forever. OpenHands' "nudge exactly once per streak" and Gemini's "first detection = feedback, second = abort" are concrete defaults worth copying: threshold 3 identical failures → one nudge, 4 → hard intervention.
- SWE-agent's "requery in a temporary branch and drop the failure once corrected" fits refused calls best. The refused shell line and its refusal never enter the permanent transcript, so later turns cannot copy them.

### Gaps
- I could not retrieve Cline's current source; the raw paths have moved. The Roo Code findings come from its fork. I found no information on Continue's handling, and this does not mean it lacks one.
- None of these projects publishes an ablation of its detector thresholds. The 3, 4, 5 and 6 values are design choices.

## 2. How should a tool refusal or error message be written for a weak model to act on it?

### Takeaway
The only measured evidence is SWE-agent's ACI ablations. They show that guardrails which reject bad actions immediately with specific feedback, plus concise feedback in general, raise success rates. They also show that once an action has failed, the chance of recovering drops sharply. Industry guidance (Anthropic) says errors should be specific, actionable and include an example of a correctly formatted call. No source found ablates the wording itself (positive vs. negative phrasing, showing the corrected call) for small models.

### Cited Findings
- SWE-agent's four ACI principles are simple actions, compact actions, concise feedback, and guardrails, the last meaning automatic error checks that help agents catch and fix mistakes quickly. — [SWE-agent paper](https://arxiv.org/abs/2405.15793)
- [measured] Ablations on SWE-bench Lite with GPT-4 Turbo, full configuration 18.0%: editing without a linting guardrail scored 15.0% (−3.0); no edit command, 10.3%; iterative search instead of summarized search, 12.0% (−6.0); a full-file viewer instead of 100 lines, 12.7%; a 30-line viewer, 14.3%; full history instead of collapsed old observations, 15.0% (−3.0). — [SWE-agent paper](https://arxiv.org/abs/2405.15793)
- [measured] 51.7% of trajectories (185/294) had at least one failed edit. An editing attempt has a 90.5% chance of eventually succeeding, but only 57.2% after one failed edit. Cascading failed edits made up 23.4% of failures, and repeatedly editing the same snippet was named a prominent failure mode. — [SWE-agent paper](https://arxiv.org/abs/2405.15793)
- [measured] Unsuccessful runs had a mean of 21 steps vs. a median of 12 for successful ones. Failing trajectories run long, which is consistent with loops. — [SWE-agent paper](https://arxiv.org/abs/2405.15793)
- [design guidance] Anthropic: "prompt-engineer your error responses to clearly communicate specific and actionable improvements, rather than opaque error codes or tracebacks", and "give examples of correctly formatted tool inputs". Many invalid-parameter errors "might suggest tools could use clearer descriptions or better examples". When truncating output, "be sure to steer agents with helpful instructions". — [Anthropic, Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)
- [measured, benchmark] CRITICTOOL (EMNLP 2025; 1,490 test cases from 733 trajectories) splits tool errors into internal ones (tool selection, hallucinated tool, parameter key, parameter value) and external ones. It finds that most LLMs struggle to recover from errors during tool calling, which leads to task failure. — [CRITICTOOL](https://arxiv.org/abs/2506.13977)
- [measured] Huang et al. (ICLR 2024): intrinsic self-correction without external feedback does not reliably help and can degrade results. Valid external feedback, such as execution results, is what helps. — [Huang et al.](https://arxiv.org/abs/2310.01798)
- Shipped error texts are short and imperative. They name the failing thing and the single fix, and Roo and OpenHands append a tool-usage reminder (see Q1). SWE-agent's default blocklist text ("Operation 'X' is not supported by this environment.") says what is wrong, not what to do. — [tools.py](https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/tools/tools.py), [responses.ts](https://github.com/RooCodeInc/Roo-Code/blob/main/src/core/prompts/responses.ts)

### Inferences
- Since the probability of success falls from 90.5% to 57.2% after a single failure, the first refusal matters most. It should carry the exact replacement call, ready to copy, such as the equivalent read-file tool invocation with the resolved path. Explaining policy is not enough. This is the inference behind the "show the corrected call" recommendation, and its wording has not been measured.
- The external-feedback finding (Huang) supports making refusals concrete and verifiable, such as "the file is already in context at message N". It argues against vague "rethink your approach" text like Gemini's nudge, which leans on the model's own self-correction.

### Gaps
- I found no published ablation comparing error-message styles (corrected-call example vs. prose, positive vs. negative, length) for small or open-weight models. SWE-agent does not ablate the empty-output or error-message text on its own.

## 3. Removing, withholding or renaming tools after misuse; dedicated tools for the misused pattern; tool-set reduction for small models

### Takeaway
There is measured evidence that fewer, better-targeted tools help small models, and that a purpose-built viewer or search tool beats raw shell access (SWE-agent). Shipped harnesses block misused commands (blocklists) or refuse to execute a repeated call. I found none that dynamically removes or renames a tool after misuse.

### Cited Findings
- [measured] Less-is-More (2024): selectively reducing the tools offered to an edge LLM for each query, via a tool recommender and controller, without fine-tuning, improves agentic success. It also cuts execution time by up to 70% and power by up to 40%. Secondary summaries give accuracy gains of up to about 35-40%, a figure I did not verify in the primary text. — [Less is More](https://arxiv.org/abs/2411.15399)
- [measured] Purpose-built ACI tools outperform shell-only alternatives. Removing the edit command drops 18.0→10.3%, and replacing summarized search with iterative search drops to 12.0%. A bounded 100-line file viewer beats showing the full file (12.7%). — [SWE-agent paper](https://arxiv.org/abs/2405.15793)
- [design] SWE-agent blocks interactive or unsupported commands by prefix, by exact match, or unless a regex matches (`block_unless_regex`), and requeries instead of executing. — [tools.py](https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/tools/tools.py)
- [design] Roo Code withholds execution of the repeated call (`allowExecution: false`) instead of removing the tool. — [ToolRepetitionDetector.ts](https://github.com/RooCodeInc/Roo-Code/blob/main/src/core/tools/ToolRepetitionDetector.ts)
- [design guidance] "Too many tools or overlapping tools can also distract agents from pursuing efficient strategies". Anthropic recommends a few consolidated tools for high-impact workflows, and namespacing whose effect "vary by LLM". — [Anthropic, Writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents)

### Inferences
- For the `cd x && cat y | head` pattern, the evidence points to two changes. Offer a dedicated read tool with path, offset and limit that covers the cd+cat+head intent in one call (SWE-agent's "compact actions"). Make the refusal for a shell-composed line name that tool and its arguments. Our harness probably already does part of this. Renaming or hiding the command tool after misuse remains an untested idea.

### Gaps
- No source measured dynamic removal or renaming of a tool after misuse. No source measured how a no-shell command tool's name affects how often models send shell syntax to it.

## 4. Context reset / fresh start after N failures; do weak models recover better from clean context than from accumulated errors?

### Takeaway
Yes, with good evidence. Sinha et al. (2025, ICLR 2026) show "self-conditioning": a model becomes more likely to make mistakes when its context holds its own earlier errors, and scaling the model does not fix this for non-thinking models. Dropping old turns (a sliding window) helps substantially. Magentic-One's stall counter also resets agent contexts on re-plan, and SWE-agent drops corrected mistakes from history. Both are designs that keep failures out of the context.

### Cited Findings
- [measured] Self-conditioning: the authors replaced chat history with artificial prior outputs at controlled error rates, then measured accuracy at turn 100. Non-thinking models (Gemma3, Qwen3, frontier non-thinking models such as Kimi-K2, DeepSeek-V3 and Qwen3-235B-Instruct) "consistently" got worse as the injected error rate rose, beyond what long context alone explains. The Figure 5 caption says scaling *increases* self-conditioning for non-thinking models, and CoT prompting does not remove it. — [Sinha et al., Illusion of Diminishing Returns](https://arxiv.org/abs/2509.09677)
- [measured] Qwen3 *thinking* models stayed stable at turn 100 regardless of the injected error rate. The authors suggest RL training and stripping prior thinking traces from history as possible reasons. — [Sinha et al.](https://arxiv.org/html/2509.09677v3)
- [measured] Mitigation: a sliding window that keeps only the N most recent turns "significantly improves performance", and smaller windows sustain longer horizons. The task was Markovian, a caveat the authors state themselves. Self-verification prompting gave mixed or negligible gains. — [Sinha et al.](https://arxiv.org/html/2509.09677v3)
- [measured] Per-step error rate rises as the task goes on. — [Sinha et al.](https://arxiv.org/abs/2509.09677)
- [design] Magentic-One: each inner-loop step of the Orchestrator's progress ledger asks "Is the team looping or repeating itself?" and "Is forward progress being made?". A stall counter goes up on loops or no progress, with the threshold set "≤2 in our experiments". Above the threshold it leaves the inner loop, reflects, updates facts and plan, and on every plan update "we force all agents to clear their contexts and reset their states." — [Magentic-One](https://arxiv.org/abs/2411.04468)
- [measured, indirect] Removing Magentic-One's ledgers cut GAIA validation performance by about 31%. The most common automated error code was "persistent-inefficient-actions" ("Agents engaged in unproductive patterns without adapting despite facing failures"). No separate ablation of the stall counter was reported. — [Magentic-One](https://arxiv.org/abs/2411.04468)
- [measured] Collapsing old observations in SWE-agent beats full history (18.0 vs 15.0%). — [SWE-agent paper](https://arxiv.org/abs/2405.15793)
- [design] SWE-agent keeps corrected format/blocklist mistakes out of the permanent history. — [agents.py](https://github.com/SWE-agent/SWE-agent/blob/main/sweagent/agent/agents.py)

### Inferences
- A 2B-active non-thinking model (or one run without thinking) is the kind of model Sinha et al. found self-conditions. Ten or more refused shell lines left in context are, in effect, injected-error history. Three things should help more than stronger refusal wording: pruning or collapsing refused-call/refusal pairs from the transcript after the turn, SWE-agent-style; replacing them with one line, "N refused shell lines omitted; use tool X"; or restarting the step from a clean, summarized state, as Magentic-One does.
- Re-reading files already in context matches SWE-agent's design, where old observations are elided or marked "outdated". Telling the model plainly that a file is already present, with its location, gives it external feedback rather than leaving it to self-correct.

### Gaps
- No study measured clean-context restarts specifically for tool-refusal loops in small coding agents. The self-conditioning result comes from a synthetic arithmetic and retrieval task.
- Reflexion's effect on tool-refusal loops was not examined here, and I did not fetch its source.

## 5. Critic/verifier or "second model rewrites the call" approaches for small models

### Takeaway
Two designs ship. Goose's tool shim uses a second local model to turn a weak model's text into structured tool calls. Gemini CLI uses a second LLM as a loop judge with a 0.9 confidence bar and a double-check model. I found no published measurement of either for small-model recovery. Huang et al. warn that the model judging itself without external signals is unreliable.

### Cited Findings
- [design] Goose tool shim: a separate interpreter model (default `mistral-nemo` on Ollama; also llama.cpp or local backends) parses the main model's output into tool calls. It is experimental. — [Goose tool-shim guide](https://goose-docs.ai/docs/guides/tool-shim)
- [anecdote/design] Goose has blogged about fine-tuning a dedicated toolshim model, motivated by poor benchmark results for models with weak tool support. — [finetuning toolshim](https://goose-docs.ai/blog/2025/04/11/finetuning-toolshim), [Goose benchmark](https://goose-docs.ai/blog/2025/03/31/goose-benchmark)
- [design] Gemini CLI's LLM loop judge: it runs after 30 turns, then every 5-15 turns depending on confidence, flags a loop only at ≥0.9 confidence, and confirms with a second model alias before acting. — [loopDetectionService.ts](https://github.com/google-gemini/gemini-cli/blob/main/packages/core/src/services/loopDetectionService.ts)
- [measured] Intrinsic self-critique degrades or fails to improve reasoning, and gains in multi-agent debate are attributed largely to self-consistency. External verifiers (code execution, tools) are what help. — [Huang et al.](https://arxiv.org/abs/2310.01798)
- [measured] CRITICTOOL finds weak self-critique and recovery across most LLMs in tool-calling error scenarios, which suggests the critic should not be the same weak model. — [CRITICTOOL](https://arxiv.org/abs/2506.13977)

### Inferences
- A deterministic rewriter will probably beat a second LLM for a pattern as regular as `cd DIR && cat FILE | head -N`. It could parse the line and run, or propose, the equivalent dedicated read call, or return it in the refusal as the call to make. It is cheaper and more reliable, and it supplies the external, verifiable feedback that Huang et al. say works. This is untested.

### Gaps
- I found no measured comparison of call-repair or shim approaches vs. better refusal text for small models, and no published Goose toolshim success-rate numbers.
