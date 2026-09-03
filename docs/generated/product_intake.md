# Product Intake Artifact

## Product Name
**The Hub – Asynchronous Collaboration Workspace with AI Decision Threads**

## Users & Stakeholders
- Engineering and consulting teams (distributed, remote) that need durable architectural decision records.
- Internal platform teams managing product roadmaps and technical debt.
- Project managers / product owners who create/approve decisions.
- External stakeholders or clients who may view prototype previews via secure tunnels.
- Compliance / audit personnel requiring traceable approval workflows.

## Problems & Desired Outcomes
| Problem | Pain Point | Desired Outcome |
|---------|-------------|-----------------|
| Meeting overload & chat fatigue | Teams spend excessive time in synchronous meetings and scrolling through chat logs. | Reduce live meeting load by shifting to asynchronous video updates that capture intent and decisions. |
| Lack of searchable, durable decision records | Decisions made in chats or one‑off videos are hard to trace for future audits or onboarding. | Create structured Decision Threads with AI‑generated transcripts, summaries, action items, and approval states that serve as ADR‑style records. |
| Fragmented prototype feedback | Prototypes often live behind firewalls and cannot be easily reviewed by external stakeholders. | Embed secure iframe previews via Tailscale/Funnel tunnels within the thread for real‑time review. |
| Limited integration with existing tooling | Teams rely on Jira, GitHub, Slack, calendars; no single place to capture decisions. | First‑class integrations that auto‑create tasks, sync statuses, and trigger webhooks on state changes. |

## Core Workflows
1. **Create Thread** – User records a short screen+camera video, optionally tags risk, related tickets, etc.
2. **AI Processing Pipeline** – Video is queued → transcription (Whisper) → summarization & action extraction (LLM). 
3. **Review & Sign‑Off** – Reviewers view transcript, edit summary/action items, and approve; status transitions DRAFT→PROCESSING→OPEN→RESOLVED.
4. **Prototype Preview** – If a tunnel URL is attached, an iframe preview is rendered within the thread for reviewers.
5. **Export / ADR Generation** – On RESOLVED, system auto‑generates a markdown/Confluence ADR document.
6. **Search & Knowledge Graph** – Users query threads by text or semantic similarity; graph links decisions to projects/Jira issues.

## MVP Candidates (Phase 1)
- Workspace and thread CRUD with role‑based permissions.
- Video recording, upload via pre‑signed MinIO URL.
- Background queue for transcription (Whisper) and summarization (LLM).
- Structured summary panel; action items extraction.
- Review & approval workflow with status machine.
- Secure iframe preview integration using Tailscale/Funnel.
- Basic export of ADR markdown.

## Deferred Scope
- Full‑text / semantic search service.
- Advanced knowledge graph linking.
- Integrations with Jira, GitHub, Slack, calendars.
- Analytics dashboards (adoption metrics).
- Enterprise features: SSO/SAML, SCIM, audit logs, retention policies.
- Localization & multi‑language support.
- Webhooks / automation engine.

## Constraints
- Must run on the existing Next.js + NestJS stack with PostgreSQL/Prisma and MinIO.
- AI worker must be decoupled; can use local or external LLM APIs.
- Secure preview requires Tailscale/Funnel or similar tunnel provider.
- Data isolation per organization (multi‑tenant). 

## Evidence vs Assumptions
| Item | Evidence | Assumption |
|------|----------|------------|
| Decision Threads as core unit | Document specifies ThreadStatus states and approval flow. | That the target market values formal ADR‑style records over informal notes. |
| Need for secure prototype previews | Text cites “sandboxed iFrame previews for live apps”. | External stakeholders will need to view prototypes behind firewalls. |
| AI transcription & summarization sufficiency | Architecture uses Whisper and frontier LLMs; queues are defined. | Users accept the accuracy of these models for decision capture. |

## Success Measures
- % of meetings replaced by async threads.
- Time saved per team (hours/month).
- Adoption rate: number of threads created per active user.
- Approval latency: average time from thread creation to RESOLVED.
- Audit compliance: ability to retrieve decision record within X days.
- Customer NPS / renewal for B2B SaaS.

## Open Product Questions
1. What is the minimum viable set of roles (Admin, Contributor, Reviewer) required by target customers? 
2. Which tunnel provider(s) will be supported out‑of‑the‑box? 
3. How granular should the approval policy be (e.g., role‑based vs custom approver lists)? 
4. What level of AI confidence threshold triggers manual review versus auto‑acceptance?
5. Should we ship integrations with Jira/GitHub as paid add‑ons or free core features? 
6. How will we handle multi‑language transcription and summarization in the MVP? 

---
