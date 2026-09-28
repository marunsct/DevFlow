"""The architecture review reads a specification, not a finished repository.

It runs before sprint planning and before any specialist writes a line, so the
repository holds the specification and its supporting documents and nothing
else. That is the expected state at this stage.

Measured on one run: the review rejected the specification six times and
ended the run on five findings, every one of them "X is missing" for something
that gets built later:

    [major] Docker containerization missing for backend, database, Redis, Prometheus
    [major] Helm charts missing for all components
    [major] CI workflow (.github/workflows/ci.yml) missing
    [major] Prometheus middleware implementation missing
    [major] PostgreSQL migration scripts for pgcrypto missing

It had run `glob alembic`, found nothing, and treated an empty repository as a
defect in a document. Four of the five also demanded things the brief never
mentions, which is the separate scope problem in `test_scope_discipline.py`.

The prompt already warned against this and even used "no CI/CD pipeline" as its
example - and the reviewer blocked on exactly that. The old wording framed it as
a feasibility test, which let "file missing" be reframed as "specification
incomplete". It now states the stage's position in the pipeline as a fact.
"""

from __future__ import annotations

from app.agents.architecture_reviewer import _SYSTEM_PROMPT


def test_the_reviewer_is_told_nothing_is_built_yet():
    assert "nothing is built yet, and that is by design" in _SYSTEM_PROMPT
    # Wrapped in the prompt source, so compare without line breaks.
    assert "You run before sprint planning" in " ".join(_SYSTEM_PROMPT.split())


def test_the_artifacts_it_kept_blocking_on_are_named():
    """Named explicitly, because the abstract rule was already there and failed."""
    for artifact in ("Dockerfiles", "CI workflows", "Helm charts", "migration scripts"):
        assert artifact in _SYSTEM_PROMPT


def test_the_reviewer_has_a_test_for_its_own_remediation_text():
    """A remediation that creates a file is the tell that the subject is wrong."""
    assert 'begins "Create", "Add" or "Implement" a file' in _SYSTEM_PROMPT
    assert "you are reviewing the wrong artifact" in _SYSTEM_PROMPT


def test_findings_must_point_at_the_specification():
    """The prompt used to invite repository evidence, which is what it acted on."""
    assert "point at something the specification says, or fails to say" in _SYSTEM_PROMPT
    assert "repository evidence for each finding" not in _SYSTEM_PROMPT


def test_not_yet_implemented_is_listed_as_a_non_blocking_condition():
    assert "the implementation has not started" in _SYSTEM_PROMPT


def test_the_observation_is_kept_but_the_run_identifier_is_not():
    """Provenance belongs in the docstring, not in the prompt.

    This asserted the run id was *in* the prompt, for a reader who could check
    whether it still applied - and that reader reads this repository, not a
    system prompt. To the model receiving it, `one run` is a token it can
    neither look up nor act on, and the sentence around it names one run's
    stack, so a rule meant for any stack arrives sounding like a rule about the
    last one. The observation is what carries the rule; the identifier stays in
    this module's own docstring, where the next person to change the rule will
    find it.
    """
    import re

    assert "rejected an 11.7 KB specification six times" in _SYSTEM_PROMPT
    assert "treated an empty repository as a defect in a document" in _SYSTEM_PROMPT
    assert not re.search(r"run-[0-9a-f]{6,}", _SYSTEM_PROMPT)


def test_the_prompt_records_that_the_remediation_restated_the_spec():
    """The sharpest evidence: the finding asked for what the document said.

    One run's specification, Deployment section:

        Kubernetes: Helm charts (helm/charts/backend, helm/charts/database,
        helm/charts/redis, helm/charts/prometheus) with RBAC, secrets, ...

    The review's required remediation for "Helm charts missing":

        Add Helm chart templates under /helm/charts/ with appropriate
        manifests, RBAC, secrets.

    Six revisions could not converge because no edit to a document satisfies a
    demand for files.
    """
    flat = " ".join(_SYSTEM_PROMPT.split())

    assert "restated what the document already said" in flat
    assert "satisfy your own finding by quoting the specification back" in flat
    assert "helm/charts/backend" in flat
