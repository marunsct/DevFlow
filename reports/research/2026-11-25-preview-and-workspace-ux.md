# Preview and workspace UX: full-screen preview, a VS Code-style workspace, co-development

Date: 2026-11-25 (written 10:00 JST). Kind: research and design. Status: proposal, nothing built.

Owner's request: "currently the ux of the preview and workspace is not so good it doesnt help actually test the
product as the screen space is limited, i want to provide a full screen preview as well as vscode style worspace view
with option for editing the files in co development mode (co development mode for brownfield approach)."

## Summary

1. The owner is right. The preview and the workspace live in the middle column of a three-column page, so on a
   1920 px screen the product gets about 970 px and the code about 740 px; on a 1366 px laptop the code gets about 340 px.
2. Space is half the problem. The preview also cannot hold state: on the app's own host the page runs with an opaque
   origin, so browser storage and cookies do not work, and there is no WebSocket, no reload and no address bar.
   A product that signs in or stores anything in the browser cannot be tested in it today.
3. Recommended: own-window routes for the preview and the workspace (no page chrome), a preview toolbar (reload,
   path, device sizes), a Monaco-based workspace (tree, tabs, search, diff, split with the preview), and
   co-development by **turn-taking**: the person edits only while the run is paused or waiting at a gate, through a
   guarded save API, and hands back with a commit plus a note to the next stage.
4. The plan's rejection of "a full editable IDE beside agents" was right about simultaneous editing and about
   code-server's defaults, and too narrow in its remedy: take-over does not need code-server. Monaco plus our own save
   route gives editing with every existing guard kept, and no terminal.
5. 16 items, UX.1-UX.16, in four phases. Phases 1-2 are UI-only and always on; phase 3 sits behind the existing
   `PRODUCT_PREVIEW`; phase 4 behind a new `CO_DEVELOPMENT` switch, off until measured.

## 1. What exists and where it falls short

### 1.1 Screen space

| Fact | Where |
|---|---|
| Preview and workspace are two of eight tabs in the centre column | `langchain-ui/src/pages/RunDashboard.tsx:173`, `:1069-1079` |
| The centre column sits between two rails of 19+23 rem (xl), 22+28 rem (2xl), 26+34 rem (2200 px and up) | `RunDashboard.tsx:1012` |
| Below 1280 px the centre panel is a fixed 26-32 rem high | `RunDashboard.tsx:1026` |
| The page shell always shows the header, the padding and the footer | `langchain-ui/src/components/Layout.tsx:99-109` |
| The run's title, controls and stage strip sit above the grid and take height from it | `RunDashboard.tsx:666-1010` |
| The workspace gives 16 rem of its column to the tree, fixed, not resizable | `langchain-ui/src/components/WorkspacePanel.tsx:173` |
| The preview's own controls (start/stop, status, Page/Requests, pointing) take three rows above the frame; the frame's floor is 28 rem | `langchain-ui/src/components/PreviewPanel.tsx:168-220`, `:229` |

Computed widths (rails, gaps and padding subtracted; approximate):

| Window | Centre column | Preview frame | Code beside the tree |
|---|---|---|---|
| 1920 x 1080 | ~1000 px | ~970 px | ~740 px |
| 1366 x 768 | ~600 px | ~570 px | ~340 px |

There is no maximise, no own-window view, no way to hide a rail, and no resizable split anywhere on the page.

### 1.2 Preview (WS.4, `PRODUCT_PREVIEW`, off)

| Shortfall | Where | Effect on testing a product |
|---|---|---|
| No reload, back, path bar, open-in-own-window or device sizes | `PreviewPanel.tsx:166-242` (whole render) | A person cannot re-enter a route, retry, or see a phone layout |
| Opaque origin on the app's own host (frame sandbox and CSP `sandbox` without `allow-same-origin`) | `PreviewPanel.tsx:24`, `:227`; `src/app/server/preview.py:514-522` | Browser storage throws; a product that stores anything in the browser fails in the preview though it works when delivered |
| Cookies dropped both ways | `docs/PRODUCT.md:1114`; `preview.py` `FORWARDED_*_HEADERS` (`:439-447`) | Sign-in and sessions cannot be tested |
| Only HTTP methods are proxied; the answer is read whole before it is sent (20 MB cap) | `src/app/server/runs.py:1249-1253`, `:1281-1290` | No WebSocket, no server-sent events, no streaming, so no hot reload and no live features |
| The product runs from a scratch copy taken at start | `src/app/server/preview_worker.py:95-103`, `:120-131` | "The workspace as it is being built" is a snapshot; it never follows the build; the person must stop and start |
| URLs built at run time are not rewritten | `docs/PRODUCT.md:1114` | A product that builds absolute paths in script breaks under the path prefix |
| Off, awaiting a supervised trial | `docs/STATE.md:102-103`; `docs/improvement-plan.md:58` | None of this is reachable by a person yet |

What is good and is kept: the signed, expiring link in the path, the internal preview network, the secret-free
container, the request console for a service without a page (`PreviewPanel.tsx:30-86`), and point and say (WS.5).

### 1.3 Workspace (WS.1-WS.3, built)

| Shortfall | Where |
|---|---|
| One file at a time: `selected` is a single path, no tabs, no split | `WorkspacePanel.tsx:115`, `:164-166` |
| Read-only by design; the only server routes are three GETs | `WorkspacePanel.tsx:192`; `runs.py:1134-1164`; `src/app/server/workspace_files.py:1-6` |
| No search across files, no go-to-file | no route in `runs.py`; `CommandPalette.tsx` lists pages and runs, not files |
| Own small highlighter, 12 px `<pre>`: no folding, no find, no minimap, no word wrap choice | `WorkspacePanel.tsx:45-58` |
| Diff is unified text behind a switch; no side-by-side | `WorkspacePanel.tsx:185`, `FileDiffs.tsx:37-56` |
| A file over 512 KB is refused; the tree stops at 5,000 files | `workspace_files.py:14-16` |
| Changes, workspace, preview and log are separate tabs: a person cannot see the code and the running product together | `RunDashboard.tsx:1060-1085` |

### 1.4 Brownfield today

An existing codebase enters once, before the run starts: an archive upload (`POST /runs/{id}/codebase`, refused once
the run is past `created`, `runs.py:327-343`) or a git clone (`src/app/server/seeding.py`), or a finished run's
product for a change request (`change_request_runs.py`). After that the person's only channels are steering notes
(`src/app/server/steering.py`, read on the stage's next model call), review gates, point and say, and rewind. There is
no way for the person to change a line, though in a brownfield run the person usually knows the code better than the
agents do. Delivery goes back as a branch and pull request (`docs/PRODUCT.md` 6.6).

## 2. What comparable products do

Facts read from each product's own documentation on 2026-11-25. "ND" = not documented on the pages read.

| Product | Preview | Editor | Human and agent edits |
|---|---|---|---|
| bolt.new | "Open in new window", "Full screen", reload, responsive mode ([release notes](https://support.bolt.new/release-notes)) | File list, edit, save; built-in terminal ([code view](https://support.bolt.new/building/code-view)) | Wait for the agent before terminal commands; whole-project version restore |
| WebContainers | Needs cross-origin isolation headers on the host page ([headers](https://webcontainers.io/guides/configuring-headers)); JS and WASM only | - | - |
| Lovable | Desktop/tablet/mobile toggle, open in new tab (needs sign-in), refresh ([preview](https://docs.lovable.dev/features/projects/preview)) | File tree, tabs, search in file and across files ([code mode](https://docs.lovable.dev/features/code-mode)) | **Save is disabled while the agent is generating**; each save is a revertable version |
| v0 | ND | Code tab beside the preview, read-only diff per message ([code editing](https://v0.app/docs/code-editing)) | **"Manual editing pauses while the agent is working"**; edits sync when a prompt is sent; Save or Discard bar |
| Replit | Screen-size presets, refresh, open in a new tab ([preview](https://docs.replit.com/features/editor/preview)) | Full editor | Agent tasks run in **isolated copies**, applied to the main version on request ([task system](https://docs.replit.com/core-concepts/agent/task-system)); checkpoints and rollback ([checkpoints](https://docs.replit.com/features/version-control/checkpoints-and-rollbacks)) |
| GitHub Copilot coding agent | none | none; review on the pull request | **Branch per task** ([docs](https://docs.github.com/en/copilot/responsible-use/copilot-coding-agent)). Copilot Workspace was retired 30 May 2025 ([GitHub Next](https://githubnext.com/projects/copilot-workspace)) |
| Cursor cloud agents | Person can take control of the agent's desktop, then release it ([docs](https://cursor.com/docs/background-agent)) | VS Code fork | Separate VM and **separate branch**; local parallel agents in git worktrees ([worktrees](https://cursor.com/docs/configuration/worktrees)); a steering message is delivered at the agent's next tool call ([agent](https://cursor.com/docs/agent/overview)) |
| OpenHands | App tab shows the served product; browser tab is view-only ([features](https://docs.openhands.dev/openhands/usage/key-features)) | Embedded VS Code, Changes tab, shared terminal | Locking ND; pause and resume exist |
| Devin | Interactive browser | VS Code with the repositories; terminals read-only until toggled ([session tools](https://docs.devin.ai/work-with-devin/devin-session-tools)) | **"Make sure that Devin is paused before taking over the IDE to avoid simultaneous, conflicting changes"**; the person tells Devin what changed, by hand |

Patterns that matter:

- **Nobody merges live.** No product read documents a CRDT (Yjs) or per-file locks between a person and an agent.
  The three working patterns are: the editor is locked while the agent works (v0, Lovable), the agent is paused
  before the person edits (Devin), or each actor works on its own copy or branch and the result is applied
  (Replit, Cursor, Copilot).
- **Telling the agent is the weak point everywhere.** Devin asks the person to describe the edit. v0 syncs files and
  leaves the agent to re-read. None documents a diff handed to the agent. This harness can do better because every
  stage already commits and already reads injected notes.
- **Own-window preview and device sizes are standard** (Bolt, Lovable, Replit).

Editor and security facts:

| Fact | Source |
|---|---|
| Monaco is MIT, built from VS Code's sources, has a diff editor and multiple models (tabs keep view state and undo); it runs no VS Code extensions and is not supported on mobile browsers | [monaco-editor](https://github.com/microsoft/monaco-editor), [monaco-react](https://github.com/suren-atoyan/monaco-react) |
| `@monaco-editor/react` loads from a CDN by default; local bundling on Vite needs `loader.config` and worker set-up | [monaco-react](https://github.com/suren-atoyan/monaco-react) |
| code-server: "Never expose code-server directly to the internet without some form of authentication and encryption", else "someone can take over your machine via the terminal"; one password; needs WebSockets, 1 GB RAM, 2 vCPUs; "built for individuals", one VM per user suggested | [guide](https://coder.com/docs/code-server/guide), [FAQ](https://coder.com/docs/code-server/FAQ) |
| OpenVSCode Server: no authentication by default; the Docker image starts without a connection token | [repository](https://github.com/gitpod-io/openvscode-server) |
| Theia: Monaco-based, not a VS Code fork, runs in the browser, EPL-2.0 | [FAQ](https://theia-ide.org/docs/faq/) |
| A sandboxed frame is "useless" if the content can be opened outside it on the same origin; `allow-scripts` with `allow-same-origin` on same-origin content removes the protection | [MDN iframe](https://developer.mozilla.org/en-US/docs/Web/HTML/Reference/Elements/iframe) |
| Untrusted content belongs on a separate sandbox domain that shares no cookies with the main one, ideally one site per subdomain; `Content-Security-Policy: sandbox` for active content | [web.dev](https://web.dev/articles/securely-hosting-user-data) |

Not verified: Monaco's bundle size (a third-party build log suggests 2-3 MB plus language workers), which editor
library Bolt, Lovable, v0 and Replit use, and how their previews are isolated.

## 3. Recommended design

### 3a. Full-screen and own-window preview

1. **Own-window route** `/runs/:runId/preview`, outside the `Layout` shell: the frame fills the window under one thin
   toolbar. The run page's Preview tab gets "Open in its own window" and "Fill the window" (the same component in a
   fixed full-viewport layer, Esc returns). The route is our own page, not the raw signed link, so link renewal
   (`PreviewPanel.tsx:127-137`), the toolbar and point and say keep working. A person can put it on a second monitor.
2. **One toolbar row** replacing today's three: start/stop and source, reload, a path field (navigates the frame under
   the signed prefix), device size (fill, phone 390 x 844, tablet 820 x 1180, custom, rotate), Page/Requests, pointing,
   status. Device sizes are a sized and centred frame; no emulation is claimed.
3. **A preview a product can be tested in** (behind `PRODUCT_PREVIEW`):
   - Serve previews from a **separate origin by default** (`PRODUCT_PREVIEW_ORIGIN` exists, `preview.py:135`), one
     host per preview where the deployment has wildcard DNS and TLS, so storage works and one product cannot read
     another's. Without it, keep today's opaque origin and say plainly on the toolbar: "Storage and sign-in do not
     work in this preview."
   - On the separate origin only, pass the product's cookies through, scoped to the preview host. Never on the app's
     host.
   - Stream responses and pass WebSocket upgrades through the same token check, so live features and the product's
     own hot reload work.
   - **Follow the build at commits, not at writes.** A stage's half-written files would break the page every few
     seconds. When a new sprint is accepted (or a stage commits, for the live source) the toolbar says "A newer
     version is ready" with one action that re-copies and restarts.
4. Stack-agnostic by construction: the preview already starts whatever the product's own start command is. A service
   keeps the request console; that console also moves to the own-window route.

### 3b. A VS Code-style workspace

Route `/runs/:runId/workspace`, outside the `Layout` shell, also reachable as "Fill the window" from the tab.

```
+--+----------------+--------------------------------+---------------------+
|  | Files          | tab  tab  tab*                 | Preview (optional   |
|F | tree, filter   |--------------------------------| split, the same     |
|S | "changed" and  | editor (Monaco)                | component as 3a)    |
|C | "yours" marks  | or side-by-side diff           |                     |
|P |                |--------------------------------|                     |
|  |                | Bottom: activity / log / tests |                     |
+--+----------------+--------------------------------+---------------------+
| status: run state, stage working now, whose turn it is, branch, file encoding |
```

- Activity bar: Files, Search, Changes (the commit list of `ChangesPanel`), Preview.
- All splits resizable and remembered per browser; every panel can be hidden.
- Tabs with a preview tab (single select reuses it, double select pins), go-to-file (Ctrl+P) over the tree already
  loaded, search across files through a new server route.
- A file an agent has just written reloads in place when the tab is clean (today's behaviour,
  `WorkspacePanel.tsx:141-145`); a status line names the stage working now.
- The run page's small Workspace tab stays as it is, with the two new actions.

**Monaco, not code-server.**

| | Monaco with our routes | code-server / OpenVSCode Server |
|---|---|---|
| Writes go through | our save route: containment, listing rules, locked-suite check, run-state check, audit | the file system directly; every guard bypassed |
| Terminal | none | a shell in the workspace; with the worker's mounts that is command execution by design |
| Sign-in | the app's own roles and tenants | one password or one token per server |
| Multi-tenant | yes, nothing new | one container per session to be safe |
| New service | none | a container, WebSocket proxying, 1 GB RAM each |
| Extensions, language servers, debugger | no | yes (Open VSX) |
| Works for any product language | syntax colours for the common ones, plain text otherwise | yes |

Monaco gives the look and the editing the owner asked for with no new attack surface. It is loaded as a lazy chunk,
bundled locally (never from a CDN: a self-hosted app and its CSP), and falls back to today's highlighter on a phone
or if the chunk fails. code-server stays what WS.6 said, optional and last, and only if a person is measured to need
a terminal or a language server (UX.16, parked).

### 3c. Co-development mode (brownfield first)

**Was the rejection right?** (`docs/improvement-plan.md:180`: "A full editable IDE beside agents that write the same
files (WS): conflicts and insecure defaults; a read-only view plus a take-over mode only (WS.6).")

- Right on conflicts, for reasons specific to this harness:
  - Stages commit with `git add -A` (`src/app/tools/version_control.py:207`, `:274`, `:359`), so a person's half-typed
    save would be swept into a stage's commit and judged as that stage's work.
  - A fix that breaks a locked test is reverted, and a stage cut off mid-way runs again (`runner.py:1304-1315`); either
    would silently undo the person's lines.
  - The write guards attribute names in a file to the stage visit that added them (`src/app/tools/repository.py:6600-6614`);
    lines appearing from nowhere break that attribution.
  - No comparable product merges live either (section 2).
- Right on insecure defaults, for code-server and OpenVSCode Server (section 2).
- Too narrow in the remedy. It equated editing with a second IDE service. Editing needs a save route, not a shell.
  And it did not weigh brownfield, where the person owns the code.

**The safe form: turn-taking with an edit session.**

| State of the run | Who may write | Editor |
|---|---|---|
| Running | agents only | read-only; "Take the turn" asks for a pause at the stage boundary (`POST /pause?at=boundary`, exists) |
| Paused, or waiting at a review gate | the one person holding the edit session | writable |
| Edit session open | that person; **resume is refused** until hand back or discard | writable; others read-only |
| Completed | nobody in place | "Change this product" starts a change-request run seeded from it (exists) |

Rules, all enforced on the server:

1. **Edit session.** `POST /runs/{id}/edit-session` (operator of the run's tenant; run paused or waiting) records who,
   when and the workspace's commit at that moment, with a lease renewed by heartbeat. One session per run. A lapsed
   lease does not discard work: the edits stay in the workspace, uncommitted, and the next session or hand back picks
   them up. While a session is open, `resume` answers 409 with the holder's name.
2. **Guarded save.** `PUT /runs/{id}/files/content` with the hash the editor loaded (`If-Match`). Refused unless: a
   session is open and held by the caller; the path passes `resolve_within_workspace` and is one the listing would
   show or a new path beside such files (never `.git`, `.harness`, installed folders, credential files, links); text,
   within the size cap; the hash matches (409 otherwise, the editor shows both versions side by side). Create, rename
   and delete follow the same rules. Written through a temporary file and a rename.
3. **Locked acceptance suite stays locked.** A path for which `suite.is_protected` is true
   (`src/app/acceptance/suite.py:1018`) is refused with the reason and the right route: a change request or a dispute,
   which already exist. Hand back checks `suite.is_as_last_locked` (`suite.py:873`) and restores on any difference.
   In a brownfield run, a seeded test that is part of the regression baseline may be edited only with an explicit
   confirmation, and the hand back names it so the baseline is re-taken knowingly, not silently.
4. **Hand back.** `POST /runs/{id}/edit-session/hand-back` with a one-line reason:
   - commits exactly the session's changes as one commit authored by the person ("By <name>: <reason>"), separate
     from every stage's commit;
   - runs the unit and locked acceptance checks once, before any agent works, so a test the person's edit broke is
     reported as theirs and is not charged to a stage's fix budget;
   - writes a hand-back note through the existing steering channel (`steering.add`, audience by the files' roles,
     read by the next stage and acknowledged on the transcript): the files, the line counts, a bounded diff, the
     reason, and the instruction that these lines are the person's decision and are changed only when a locked test
     requires it. The diff is marked as data, as point and say marks markup;
   - records `run.edit.hand_back` in the audit trail and the Sprint Record; the Changes list labels the commit;
   - offers a rewind (exists) when the edit touched files an earlier stage produced that later stages read, such as
     the specification or a contract;
   - then resume is allowed.
5. **Discard** restores the session's files to the commit recorded at its start. Nothing else is touched.
6. **Brownfield extras.** Rebuild the code map (`agents/code_map.py`) after a hand back that adds, removes or renames
   a module. Keep the person's commit as its own commit in the delivered branch where pull-request delivery is on.
   And offer the form real teams use: **branch per actor**. The person edits in their own editor and pushes; at a
   pause, "Bring in changes from the source repository" fetches and merges them into the workspace, stops on a
   conflict and shows it, and then follows hand back steps 2-4. This needs no editor of ours at all and suits a large
   codebase best. (To verify before building: that a cloned seed keeps its remote, `runs.py:509`.)

**How the next stage learns of the edit, in order of strength:** the commit in the history every stage's "what
changed" tool reads; the hand-back note on its next model call, acknowledged; the check results taken after the edit;
the rebuilt code map. This is stronger than any product in section 2.

**Security.**

- No terminal and no execution route: an edit can only reach execution through the same sandboxed stages and preview
  container as agent-written code.
- Operator role, tenant check, audit of session open, each hand back and each discard (file names and counts, never
  contents).
- File text is only ever shown as text. No workspace file is rendered as a page in the app's origin; HTML is seen
  through the preview's origin.
- Monaco bundled locally; no CDN, no new `connect-src`.
- The preview's separate origin shares no cookie with the app; the pop-out is our own route, so the signed link's
  short life is kept.

## 4. Phased build plan

Sizes: S under a day, M 1-3 days, L a week. "Fails on old" names the test that must fail before the change.
Copy-only changes get no test (owner 2026-11-17). Everything is stack-agnostic: no item reads the product's language.

### Phase 1: space (UI only, always on, keeps the release-candidate count)

| Item | What | Files | Size | Test (fails on old) | Needs |
|---|---|---|---|---|---|
| UX.1 | "Fill the window" on the centre panel: fixed full-viewport layer, Esc returns, state in the URL (`?fill=1`); both rails collapsible, remembered | `RunDashboard.tsx`, `Tabs` | S | `RunDashboard.test.tsx`: with `fill=1` the rails are not rendered and Esc removes the parameter | - |
| UX.2 | Own-window routes `/runs/:runId/preview` and `/runs/:runId/workspace` outside `Layout`; "Open in its own window" on both tabs; command palette entries | `App.tsx`, new `pages/RunPreview.tsx`, `pages/RunWorkspace.tsx`, `CommandPalette.tsx` | S | route test: the page renders the panel without the header or footer, and refuses without sign-in | - |
| UX.3 | Preview toolbar in one row: reload, path field, device sizes with rotate; the three rows collapse into it | `PreviewPanel.tsx`, new `PreviewToolbar.tsx` | M | `PreviewPanel.test.tsx`: choosing a size sets the frame's width and height; a path entered changes the frame's source under the signed prefix and never outside it; reload re-requests | - |
| UX.4 | The toolbar states it when storage and sign-in cannot work (no separate origin) | `PreviewPanel.tsx` | S | none (copy) | UX.3 |

### Phase 2: the workspace (UI plus two read-only routes, always on)

| Item | What | Files | Size | Test (fails on old) | Needs |
|---|---|---|---|---|---|
| UX.5 | Workspace shell: activity bar, resizable tree, tabs with a preview tab, bottom panel (activity, log), status line; go-to-file | new `components/workspace/*`, `WorkspacePanel.tsx` reused for the tree | M | opening two files shows two tabs and keeps the first; closing the active one selects its neighbour; go-to-file filters the loaded tree | UX.2 |
| UX.6 | Monaco as the reader and the side-by-side diff, lazy, bundled locally, fallback to the present highlighter | `package.json`, `vite.config.ts`, new `components/workspace/Editor.tsx` | M | with the editor module failing to load, the file's text is still shown; the diff view is given the base text and the current text. Build check: no request to an outside host | UX.5 |
| UX.7 | Search across files: `GET /runs/{id}/files/search?q=` over listed files only, capped in results and time | `runs.py`, `workspace_files.py`, `api.ts`, search panel | M | pytest: a hit in a listed file is returned with its line; a hit in `.harness`, `.git` or an unlisted file is not; another tenant gets 404 | UX.5 |
| UX.8 | `GET /files/content` returns the file's hash and, with `?at=accepted`, the base text for the diff; split editor and preview | `runs.py`, `workspace_files.py`, `changes.py` | S | pytest: the hash changes when the file does; the base text is the last accepted sprint's | UX.6 |

### Phase 3: a preview a product can be tested in (behind the existing `PRODUCT_PREVIEW`; measured)

| Item | What | Files | Size | Test (fails on old) | Needs |
|---|---|---|---|---|---|
| UX.9 | Separate preview origin as the deployed default, one host per preview where wildcard DNS exists; the product's cookies pass on that origin only | `preview.py`, `runs.py`, `deploy/Caddyfile`, `docker-compose.yml`, HANDOVER | M | pytest: on a separate origin a `Set-Cookie` is passed, scoped to the preview host; on the app's host it is still dropped; a request to the app's host for a preview path is refused | supervised trial (`docs/STATE.md:102`) |
| UX.10 | Streamed responses and WebSocket pass-through under the same token check and idle clock | `runs.py`, `preview.py` | M | pytest: an event stream's first chunk arrives before the upstream closes; an upgrade with a bad or expired token is refused; one with a good token echoes | UX.9 |
| UX.11 | Follow the build: the status names the commit the preview runs; a newer accepted sprint or commit shows "A newer version is ready" with one restart action | `preview.py`, `preview_worker.py`, `PreviewPanel.tsx` | M | pytest: the status reports `behind: true` after a later sprint tag; vitest: the action calls start with the same source | UX.3 |

Measured for the phase: start success against the delivered-start check, share of previews where a stored value
survives a reload, zero access without a token (the existing WS.4 measures plus one).

### Phase 4: co-development (new switch `CO_DEVELOPMENT`, off; measured before it is turned on)

| Item | What | Files | Size | Test (fails on old) | Needs |
|---|---|---|---|---|---|
| UX.12 | Edit session: open, heartbeat, close; resume refused while one is open; one holder | new `src/app/server/edit_session.py`, `runs.py`, `runner.py` | M | pytest: open on a running run is 409; a second person's open is 409; resume during a session is 409; a lapsed lease keeps the files | - |
| UX.13 | Guarded save, create, rename, delete | `edit_session.py`, `workspace_files.py`, `runs.py` | M | pytest, one per refusal: no session; not the holder; stale hash; path outside the workspace; `.harness`, `.git`, a credential file, a link; a path inside the locked suite; too large; not text. And: with the switch off every write route is 403 | UX.12 |
| UX.14 | Editor write mode: unsaved marks, save, the stale-hash view, discard, "Take the turn", whose-turn status | `components/workspace/*`, `api.ts` | M | vitest: read-only while running; a 409 on save shows both versions and keeps the person's text; discard asks first | UX.6, UX.13 |
| UX.15 | Hand back: the person's own commit, checks before any stage, the note to the next stage, audit, Sprint Record line, rewind offer; discard to the session's start | `edit_session.py`, `version_control.py`, `steering.py`, `graph/workflow.py`, `runs.py` | L | pytest: the commit holds exactly the session's files and the person as author; a changed locked suite is restored and reported; the next stage's first call carries the note with the file names; a test the edit broke is recorded as the person's; discard restores only the session's files. The note's wording gets the banned-words test | UX.13 |
| UX.16a | Brownfield: code map rebuilt after a structural hand back; baseline tests editable only with confirmation and re-taken knowingly; the person's commit kept apart in the delivered branch | `agents/code_map.py`, `acceptance/regression_contract.py`, `repository_delivery.py` | M | pytest: a renamed module appears in the next stage's code map; an edited baseline test without confirmation is refused; the delivered branch has two authors' commits | UX.15 |
| UX.16b | Bring in changes from the source repository at a pause (branch per actor), conflicts shown, then hand back steps | `seeding.py`, `edit_session.py`, `runs.py`, UI action | M | pytest with two local repositories: a pushed commit is merged and noted; a conflict stops with the workspace unchanged | UX.15; verify the seed keeps its remote |
| UX.16 (parked) | code-server on a paused run in its own container (the original WS.6) | - | L | - | only if phase 4's numbers show a need for a terminal or language server |

Measured for the phase, on brownfield families first (`tasks-api-change`): edits lost (must be 0), writes accepted
while a stage was running (0), locked-suite differences after a session (0), share of hand-back notes acknowledged by
the next stage, reverts of the person's lines by a later stage, and the hidden score against the same run without the
edit. Kept on only if no measure regresses.

Order and bundling: phases 1 and 2 are app-only deploys and can ship at any run boundary. Phase 3 follows the
supervised preview trial already queued. Phase 4 changes resume and adds a commit path, so it ships as one bundle at
a run boundary with the switch off, then one supervised brownfield run with it on.

Plan bookkeeping when accepted: WS.6 in `docs/improvement-plan.md` is replaced by UX.12-UX.16, and the rejected line
at `:180` is reworded to "simultaneous editing, and a second IDE service by default".

## 5. Risks and what I would not build

| Risk | Answer |
|---|---|
| A person leaves a session open and the run never resumes | The lease lapses; the run page and the needs-you inbox show "waiting for hand back"; an operator can discard |
| The person's edit breaks the build and the agents burn budget on it | Checks run at hand back, before any stage; failures are shown to the person first, with "hand back anyway" explicit |
| An agent rewrites the person's lines later | The note says not to; reverts are counted. A hard write guard on the person's lines is **not** proposed now: it could block a legitimate fix. Add it behind its own switch only if the count is not zero |
| Monaco's weight | Lazy chunk, loaded only on the workspace route; the run page is unchanged |
| A separate preview origin needs DNS and TLS the owner's machine may not have | The opaque-origin mode stays as the fallback and says what it cannot do |
| Cookies and WebSockets widen the preview proxy | Only on the separate origin, same token check, same idle stop, same internal network |
| The measure of a run changes when a person edits it | A run with a hand back is marked as co-developed and kept out of benchmark scoring |

Not to build:

- **Simultaneous editing with agents** (locks per file, CRDT/Yjs). No comparable product does it, and the harness's
  stage commits, reverts and write guards all assume one writer.
- **code-server or OpenVSCode Server as the default editor.** A shell beside the worker's mounts, single-password
  sign-in, a container per session.
- **A terminal in the browser.** Commands are run by stages in the sandbox and by the preview container; a person's
  shell is the largest new attack surface for the least testing value.
- **WebContainers for the preview.** Already rejected (`docs/improvement-plan.md:181`): JS and WASM only.
- **Hot reload on every agent write.** Half-written files; restart at commits instead.
- **Editing a completed run in place.** It would change a delivered, scored product; a change-request run already
  does this with a record.
- **Language servers, debugger, extensions.** Not needed to read, edit and test; revisit with UX.16.
