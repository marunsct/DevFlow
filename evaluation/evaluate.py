"""Run LangSmith evaluation against the product-development workflow.

Usage:
    LANGCHAIN_API_KEY=... python evaluation/evaluate.py

This script:
1. Creates a LangSmith dataset from the examples in ``app.evaluation.datasets``
   (idempotent — skips if the dataset already exists).
2. Runs each example through the workflow's intake and tools/models stages.
3. Scores the outputs with the heuristic evaluators from
   ``app.evaluation.evaluators``.

The evaluation is designed to test early-stage quality (intake, architecture)
without requiring the full specialist/sprint loop, keeping cost and runtime
manageable.
"""

import os
import sys

from langsmith import Client
from langsmith.evaluation import evaluate

from app.evaluation.datasets import DATASETS
from app.evaluation.evaluators import (
    evaluate_architecture_completeness,
    evaluate_assumption_labeling,
    evaluate_explanation_quality,
    evaluate_requirement_coverage,
    evaluate_review_accuracy,
    evaluate_tool_model_decision_quality,
    evaluate_tool_use_safety,
)
from app.graph.workflow import build_workflow_graph
from app.documents import DocumentContent

client = Client()

DATASET_NAME = "Product Workflow Test Dataset"
DATASET_DESCRIPTION = "Heuristic evaluation dataset for the agentic product-development workflow."


def create_dataset() -> None:
    """Create or update the LangSmith dataset from the in-repo examples."""
    if client.has_dataset(dataset_name=DATASET_NAME):
        print(f"Dataset '{DATASET_NAME}' already exists — skipping creation.")
        return

    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description=DATASET_DESCRIPTION,
    )

    for name, example in DATASETS.items():
        client.create_example(
            inputs={"content": example["input"], "name": f"{name}.md"},
            outputs=example.get("expected", {}),
            metadata=example.get("metadata", {}),
            dataset_id=dataset.id,
        )

    print(f"Dataset '{DATASET_NAME}' created with {len(DATASETS)} examples.")


def run_workflow(inputs: dict) -> dict:
    """Target function: run the workflow intake stage and return structured output.

    Only runs through product_manager and tools_models to keep evaluation
    fast and cheap.  The evaluators are designed around these stages.
    """
    graph = build_workflow_graph(repo_root=".")

    document = DocumentContent(
        content=inputs["content"],
        metadata={"filename": inputs.get("name", "eval_input.md")},
    )

    from app.state import RepositoryContext
    from app.tools.repository import build_repository_context

    repository = build_repository_context(".")

    from app.graph.workflow import start_workflow

    state = start_workflow(
        graph,
        document,
        repository,
        thread_id=f"eval-{inputs.get('name', 'unknown')}",
    )

    # Collect outputs from whichever stages completed before the run paused.
    result: dict = {}

    intake = state.get("product_intake")
    if intake is not None:
        result["intake"] = intake.model_dump_json(indent=2) if hasattr(intake, "model_dump_json") else str(intake)

    tools = state.get("tools_and_models")
    if tools is not None:
        result["tools_models"] = tools.model_dump_json(indent=2) if hasattr(tools, "model_dump_json") else str(tools)

    spec = state.get("technical_specification")
    if spec is not None:
        result["specification"] = spec.model_dump_json(indent=2) if hasattr(spec, "model_dump_json") else str(spec)

    review = state.get("architecture_review")
    if review is not None:
        result["review"] = review.model_dump_json(indent=2) if hasattr(review, "model_dump_json") else str(review)

    result["stage"] = state.get("stage", "unknown")
    return result


# Adapter functions for LangSmith's evaluator interface.
# LangSmith passes (run, example) but our evaluators expect (output, expected).

def _adapt(evaluator_fn):
    """Wrap a (run_output, expected) evaluator for LangSmith's (run, example) interface."""
    def wrapper(run, example):
        outputs = run.outputs or {}
        expected = example.outputs or {}
        # Combine all output fields into one text blob for heuristic evaluation.
        combined_output = "\n".join(str(v) for v in outputs.values())
        return evaluator_fn(combined_output, expected)
    return wrapper


def main() -> None:
    create_dataset()

    evaluators = [
        _adapt(evaluate_requirement_coverage),
        _adapt(evaluate_assumption_labeling),
        _adapt(evaluate_tool_model_decision_quality),
        _adapt(evaluate_architecture_completeness),
        _adapt(evaluate_review_accuracy),
        _adapt(evaluate_explanation_quality),
        _adapt(evaluate_tool_use_safety),
    ]

    print("Running evaluation...")
    experiment_results = evaluate(
        run_workflow,
        data=DATASET_NAME,
        evaluators=evaluators,
        experiment_prefix="product-workflow-eval",
    )
    print("Evaluation complete!")
    print(experiment_results)


if __name__ == "__main__":
    if "LANGCHAIN_API_KEY" not in os.environ:
        print("Please set LANGCHAIN_API_KEY to run the evaluation.", file=sys.stderr)
        sys.exit(1)
    main()
