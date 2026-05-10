# SprintOS MVP

**SprintOS** is a local app-first execution engine: turn a messy idea into a small app draft, open it, improve it safely, test it locally, and package it for manual testing.

The default main lane is now:

```text
Create App → follow-up questions / assumptions → Latest Generated App → Open Preview → Test App → Download App → Prepare for Codex
```

SprintOS should not add new user-facing surface area until this simplified main lane has been tested in real use.

It is designed for burst-based work:

```text
Idea → create app → open preview → improve safely
```

## What this MVP includes

- Local web app
- No required dependencies
- SQLite project storage
- Workflow templates stored as JSON files
- Idea capture
- Auto workflow selection
- 30 / 60 / 120 / 240 minute sprint modes
- Offline template mode
- Optional OpenAI or DeepSeek provider integration
- AI app-file generation for local prototype drafts
- Cut Scope button
- Resume/restart card
- App draft generation
- Markdown export
- Progress notes
- App-first success cards and App Draft state summaries
- Source Pack handoff files and local testing packages for manual testing or manual deployment review
- Today Dashboard global guidance layer for what to continue next across all projects
- Project Command Center guidance layer for one clear current state and one recommended next action
- Focus Session execution layer for turning the recommended action into one contained work block
- Activity Timeline local memory layer for recent project/global events, artifact creation, blockers, failures, and next tiny actions
- Artifact History read-only layer for inspecting older generated outputs without changing latest-artifact behavior
- Local Backup & Restore v1 for local-only backup ZIP creation, verification, and explicit restore
- Setup Doctor & First Run Onboarding v1 for local-only runtime readiness checks, compact setup guidance, and Create App-first onboarding
- Guided Demo Project v1 for a deterministic local sample project that walks through sprint, prototype, build pack, workspace, release, feedback, and next-step artifacts without needing a real idea first

## Activity Timeline v1

SprintOS now includes a compact **Activity Timeline** for each project plus a small **Recent Activity** block on the Today Dashboard.

- It is the local memory layer for what happened, when it happened, what artifact or report was produced, what failed or was blocked, and what the next tiny action was.
- It is local-only and best-effort. Timeline recording should never break the primary project, export, pipeline, workspace, or AI-routing flow.
- It supports the Today Dashboard and Project Command Center as an additive recency/explanation source. It does not replace their deterministic recommendation rules.
- It never stores `.env` contents, API keys, Authorization headers, raw provider prompts, raw provider responses, or full workspace file contents.
- Manual notes are supported through the project timeline panel and the local `/api/add_activity_event` endpoint.
- Timeline exports stay local and are included in Markdown/ZIP project exports as `activity-timeline.md`.

## Technical Details And History

SprintOS now includes a compact **Artifact History** panel in the selected project view, but it is intentionally treated as technical detail instead of the main success surface.

- It is read-only and local-only.
- It does not change the existing latest-artifact panels or latest-artifact recommendation behavior.
- It groups older generated outputs such as Quick Launch runs, pipeline runs, prototype/deploy/build artifacts, workspace artifacts, verification runs, Focus Sessions, release iterations, and recent activity.
- The main lane should foreground app preview, app source, app testing, and testing-package status before any of these internal artifact concepts.
- It exposes only safe metadata plus existing safe report/ZIP links and prompt-copy affordances where available.
- It never reads or exports `.env` contents, API keys, Authorization headers, raw provider prompts/responses, or full workspace file contents.
- History exports stay local and are included in project ZIP exports as `artifact-history.md`.

## Today Dashboard v1

SprintOS now opens with a compact **Today / Continue** card above **Create App**.

- It is the global guidance layer across all projects.
- It is local-only and deterministic.
- It now leads with a single `Continue` recommendation and keeps `Create App` as the default creation path.
- It now keeps setup, backup, sample-project, and runtime details secondary behind compact disclosures instead of using them as first-open dashboard cards.
- It keeps the classic sprint planner available as `Plan Only` behind an advanced disclosure.
- It can reference recent Activity Timeline events to explain why a project is recent or why a recommendation is being surfaced.
- It does not replace the Project Command Center. The Command Center still owns project-level guidance inside the selected project view.
- It never invokes Codex automatically, never deploys automatically, never calls GitHub, never runs git, and never reads or exports `.env` contents.
- `Run Today Action` only resolves to safe local SprintOS actions or returns local prompts/paths/messages when the next move is intentionally manual.

## Setup Doctor & First Run Onboarding v1

SprintOS now includes a compact **Setup Doctor** near the top of the Today Dashboard.

- It is local-only and deterministic.
- It checks runtime readiness such as local folders, SQLite access, launcher files, backup state, AI mode safety, `.gitignore` / `.env.example`, and obvious hardcoded-key markers.
- It never reads or exports `.env` contents, never exposes API keys, never calls external APIs, and never runs the full test suite.
- It can only run two local actions directly: create the first local backup or verify the latest local backup through the existing backup helpers.
- All other recommended actions stay manual, such as switching AI back to offline mode, opening the Today Dashboard, or creating the first app.
- When no projects exist yet, SprintOS points the user to `Create App` first and keeps the sample app secondary.

## Guided Demo Project v1

SprintOS now includes a compact **Sample Project** entry point for first-run onboarding and local testing.

- It is local-only and deterministic.
- It uses offline generation by default and does not require an API key.
- It creates a normal SprintOS project called `AI Study Flashcard Helper`.
- Quick mode creates the project, sprint, app draft, app source package, Command Center state, and a demo report.
- Full mode also creates the app workspace, snapshot, change report, verification run, testing package, sample release feedback, and release iteration prompt.
- It never invokes Codex automatically, never deploys, never creates GitHub repos, never copies `.env`, and never stores raw provider prompts or responses.
- It writes report files under `exports/demo_runs/` and the resulting project/artifacts can be deleted like any other local SprintOS data.

## Project Command Center v1

SprintOS keeps the **Project Command Center** available in each selected project view behind Project Guidance.

- It is the main project guidance layer.
- It does not replace the advanced prototype, build, workspace, verification, or release panels.
- It reduces decision fatigue by answering one question clearly: what is the next safest move right now?
- App-First UI Simplification v1 keeps the latest generated app and its `Open Preview`, `Test App`, `Download App`, `Source Pack`, and `Prepare for Codex` actions ahead of the Command Center.
- It now also surfaces the latest timeline event so the user can see what last happened before acting again.
- Recommended actions stay local-only and deterministic.
- The Command Center never invokes Codex automatically, never deploys automatically, never calls GitHub, and never exports `.env` contents.
- The primary safe action button only runs local SprintOS actions such as prototype generation, pipeline runs, workspace export, snapshots, sync, verification, and release-pack creation.

## Focus Session v1

SprintOS now adds a compact **Focus Session** panel directly under the Project Command Center.

- It is the execution layer on top of the Command Center.
- It is local-only and stores session state in SQLite plus local report folders under `exports/focus_sessions/`.
- It never invokes Codex automatically, never deploys automatically, never calls GitHub, and never reads or exports `.env` contents.
- It is designed to reduce decision fatigue by answering five questions clearly:
  - what am I doing right now?
  - what is the exact done definition?
  - what should I not do in this session?
  - what is the next tiny action?
  - what happened when the session ended?
- Sessions can be started for `15`, `30`, `60`, or `120` minutes.
- SprintOS captures a progress note, a completion/stop report, a resume note, and a Codex follow-up prompt only when that handoff is actually relevant.

## App-First UI Simplification v1

SprintOS now keeps the default UI centered on the app-generation lane:

- Create App
- Follow-up questions / assumptions
- Latest Generated App
- Open Preview
- Test App
- Download App
- Source Pack
- Prepare for Codex

It groups secondary project and technical tools into collapsible sections:

- Project Guidance
- Advanced App Tools
- Developer Tools
- Feedback
- Technical Details
- AI

- The main user should not need to understand Build Packs, Deploy Packs, pipeline reports, or workspace-sync reports in order to see that SprintOS created an app.
- App preview, app source, app testing, and testing-package status should stay more prominent than internal report or ZIP links.

- Project Guidance is collapsed by default so Focus Session, Activity Timeline, and Artifact History do not compete with the app card.
- Advanced App Tools and Developer Tools stay collapsed by default.
- Feedback opens by default when prototype or release feedback work already exists.
- Technical Details and AI stay collapsed by default unless the current state needs attention.
- The selected-project jump buttons use browser-only state. If the browser supports `localStorage`, open/collapsed section state is remembered there only. Nothing about this UI state is stored in SQLite or changes product behavior.
- UI Template Decomposition v1 keeps this surface in vanilla HTML/CSS/JS while moving low-risk rendering helpers into `sprintos_core/` so future UI edits do not keep expanding `sprintos.py`.

## Run locally

```bash
cd sprintos_mvp
python3 scripts/launch.py
```

Classic start:

```bash
python3 sprintos.py
```

macOS double-click:

```bash
chmod +x run_sprintos.command
./run_sprintos.command
```

The launcher waits for local health, opens the browser at:

```text
http://127.0.0.1:8844
```

To stop SprintOS:

```bash
Ctrl+C
python3 scripts/stop.py
```

Local data folders:

```text
data/sprintos.sqlite
exports/
workspaces/
backups/
```

Safety notes:

- `.env` stays local and ignored.
- The launcher does not upload anything.
- The launcher does not print or expose API keys.

## Testing

Fast iteration check:

```bash
python3 scripts/test_fast.py
```

Full regression check:

```bash
python3 scripts/test_full.py
```

Standalone commands:

```bash
python3 -m unittest
python3 scripts/smoke.py
python3 scripts/health.py
```

## Is SprintOS ready?

Start:

```bash
python3 scripts/launch.py
```

Run health:

```bash
python3 scripts/health.py
```

Run readiness:

```bash
python3 scripts/readiness.py
```

Try sample project:

- Use Sample Project in the UI.

Try real idea:

- Use Create App.

Demo-ready app generation coverage and a concise demo script are in [`docs/DEMO_READINESS.md`](docs/DEMO_READINESS.md).

## AI App Generator v1

SprintOS can now use its existing optional provider layer to generate actual local prototype app files from an idea during `Create App`.

- It generates small vanilla `index.html`, `style.css`, `app.js`, `README.md`, and `TEST_PLAN.md` files when AI is usable.
- It still falls back to deterministic offline generation by default or whenever provider output is unavailable or invalid.
- Set `SPRINTOS_APP_GENERATION_FALLBACK_MODE=report_only` when you want true AI-only app generation testing. In this mode, Create App stops and writes a local failure report instead of creating offline app files.
- In `report_only` mode, schema validation failures stop before files are created; the app state says no app was created, no fallback was used, and no preview is available.
- Generated apps are local prototypes only, not production apps.
- Generated browser apps must stay previewable by opening `index.html`.
- Generated browser apps must never call OpenAI or DeepSeek directly, must never embed API keys, and must never rely on external CDNs.
- OpenAI app generation uses the Responses API `text.format` JSON Schema path with a shallow strict schema. DeepSeek uses JSON object mode and then the same SprintOS validator.
- SprintOS stores only redacted provider/result metadata such as provider, model, fallback reason, validation category, app type, and generated filenames.
- The `app_file_generation` task needs a larger budget than planning tasks. When no budget env values are set, SprintOS uses 90 seconds and 6000 output tokens for app generation while leaving generic planning defaults smaller.
- Deterministic fallback apps are intentionally app-specific for common shapes such as `Idea Scorecard`, `Budget Snapshot`, and `Study Card Builder`.
- Canonical app-shape contracts v1 are enforced after schema and safety checks for common generated app shapes. A business idea scorer must include `idea-input`, `score-idea`, `idea-score`, `idea-risks`, `idea-smallest-test`, and `idea-next-action` with the required template markers, and `app.js` must update those outputs from the idea text.
- A budget calculator must include numeric `budget-income` plus numeric expense inputs, `budget-run`, `budget-savings`, `budget-breakdown`, and `budget-recommendation` with the required template markers, and `app.js` must update those outputs from income and expense values.
- `app_shape_validation_failed` means the AI returned app files, but the files did not include the required app-specific surfaces. In `report_only` mode, SprintOS stops with a sanitized failure report instead of silently using template fallback.
- AI-only failure reports are written under `exports/app_generation_failures/` and include sanitized provider/model/category/retry metadata plus safe validation details such as missing fields, missing files, invalid filenames, app-shape failures, or safety failures. They do not store API keys, `.env` contents, raw prompts, raw provider responses, Authorization headers, or full stack traces.

## Optional AI mode

SprintOS stays offline/template-first by default. No API key is required for startup, tests, smoke, health, or normal use.

To opt in locally:

```bash
cp .env.example .env
```

Set only the values you want in `.env`, or export them in your shell.

Offline:

```bash
export SPRINTOS_AI_PROVIDER="offline"
export SPRINTOS_AI_ENABLED="false"
python sprintos.py
```

OpenAI:

```bash
export SPRINTOS_AI_PROVIDER="openai"
export SPRINTOS_AI_ENABLED="true"
export SPRINTOS_MODEL="gpt-4.1-mini"
export OPENAI_API_KEY="your_api_key_here"
python sprintos.py
```

DeepSeek:

```bash
export SPRINTOS_AI_PROVIDER="deepseek"
export SPRINTOS_AI_ENABLED="true"
export SPRINTOS_MODEL="deepseek-v4-flash"
export DEEPSEEK_API_KEY="your_deepseek_key_here"
python sprintos.py
```

On Windows PowerShell for OpenAI:

```powershell
$env:SPRINTOS_AI_PROVIDER="openai"
$env:SPRINTOS_AI_ENABLED="true"
$env:SPRINTOS_MODEL="gpt-4.1-mini"
$env:OPENAI_API_KEY="your_api_key_here"
python sprintos.py
```

If AI is disabled, the key is missing, the request fails, or the response is malformed, SprintOS falls back to deterministic offline output.

App generation fallback policy:

```bash
# Default: create a local template app if AI app generation fails.
export SPRINTOS_APP_GENERATION_FALLBACK_MODE="template"

# AI-only/report-only: stop and create a failure report if AI app generation fails.
export SPRINTOS_APP_GENERATION_FALLBACK_MODE="report_only"
```

`SPRINTOS_DISABLE_OFFLINE_APP_FALLBACK=true` is also accepted as a boolean alias for app generation. This only affects `app_file_generation` / Create App app draft generation; it does not disable offline SprintOS behavior globally.

Generation modes:

- `auto`: use the saved per-task route when one is enabled, otherwise use the global provider config, and still fall back safely if the provider is unusable or invalid.
- `offline`: force deterministic local output and skip provider calls.
- `ai`: attempt AI for that action, but still fall back safely if the provider is unavailable or the output is invalid.

Do not commit `.env`. Use `.env.example` as the template. `.env` stays local and ignored. OpenAI and DeepSeek keys are separate. No tests require a real provider call.

Recommended local budget for Create App with AI:

```bash
export SPRINTOS_AI_TIMEOUT_SECONDS="90"
export SPRINTOS_AI_MAX_OUTPUT_TOKENS="6000"
```

Restart `python3 sprintos.py` after changing `.env` or exported environment values. `/api/ai_status` reports both the generic provider budget and the app-generation budget without exposing keys.

## AI routing

SprintOS can route individual generation tasks to different provider/model preferences without storing secrets.

- Routes are saved locally in SQLite as task preferences only: task name, generation mode, provider, model, and enabled state.
- Keys are still read only from the local environment or repo-root `.env`.
- Schema validation and redacted diagnostics still run after every provider response.
- If a routed provider is disabled, missing a key, fails, or returns invalid output, SprintOS falls back to deterministic offline output.

Included presets:

- `Cheap DeepSeek`: route all supported tasks to `deepseek-v4-flash`.
- `Conservative OpenAI`: keep all supported tasks on OpenAI with the provider default model.
- `Offline Only`: force every supported task back to local deterministic generation.

The provider-aware app-generation task is `app_file_generation`. `Create App` and prototype generation use it automatically when the saved route or global provider config is usable.

## Provider comparison and cost estimates

SprintOS can run local provider evals and route recommendations without real provider calls by default.

- `Offline Eval` runs deterministic local fixtures across the supported AI tasks.
- `Fake Provider Eval` runs fake valid, malformed, and missing-field provider responses for OpenAI and DeepSeek with no network calls.
- `Live Provider Eval` is intentionally skipped by default in v1 unless you explicitly wire it in later.
- Cost figures are local estimates only, not billing truth.
- Eval rows and diagnostics never store API keys, raw prompts, or raw provider responses.

Local price estimates can be overridden with environment variables:

```bash
export SPRINTOS_OPENAI_INPUT_COST_PER_1M="0.60"
export SPRINTOS_OPENAI_OUTPUT_COST_PER_1M="2.40"
export SPRINTOS_DEEPSEEK_INPUT_COST_PER_1M="0.20"
export SPRINTOS_DEEPSEEK_OUTPUT_COST_PER_1M="0.80"
```

Recommended workflow:

1. Apply the `Cheap DeepSeek` preset.
2. Run offline evals.
3. Apply the latest route recommendations.
4. Use Create App.

## Generated AI Tool Runtime

SprintOS's own optional AI provider layer is separate from the runtime generated inside `ai_tool_stub` Build Packs.

- SprintOS still stays offline/template-first by default.
- SprintOS can optionally use OpenAI or DeepSeek to generate local prototype app files, but that generation stays separate from generated app runtime settings.
- Generated `ai_tool_stub` Build Packs now include a stdlib-only local `app.py` with a server-side `/api/generate` route.
- Generated apps default to mocked/offline output and do not require an API key for startup, tests, smoke, health, or normal local use.
- A generated app can opt into OpenAI locally only through its own `.env` next to the generated `app.py`.
- DeepSeek runtime support for generated apps is intentionally left as a separate follow-up task.
- Generated apps do not use the `openai` Python package and do not send provider requests from the browser.
- Generated app smoke tests and Run & Verify checks must pass without real network calls.

## Exporting a Build Pack to a Codex workspace

SprintOS can now promote the latest generated Build Pack into a stable local workspace under `workspaces/`.

- The workspace is for the generated app, not for SprintOS internals.
- SprintOS copies the Build Pack into a new local workspace folder, adds `CODEX_START_HERE.md`, `RUN_AND_TEST.md`, `WORKSPACE_README.md`, `SPRINTOS_ORIGIN.md`, `LOCAL_ONLY_NOTICE.md`, `workspace.json`, and manual git init scripts.
- `.env` is never copied into the workspace.
- The generated git helper scripts are manual only. SprintOS does not run them, does not create remotes, and does not push anywhere.

## Workspace Sync v1

SprintOS can inspect an exported workspace after Codex changes it and generate a local-only follow-up bundle under `exports/workspace_syncs/`.

- Workspace Sync never uploads code and does not call GitHub APIs.
- Workspace Sync never reads or exports `.env` contents.
- Workspace Sync stores only small local change summaries, report files, and safe metadata.
- If the workspace is a git repo, SprintOS uses local `git status --short`; otherwise it falls back to deterministic mtime checks.
- Workspace Sync only runs known generated smoke tests: `python3 tests/smoke_static.py` or `python3 tests/smoke_app.py`.
- Workspace Sync does not run arbitrary commands, does not launch long-lived servers, and does not invoke Codex automatically.

## Workspace Snapshot & Restore v1

SprintOS can create a local safety snapshot of an exported workspace before or after heavy Codex edits.

- Snapshots are stored under `exports/workspace_snapshots/`.
- Restore reports are stored under `exports/workspace_restores/`.
- Snapshot manifests are metadata/hash based only. SprintOS stores file paths, sizes, mtimes, and SHA256 values, not file contents.
- `.env` and other `.env*` files are excluded from snapshots.
- `.git` internals, `__pycache__`, `node_modules`, generated ZIPs, and obvious binary/cache files are excluded.
- Restore replaces restore-managed workspace files from the snapshot, preserves the workspace root, preserves existing `.env`, and does not restore `.git` internals.
- Snapshot compare is summary-only in v1: added, modified, removed, unchanged. It does not show full diffs.
- Snapshot/restore stays local-only. SprintOS does not invoke Codex, call GitHub APIs, create repos, push, or deploy during snapshot or restore.

## Local Backup & Restore v1

SprintOS can create a local-only backup ZIP for the repo state it manages and restore from that backup only through an explicit local action.

- Backups are stored under `backups/`.
- Backup reports are stored under `exports/local_backups/`.
- Restore reports are stored under `exports/local_restores/`.
- Backups include local SprintOS state such as `data/`, `exports/`, `workspaces/`, and core repo docs/code roots when present.
- `.env`, `.env*`, `.git` internals, backup ZIPs, caches, Authorization headers, and obvious API key leaks are excluded.
- `.env` is excluded from backups and must be recreated manually after moving machines or restoring state.
- Restore defaults to dry run. Real restore requires explicit confirmation.
- Review a backup before sharing it. Backups may include generated workspace/app source and local reports.

## Workspace Release Pack v1

SprintOS can package the latest exported workspace into a local release-candidate folder under `exports/workspace_releases/`.

- Release packs are local release candidates, not automatic deployments.
- SprintOS copies releasable workspace files into `app/` inside the release pack and preserves relative paths.
- `.env` and `.env*` files are excluded from the copied app folder and are never read into release reports.
- `.git` internals, `__pycache__`, `node_modules`, generated ZIPs, and obvious cache/binary files are excluded.
- SprintOS generates `RELEASE.md`, `RELEASE_NOTES.md`, `TESTER_INSTRUCTIONS.md`, `DEPLOY_OR_SHARE.md`, `CODEX_NEXT_PROMPT.md`, and `release-pack.json`.
- Release ZIPs are meant for manual review and manual sharing only.
- Review the release pack before sharing it. SprintOS does not deploy it automatically.

## Release Feedback Intake v1

SprintOS can collect local-only feedback for the latest Workspace Release Pack, summarize it, and generate the next Codex prompt for the exported workspace.

- Feedback can be added manually or imported from JSON if the shared app supports a local feedback export.
- Feedback stays local-only in SQLite plus local exports. SprintOS does not send it anywhere externally.
- Raw imported JSON is sanitized/redacted before storage so API keys, Authorization headers, `.env` content, prompts, and provider responses are not preserved.
- SprintOS generates a release-iteration brief and a release-iteration Codex prompt, but it does not invoke Codex automatically.
- Today Dashboard and Project Command Center can use release feedback state to recommend: share with testers, generate release iteration, copy the release-iteration prompt, or park the project.
- This completes the local release → test → feedback → iterate loop without adding backend collection, auth, or cloud sync.

## Workflows

Workflows live in:

```text
workflows/
```

Current defaults:

- `business_validation.json`
- `software_mvp.json`
- `digital_product.json`
- `content_batch.json`
- `resume_project.json`

To add a workflow, copy one JSON file, change the ID/name/description/rules, then restart the app.

## MVP rule

Do not overbuild SprintOS before using it.

The first real milestone is:

```text
Use SprintOS to finish one external artifact.
```

Examples:

- a landing page
- a local prototype
- a digital product outline
- a published post
- a sent outreach message
- a finished README

## Suggested first test

Paste this into SprintOS:

```text
I want to build a personal execution engine that turns my random ideas into 2-hour sprints, generates the assets, cuts scope, and saves the restart point when I lose interest.
```

Choose:

```text
Workflow: Software MVP Scope
Timebox: 2 hours
Energy: High
End output: local working prototype
```

Then hit **Generate Sprint**.

## Safety / operating rule

SprintOS should generate drafts, checklists, files, and plans. It should not automatically publish, spend money, send cold emails, or perform irreversible actions without your review.
