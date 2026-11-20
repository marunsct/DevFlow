# Constrained decoding and structured-output enforcement for a small local model on llama.cpp

Scope: forcing a tool-call or schema answer instead of prose from an open-weight model served by llama.cpp's OpenAI-compatible server (`--jinja`). The target is LFM2.5-24B-A2B (24B total, ~2B active MoE). The failures seen: prose where a tool answer is required, schema near-misses (a string where a list is wanted), and whole shell lines in one argument.

Evidence strength labels: **[strong]** = primary source code or a peer-reviewed/benchmark paper with numbers; **[medium]** = official docs, or a vendor blog with reproducible numbers; **[weak]** = abstract only, secondary blog, or my inference from code.

Source-code findings come from llama.cpp `master`, fetched 2026-10-23. Line numbers drift, so file URLs are given without line anchors.

---

## 1. llama.cpp: how tool calls and schemas are constrained, limits, and how reasoning interacts

### Takeaway
llama.cpp turns tools into a grammar. The grammar is **lazy** (it starts only when a trigger string appears) under `tool_choice: "auto"`, and **non-lazy** under `"required"` or `response_format`. For LFM2/LFM2.5 specifically, the tool-call grammar is a Python-call grammar. It enforces only the tool name, the argument names and string-vs-non-string values. **It does not enforce JSON-schema types (array), `enum`, `minItems`, `pattern` or `required` inside tool arguments.** The OpenAI "named function" `tool_choice` object is silently downgraded to `"auto"`. Full schema enforcement (arrays, minItems, patterns, enums) is only available through `response_format`/`json_schema` **without tools**.

### Cited Findings

**General mechanism and flags**
- Function calling is used in `llama-server` with `--jinja`. It is "supported for all models": templates without a native handler fall back to a **Generic** handler (log line `Chat format: Generic`), which "may consume more tokens and be less efficient than a model's native format." [strong] — [llama.cpp docs/function-calling.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md)
- "Beware of extreme KV quantizations (e.g. `-ctk q4_0`), they can substantially degrade the model's tool calling performance." [medium; official warning, no numbers] — [function-calling.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md)
- Parallel tool calls are "disabled by default"; enable them per request with `"parallel_tool_calls": true` ("only supported on some models, verification is based on jinja template"). [strong] — [function-calling.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md); [server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- You can check which template is in use (and whether a tool-use variant exists) at `GET /props` (`chat_template`, `chat_template_tool_use`). You can override it with `--chat-template-file`. [strong] — [function-calling.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md)
- If a template "supports tool calls but does not natively describe tools", the server logs: "The fallback behaviour used may produce bad results, inspect prompt w/ --verbose & consider overriding the template." [strong, code] — [common/chat.cpp](https://github.com/ggml-org/llama.cpp/blob/master/common/chat.cpp)

**Per-request parameters (`/v1/chat/completions`)**
- `response_format` accepts `{"type":"json_object"}`, `{"type":"json_object","schema":{...}}` or `{"type":"json_schema","json_schema":{"schema":{...}}}`. In code, an empty schema becomes `{"type":"object"}`. Any other `type` throws "response_format type must be one of \"text\" or \"json_object\"". [strong, code] — [server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md); [tools/server/server-common.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-common.cpp)
- `json_schema` and `grammar` are also accepted as raw per-request fields. Sending both raises "Cannot use both json_schema and grammar". [strong, code] — [server-common.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-common.cpp)
- A custom `grammar` together with `tools` (and `tool_choice` other than `none`) is rejected: "Cannot use custom grammar constraints with tools." / "Cannot specify grammar with tools". [strong, code] — [server-common.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-common.cpp); [chat.cpp](https://github.com/ggml-org/llama.cpp/blob/master/common/chat.cpp)
- **`tool_choice` is read as a string only**: `json_value(body, "tool_choice", std::string("auto"))`. The string is then parsed to `auto` / `none` / `required`; anything else throws "Invalid tool_choice". `json_value` catches a type error, logs "Wrong type supplied for parameter ... using default value", and returns the default. So the OpenAI named form `{"type":"function","function":{"name":...}}` **silently becomes `"auto"`**. [strong, code] — [server-common.cpp](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-common.cpp); [server-common.h](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/server-common.h); [chat.cpp `common_chat_tool_choice_parse_oaicompat`](https://github.com/ggml-org/llama.cpp/blob/master/common/chat.cpp)
- The object form `{"type":"tool","name":"..."}` is documented only under the Anthropic-compatible `POST /v1/messages` section of the README, not under chat completions. [strong] — [server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)
- Reasoning controls:
  - per request: `chat_template_kwargs` (e.g. `{"enable_thinking": false}`), `reasoning_effort` ("If `none`, reasoning/thinking is disabled"), `reasoning_format` (`none` = raw text);
  - server flags: `--reasoning-budget N` ("0 for immediate end"), `--reasoning-budget-message`, and `-rea on|off|auto`.

  [strong] — [server README](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md)

**LFM2 / LFM2.5 handler (what actually constrains this model)**
- llama.cpp has dedicated LFM2 and LFM2.5 handlers. LFM2.5 is detected by a template containing `List of tools: [` and no `<|tool_list_start|>` ("Using specialized template: LFM2.5"). [strong, code] — [chat.cpp](https://github.com/ggml-org/llama.cpp/blob/master/common/chat.cpp)
- Parser shape: `generation_prompt + optional(<think>…</think>) + content(until "<|tool_call_start|>") + "<|tool_call_start|>" + python_style_tool_calls + "<|tool_call_end|>"`. [strong, code] — [common/parsers/lfm2.cpp](https://github.com/ggml-org/llama.cpp/blob/master/common/parsers/lfm2.cpp)
- When the grammar is lazy:
  - Code: `grammar_lazy = !(has_response_format || (has_tools && tool_choice == REQUIRED))`, with the trigger `{WORD, "<|tool_call_start|>"}`.
  - Under `auto`, nothing is constrained until the model itself emits `<|tool_call_start|>`, so a pure-prose answer is fully legal.
  - Under `required` the grammar is active from the first token.

  [strong, code] — [lfm2.cpp](https://github.com/ggml-org/llama.cpp/blob/master/common/parsers/lfm2.cpp)
- If tools are present and `tool_choice != none`, the parser takes the tool branch. `response_format`'s schema is used **only** in the no-tools / `tool_choice:"none"` branch (`p.schema(p.json(), "response-format-schema", json_schema)`). Sending tools plus `response_format` does not constrain the tool arguments to that schema. [strong, code] — [lfm2.cpp](https://github.com/ggml-org/llama.cpp/blob/master/common/parsers/lfm2.cpp)
- **What the Python-style tool grammar enforces**
  - For each tool it emits `name(` + args + `)`. Each arg is `prop_name=` plus a value.
  - Value: if the property `type == "string"`, a quoted string (single or double quotes, any content). Otherwise any `python_or_json_value()`.
  - Args are `arg_choice + zero_or_more("," arg_choice)`. So args may come in any order and may repeat, and `required` is not enforced. `enum`, `pattern`, `minItems` and array-vs-scalar typing are not enforced for tool args.

  [strong, code] — [common/chat-peg-parser.cpp `python_style_tool_calls`](https://github.com/ggml-org/llama.cpp/blob/master/common/chat-peg-parser.cpp)
- JSON-style handlers do apply the full parameter schema: `tool_args(schema(json(), "tool-N-schema", params))`. These are the handlers used by Hermes/Qwen-style templates. [strong, code] — [chat-peg-parser.cpp](https://github.com/ggml-org/llama.cpp/blob/master/common/chat-peg-parser.cpp)
- Liquid's own docs:
  - LFM tool calls are Pythonic by default: `<|tool_call_start|>[get_candidate_status(candidate_id="12345")]<|tool_call_end|>`.
  - The tool list goes in the system prompt as `List of tools: [json]`.
  - Adding "Output function calls as JSON" to the system prompt switches to JSON format; the docs show no JSON example.

  [medium] — [Liquid AI docs: tool use](https://docs.liquid.ai/docs/key-concepts/tool-use)

**GBNF JSON-schema converter limits (the `response_format` path)**
- These limits are listed verbatim in the docs:
  - `additionalProperties` defaults to `false`;
  - "Unsupported features are skipped silently";
  - you can't mix `properties` with `anyOf`/`oneOf` in the same type;
  - "`prefixItems` is broken (but `items` works)";
  - `minimum`/`maximum` work for `integer` only;
  - nested `$ref`s are broken;
  - "patterns must start with `^` and end with `$`";
  - no `patternProperties`;
  - `uniqueItems`, `contains`, `not` and `if/then/else` are unsupported.

  [strong] — [grammars/README.md](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)
- The GBNF converter "always puts required properties first", whatever their order in `properties`. The optional LLGuidance backend (build with `-DLLAMA_LLGUIDANCE=ON`) keeps definition order, defaults `additionalProperties` to `true`, and errors on unsupported schemas instead of ignoring them. Mask computation averages about 50 µs per token on a 128k vocabulary. [strong] — [docs/llguidance.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/llguidance.md)
- On the JSON Schema Test Suite, llama.cpp's converter had 37 categories with compile errors, 18 over-constrained and 7 under-constrained. Guidance/llguidance had the fewest failures. [strong] — [JSONSchemaBench, arXiv 2501.10868](https://arxiv.org/html/2501.10868)

### Inferences
- **The observed failures follow directly from the code paths, not only from model weakness [weak→medium, inferred from code]:**
  - (a) Prose instead of a tool call is grammatically allowed under `auto`, because the lazy grammar has no trigger until `<|tool_call_start|>`.
  - (b) A string where a list is wanted is allowed by the LFM2.5 tool grammar: for a non-string param it accepts any Python/JSON value, and a string-typed param accepts any quoted text.
  - (c) A whole shell line in one argument is allowed for any `string` param, and also for an array param, because a one-element list or even a bare string passes.
- **Use `tool_choice: "required"`** (the string, not the object) where a tool answer is mandatory; this makes the LFM2.5 grammar non-lazy. It is unverified whether `content(until <|tool_call_start|>)` still allows some prose before the forced call when the grammar is non-lazy. The parser allows it, so expect a possible text preamble but a guaranteed call.
- **For a single structured answer that must obey types, `minItems`, `enum` and `pattern`:** send no tools (or `tool_choice:"none"`) and send `response_format: {"type":"json_schema", ...}`. Only this branch compiles the full JSON schema for LFM2.5. The optional `<think>…</think>` block before the JSON stays free, which is the "reason, then constrain" pattern (section 2).
- **To force one specific tool under llama.cpp:** pass only that tool in `tools` with `tool_choice:"required"`. This is the practical replacement for named `tool_choice`, which is silently ignored. Clients that send the named object, such as LangChain `with_structured_output(method="function_calling")` or `ToolStrategy`, get `auto` semantics on llama.cpp; check the server log for "Wrong type supplied for parameter 'tool_choice'".
- Switching LFM2.5 to JSON calls through the system prompt would probably break llama.cpp's parsing, because the LFM2.5 handler parses only `<|tool_call_start|>[python calls]` [weak, inference].
- If the run uses `-ctk`/`-ctv` below q8_0, that is a documented risk factor for tool calling.

### Gaps
- No measured numbers for how much KV-cache quantization degrades tool calls (the docs give only a warning).
- I did not run a live llama.cpp test to confirm whether `required` with the LFM2.5 grammar allows leading prose, or how `--reasoning-budget` interacts with a non-lazy grammar (for example, whether the budget's forced `</think>` is grammar-compatible).
- No llama.cpp benchmark of LFM2.5 tool-call validity was found.

---

## 2. Evidence: does constrained decoding help or hurt small models (compliance and task quality)?

### Takeaway
Good engines are at worst neutral on reasoning-task accuracy and slightly positive, while making the output reliably parseable. The famous "format restrictions hurt reasoning" result mostly came from forcing the answer before any reasoning, with under-specified prompts. The consistent, well-supported pattern is: let the model reason in free text, or in a first required `reasoning` field, then constrain only the answer.

### Cited Findings
- **JSONSchemaBench** (10k real schemas, 2025):
  - On GlaiveAI schemas, schema coverage was LM-only 0.90 vs Guidance 0.96 / Llamacpp 0.95 / Outlines 0.95 / XGrammar 0.93.
  - On GitHub-Hard schemas: LM-only 0.13, Guidance 0.41, Llamacpp 0.39, XGrammar 0.28, Outlines 0.03.
  - Open engines were run with Llama-3.2-1B for coverage. [strong]

  — [arXiv 2501.10868](https://arxiv.org/html/2501.10868)
- **JSONSchemaBench quality**, Llama-3.1-8B-Instruct:

  | Method | Last Letters | Shuffle Objects | GSM8K |
  |---|---|---|---|
  | LM only | 50.7 | 52.6 | 80.1 |
  | llama.cpp | 52.0 | 52.6 | 82.4 |
  | XGrammar | 51.2 | 52.7 | 83.7 |
  | Outlines | 53.3 | 53.0 | 81.6 |
  | Guidance | 54.0 | 55.9 | 83.8 |

  Every constrained engine was at or above baseline. [strong] — [arXiv 2501.10868](https://arxiv.org/html/2501.10868)
- JSONSchemaBench efficiency (Llama-3.1-8B, llama.cpp backend): time per output token was LM-only 15.4 ms vs llama.cpp grammar 29.98 ms vs Guidance 6.37 ms. Guidance's fast-forwarding of forced tokens cut total time by about 50%. [strong] — [arXiv 2501.10868](https://arxiv.org/html/2501.10868)
- **"Let Me Speak Freely?"** (Tam et al., v3 Oct 2024) reports a "significant decline in LLMs reasoning abilities under format restrictions", worse with stricter constraints. [weak here: abstract only read] — [arXiv 2408.02442](https://arxiv.org/abs/2408.02442)
- **dottxt rebuttal**: the paper compared different prompts for the NL and JSON runs, its JSON-mode prompts never gave a schema, and it used claude-3-haiku as the answer parser; a flexible regex beat that parser (0.61 vs 0.57 on Last Letter). Re-run with matched prompts, Llama-3-8B-Instruct, unstructured vs structured:

  | Task | Unstructured | Structured |
  |---|---|---|
  | GSM8K | 0.77 | 0.78 |
  | Last Letter | 0.73 | 0.77 |
  | Shuffle Objects | 0.41 | 0.44 |

  Recommendations:
  - put a reasoning field **before** the answer;
  - show the exact schema and a matching example in the prompt;
  - use the model's chat template;
  - parse with a deterministic regex, not an LLM.

  [medium: vendor blog, reproducible] — [dottxt "Say What You Mean"](https://blog.dottxt.ai/say-what-you-mean.html)
- **CRANE** (ICML 2025): proves that restricting output to a grammar of only valid final answers reduces expressivity and reasoning. It shows that adding reasoning rules to the grammar (free reasoning, then constrained output) preserves reasoning. It reports up to +10 points over constrained and unconstrained baselines on GSM-Symbolic and FOLIO with open models. [strong, but abstract-level detail] — [arXiv 2502.09061](https://arxiv.org/abs/2502.09061)
- **XGrammar** (MLSys 2025): splits the vocabulary into context-independent tokens (prechecked) and context-dependent tokens (checked at runtime). It reports "up to 100x speedup" and "near-zero overhead" in end-to-end serving. [strong] — [arXiv 2411.15100](https://arxiv.org/abs/2411.15100)
- LLGuidance: mask about 50 µs/token, p99 0.5 ms, and the "excellent" JSON-schema conformance used in JSONSchemaBench; it can be built into llama.cpp. [strong] — [llama.cpp docs/llguidance.md](https://github.com/ggml-org/llama.cpp/blob/master/docs/llguidance.md)

### Inferences
- For LFM2.5, the safest pattern is to keep `<think>` (or a free-text turn) unconstrained and constrain only the final JSON or tool call. llama.cpp's LFM2 parser already places an optional free `<think>` block before the constrained part.
- When a JSON answer carries its own reasoning field, make that field **required and first**: GBNF puts required properties first, so an optional `reasoning` field would come after the answer.
- Constraining is unlikely to cost accuracy, judging by the 8B evidence. The bigger risk with a 2B-active model is that a hard constraint forces a *valid but wrong* value: vLLM's docs put it as "a validly-parsable function call - not a high-quality one". So a constraint should be paired with semantic validation (section 4).

### Gaps
- No study found that measures constrained decoding on a ~2B-active MoE such as LFM2.5. The small-model data is Llama-3.2-1B (coverage) and 8B models (quality).
- I did not read the full numbers in "Let Me Speak Freely" (only the abstract).

---

## 3. Schema design for small models (flatness, enums, optional fields, argument shapes)

### Takeaway
Evidence that deep or complex schemas hurt compliance is moderate, and is strongest for small models. For "program and args in one string", the reliable fixes are structural:
- separate `program` and `args` fields;
- an `args` array;
- an anchored `pattern` on the program field.

These are enforceable only where the full JSON-schema grammar is applied (`response_format` on llama.cpp, or JSON-style tool handlers). Under LFM2.5's Python-style tool grammar they must be checked after generation.

### Cited Findings
- Compliance and coverage fall sharply with schema complexity even under constraint: on GitHub-Hard, the best open engine reached 0.41 coverage, against 0.96 on simple GlaiveAI function schemas. [strong] — [JSONSchemaBench](https://arxiv.org/html/2501.10868)
- **SO-Bench** (multimodal): as schema depth increases, metrics degrade for all models. A 4B model lost about 40% at the deepest levels while larger models stayed above 95%. [medium; from search summary, multimodal] — [arXiv 2511.21750](https://arxiv.org/pdf/2511.21750)
- **PARSE** (Amazon, EMNLP 2025 Industry): LLM-driven rewriting of schemas for clarity (ARCHITECT), plus reflection and guardrail extraction (SCOPE), gave up to +64.7% extraction accuracy on SWDE and about 10% across models. Errors fell 92% within the first retry. This supports "schemas written for developers are not optimal for LLMs; descriptions and naming matter". [weak-medium: abstract] — [arXiv 2510.08623](https://arxiv.org/abs/2510.08623)
- A secondary blog recommends 2–3 nesting levels for extraction schemas and cites PARSE / LLMStructBench. [weak, unverified secondary] — [tianpan.co](https://tianpan.co/blog/2026-04-12-schema-driven-prompt-design-letting-your-data-model-drive-your-prompt-structure)
- llama.cpp mechanics that shape schema design: [strong] — [grammars/README.md](https://github.com/ggml-org/llama.cpp/blob/master/grammars/README.md)
  - patterns must be anchored `^…$`;
  - `prefixItems` is broken, so "first array item must match X" cannot be expressed;
  - `items` + `minItems`/`maxItems` work (README example: `{"items":{"type":"string"},"minItems":10,"maxItems":100}`);
  - `additionalProperties:false` is the default, "reduces hallucinations".
- `enum` constraints and integer bounds are compiled into GBNF on the `response_format` path. They are not enforced on the LFM2.5 tool path, which enforces only string vs non-string. [strong, code] — [chat-peg-parser.cpp](https://github.com/ggml-org/llama.cpp/blob/master/common/chat-peg-parser.cpp)
- OpenHands' post-hoc validator coerces `integer` with `int()` and `array` with `json.loads`. It rejects values not in `enum`, unknown parameters and missing `required` parameters, each with a specific error message. [strong, code] — [OpenHands SDK fn_call_converter.py](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/llm/mixins/fn_call_converter.py)

### Inferences
- **A shape that prevents "program and args in one string" [inference]:**
  ```json
  {"type":"object","properties":{
    "program":{"type":"string","pattern":"^[A-Za-z0-9._/+-]+$","description":"executable name only, no spaces"},
    "args":{"type":"array","items":{"type":"string"},"description":"one element per argument"}},
   "required":["program","args"]}
  ```
  - The anchored no-whitespace pattern makes a whole shell line impossible in `program`, under grammar.
  - `prefixItems` is broken, so a single `argv` array with a constrained first element is not expressible in llama.cpp GBNF. Split it into two fields instead.
  - Do not put a no-space `pattern` on `args` items, because real arguments contain spaces.
- Keep schemas flat (one level), all fields required, enums for every closed set, and short descriptions that state the shape ("list of strings, one per item").
- Avoid optional fields: GBNF reorders them after required ones, and a small model often omits them. Use `required` + a nullable or empty-list default instead.
- Avoid `anyOf` mixed with `properties` (it is unsupported) and nested `$ref`.
- Under the LFM2.5 tool path, schema keywords act only as prompt text. The harness must validate and coerce after generation, for example: wrap a bare string into `[string]` when the type is array; reject a `program` that contains whitespace and re-ask with a specific error. Use OpenHands-style typed errors.

### Gaps
- No controlled study found that isolates single-string vs array arguments, enum vs free string, or optional-field count, on small models. The recommendations above are mechanism-based, not measured.
- PARSE and SO-Bench numbers come from abstracts or search summaries, not full papers.

---

## 4. How harnesses repair malformed tool calls and convert prose into structured answers

### Takeaway
Mature harnesses combine three things:
1. tolerant parsing (closing missing tags, normalising malformed parameter tags, stripping wrapper/think tags);
2. alias tables for tool names;
3. strict schema validation that returns precise, typed error messages to the model as a tool/observation message for a bounded retry.

LangChain's `ToolStrategy` builds the retry-with-error loop in; a constrained second "extraction" call is the standard prose-to-structure fallback.

### Cited Findings
- **OpenHands** `fn_call_converter.py` (non-native tool-call mode):
  - It describes tools in the prompt with an in-context example and parses `<function=NAME>…<parameter=x>…</parameter></function>` with the regex `<function=([^>]+)>\n?(.*?)</function>`, using stop word `</function`.
  - `_fix_stopword` appends a missing `</function>` (or completes a trailing `</`).
  - `_preprocess_model_output` strips `</think>` and `<tool_call>` wrappers just before or after a call.
  - `_normalize_parameter_tags` rewrites `<parameter=name=value</parameter>` to `<parameter=name>value</parameter>`.
  - `TOOL_NAME_ALIASES` maps legacy names (`bash`/`execute_bash` → `terminal`, `str_replace_editor` → `file_editor`).
  - `_extract_and_validate_params` coerces types and raises `FunctionCallValidationError` with specific messages ("Parameter 'x' is expected to be an array.", "...one of [enum]", "Missing required parameters ...", "Function 'x' not found in available tools: [...]").

  [strong, code] — [OpenHands SDK fn_call_converter.py](https://github.com/OpenHands/software-agent-sdk/blob/main/openhands-sdk/openhands/sdk/llm/mixins/fn_call_converter.py)
- **LangChain v1** `create_agent(response_format=...)`:
  - `ToolStrategy` "uses artificial tool calling to generate structured output"; `ProviderStrategy` "uses provider-native structured output generation".
  - Structured output is produced in the main loop with no extra LLM call.
  - `ToolStrategy(handle_errors=...)` (default `True`) retries on `StructuredOutputValidationError` and `MultipleStructuredOutputsError`. The error is fed back as a ToolMessage; it can be a fixed string, exception types or a custom function.

  [strong, official docs] — [LangChain structured output](https://docs.langchain.com/oss/python/langchain/structured-output#error-handling-strategies); [LangChain v1 migration](https://docs.langchain.com/oss/python/migrate/langchain-v1#tool-and-provider-strategies); [LangChain v1 release notes](https://docs.langchain.com/oss/python/releases/langchain-v1#structured-output)
- LangGraph guidance for "LLM-recoverable errors (tool failures, parsing issues)": "Store error in state and loop back" so the model sees what went wrong. [medium] — [LangGraph: thinking in LangGraph](https://docs.langchain.com/oss/python/langgraph/thinking-in-langgraph#handle-errors-appropriately)
- PARSE reports a 92% reduction in extraction errors within the first retry when guardrail errors are fed back. [weak-medium, abstract] — [arXiv 2510.08623](https://arxiv.org/abs/2510.08623)
- dottxt: prefer deterministic regex parsing to an LLM parser. A flexible regex (0.61) beat claude-3-haiku as parser (0.57). [medium] — [dottxt](https://blog.dottxt.ai/say-what-you-mean.html)
- "Let Me Speak Freely" motivates a two-step approach: answer freely, then convert to the format. [weak: abstract read; the two-step detail is from the paper's framing and was not verified in the full text] — [arXiv 2408.02442](https://arxiv.org/abs/2408.02442)

### Inferences
- **Prose-to-structure fallback for llama.cpp + LFM2.5 [inference, consistent with CRANE/dottxt]:** when a turn that must produce a structured answer returns prose, do not just re-prompt "use the tool". Send a second, cheap request:
  - the prior prose as context;
  - **no tools**, with `response_format: json_schema` (the full grammar, non-lazy);
  - or a single tool with `tool_choice:"required"`.

  This extracts the answer from the prose with the schema enforced. It is the llama.cpp equivalent of a "with_structured_output" extraction pass.
- With LangChain on llama.cpp:
  - `ProviderStrategy` maps to `response_format`, which is the fully enforced path on llama.cpp.
  - `ToolStrategy` maps to tool calling. On LFM2.5 that enforces only Python-call syntax, and any named `tool_choice` it sends is ignored, so it relies on `handle_errors` retries.
- Repair layers worth copying for LFM2.5 Python-style calls:
  - coerce a bare string into a single-element list for array params;
  - `json.loads`/`ast.literal_eval` a string that looks like a list;
  - an alias table for near-miss tool names;
  - typed error messages that name the parameter and the expected shape.

### Gaps
- No published measurement found of repair-layer hit rates (how many malformed calls are recovered) for small local models.
- Unverified: which JSON-repair libraries (e.g. json_repair) mature harnesses use; I did not inspect them.

---

## 5. vLLM / SGLang comparison

### Takeaway
vLLM makes the same distinction more explicitly. Named and `required` tool choice always use schema-derived structured outputs, while `auto` is parse-only unless tools are marked `strict`. That confirms that "auto" mode anywhere gives no argument-validity guarantee.

### Cited Findings
- vLLM, named function: "will use structured outputs to ensure the response matches the tool parameter object... You are guaranteed a validly-parsable function call - not a high-quality one." [strong, official docs] — [vLLM tool calling](https://docs.vllm.ai/en/latest/features/tool_calling.html)
- vLLM `required`: guaranteed to generate one or more tool calls, using structured outputs, "with any supported model". [strong] — [vLLM tool calling](https://docs.vllm.ai/en/latest/features/tool_calling.html)
- vLLM `auto`: constrained by structural tags only when a tool sets `strict: true` or `--tool-strict-level` is `function`/`parameter`; "Otherwise, vLLM extracts tool calls from raw text, so arguments may occasionally be malformed or violate the function's parameter schema." xgrammar is the default structured-output backend. [strong] — [vLLM tool calling](https://docs.vllm.ai/en/latest/features/tool_calling.html)

### Inferences
- llama.cpp gives the following under each `tool_choice` setting:
  - `required`: a forced call, but for LFM2.5 only syntax-level argument enforcement.
  - named: no support, silently treated as `auto`.
  - `auto` (lazy): no guarantee.
- vLLM would enforce the full parameter schema for named and `required` choice. For this model on llama.cpp, the closest equivalent is `response_format` with no tools.

### Gaps
- SGLang's tool-choice and constraint behaviour was not researched (lower priority; comparison only).
- vLLM's docs do not describe how a reasoning parser interacts with `required`/named choice.
