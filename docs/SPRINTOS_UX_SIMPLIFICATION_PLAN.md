# SprintOS UX Simplification Plan

## Goal
Make SprintOS feel like one guided lane, not a local product control center.

## Product Rule
At any moment, SprintOS should answer only three questions:

1. What project am I in?
2. What is the next step?
3. What output will I get if I do it?

Everything else should be secondary, advanced, or hidden.

## Proposed Simplified UI Structure
### First Open
Show only:

- One `Continue` card if a project exists
- One `Start New Project` card
- One compact `Projects` list

Hide by default:

- Classic sprint generation
- AI status
- Local runtime
- Setup Doctor detail
- Guided Demo detail
- Backup restore detail

### After Project Selection
Top of page:

- Project title
- Current stage
- One dominant action button
- One sentence explaining why this is the next step
- One expected output line

Directly below:

- Focus Session
- Recent Project History

Below that:

- Collapsible advanced sections

## What Should Be Shown On First Open
- Continue This
- Start New Project
- Recent Projects

Optional compact support line:

- `Local setup has 1 warning: no backup yet`

Not a full panel. Just a status line with a `Review` affordance.

## What Should Be Shown After Project Selection
- Project Command Center
- Focus Session
- Recent Project History

Only the current stage section should auto-open:

- Planning
- Build
- Workspace
- Release

Everything else should stay collapsed.

## What Should Be Hidden Under Advanced
- Plan-only sprint generation
- Prototype/build/hosting target overrides
- Snapshot create/compare/restore
- Manual JSON feedback import
- AI routing and provider evals
- Runtime metadata
- Backup ZIP/report links
- Artifact history browser

## Proposed Naming Changes
- `Quick Launch` -> `Start Project`
- `Quick Launch Testable Version` -> `Start Project`
- `Generate Sprint` -> `Plan Only`
- `Today Dashboard` -> `Today`
- `Run Today Action` -> `Continue`
- `Run Recommended Action` -> `Do Next Step`
- `Setup Doctor` -> `Local Setup Check`
- `Guided Demo` -> `Sample Project`
- `Workspace Sync` -> `Check Workspace Changes`
- `Run Run & Verify` -> `Verify Workspace`
- `Artifact History` -> `Older Outputs`
- `Build Pack` -> keep
- `Release Pack` -> keep

## Proposed Primary Flow
1. Enter raw idea.
2. Click `Start Project`.
3. SprintOS creates the first useful package.
4. SprintOS opens the project automatically.
5. Command Center shows one next step.
6. User starts a Focus Session.
7. User advances the project through one clear stage lane.

## Proposed Panel Merge / Removal Plan
### Merge
- Merge Today action language and Command Center action language.
- Merge Activity Timeline and Artifact History into one calmer history model in the UI.
- Merge workspace actions into one sequential workspace lane.

### Hide
- Hide classic sprint generation by default.
- Hide AI summary from sidebar.
- Hide backup restore until explicitly needed.
- Hide export/report clutter behind details blocks.

### Keep but demote
- Setup Doctor
- Guided Demo
- Local Backup
- AI configuration
- Snapshot restore

## Wireframe-Style Text Outline
### First Open
`Header`

`Continue`
- Current project
- Current stage
- Next action
- `Continue`

`Start New Project`
- Raw idea input
- Optional small advanced disclosure
- `Start Project`

`Projects`
- Compact list

`Support`
- Local setup status
- Backup status

### Selected Project
`Project Hero`
- Project title
- Stage
- Status
- Next tiny action
- `Do Next Step`

`Focus Session`
- Timebox
- Done definition
- Progress note

`Recent Project History`
- Last action
- Last artifact
- Last blocker

`Current Stage`
- Only the relevant stage section expanded

`Advanced`
- Planning
- Build
- Workspace tools
- Release tools
- AI
- Safety

## Sequence Rules
- If there is a recommended project, lead with continue, not creation.
- If no project exists, lead with Start Project, not setup tooling.
- If a project is selected, Command Center outranks every other panel.
- If a Focus Session is active, it outranks all advanced controls.
- If a stage is incomplete, only that stage should be visually primary.

## Non-Goals
- No new dependencies
- No UI framework rewrite
- No cloud features
- No automatic Codex invocation
- No behavior expansion

## Expected Outcome
After simplification, SprintOS should feel less like:

- admin dashboard
- devtools console
- local operations center

And more like:

- guided personal execution lane
