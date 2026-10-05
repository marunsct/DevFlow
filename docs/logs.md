I’ll trace the actual implementation against the product’s promised workflow, safety boundaries, persistence, and benchmark evidence—not just restate the overview. I’ll start with repository guidance and the working tree, then follow the main execution paths and tests before giving prioritized recommendations.

Read 
Completed with input: {
  "path": "/home/arun/Desktop/langchain/.github/skills/Agents.md"
}

Read 
Completed with input: {
  "path": "/home/arun/Desktop/langchain/docs/development-workflow.md"
}
Tool execution failed: Path does not exist

Ran terminal command: git status --short && printf '\nTop-level files:\n' && find . -maxdepth 2 -type f -not -path './.git/*' | sort | sed -n '1,220p'

Find files matching `src/app/{graph,agents,tools,analysis,acceptance,stacks,models,server,observab...`

Find files matching `tests/**/*`

Read 
Completed with input: {
  "path": "/home/arun/Desktop/langchain/pyproject.toml"
}

Read , lines 1 to 200
Completed with input: {
  "path": "/home/arun/Desktop/langchain/docs/architecture-decisions.md",
  "view_range": [
    1,
    200
  ]
}

Read , lines 1 to 240
Completed with input: {
  "path": "/home/arun/Desktop/langchain/benchmarks/README.md",
  "view_range": [
    1,
    240
  ]
}

Find files matching `docs/*`

Ran terminal command: git status --short && git branch --show-current && git log -1 --format='%h %s' && wc -l src/app/graph/*.py src/app/server/{runner,tasks,runs,run_store,workspaces,auth,settings}.py src/app/tools/{sandbox,repository,agent_toolkit}.py src/app/acceptance/*.py src/app/ci.py src/app/observability/*.py

Ran terminal command: find . -maxdepth 2 -type f \( -name 'AGENTS.md' -o -name 'HANDOVER.md' -o -name 'harness-improvement-plan.md' -o -name 'PRODUCT.md' -o -name 'README.md' \) -not -path './.git/*' | sort

Ran terminal command: rg -n '^(class|def|async def) |^    (class|def|async def) |^@.*(router|app)\.' src/app/graph/workflow.py

Ran terminal command: rg -n '^(class|def|async def) |^    (class|def|async def) ' src/app/tools/sandbox.py src/app/tools/repository.py src/app/tools/agent_toolkit.py

Ran terminal command: rg -n '^(class|def|async def) |^    (class|def|async def) |^@.*(router|app)\.' src/app/server/{runner,tasks,runs,run_store,workspaces,auth,settings}.py src/app/graph/{acceptance_nodes,engineering,delivery,escalation,checkpointing}.py

Read , lines 1 to 200
Completed with input: {
  "path": "/home/arun/Desktop/langchain/docs/HANDOVER.md",
  "view_range": [
    1,
    200
  ]
}

Read , lines 1 to 180
Completed with input: {
  "path": "/home/arun/Desktop/langchain/docs/harness-improvement-plan.md",
  "view_range": [
    1,
    180
  ]
}

Read , lines 1 to 200
Completed with input: {
  "path": "/home/arun/Desktop/langchain/docs/redesign-software-company.md",
  "view_range": [
    1,
    200
  ]
}

Search for `^def .*node|^async def .*node|add_node\(|add_edge\(|add_conditional_edges\(|S...`

Search for `^def |^async def |^class |^    def |^    async def `

Search for `^def |^async def |^class |^    def |^    async def `

Search for `^def |^async def |^class |^    def |^    async def `

Search for `^def |^async def |^class |^    def |^    async def `

The repository has a substantial gap between the overview and the live tree’s scale: the main graph, sandbox, and repository tool modules alone total roughly 18,000 lines. I’m narrowing the review around actual control-flow and enforcement points now, and I’ll call out where a recommendation is grounded in implementation versus where it would need run-level proof.

Search for `^\s{0,8}(async )?def `

Read , lines 430 to 770
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/graph/workflow.py",
  "view_range": [
    430,
    770
  ]
}

Read , lines 1 to 260
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/runner.py",
  "view_range": [
    1,
    260
  ]
}

Read , lines 1 to 240
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/agents/role_agent.py",
  "view_range": [
    1,
    240
  ]
}

Read 
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/models/endpoints.py"
}

Read 
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/models/roles.py"
}

Ran terminal command: rg -n '^\s{0,8}(async )?def (build_workflow_graph|_route_from_stage|_entry_router|specialist_dispatch_node|specialist_worker_node|specialist_gather_node|ci_gate_node|milestone_review_node|release_node|product_manager_node|architecture_review_node)' src/app/graph/workflow.py && rg -n '^class |^def ' src/app/tools/sandbox.py | tail -45 && rg -n '^class |^def ' src/app/tools/repository.py | tail -55

Read , lines 1 to 280
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/tools/sandbox.py",
  "view_range": [
    1,
    280
  ]
}

Read , lines 1 to 300
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/acceptance/suite.py",
  "view_range": [
    1,
    300
  ]
}

Read , lines 1 to 320
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/graph/engineering.py",
  "view_range": [
    1,
    320
  ]
}

Read , lines 1 to 280
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/stacks/__init__.py",
  "view_range": [
    1,
    280
  ]
}

Read , lines 1 to 280
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/analysis/work_orders.py",
  "view_range": [
    1,
    280
  ]
}

Read , lines 990 to 1160
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/graph/workflow.py",
  "view_range": [
    990,
    1160
  ]
}

Read , lines 4280 to 4460
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/graph/workflow.py",
  "view_range": [
    4280,
    4460
  ]
}

Read , lines 5180 to 5460
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/graph/workflow.py",
  "view_range": [
    5180,
    5460
  ]
}

Read , lines 5900 to 6100
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/graph/workflow.py",
  "view_range": [
    5900,
    6100
  ]
}

Read , lines 460 to 780
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/runner.py",
  "view_range": [
    460,
    780
  ]
}

Read , lines 240 to 500
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/agents/role_agent.py",
  "view_range": [
    240,
    500
  ]
}

Search for `def validate_command|def allowed_executables|def _allowed|def execute\(|def _...`

Read , lines 2600 to 2760
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/tools/sandbox.py",
  "view_range": [
    2600,
    2760
  ]
}

Read , lines 3890 to 4160
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/tools/sandbox.py",
  "view_range": [
    3890,
    4160
  ]
}

Read , lines 1 to 260
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/agents/security_reviewer.py",
  "view_range": [
    1,
    260
  ]
}

Read , lines 1 to 260
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/auth.py",
  "view_range": [
    1,
    260
  ]
}

Read , lines 1 to 260
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/observability/cost_tracker.py",
  "view_range": [
    1,
    260
  ]
}

Ran terminal command: rg -n 'def (validate_command|allowed_executables|_run\(|execute\(|_execute_here)|CONTAINER_MODE|NETWORK_CATEGORIES|SANDBOX_EXECUTION_MODE|ALLOW_COMMAND_EXECUTION' src/app/tools/sandbox.py && rg -n 'async def (start_run|resume_run|cancel_run|_dispatch|_run_loop|_handle_state|_finish_cancelled)|def (_persist|_update_record)' src/app/server/runner.py && rg -n 'SANDBOX_EXECUTION_MODE|ALLOW_COMMAND_EXECUTION|OBJECT_STORE_BUCKET|WEB_CONCURRENCY|CELERY_CONCURRENCY' docker-compose*.yml Dockerfile

Read , lines 1 to 300
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/graph/acceptance_nodes.py",
  "view_range": [
    1,
    300
  ]
}

Read , lines 1 to 280
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/graph/delivery.py",
  "view_range": [
    1,
    280
  ]
}

Read , lines 1 to 260
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/stacks/release.py",
  "view_range": [
    1,
    260
  ]
}

Read , lines 260 to 550
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/analysis/work_orders.py",
  "view_range": [
    260,
    550
  ]
}

Search for `security_review|security reviewer|SOURCE_BUDGET|unreviewed|retention|transcri...`

Read , lines 20 to 92
Completed with input: {
  "path": "/home/arun/Desktop/langchain/docker-compose.yml",
  "view_range": [
    20,
    92
  ]
}

Read , lines 185 to 226
Completed with input: {
  "path": "/home/arun/Desktop/langchain/docker-compose.yml",
  "view_range": [
    185,
    226
  ]
}

Read , lines 1690 to 1805
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/tools/sandbox.py",
  "view_range": [
    1690,
    1805
  ]
}

Read , lines 4300 to 4445
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/tools/sandbox.py",
  "view_range": [
    4300,
    4445
  ]
}

Read , lines 65 to 115
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/runner.py",
  "view_range": [
    65,
    115
  ]
}

Read , lines 250 to 420
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/observability/cost_tracker.py",
  "view_range": [
    250,
    420
  ]
}

Ran terminal command: rg -n 'execution_enabled\(|ALLOW_COMMAND_EXECUTION|run_terminal_command|sandbox.*enabled|_require_a_reachable_model|budget_exceeded|run_cost\(' src/app docker-compose.yml docs tests | head -200

Read , lines 72 to 106
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/runner.py",
  "view_range": [
    72,
    106
  ]
}

Read , lines 830 to 1010
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/runner.py",
  "view_range": [
    830,
    1010
  ]
}

Read , lines 1040 to 1235
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/runner.py",
  "view_range": [
    1040,
    1235
  ]
}

Read , lines 1598 to 1644
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/runner.py",
  "view_range": [
    1598,
    1644
  ]
}

Read , lines 1 to 180
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/observability/transcript.py",
  "view_range": [
    1,
    180
  ]
}

Read , lines 1 to 250
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/runs.py",
  "view_range": [
    1,
    250
  ]
}

Search for `_require_run\(|DELETE|delete_run|transcript|forget_run|delete_object|workspace`

Ran terminal command: rg -n '_budget_exceeded|def _require_a_reachable_model|def _the_model_for_this_attempt|SOURCE_BUDGET|def delete_run|def pack_for|def pack_named|def select_pack|def _selected_pack' src/app/server/runner.py src/app/server/runs.py src/app/agents/security_reviewer.py src/app/stacks/__init__.py src/app/graph/workflow.py

Read , lines 330 to 455
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/runs.py",
  "view_range": [
    330,
    455
  ]
}

Read , lines 520 to 690
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/runs.py",
  "view_range": [
    520,
    690
  ]
}

Read , lines 175 to 330
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/graph/acceptance_nodes.py",
  "view_range": [
    175,
    330
  ]
}

Read , lines 250 to 480
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/acceptance/suite.py",
  "view_range": [
    250,
    480
  ]
}

Read , lines 1 to 240
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/tasks.py",
  "view_range": [
    1,
    240
  ]
}

Read , lines 1 to 240
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/events.py",
  "view_range": [
    1,
    240
  ]
}

Read , lines 270 to 305
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/runner.py",
  "view_range": [
    270,
    305
  ]
}

Read , lines 785 to 835
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/runner.py",
  "view_range": [
    785,
    835
  ]
}

Read , lines 42 to 90
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/models/roles.py",
  "view_range": [
    42,
    90
  ]
}

Read , lines 300 to 395
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/stacks/__init__.py",
  "view_range": [
    300,
    395
  ]
}

Read , lines 180 to 280
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/graph/delivery.py",
  "view_range": [
    180,
    280
  ]
}

Ran terminal command: rg -n 'SOURCE_BUDGET|def _the_source_under_review|def execution_enabled|def execution_mode|def _budget_exceeded|def _require_a_reachable_model|async def start_run|async def delete_run|def release\(|def write\(|def build_workflow_graph|def pack_named|def pack_for|def select|def gaps\(|def declared_tests|MAX_RUN_COST_USD|ALLOW_COMMAND_EXECUTION|SANDBOX_EXECUTION_MODE' src/app/agents/security_reviewer.py src/app/tools/sandbox.py src/app/server/runner.py src/app/server/runs.py src/app/graph/delivery.py src/app/stacks/__init__.py src/app/acceptance/suite.py docker-compose.yml

Ran terminal command: find langchain-ui/src -maxdepth 3 -type f | sort | sed -n '1,180p'

Ran terminal command: rg -n '^def _.*\(|^class |^async def ' src/app/server/agent_stream.py src/app/server/object_store.py src/app/server/runtime_settings.py src/app/plugins/{seed.py,middleware.py,registry.py} src/app/observability/transcript.py src/app/analysis/language_service.py

Search for `TODO|FIXME|NotImplementedError|pass\s*(#.*)?$`

Ran terminal command: find src/app -type f -name '*.py' -not -path '*/__pycache__/*' -print0 | xargs -0 wc -l | tail -1 && find langchain-ui/src -type f \( -name '*.ts' -o -name '*.tsx' \) -print0 | xargs -0 wc -l | tail -1 && find tests -maxdepth 1 -type f -name 'test_*.py' | wc -l

Read , lines 1 to 250
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/object_store.py",
  "view_range": [
    1,
    250
  ]
}

Read , lines 1 to 260
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/runtime_settings.py",
  "view_range": [
    1,
    260
  ]
}

The code confirms several useful design strengths—most importantly, the sandbox is argv-based and defaults to per-command containers in Compose, and acceptance failures are measured by the harness rather than accepted from an agent’s summary. I’ve also found a few mismatches between what the product promises and what the current runtime/configuration guarantees; I’m checking their exact boundaries before prioritizing them.

Search for `^def write\(|except Exception|def delete\(|def archive_file|def delete_run|de...`

Search for `def delete\(|def archive_file|delete_object|object_store\(\)\.delete|\.delete...`

Read , lines 235 to 330
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/runs.py",
  "view_range": [
    235,
    330
  ]
}

Read , lines 290 to 420
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/server/object_store.py",
  "view_range": [
    290,
    420
  ]
}

Read , lines 78 to 158
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/agents/security_reviewer.py",
  "view_range": [
    78,
    158
  ]
}

Read , lines 95 to 160
Completed with input: {
  "path": "/home/arun/Desktop/langchain/src/app/stacks/release.py",
  "view_range": [
    95,
    160
  ]
}

Ran terminal command: rg -n '^def (transcripts_enabled|record|_the_source_under_review|build_judgement_model|_budget_exceeded|execution_enabled|choose_pack|gaps|write)\b|^    async def delete_run\b|^def release\b|^def build_workflow_graph\b|^    def _run\b|^    def _require_a_reachable_model\b|^    async def start_run\b' src/app/observability/transcript.py src/app/agents/security_reviewer.py src/app/models/roles.py src/app/server/runner.py src/app/tools/sandbox.py src/app/stacks/__init__.py src/app/acceptance/suite.py src/app/server/runs.py src/app/graph/delivery.py src/app/stacks/release.py src/app/graph/workflow.py

Ran terminal command: wc -l langchain-ui/src/pages/{RunDashboard,Settings,Home}.tsx langchain-ui/src/api/index.ts langchain-ui/src/components/{ApprovalGate,ReviewPanel,DeliveryPanel,ExecutionFlow}.tsx

Read , lines 1 to 260
Completed with input: {
  "path": "/home/arun/Desktop/langchain/langchain-ui/src/api/index.ts",
  "view_range": [
    1,
    260
  ]
}

Read , lines 1 to 300
Completed with input: {
  "path": "/home/arun/Desktop/langchain/langchain-ui/src/pages/RunDashboard.tsx",
  "view_range": [
    1,
    300
  ]
}

Read , lines 1 to 250
Completed with input: {
  "path": "/home/arun/Desktop/langchain/langchain-ui/src/components/ApprovalGate.tsx",
  "view_range": [
    1,
    250
  ]
}

Read , lines 1 to 270
Completed with input: {
  "path": "/home/arun/Desktop/langchain/langchain-ui/src/components/ReviewPanel.tsx",
  "view_range": [
    1,
    270
  ]
}

Read , lines 1 to 230
Completed with input: {
  "path": "/home/arun/Desktop/langchain/langchain-ui/src/pages/Settings.tsx",
  "view_range": [
    1,
    230
  ]
}

## My assessment

I traced the main path from starting a run through the API, runner, LangGraph workflow, agent tools, acceptance checks, reviews, release, and persisted run data. I also checked the benchmark and test setup and sampled the UI paths for approvals and run status.

One caveat: the checkout is at `d689ea6`, while the attached overview says it describes code around `467872b`. I treated the current code as authoritative. The repository is large—about 71,700 Python lines, 6,600 frontend lines, and 484 test files—so this is a code-grounded systems review, not a claim that I inspected every line and fixture. I did not run the test suite or a benchmark.

**Overall:** the harness shows unusually strong attention to guardrails, recovery, and evidence. The main opportunity is to make the product’s promises match the runtime’s actual guarantees. I would focus next on reliable, measurable delivery—not adding more agents or heuristics.

## Highest-priority improvements

### 1. Fail early when a run cannot build and test

The default Compose configuration sets `ALLOW_COMMAND_EXECUTION` to `false` and selects container execution. The sandbox then returns an error for every command, while container execution also needs a working runtime/socket configuration. But run startup checks model reachability, not whether commands can actually run. So a deployment can accept a run that cannot scaffold, install, or verify a product. See `docker-compose.yml`, `execution_enabled`, `SandboxExecutor._run`, and `WorkflowRunner.start_run`.

Keep execution opt-in if that is the safety policy, but add a **run-readiness check** before consuming model calls: report whether command execution is enabled, whether the selected sandbox is available, and whether its required runtime is reachable. If execution is intentionally disabled, label the mode clearly as planning-only rather than implying it will deliver a tested product. Don’t solve this simply by turning execution on everywhere: Compose notes that access to the Docker socket is effectively root-level access to the host.

There is also a documentation mismatch to resolve: the overview describes in-container execution as the deployed default, while Compose defaults to container execution.

### 2. Make “definition of done” independent enough to trust

The locked acceptance suite is a real strength: the harness runs it, restores changes to it, reads test results, and compares batches against prior results. That is substantially better than accepting an agent’s claim that its own work passed. See `suite locking and execution` and `CI regression checks`.

The remaining weakness is that mechanical criterion coverage is based partly on test names carrying IDs such as `AC-3`; that confirms a label exists, not that the test would fail when the requested behavior is absent. The QA review helps, but it is still model judgment. See `gaps` and `acceptance review`.

I’d add **independent checks of test strength**: run controlled mutations against the product and confirm the acceptance suite catches them; add external, human-authored benchmark tests that the run never sees; and measure false acceptance, not just pass rate. The benchmark gate is the right foundation, but the current five briefs and 8–10 hidden tests per brief are an early signal, not yet broad evidence for a general-purpose harness. The overview reports 0/2 clean runs at its first stage; I did not verify the live benchmark state.

### 3. State the supported product boundary precisely

The design is extensible through stack packs, but the code also has an explicit “no matching pack” path: the agents must set up and test the product themselves. `choose_pack` can return `None`; the documented packs cover a bounded set of product kinds and language combinations. See `choose_pack` and `the pack definitions`.

That’s a sensible architecture, but it doesn’t yet substantiate “any product in any language.” Describe support in capability tiers, for example:

- **Pack-supported:** known scaffold, commands, and test runner.
- **Custom stack:** no scaffold; agents supply the setup and test contract.
- **Unsupported or unverified:** do not claim a tested handoff.

Then expand support by adding and validating packs, rather than by growing generic checks that appear to work across stacks but have only been measured on a few. The benchmark matrix should grow alongside those claims.

### 4. Don’t present partial pricing as a hard spending cap

The tracker correctly identifies calls it cannot price instead of inventing a dollar amount. However, `_budget_exceeded` compares only the known dollar total; unpriced calls don’t count toward `MAX_RUN_COST_USD`. See `_budget_exceeded` and `cost accounting`.

That is honest accounting, but it means the setting is **not a guaranteed cap** when using a paid model with missing pricing or missing usage data. Show that limitation in the UI and run record. If the operator requires a hard limit, either refuse to start without complete pricing or enforce an independent bound, such as maximum tokens or model calls, and clearly label it as a different kind of limit.

### 5. Make deletion and retention cover the data the harness actually stores

The transcript system is enabled by default and records model requests, responses, tool calls, and tool results; those can contain customer briefs and source code. See `transcripts_enabled` and `record`.

The run-delete endpoint removes local uploads, the workspace, checkpoints, and event history, but it does not appear to purge the transcript or the durable object-store copy of an upload. See `delete_run`, `object storage`, and `transcript storage`.

Define retention and deletion as a product contract: what “delete run” removes, what is retained for auditing, for how long, and whether an admin can override it. Make durable copies and transcripts part of that contract, with an explicit retention/hold option if they must be kept. This matters especially if the intended users will put proprietary code into runs.

### 6. Make reviewer confidence and release completeness visible

Two cases can make the workflow look more authoritative than its evidence:

- A configured judgement model that fails to build falls back to the default model. If it was explicitly configured to provide stronger review, the run should visibly record that downgrade or stop, rather than relying on a log message. See `build_judgement_model`. Also, the overview says the current deployment has no separate judgement model, so those review stages are not independent model reviews in that configuration.
- The security reviewer’s source input is capped at 24,000 characters; files beyond that limit can be omitted. Its output does not appear to require a completeness report. See `_the_source_under_review`. Record which files were reviewed and skipped, and don’t label an incomplete review as fully passed.
- Release packaging is best-effort: the release writer catches errors and returns, while the graph proceeds through release. An unsupported stack can also produce no pack-generated files. See `write` and `release`. If CI and deployment files are part of the promised handoff, make their presence a release condition—or explicitly report that the run completed without them.

## What I would *not* do next

I would avoid a broad rewrite before the benchmark gate is working. The core graph builder is nearly 7,000 lines, and the repository and sandbox tools are also very large; that creates a real maintenance burden. See `workflow graph construction`, `repository tools`, and `sandbox execution`.

But the code already has meaningful modular boundaries for acceptance, engineering, delivery, and escalation. Keep those boundaries, establish clean benchmark runs, and then extract further workflow stages behind typed contracts. That gives you a safer refactor target than changing orchestration while run-level behavior is still being established.

## Bottom line

The strongest part of DevFlow is its insistence on **observable work and test evidence**: locked acceptance tests, regression checks, bounded tool execution, checkpoints, and recorded decisions are all aligned with the product description. The main risks are **run readiness, strength of independent evaluation, and overclaiming support or guarantees**.

My recommended order is: **add execution preflight; strengthen and broaden the benchmark gate; make spend and data-retention semantics explicit; then improve reviewer and release completeness reporting.** The overview should also be updated to match the current checkout and clarify which stack configurations are genuinely scaffolded and tested.