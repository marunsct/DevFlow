# Inkling 2 Mini: how its reasoning is really controlled, and what the harness should send

Date: 2026-11-27 (JST). Read-only research; nothing in `src/`, `tests/`, the settings or the model servers was changed.
No completion request was sent to any model server. Only `GET /props`, `GET /slots` and the balancer's status page
were read.

Evidence:

- the live `/props` of the server at `:2001` (chat template, template capabilities, build `b12641-eb3982317`);
- the model file's GGUF header (`Inkling-2-Mini-UD-Q4_K_M.gguf`, read with a small header reader);
- the source of the llama.cpp branch the two servers are built from (`/home/arun/aiengine/inklingvulkan`);
- the model's diagnosis kept in the worker (`/app/data/model-fitness/Inkling-2-Mini-UD-Q4_K_M.gguf.json`);
- the transcripts of the two live runs, `run-e3acafda` (web to-do brief) and `run-f6502d06` (Hono service brief),
  read at 02:40 JST, both then in `principal_architect`;
- the model card and the Unsloth guide (sources at the end).

What was **not** done: no request was sent to prove a switch. Every claim about what the server does comes from its
source code and its `/props`. Every claim about what the model then does is from its card. The IK items below
therefore start by measuring.

## Short answers

1. **The diagnosis was wrong to say "not honoured". Its question was too easy to tell.** It asks "What is 12 plus
   30?". The model spent 47 tokens as served, 48 with effort `none`, 40 with `low`, 38 with the template switch off.
   There was almost no reasoning to remove, so no switch could pass the "under 70% of as served" test.
2. **This model has one prompt-level control: a number in a system line.** The chat template writes
   `Thinking effort level: <n>` once, before the first non-system message. `n` comes from `reasoning_effort`:
   none 0, minimal 0.1, low 0.2, medium 0.7, high 0.9, xhigh and max 0.99. When no effort is given the template uses
   **0.9 (high)**. The template never reads `enable_thinking`, so that switch does nothing here.
3. **`reasoning_effort: "none"` does the opposite of what it says on this server.** llama.cpp turns the top-level
   value `none` into `enable_thinking = false` and then **removes** the effort from the template's arguments. The
   template ignores `enable_thinking` and falls back to its default, 0.9. So "none" means "high". The only way to
   give the template a real zero is `chat_template_kwargs: {"reasoning_effort": "none"}` with no top-level field.
4. **The effort number is a request to the model, not a limit.** The card says: "Setting reasoning effort to its
   minimum does not fully disable reasoning", and "Inkling 2 Mini has very little controllability over its chain of
   thought". It also reports long reasoning loops and recommends "setting limits on output tokens and agent turns".
5. **There is a hard limit, and the harness can send it per request.** This server build reads
   `reasoning_budget_tokens` (also spelt `thinking_budget_tokens`) and `reasoning_budget_message` from the request
   body. After that many reasoning tokens the sampler forces the end-of-thinking token and the model must answer.
   `0` ends thinking at once. The harness sends none of these today.
6. **No server flag is needed.** Every control has a per-request form. The owner's flags (`--reasoning-effort`,
   `--reasoning-budget`) only set the default for calls that send nothing.
7. **What the two runs show:** about 80% of the output is reasoning. One architect reply reasoned to the 32,000 cap
   (7 minutes), was salvaged (3 more minutes), 44,097 tokens for an answer of about 10,000. No broken tool call, no
   call to a tool not offered, no failed structured answer so far. Two other defects were found on the way: a named
   tool choice is silently ignored by this server while the harness believes it is honoured (IK.6), and a short
   helper call nearly spent its whole 2,048-token cap reasoning (IK.4).

## 1. How the reasoning is controlled

### 1.1 The chat template

The template in `/props` is the same one the repository already holds in
`tests/captured/llama-cpp-props-one-slot-behind-a-balancer.json` (identical text). The GGUF header holds it too
(6,868 characters against 6,867 in `/props`; I did not diff the one character).

What it does with reasoning:

- It defines `effort_map`: none 0.0, minimal 0.1, low 0.2, medium 0.7, high 0.9, xhigh 0.99, max 0.99.
- `reasoning_effort` may be one of those names, or a number from 0.0 to 0.99. An unknown name raises an error.
- If `reasoning_effort` is not defined, it uses 0.9.
- It writes one line, `<|message_system|><|content_text|>Thinking effort level: 0.7<|end_message|>`, before the first
  message that is not a system message.
- It never mentions `enable_thinking`.
- A reply is a list of blocks: `<|content_thinking|>…<|end_message|>`, `<|content_text|>…`, and tool calls as
  `NAME<|content_invoke_tool_json|>{"name":…,"args":{…}}`. A reply may hold several thinking blocks.

`/props` reports `supports_reasoning_effort: true`, levels `minimal, low, medium, high, max`, none rejected.

### 1.2 What the server does with each request field

From `tools/server/server-common.cpp`, `common/chat.cpp`, `common/arg.cpp`, `common/reasoning-budget.cpp` and
`common/parsers/inkling.cpp` of the branch the servers run.

| Sent in the request | What the server does | Effect on this model |
|---|---|---|
| nothing | template default | effort 0.9 |
| `reasoning_effort: "low"` (also minimal, medium, high, max) | passed to the template | 0.2 (0.1, 0.7, 0.9, 0.99) |
| `reasoning_effort: "none"` | sets `enable_thinking=false`, **erases** the effort | template default, 0.9 |
| `chat_template_kwargs: {"enable_thinking": false}` | passed to the template | none; the template does not read it |
| `chat_template_kwargs: {"reasoning_effort": "none"}`, no top-level field | passed to the template | 0, the lowest the model knows |
| `chat_template_kwargs: {"reasoning_effort": 0.05}` | passed to the template | any number 0.0-0.99 |
| `reasoning_budget_tokens: N` (or `thinking_budget_tokens`) | sampler counts tokens after the thinking-start token; at N it forces the end-of-message token | hard limit per thinking block; `0` ends it at once |
| `reasoning_budget_message: "…"` | written just before the forced end | the model reads why it stopped |
| `reasoning_control: true` | lets `POST /v1/chat/completions/control` end reasoning mid-reply | a live stop, not needed if a budget is sent |
| `tool_choice: {"type":"function","function":{"name":…}}` | **wrong type, logged, read as `auto`** | nothing is forced (see 4.1) |
| `tool_choice: "required"` | grammar forces some tool call | honoured |

Two details matter for a budget on this model:

- The budget is per thinking block. The sampler re-arms when a new `<|content_thinking|>` starts. A reply with three
  thinking blocks may spend three budgets. The reply cap stays the outer limit.
- The budget works together with the lazy tool-call grammar (the sampler replays the end token to the grammar), so
  it should not break tool calls. This is read from the code, not measured.

### 1.3 Server flags (owner only)

The servers run with `--jinja --temp 1.0 --top-p 1.0 --top-k 40 --min-p 0.0 -np 1 -c 231072`. No reasoning flag is
set. The flags that exist:

- `--reasoning-effort LEVEL`: the default effort for requests that send none.
- `--reasoning-budget N` and `--reasoning-budget-message`: the default budget.
- `--reasoning on|off`: sets `enable_thinking`; no effect on this template.
- `--chat-template-kwargs`: any template argument as a default.

Each has a request field that overrides it, so none is required. A flag would only help callers that send nothing.

### 1.4 The model card

- Thinking Machines' card: effort at its minimum "does not fully disable reasoning"; the model "sometimes became
  stuck in long reasoning loops, or repeatedly re-checked its own work without making progress, particularly when
  debugging code"; "We recommend setting limits on output tokens and agent turns"; "very little controllability over
  its chain of thought".
- Unsloth's Inkling 2 guide gives the same effort table, says the GGUF template defaults to high, that `none` "does
  not strictly guarantee zero reasoning", and sets effort with `--chat-template-kwargs '{"reasoning_effort":"high"}'`.
- The Hugging Face launch post says 0.7 (medium) "seems to provide a good trade-off".
- Neither page mentions a reasoning budget. That is llama.cpp's own feature.

## 2. What the harness sends today, and what it could send

### 2.1 Today

- **Stage calls.** The run's thinking mode is `on`, effort `medium`. `ThinkingPolicy.openai_arguments`
  (`src/app/agents/thinking.py`) sends `reasoning_effort: "medium"` and
  `chat_template_kwargs.enable_thinking: true`. So the model runs at 0.7. The settings allow only low, medium and
  high. In mode `default` nothing is sent and the model runs at 0.9, which is more reasoning than mode `on`.
- **"Answer without reasoning" calls** (`answering_without_reasoning`): `enable_thinking: false`, plus the
  measured least effort. The diagnosis kept no least effort, so only `enable_thinking: false` is sent. On this model
  that changes nothing. Every mechanism built on it is inert here: the call after a spiral, the helper calls in
  `src/app/plugins/middleware.py`, thinking off after a salvaged reply.
- **Had the diagnosis picked `none`**, the harness would have sent the top-level field and raised the effort from
  0.7 to 0.9. The 70% test happened to prevent that.
- **No budget is sent.** `reasoning_budget_tokens` appears nowhere in `src/`.
- **Reply salvage** works on this model (`reasoning_field` shape, continuation, tools). It is what rescued the
  architect reply. It costs a second request and only starts after the whole cap is spent.

### 2.2 The diagnosis

`_reasoning_cost` in `src/app/models/diagnostics.py` asks "What is 12 plus 30?" four ways and compares output
tokens. `settled` calls a switch honoured when it costs under 70% of "as served". Measured here: 47 / 48 / 40 / 38.
The question needs no reasoning, so the result says nothing. It also never tries the two forms that can work on
this server: the effort as a template argument, and a reasoning budget.

### 2.3 Who can set what

| Control | Per request by the harness | Server flag |
|---|---|---|
| effort low / medium / high | yes, sent today | `--reasoning-effort` |
| effort minimal | yes, the settings do not offer it yet | same |
| effort none (0) | yes, only as a template argument (IK.2) | `--chat-template-kwargs` |
| hard reasoning budget | yes, not sent yet (IK.3) | `--reasoning-budget` |
| thinking fully off | yes, as budget 0 (IK.4); the template has no switch | `--reasoning-budget 0` |
| stop reasoning mid-reply | yes (`reasoning_control` plus the control endpoint); not proposed | none |
| forced answer tool | `required` only; a named choice is ignored (IK.6) | none |
| sampling | owner's (ADR-0008) | as launched |

## 3. Proposed harness changes

All are general: they are for any model whose reasoning cannot be switched off by the usual fields. What is used for
a given model is decided by its diagnosis and kept in its profile. Nothing names Inkling in code.

Order: IK.1 and IK.2 first (they make the measurement true), then IK.6 (a wrong setting is live now), then IK.3 and
IK.4 behind a switch until measured.

### IK.1 The reasoning probe asks a question that needs reasoning, and says "not measurable" when it cannot tell

- **Problem.** A question answered in 47 tokens cannot show a switch working. The diagnosis then records "not
  honoured", and everything that depends on a switch goes quiet for that model.
- **Change.** In `src/app/models/diagnostics.py`: replace `_QUESTION` for the cost probe with one that a reasoning
  model does reason about (the multi-step puzzle `thinking._PROBE_QUESTION` already uses, or a small stage-shaped
  request). If "as served" costs under a floor (about 200 tokens), record the switches as *not measurable* instead
  of *not honoured*, and say so in the advice. `Settings` gets a third state for it. `capabilities.py` (the
  `thinking_switch` line) and `steering_job.py` show it.
- **Test (fails on old code).** A stub server that answers 47 / 48 / 40 / 38 tokens: old code keeps "reasoning_effort
  not honoured; template thinking switch not honoured"; new code keeps "not measurable" and does not write a
  `least_reasoning_effort` of "". A second stub answering 900 as served and 250 for `low`: `low` is kept.
- **Effect.** No false "not honoured" for a model that reasons only when the work is hard.

### IK.2 The effort is also tried as a template argument, with the levels the server lists

- **Problem.** On llama.cpp the top-level `none` erases the effort, so a template that reads only `reasoning_effort`
  goes to its own default. The value that works is the template argument. The harness never tries it. It also never
  tries `minimal`, which `/props` lists.
- **Change.**
  - `diagnostics._reasoning_cost`: add the ways `chat_template_kwargs.reasoning_effort` = `none`, and each level in
    `/props` `chat_template_caps.reasoning_effort_levels` below `low`. Read the caps with the existing `/props`
    reader (`server_profile.py` or `capabilities.py`), no model call.
  - `diagnostics.Settings`: keep the route with the value, for example `least_reasoning_effort = "none"` and
    `effort_route = "template"` (or `"field"`).
  - `thinking.answering_without_reasoning` and `thinking._reasoning_spent`: when the route is `template`, put the
    effort in `extra_body.chat_template_kwargs` and send no top-level `reasoning_effort`.
  - `CompatibleChatOpenAI._get_request_payload` (`src/app/models/__init__.py`): on such a call, drop the client's own
    top-level `reasoning_effort`, because the server lets the top-level value overwrite the template argument.
  - `_thinking_is_off_in` (`src/app/models/__init__.py`) and `sampling_modes.py` line 299: recognise the new form as
    "thinking off".
- **Test (fails on old code).** For a server whose kept diagnosis has the route `template`:
  `answering_without_reasoning(model)` returns `chat_template_kwargs.reasoning_effort == "none"`, and the payload
  built for that call has no top-level `reasoning_effort`. On old code the payload carries the client's `medium` and
  nothing else. A second test: a diagnosis where top-level `none` costs as much as "as served" never keeps `none`
  for the field route.
- **Effect.** The "answer now" calls reach the model's lowest effort (0 instead of 0.7 here). How much that saves is
  for the diagnosis to measure; the card says it is not zero reasoning.

### IK.3 A reasoning budget is sent where the server enforces one, so a reply always has room to answer

- **Problem.** A reply that reasons to its cap writes nothing. Salvage then costs a second request, after the whole
  cap is gone. Measured here: 32,000 tokens of reasoning (7 minutes at about 76 tokens a second), then a 12,097-token
  salvage (3 minutes). The answer itself was about 10,000 tokens.
- **Change.**
  - `diagnostics`: one more check, "a reasoning budget is enforced": the reasoning question with
    `reasoning_budget_tokens: 64` and `reasoning_budget_message`. Passed when the reply's reasoning is near the
    budget and an answer follows. A server that refuses the field (400/422) or ignores it fails. Kept in `Settings`
    as `reasoning_budget: bool`.
  - `src/app/models/__init__.py`, where the reply cap is applied to the payload: when the serving model's diagnosis
    has `reasoning_budget`, add `reasoning_budget_tokens = cap - answer room` and
    `reasoning_budget_message = reply_salvage.ENOUGH`. The answer room is the stage's measured answer size, at least
    `thinking.MIN_ANSWER_TOKENS`; `thinking.thinking_budget_tokens(effort, cap)` already computes this split for
    Anthropic and can be reused. Self-hosted servers only (`endpoints.is_self_hosted`).
  - Reply salvage stays as the fallback: the budget is per thinking block, so a reply can still reach the cap.
  - Behind a switch (`REASONING_BUDGET`), off until measured, per the owner's rule for efficiency changes. Add it to
    `docs/measuring.md`.
- **Test (fails on old code).** With the switch on and a diagnosis that enforces a budget, the payload of a stage
  call capped at 32,000 carries `reasoning_budget_tokens` below the cap by the answer room, and the message. A
  hosted API's payload carries neither. With the switch off, neither. Old code: the field is absent in all three.
- **Effect.** The architect reply above would have stopped reasoning at about 20,000 tokens and answered in the same
  request: about 30,000 tokens in place of 44,097, about 3 minutes saved, and no second read of a 60,000-token
  request. More important, a reasoning loop can no longer take the whole cap. The risk to measure: an answer written
  after reasoning was cut short may be worse. Salvage has the same property, so the comparison is fair.
- **Note.** `reply_salvage.py` says a cap on reasoning "would have cost more" on an earlier model, because 74 good
  replies finished between 16,000 and 32,768 tokens. That is why the budget here is the cap minus the answer, not a
  small number: it only removes the case where nothing is left to answer with.

### IK.4 "Thinking off" has a form that works when the model has no switch: a zero or small budget

- **Problem.** `answering_without_reasoning` returns settings that do nothing on this model. A helper call capped at
  2,048 tokens spent 1,833 of them to answer "javascript, html, css" (23 seconds; another spent 849). At the cap the
  reply is empty and the helper reads it as "no frameworks named".
- **Change.** In `thinking.answering_without_reasoning`: when the diagnosis found no working switch but an enforced
  budget, add `reasoning_budget_tokens` to the extra body: 0 where the diagnosis measured that a zero budget still
  answers correctly, else a small number (about 256). Combine with the lowest effort from IK.2.
  `_thinking_is_off_in` and `sampling_modes` treat a budget at or under that number as "off", so the thinking-off
  reply cap and the per-mode sampling keep working. The diagnosis adds the check "answers with a zero budget".
- **Test (fails on old code).** For a model whose diagnosis has no switch and an enforced budget,
  `answering_without_reasoning` returns a `reasoning_budget_tokens`; `_thinking_is_off_in` is true for that call.
  Old code returns only `enable_thinking: false`.
- **Effect.** The switched-off calls really are short on this model: helper calls, the call after a spiral, the
  stage after a salvaged reply. It uses the same switch as IK.3.

### IK.5 The effort a model runs at comes from its profile, with every level its server lists

- **Problem.** The settings offer low, medium and high. In mode `default` the harness sends nothing, and this model
  then runs at 0.9, above `on` + `medium`. Nothing tells the owner that.
- **Change.** `src/app/server/settings.py`, `src/app/config.py`, `thinking.normalise_effort`: accept `minimal` (and
  pass any level the server's `chat_template_caps.reasoning_effort_levels` lists). The diagnosis advice states the
  template's own default when the template names one ("with nothing sent this model reasons at high"). The per-model
  profile (`src/app/server/model_profiles.py` already carries `thinking_effort`) is where a model's level is kept.
- **Test (fails on old code).** `normalise_effort("minimal")` stays `minimal` and reaches the payload; today it
  becomes `medium`.
- **Effect.** The owner can run this model at `low` (0.2) or `minimal` from its profile, with no code path specific
  to it. **This needs no code today for `low`:** setting the profile's effort to `low` is an owner or operator
  setting, and is the cheapest first experiment. I did not change it.

### IK.6 A named tool choice that the server ignores is not recorded as honoured

- **Problem.** llama.cpp reads `tool_choice` as a string. An object (a named tool) is the wrong type; the server logs
  a warning and uses `auto`. The diagnosis check "one tool named" still passed 3 of 3, because the model chose that
  tool by itself. The stage-shaped checks show the truth: "a structured answer forced" 0 of 3, "forced after a long
  request" 0 of 2, "a structured answer, required" 3 of 3. `settled` then says "forced stays", and `apply` adds the
  server to `named_answer.HONOURED`. From then on, every call where only the answer is allowed replaces `required`
  (which this server enforces) with a named choice (which it ignores). That is weaker than before the feature.
- **Change.** In `diagnostics.settled`: when the stage-shaped forced checks fail and "a structured answer, required"
  works, choose `structured_answers = "required"`, whatever the reason the named form failed (today it needs an LM
  Studio error text). In `diagnostics.apply`: add to `HONOURED` only when "a structured answer forced" itself
  passed. Add a check that tells a real force from luck: name a tool the request does not fit (the capabilities probe
  `forced_tool_enforced` already does this for `required`).
- **Test (fails on old code).** Checks as measured here (named 3/3, required 3/3, structured forced 0/3, long 0/2,
  offered 0/3, structured required 3/3): old code gives `forced` and puts the server in `HONOURED`; new code gives
  `required` and leaves it out.
- **Effect.** Answer-only calls keep `required` on llama.cpp servers. Fewer calls that bring back a refused read
  instead of the answer. This is a correctness fix, so no switch.
- **Later option.** A real force on such a server is `required` with only the answer tool in the list. That changes
  the tool list, and this template writes the tools first, so the whole prompt is read again. Worth measuring only
  if `required` alone still loses calls.

## 4. Other problems seen in the two runs

Read at 02:40 JST. Both runs were in `principal_architect`. `run-e3acafda`: 14 replies, 81,756 output tokens.
`run-f6502d06`: 18 replies, 74,180 output tokens.

### 4.1 Tool calls and structured answers

- **No broken call so far.** 0 invalid tool calls in 32 replies, 29 tool calls all successful, no call to a tool
  that was not offered, every structured answer arrived as its tool call.
- **The diagnosis warns of what has not happened yet.** In its stage-shaped checks the model called
  `run_terminal_command` instead of answering (0 of 3), went on after its tests passed (0 of 3), joined programs
  with `&&` and `||` in one command (0 of 3), and ignored a refusal twice in three. Guidance fixed two of these in
  the probe (`answer_in_schema`, `one_program_a_command`). Expect them in the build and fix stages, where there is a
  terminal. Tier: weak (0.611).
- **One reply in the deep diagnosis wrote its tool call as text**:
  `SprintPlanOutput<|content_invoke_tool_json|>{"name":"SprintPlanOutput","args":{"…`, finish `stop`. The server's
  parser missed it. `src/app/agents/text_tool_calls.py` recovers calls written as text, but knows only `<tool_call>`
  style wrappers and fenced JSON. If this shows up in a run, the general fix is one more recognised shape there: a
  known tool name followed by a JSON object holding `name` and `args`.
- **Find-and-replace edits were well formed 67% of the time** in the diagnosis; whole-file writes 100%. The harness
  already prefers whole-file writes for short files on such a model.

### 4.2 Reasoning cost

- By characters, reasoning is about 77% of what `run-e3acafda` wrote and 86% of `run-f6502d06`.
- Specialist advice replies: 6,600 to 13,600 tokens each, 1.5 to 3.5 minutes, for one structured answer.
- The architect reply: sent 02:17:09, cut at the cap 02:24:12, salvaged 02:27:02. 44,097 tokens, 114,303
  characters of reasoning kept. `principal_architect` is not in the plan-and-review reply cap (20,000) by design, so
  it runs to 32,000.
- Each server has one slot. With two runs in parallel mode, four requests were open on two slots. The three
  parallel specification sections of `run-e3acafda` were sent at 02:27:02 and wait behind the other run's
  architect reply. Long reasoning on one request is now waiting time for another run.

### 4.3 Wasted reads

Every stage opens by reading `docs/decision_log.md` and `docs/tools_and_models.md` again: 12 and 8 reads across the
two runs. Five reads were of a file "quoted whole in your request" and were answered with that note. Each is a model
call of 3 to 30 seconds. The decision log and the tools document could be quoted in the request as the intake is, or
the stage told they are. Not specific to this model, but this model does it every time.

### 4.4 Not the model: two harness defects seen in the same logs

- **The package registry read is cut at 8 MiB.** `Could not read the releases of npm playwright: Unterminated
  string starting at … char 8388411`, also for `@playwright/test` and `@types/node`, eight times in 15 minutes.
  `MAX_RESPONSE_BYTES = 8 * 1024 * 1024` in `src/app/tools/package_registry.py` cuts the registry document and the
  JSON then fails. The release check for those packages is silently skipped.
- **"mobile" was treated as a library.** `run-e3acafda` asked for documentation topics with "Libraries: mobile,
  Playwright" and sent `mobile 0.0.1` to the advisory lookup. The word came from the brief ("mobile viewport"), not
  from a package list.

## 5. What the owner could do without any code

None of this is required. Listed because it is quick.

1. Set this model's effort to `low` in its profile. The model then gets 0.2 instead of 0.7. Quality at 0.2 is not
   measured.
2. Or launch the servers with `--reasoning-budget 20000 --reasoning-budget-message "<one sentence>"`. Every request
   then stops reasoning at 20,000 tokens per block. A request field from the harness would override it later.

## Sources

- Model card: https://huggingface.co/thinkingmachines/Inkling-2-Mini
- GGUF repository the file comes from: https://huggingface.co/unsloth/Inkling-2-Mini-GGUF
- Unsloth guide, Inkling 2 (effort table, template default, `--chat-template-kwargs`): https://unsloth.ai/docs/models/inkling-2
- Hugging Face launch post (effort names, 0.7 as a trade-off, vLLM parsers): https://huggingface.co/blog/thinkingmachines-inkling
- llama.cpp, top-level `reasoning_effort: "none"` (found by search, not opened): https://github.com/ggml-org/llama.cpp/pull/26045
- Local source of the running servers: `/home/arun/aiengine/inklingvulkan` at `eb3982317` -
  `tools/server/server-common.cpp` (lines 1507, 1630-1690), `tools/server/server-common.h` (line 46),
  `common/chat.cpp` (lines 324-334, 1100-1142), `common/arg.cpp` (lines 3750-3800), `common/reasoning-budget.cpp`,
  `common/sampling.cpp` (lines 323, 470-505), `common/parsers/inkling.cpp`, `tools/server/README.md`
  (lines 1468-1474), `INKLING.md`.
- Harness code read: `src/app/agents/thinking.py`, `src/app/models/diagnostics.py`, `src/app/models/__init__.py`,
  `src/app/models/reply_salvage.py`, `src/app/models/named_answer.py`, `src/app/models/capabilities.py`,
  `src/app/models/sampling_modes.py`, `src/app/plugins/middleware.py`, `src/app/agents/text_tool_calls.py`.
