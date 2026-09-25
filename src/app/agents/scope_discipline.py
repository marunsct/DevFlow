"""One rule, shared by the stages that can inflate a project's scope.

Scope inflation in this pipeline is not one agent's mistake. It compounds
down the chain, and each step is locally reasonable:

 The stack selector added "Celery with Redis" and "Prometheus + Grafana",
   justified by "future features like notifications" and observability.
2. The architect, given that stack, wrote ADRs for Helm deployment artefacts,
   Prometheus middleware and pgcrypto encryption at rest.
3. The architecture reviewer then raised three **blocking** findings because
   the Helm charts, the Prometheus `/metrics` middleware and the pgcrypto
   migrations were missing - none of which the brief ever asked for.

By step 3 the project cannot proceed until it ships Kubernetes deployment
artefacts for a task dashboard. The same shape killed the previous run, where
a stack with two test frameworks consumed a whole sprint and all of its
remediation attempts without the application being started.

No single stage was unreasonable given its input, which is why the rule has to
be stated at every one of them rather than at the one that started it.
"""

from __future__ import annotations

SCOPE_DISCIPLINE = """
Scope discipline - the brief is the boundary:
- The product intake is the whole of what this product must do. Something it
  does not ask for is not a requirement, however standard the practice is.
- You may recommend work beyond it. Record that as a suggestion, or as
  future work in the specification - never as a blocking or major finding, and
  never as a delegated task. A stage cannot be held up for omitting something
  nobody asked for.
- Judge what is here against what was asked for. "This is missing" is only a
  defect when the intake asked for it; otherwise it is an idea, and ideas do
  not block.
- Observed on  The brief mentions none of
  those words. Each step that got there was reasonable given the step before
  it, and the result was a task dashboard that could not proceed without
  Kubernetes deployment artefacts.

- Evidence that cannot exist here is not a missing deliverable. There is no
  browser, no database server and no container runtime, so "no screenshot",
  "migrations were not applied" and "the image was not built" describe this
  environment, not a fault in the work. Ask for what can be produced - the
  file, the migration, the test that runs - and never block a sprint for the
  absence of the rest.""".strip()


__all__ = ["SCOPE_DISCIPLINE"]
