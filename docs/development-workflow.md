# Reusable Product Development Workflow

This repository uses a gated, role-based workflow for developing any product described by a supplied product document. The existing The Hub documents are a worked example of the resulting artifacts.

## Guided Teaching Mode

The workflow is developed interactively. The assistant first presents the overall plan, then explains and implements one numbered step, validates that step, and explains the result before proceeding. This prevents a beginner from receiving a large unexplained code dump and makes each architectural choice inspectable.

Every generated code change must be accompanied by beginner-readable explanations for non-obvious purpose, inputs, outputs, control flow, failure behavior, security assumptions, and relevant terminology. The explanation may be a nearby comment or a linked document; comments should explain reasons and behavior rather than restate syntax.

## Order Of Work

1. **Product Manager** extracts users, problems, outcomes, scope, and unresolved product questions into `docs/product-intake.md` when product ambiguity affects delivery.
2. **Tools and Models Architect** defines and compares tools, frameworks, services, model providers, model roles, versions, contracts, and validation targets in `docs/tools-and-models.md`.
3. **Principal Architect** reads the repository and every supplied product document, then creates or updates `docs/technical-specification.md` and `docs/architecture-decisions.md` using the generic templates and the approved tools/models plan.
4. **Senior Architect Reviewer** reviews those documents for completeness, feasibility, security, operability, and unjustified assumptions. The reviewer records findings and approval status.
5. **Scrum Master** converts the approved specification into `docs/implementation-plan.md`, breaking the work into independently verifiable sprints.
6. **Technical Team Lead** selects one sprint at a time, defines the milestone scope, delegates specialist work, integrates results, and requires the milestone review before starting the next sprint.
7. **Specialists** implement only their assigned slice:
   - UI and UX
   - Database and migrations
   - Backend service and APIs
   - Testing and quality engineering
   - Documentation and code explanation
8. **Milestone Reviewer** reviews every specialist contribution at each small milestone and records findings before the lead accepts the work.
9. **Security and Reliability Engineer** performs threat, privacy, operational, and deployment reviews at architecture approval and before release.

Optional user review sessions may be enabled after technical specification generation and after each sprint completion. The user can inspect the artifact, approve it, skip the optional review, or request changes. Requested changes create a new artifact revision and rerun the responsible stage; they do not replace the original history.

## Mandatory Gates

- No implementation dependencies are added until `docs/tools-and-models.md` is approved, unless a documented bootstrap dependency is required for a validation experiment.
- Code must be beginner-readable: document the purpose, inputs, outputs, failure behavior, and security assumptions of every non-obvious line or block near the code or in linked documentation.
- Every sprint has a goal, scope, dependencies, acceptance criteria, test evidence, risks, and rollback or recovery notes.
- Every sprint must run tests applicable to its scope, track failures as owned defects, add regression coverage for fixes, and record retest evidence before acceptance.
- Optional user review does not replace automated tests, milestone review, security review, or mandatory architecture approval.
- Web progress must expose sanitized, auditable run events and support live events, polling, or an explicit spinner mode.
- A sprint is not complete until tests pass, documentation is updated, the milestone review has no unresolved blocking findings, and the technical lead records acceptance.
- Agents must inspect existing files and current behavior before modifying code. They must preserve unrelated user changes.

## Scope Control

The Principal Architect must define the first valuable release and explicitly defer non-essential capabilities. Do not inherit The Hub's MVP boundary for another product; derive scope from the supplied product document, repository evidence, user outcomes, constraints, and delivery risk.

## Agent Invocation

Use the reusable workspace agents in `.github/agents/` by role. `product-delivery-orchestrator` is the normal entry point, and `product-technical-lead` is the normal coordinator after architecture and planning approval. Agents should return artifact paths, decisions, validation commands, findings, and blockers rather than only narrative status.
