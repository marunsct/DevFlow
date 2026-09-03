# <Product Name> Tools And Models Plan

**Status:** Draft | Under Review | Approved  
**Source documents:** <paths or links>  
**Date:** YYYY-MM-DD

## 1. Decision Scope

Define the tools, frameworks, model providers, model roles, data stores, development tools, and operational services needed for the approved product scope.

## 2. Requirements Mapped To Choices

| Requirement or workflow | Tool/model choice | Why it is needed | Evidence | Validation |
|---|---|---|---|---|
|  |  |  |  |  |

## 3. Tool Inventory

| Area | Selected tool | Version or compatibility range | Alternatives considered | Selection rationale | Exit or replacement criteria |
|---|---|---|---|---|---|
| UI |  |  |  |  |  |
| API/service |  |  |  |  |  |
| Database |  |  |  |  |  |
| Storage |  |  |  |  |  |
| Messaging/jobs |  |  |  |  |  |
| Authentication |  |  |  |  |  |
| Observability |  |  |  |  |  |
| Testing |  |  |  |  |  |
| Deployment |  |  |  |  |  |

## 4. Model Inventory

| Model role | Selected provider/model | Local or hosted | Inputs and outputs | Quality target | Cost/latency target | Fallback | Data/privacy constraints |
|---|---|---|---|---|---|---|---|
| Primary generation |  |  |  |  |  |  |  |
| Embeddings |  |  |  |  |  |  |  |
| Classification/extraction |  |  |  |  |  |  |  |
| Speech/vision |  |  |  |  |  |  |  |
| Evaluation/judge |  |  |  |  |  |  |  |

## 5. Tool And Model Contracts

For each model or external tool, define the versioned request/response contract, timeout, retry policy, rate limit, error behavior, authentication method, logging policy, and health check.

## 6. Decision Records

For each material choice, add an ADR with context, alternatives, decision, detailed rationale, consequences, security/privacy impact, operational impact, and validation evidence in `docs/architecture-decisions.md`.

## 7. Approval Gate

- [ ] Every MVP requirement maps to a tool or model choice.
- [ ] Versions and compatibility ranges are recorded.
- [ ] Alternatives and replacement criteria are recorded.
- [ ] Local versus hosted data handling is explicit.
- [ ] Quality, latency, cost, timeout, and fallback targets are testable.
- [ ] Security, privacy, licensing, and operational risks are reviewed.
- [ ] The plan is approved before implementation dependencies are added.
