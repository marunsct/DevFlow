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
