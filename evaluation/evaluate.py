import asyncio
import os
from langsmith import Client
from langsmith.evaluation import evaluate, LangChainStringEvaluator

from app.graph.workflow import build_workflow_graph
from app.documents import DocumentContent

# A minimal example demonstrating how to evaluate the LangGraph workflow using LangSmith

client = Client()

# Example dataset
dataset_name = "Product Workflow Test Dataset"
dataset_description = "A dataset for testing the agentic product-development workflow."

def create_dataset():
    if not client.has_dataset(dataset_name=dataset_name):
        dataset = client.create_dataset(
            dataset_name=dataset_name,
            description=dataset_description,
        )
        
        client.create_example(
            inputs={"content": "We need a secure REST API for a user management system.", "name": "user_api_spec.md"},
            outputs={"expected_technology": "FastAPI", "expected_security": "OAuth2"},
            dataset_id=dataset.id,
        )
        print(f"Dataset '{dataset_name}' created.")
    else:
        print(f"Dataset '{dataset_name}' already exists.")

# Target function for the evaluator
def run_workflow(inputs: dict) -> dict:
    """Wrapper around our workflow graph to adapt it for evaluation."""
    graph = build_workflow_graph(model="gpt-4o-mini", repo_root=".")
    
    document = DocumentContent(
        content=inputs["content"],
        metadata={"filename": inputs["name"]}
    )
    
    # We use a dummy thread_id and invoke synchronously for the test
    # (Since our checkpointer allows synchronous invoke or we bypass the saver)
    state = graph.invoke(
        {
            "product_intake": document,
            "stage": "product_intake",
            "thread_id": "eval-test-thread",
        }
    )
    
    tech_choice = state.get("tools_and_models")
    security = state.get("security_review")
    
    return {
        "technology": tech_choice.selected_technologies[0].name if tech_choice and tech_choice.selected_technologies else "None",
        "security": security.findings[0].description if security and security.findings else "None",
    }

def main():
    create_dataset()
    
    # We evaluate using basic string matchers or LLM-as-a-judge
    qa_evaluator = LangChainStringEvaluator("qa")
    
    print("Running evaluation...")
    experiment_results = evaluate(
        run_workflow,
        data=dataset_name,
        evaluators=[qa_evaluator],
        experiment_prefix="product-workflow-eval",
        # To avoid blocking on human approval in testing, the workflow should either
        # be invoked with human-in-the-loop disabled or we just test the initial phases.
    )
    print("Evaluation complete!")
    print(experiment_results)

if __name__ == "__main__":
    if "LANGCHAIN_API_KEY" not in os.environ:
        print("Please set LANGCHAIN_API_KEY to run the evaluation.")
    else:
        main()
