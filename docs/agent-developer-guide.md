# Agent Developer Guide

Welcome to the Product Development Workflow! This guide explains how to build, modify, and evaluate LangGraph agents in this repository.

## Adding a New Agent

1. **Define the Agent's Role:** Determine the inputs (from the state) and outputs (what it will write to the state or repository) for the new agent.
2. **Create the Agent Module:** Create a new Python file in `src/app/agents/`. E.g., `my_agent.py`.
3. **Use `create_role_agent`:** Use the helper function `create_role_agent` from `src/app/agents/role_agent.py` to scaffold your agent.
4. **Implement Tools:** Write custom LangChain tools (`@tool`) that the agent can use to perform actions.
5. **Add to the Workflow:** Update `src/app/graph/workflow.py` to include your new agent node and wire up its edges.

## Handling State

- The global state is defined in `src/app/state.py` as `WorkflowState`.
- Avoid modifying fields owned by other agents unless necessary.
- Ensure that any new structured outputs are added to `CHECKPOINTED_TYPES` in `src/app/graph/checkpointing.py` so they are serialized correctly by SQLite.

## Evaluation with LangSmith

We use `langsmith` for evaluating the agents' performance.

To run the evaluations:
1. Ensure your `LANGCHAIN_API_KEY` is set in the environment.
2. Run `python evaluation/evaluate.py`.
3. Review the results on the LangSmith dashboard.

## Deployment

The application is deployed using Docker. The `Dockerfile` at the root uses a multi-stage build:
1. Node.js for building the React frontend.
2. Python for serving the FastAPI backend, which also serves the frontend static assets.
