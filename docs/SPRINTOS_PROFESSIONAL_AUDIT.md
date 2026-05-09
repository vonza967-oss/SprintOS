# SprintOS Professional Audit

## Executive Summary
SprintOS has a strong core idea and unusually solid local-first discipline, but the current product surface is trying to explain too many internal systems at once. The app is functionally impressive and operationally safer than most MVPs, yet it is not cleanly understandable. It currently behaves more like a local product-workbench than a momentum-preserving execution guide.

The biggest issue is not that SprintOS lacks features. The biggest issue is that the app exposes too many layers, terms, and controls too early. The product says "one next step," but the UI repeatedly offers several parallel next steps. That contradiction is likely the main reason the experience feels messy.

Verdict: SprintOS is usable for a disciplined solo builder who already understands its model. It is not yet clean enough to reliably reduce decision fatigue for a first-time or low-momentum session.

## Current Readiness Verdict
Baseline checks passed:

- `python3 scripts/health.py`: PASS
- `python3 scripts/readiness.py`: PASS
- `python3 scripts/test_fast.py`: PASS
- `python3 scripts/smoke.py`: PASS
- `python3 scripts/test_full.py`: PASS

Additional diagnostic issue discovered outside the required baseline:

- `python3 sprintos.py`: failed on default port with `OSError: [Errno 48] Address already in use`
- `python3 scripts/launch.py`: failed because port `8844` was already occupied by an older SprintOS process that did not answer the current `/api/health` contract

Assessment:

- Runtime quality is better than UX quality.
- Test discipline is better than product simplicity.
- Safety posture is better than flow clarity.

## Strongest Parts To Preserve
- Local-first discipline is real, not cosmetic. Backup, workspace, release, sync, and verification flows consistently avoid cloud assumptions.
- Offline-first behavior is preserved throughout the stack. The app still works without AI keys or network access.
- Secret-handling rules are taken seriously. The repo consistently excludes `.env`, `.git`, obvious key patterns, and sensitive provider payloads.
- Test coverage is broad. The full suite passed `432` tests, plus smoke and health.
- The core artifact chain is coherent: sprint -> prototype/build pack -> workspace -> sync -> verify -> release -> feedback -> next prompt.
- Command Center and Focus Session are the right product instincts. They are the most promising pieces of the UX.
- Safety helpers are better than typical MVP quality: path checks, safe ZIP serving, explicit restore confirmation for local backups, no automatic git/deploy/Codex execution.

## Biggest Weaknesses
- SprintOS is over-exposed. It surfaces too many concepts, panels, and actions at once.
- The app contradicts its own product promise. It claims one next step while presenting a multi-tool control surface.
- `sprintos.py` is a very large monolith at `27,029` lines, with `663` functions and `106` API GET endpoints. This is a maintainability risk, not just an aesthetic issue.
- The product vocabulary is too dense: Today Dashboard, Setup Doctor, Quick Launch, Guided Demo, Command Center, Focus Session, Artifact History, Build Pack, Workspace Sync, Run & Verify, Release Pack, Release Feedback, AI routing, provider evals, and more.
- The app still exposes both the old sprint-generation workflow and the newer Quick Launch workflow side by side, which creates duplicate entry points.
- Documentation is feature-inventory heavy. README and architecture material amplify the sense that SprintOS is a platform, not a focused flow.

## Top 10 Issues Found
1. The first screen is overcrowded. Before a project is even selected, the sidebar shows Today Dashboard, Quick Launch, classic sprint generation, AI status, and the project list. This is too many competing entry points.
2. SprintOS has duplicate creation flows. "Quick Launch Testable Version" and "Generate Sprint" both look like legitimate starting points but imply different models.
3. Command Center guidance is undermined by surrounding controls. The product says "follow the recommendation," while the UI keeps adjacent manual alternatives one click away.
4. The product exposes internal artifact taxonomy too early. Users are asked to reason about prototypes, build packs, deploy packs, workspaces, sync, verification, release packs, and iterations before they need those distinctions.
5. The app uses too many similar action labels. "Run Today Action," "Run Recommended Action," "Start Focus Session," "Make Testable Version," "Generate Build Pack," "Run Run & Verify," and "Create Release Pack" compete semantically.
6. Runtime tooling is confusing under port conflict. The launcher assumes `8844`; when a stale local process is already there, the user gets a start failure instead of a clean "another SprintOS is running, and it may be outdated" explanation.
7. The backend surface area is too large for the current phase. `25` SQLite tables and `106` GET API endpoints are disproportionate to a single-user local tool focused on momentum.
8. The project hydration payload is bloated. One project API response contains `44` top-level keys, and the Command Center itself contains `26` keys. This is overhydration and a sign of concept sprawl.
9. Docs reinforce complexity. README and architecture docs read like subsystem announcements instead of a simple operator guide.
10. Tests cover correctness well, but they do not protect simplicity. The current test suite reduces regression risk while also making UI/process simplification harder because many flows are now deeply encoded.

## UX Problems
### What is visually overwhelming
- The left sidebar is doing too much. It combines guidance, project creation, old sprint generation, AI summary, and project navigation.
- The selected project view still contains too many visible sub-systems even after introducing section grouping.
- The Today Dashboard includes recommendation, backup, setup, runtime, demo, blocked projects, release-ready projects, recent activity, and recent projects in one place.

### What panels compete for attention
- Today Dashboard vs Quick Launch
- Quick Launch vs classic sprint generation
- Command Center vs advanced per-project action panels
- Focus Session vs manual project controls
- Activity Timeline vs Artifact History
- Workspace Release Pack vs Release Feedback vs Run & Verify
- AI status in sidebar vs AI section inside project view

### What labels are unclear
- "Quick Launch Testable Version"
- "Run Today Action"
- "Run Recommended Action"
- "Run Run & Verify"
- "Workspace Sync"
- "Artifact History"
- "Guided Demo"
- "Setup Doctor"
- "End output"
- "Generation mode"

### What actions sound too similar
- "Generate Sprint" vs "Quick Launch Testable Version"
- "Run Today Action" vs "Run Recommended Action"
- "Generate Build Pack" vs "Make Testable Version"
- "Export Workspace" vs "Run Workspace Sync"
- "Run Verification" vs "Run Run & Verify"
- "Generate Iteration Brief" vs "Generate Release Iteration"
- "Copy Codex Prompt" in multiple places with different meanings

### What should be hidden by default
- Classic sprint generation on first open
- Global AI status summary
- Setup Doctor detail and export actions
- Local Runtime panel
- Artifact History
- Manual timeline note entry
- AI route controls and provider evals
- Release feedback import controls
- Most report/ZIP buttons

### What should be the single primary action
- First open with no project: `Quick Launch`
- First open with active project: `Continue Project`
- Inside project: `Run the Command Center action`
- During work: `Start/continue Focus Session`

### What should move into advanced settings
- Prototype target override
- Hosting target override
- Build target override
- Generation mode override
- AI route presets
- Provider evals
- Backup restore controls
- Manual JSON feedback import
- Manual artifact export bundles

### What should be merged or simplified
- Merge classic sprint generation into Quick Launch or hide it behind Advanced
- Merge Today "Run Today Action" and project "Run Recommended Action" language into one shared pattern
- Merge Activity Timeline and Artifact History into one calmer "Recent Project History" view, with latest-artifact actions still separate
- Merge workspace-facing controls into one sequential "Workspace" stepper: Export -> Sync -> Verify -> Release

### What should be renamed
- `Quick Launch Testable Version` -> `Start Project`
- `Generate Sprint` -> `Plan Only`
- `Run Today Action` -> `Continue`
- `Run Recommended Action` -> `Do Next Step`
- `Run Run & Verify` -> `Verify Workspace`
- `Workspace Sync` -> `Check Workspace Changes`
- `Artifact History` -> `Older Outputs`
- `Setup Doctor` -> `Local Setup Check`
- `Guided Demo` -> `Sample Project`

### What should be removed from the main flow
- Persistent runtime metadata
- AI diagnostics and provider evals
- Most ZIP/download actions
- Manual export/report utilities
- Release iteration tools until release feedback actually exists

### What should only appear after needed
- Release Pack and Release Feedback after a workspace exists
- Workspace Snapshot after first workspace export
- Run & Verify after workspace sync or build pack exists
- AI route tuning after user deliberately opts into AI
- Backup restore only after a backup exists

## Workflow Problems
### Where the user can get lost
- At the very start, because there are two creation flows and multiple guidance surfaces.
- After Quick Launch, because the project view still exposes many alternative moves.
- During workspace stage, because Export Workspace, Snapshot, Sync, Verify, Release, and Feedback are all visible in the same project.
- During handoff, because there are many different prompt/report/export files with overlapping purposes.

### Where there are too many choices
- First open sidebar
- Selected project action sections
- AI section
- Release/testing area
- Export/report/ZIP affordances everywhere

### Where actions are duplicated
- Dashboard recommendation vs Command Center recommendation
- Quick Launch vs Generate Sprint vs Run Testable Pipeline
- Multiple "copy prompt" affordances
- Multiple verification-ish concepts: readiness, sync, verify, release checks

### Where the same thing has multiple names
- "Verification" and "Run & Verify"
- "Build Pack" and "Codex build ready"
- "Workspace Release Pack" and "release candidate"
- "Command Center next action" and "next tiny action" and "recommended action"

### Where internal concepts appear too early
- Build target
- Hosting target
- Prototype type
- Workspace sync
- Provider routing
- Eval modes
- Artifact history categories

### Where the next action is unclear
- When Today Dashboard says "Start Focus Session" but the global action is "Export Workspace"
- When a project can be advanced from multiple places without a strong visual hierarchy
- When Quick Launch succeeds and still leaves a dense project page

### Where Codex handoff is confusing
- There are multiple Codex prompt artifacts across sprint, prototype, build pack, quick launch, workspace sync, release pack, and verification
- The user has to infer which prompt is authoritative for the current stage

### Where report/ZIP links become noisy
- Quick Launch outcome
- Command Center secondary actions
- Focus Session
- Workspace Snapshot / Sync / Release / Verification panels
- Artifact History

### Where the flow should be linearized
- Workspace stage should behave like one lane:
  1. Export Workspace
  2. Sync Workspace
  3. Verify Workspace
  4. Create Release Pack
  5. Add Release Feedback
  6. Generate next Codex prompt

## Product Simplicity Review
SprintOS should feel like:

> I have an idea. SprintOS tells me the next step and creates the right package.

Current reality:

- It partially does that after the user already understands the model.
- On first contact, it feels closer to an admin dashboard plus local tooling console.

### Simplified Product Model
#### Primary user action
- Start or continue one project

#### Secondary actions
- Review the current project state
- Run the next safe step
- Save a restart point
- Export the current artifact

#### Advanced actions
- Override prototype/build/hosting targets
- Run workspace snapshots/restores
- Import feedback JSON
- Tune AI provider routing
- Run provider evals

#### Hidden or rare actions
- Backup restore
- Artifact history browsing
- Local runtime inspection
- Release iteration prompt generation
- Manual timeline notes

#### Dangerous actions
- Real local restore
- Workspace snapshot restore
- Any action that replaces files

### Recommended Information Architecture
- Global level:
  - One continue card
  - One start-new-project card
  - Compact project list
- Project level:
  - One project state card
  - One next-step button
  - One focus session block
  - One compact recent-history block
- Advanced level:
  - Planning
  - Build
  - Workspace
  - Release
  - AI
  - Safety

## Risk Review
### 1. Data Safety
- Local backup flow is comparatively strong, but backup/restore is still a psychologically risky surface to expose prominently on the dashboard.
- Workspace restore is destructive by design, even with a pre-restore snapshot. It should remain guarded and visually secondary.
- Snapshot restore removes files absent from the snapshot. This is valid behavior, but high-stakes.
- The app is careful with confirmations for local backup restore, but workspace restore has no equivalent dry-run mode.

### 2. Security
- Path handling generally looks good. Safe file-serving helpers are used consistently.
- `.env` exclusion is consistently enforced across workspace, snapshot, release, and backup flows.
- AI diagnostics are redacted and safer than average.
- Main residual risk is breadth: too many routes and file flows increase the chance of future mistakes.

### 3. Local Runtime
- Port handling is brittle. `scripts/launch.py` and `scripts/stop.py` hardcode `127.0.0.1:8844`.
- A stale SprintOS process can block startup and produce a confusing failure mode.
- Runtime status is useful, but it does not belong in the main decision surface.

### 4. AI Provider Behavior
- Routing model is thoughtful but too visible.
- Cost estimates are correctly labeled as local estimates, but the presence of cost and eval tooling adds control-panel energy.
- The product exposes too many AI settings for a tool whose main promise is momentum.

### 5. Generated App Quality
- Build Packs are directionally useful for Codex handoff.
- Prototype and release artifacts appear structurally sound.
- The quality risk is less about broken output and more about genericness plus prompt sprawl.
- Generated workspaces are probably usable for Codex, but the number of companion docs/prompts is high.

### 6. Maintainability
- `sprintos.py` is the main long-term engineering risk.
- `init_db()` being a 500+ line schema initializer with partial ad hoc migration behavior is a future change hazard.
- UI rendering, route handling, persistence, and artifact generation remain tightly coupled.
- Tests are broad but heavily centralized in `tests/test_sprintos.py` at `5,470` lines.
- `scripts/smoke.py` at `524` lines is useful but monolithic.

### 7. User Psychology
- SprintOS helps most when the user is already in motion.
- SprintOS hurts when the user is tired, uncertain, or opening it after a gap.
- It currently increases decision fatigue at the top of the funnel.
- It does create tangible progress artifacts, which is a major strength worth protecting.

## What Is Likely Confusing The User Right Now
- Too many nouns
- Too many buttons
- Too many parallel "next actions"
- Too many prompt/report artifacts
- Too much local-tooling detail mixed into the main product flow
- A visible split between "guidance mode" and "toolbox mode"

Most likely root cause:

- The app has grown by additive capability, but not yet by subtractive presentation.

## Scorecard
- Core concept clarity: 7/10
  - The underlying idea is strong and easy to believe in.
- UI clarity: 4/10
  - The app surface does not consistently enforce one obvious move.
- Workflow clarity: 5/10
  - The intended flow exists, but the UI lets the user bypass or dilute it constantly.
- App-generation usefulness: 7/10
  - The generated chain is practical enough for solo local use.
- Codex handoff quality: 7/10
  - Artifacts are useful, but too many prompts compete for authority.
- Local safety: 8/10
  - Strong constraints, path safety, and secret avoidance.
- Backup safety: 8/10
  - Better than expected, though restore surfaces should stay visually secondary.
- Maintainability: 3/10
  - The monolith and route/schema sprawl are now material risks.
- Test coverage: 8/10
  - Broad and disciplined, though concentrated in very large files.
- Daily usability: 5/10
  - Functional, but mentally expensive.
- Public product readiness: 2/10
  - Not because it is broken, but because the current experience assumes too much internal literacy.

## 10 Quickest Improvements
1. Make Quick Launch the only visible creation path on first open.
2. Move classic sprint generation behind an `Advanced` disclosure.
3. Replace `Run Today Action` and `Run Recommended Action` with one shared label: `Do Next Step`.
4. Hide AI status from the sidebar unless AI is explicitly enabled.
5. Move Local Runtime out of Today Dashboard.
6. Collapse backup restore controls until a backup exists and the user explicitly asks to restore.
7. Collapse report/ZIP actions into a single `More` menu or details block per panel.
8. Rename `Run Run & Verify` to `Verify Workspace`.
9. Make Command Center the only prominent action surface once a project is selected.
10. Reduce Today Dashboard to one continue card plus one compact project list.

## What Should Be Fixed First
### Priority 0
- Remove duplicate starting flows from first open
- Reduce first-open sidebar to guidance + one start action
- Make the Command Center action visibly dominant
- Normalize action naming across Dashboard and project view

### Priority 1
- Linearize the workspace stage
- Collapse low-frequency report/export controls
- Push AI configuration behind explicit opt-in
- Downgrade runtime/setup/backup detail from primary UI to support UI

### Priority 2
- Break `sprintos.py` further along stable seams without changing entrypoint behavior
- Separate schema bootstrap from migrations
- Split smoke/test monoliths

## What Should Not Be Built Next
- More dashboards
- More artifact types
- More AI providers
- More routing/eval sophistication
- Deployment automation
- GitHub automation
- Public SaaS features
- Accounts, auth, billing, sync

Reason:

- None of those solve the core problem, which is clarity. They would deepen the exact complexity that is currently making the product feel messy.

## Closing Verdict
SprintOS is a good system hiding inside a crowded interface.

The right next move is not feature growth. The right next move is a focused UX simplification PR that reduces visible choices, removes duplicate entry points, strengthens the main lane, and keeps all local-first safety behavior intact.
