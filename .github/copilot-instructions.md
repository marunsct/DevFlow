# LangChain and LangGraph Development

This repository contains local LangSmith development guidance. Treat the local guides below as the first source of truth for decisions involving LangChain, LangGraph, LangSmith, tracing, datasets, or evaluators.

## Required Guidance Check

Before making a design decision, changing code, adding dependencies, or writing examples for LangChain or LangGraph:

1. Read `.github/skills/Agents.md` for the repository-wide LangSmith workflow.
2. Read every applicable skill before writing code:
   - `.github/skills/langsmith-trace/SKILL.md` for tracing, run/trace inspection, exporting, or debugging.
   - `.github/skills/langsmith-dataset/SKILL.md` for creating, importing, exporting, or managing evaluation datasets and examples.
   - `.github/skills/langsmith-evaluator/SKILL .md` for evaluator creation, run functions, evaluation pipelines, or evaluator CRUD.
3. Prefer the imports, commands, scripts, and patterns in those skills over invented alternatives.
4. Check the current project configuration and environment variables before using LangSmith APIs. Never expose API keys in source code, commands, logs, or responses.

If a required local guide is missing, ambiguous, or contradicts an external assumption, stop and state the discrepancy. Verify against current official LangChain documentation before proceeding; do not silently guess.

## LangChain and LangGraph Rules

- For LangChain or LangGraph applications, use the documented LangSmith tracing configuration and preserve useful trace names, metadata, and hierarchy.
- When investigating behavior, query complete traces before individual runs unless the task specifically requires a single run. Preserve the parent/child hierarchy when analyzing agent or graph execution.
- Before writing extraction or evaluator logic, run the agent on representative inputs and inspect the actual output and trace structure. Do not assume output fields, trajectory shape, or evaluator input types.
- Keep offline and online evaluator contracts distinct. Confirm the target (`--dataset` or `--project`) and the expected runtime shape before implementing or uploading an evaluator.
- Evaluators must return one metric per evaluator. Follow the local skill's language-specific return format and local-versus-uploaded behavior.
- Validate required environment variables and target projects/datasets before network operations. Use read-only preflight checks where the applicable skill requires them.
- Handle destructive LangSmith operations conservatively: inspect matches first, honor confirmation prompts, and use non-interactive confirmation only when explicitly appropriate.
- For LangGraph subgraphs and nested agent calls, use the tracing and streaming options documented in the evaluator skill rather than assuming nested calls appear in default outputs.

## Change and Validation Workflow

- Make the smallest change that satisfies the request and follow existing project conventions.
- After edits, run the narrowest relevant test, example, type check, or validation command available.
- For observability or evaluation changes, verify both the local behavior and the resulting trace, dataset, or evaluator contract when credentials and services are available.
- Do not add LangChain or LangGraph dependencies without checking the existing dependency and version configuration first.

## Product Development Workflow

For any product-development request backed by a supplied product document, follow `docs/development-workflow.md` and use the reusable workspace agents in `.github/agents/`.

- Start with `product-delivery-orchestrator` for new product work or a cross-cutting change.
- Require product intake when ambiguity affects scope or user behavior.
- Run `product-tools-models-architect` as Step 1 to define and compare tools, frameworks, services, model roles, versions, contracts, and validation experiments before adding implementation dependencies.
- Do not implement before `product-principal-architect` has inspected the repository and product documents, updated the specification and ADRs, and `product-senior-architect-reviewer` has approved them.
- Use `product-scrum-master` to create the sprint plan, then `product-technical-lead` to execute exactly one sprint at a time.
- Delegate UI, database, backend, testing, documentation, and security/reliability work to the role specialists; do not hard-code product-specific assumptions into reusable workflow artifacts.
- Require `product-milestone-reviewer` to review every milestone before the Technical Lead accepts it.
- Record decisions, rationale, risks, validation evidence, and unresolved questions in the product-specific `docs/` artifacts.
- Write beginner-readable code: explain the purpose, inputs, outputs, failure behavior, and security assumptions of every non-obvious line or block near the code or in linked documentation. Avoid comments that merely restate syntax.

## Guided Teaching Mode

When developing this LangChain/LangGraph workflow, act as both implementation partner and teacher. This rule applies to every step, agent, file, and milestone:

1. Present the complete plan and identify the current numbered step before editing files.
2. Explain the goal, relevant concepts, expected files, design choices, and success check for the current step in beginner-friendly language.
3. Implement only the current step. Do not silently implement later steps or jump over a gate.
4. Run the narrowest focused validation immediately after the edit.
5. Explain what the code does, why it was chosen, what the validation proves, and any limitations or next decisions.
6. Continue to the next step only after the current step is understandable and validated; ask for clarification when a product or architecture decision cannot be safely inferred.

## Beginner Code Documentation Standard

This standard is mandatory for all generated or modified code, configuration, tests, prompts, tools, agent definitions, and workflow logic:

- Assume the reader is new to Python, LangChain, Deep Agents, LangGraph, and the project domain.
- Explain why a non-obvious line, block, class, function, type, setting, prompt, or dependency exists, not only what its syntax does.
- Document inputs, outputs, state changes, control flow, failure behavior, validation rules, retries, side effects, and security assumptions.
- Use meaningful nearby comments for code-specific reasoning and a linked Markdown guide for larger concepts, workflows, API contracts, or multi-file behavior.
- Explain unfamiliar terms at first use, including type hints, dataclasses, schemas, nodes, edges, state, tools, agents, interrupts, checkpoints, and structured output.
- Keep comments accurate when code changes. Do not leave comments that describe an older implementation.
- Do not add noisy comments that translate obvious syntax line by line. If a beginner needs a line-by-line explanation, create or update a companion guide in `docs/`.
- Every implementation step must update documentation when the new behavior, decision, setup command, failure mode, or security assumption is not already documented.
- Every final response for a code change must include the changed files, the concepts introduced, the validation performed, what the validation proves, and any remaining limitations.
