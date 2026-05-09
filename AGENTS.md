# SprintOS Repo Guide

## Product Philosophy
- SprintOS is a personal execution engine for turning messy ideas into small finished sprints.
- Optimize for momentum, clarity, and visible outputs over completeness.
- Preserve the burst-workflow: idea, create app, open preview, improve, test, package.
- Treat `Create App` (the Quick Launch flow) as the default creation path and keep the classic sprint planner behind an advanced `Plan Only` disclosure.
- Treat the Today Dashboard as the global guidance layer across all projects: one clear cross-project state, one best project to continue, one safe global action.
- Treat the Project Command Center as the main guidance layer for the selected project: one clear state, one recommended next action, one safe way forward.
- Treat Focus Session as the execution layer on top of the Project Command Center: one contained session, one exact done definition, one saved restart point.
- Treat Activity Timeline as the local memory layer for what happened, what app or package was created, what failed or was blocked, and what the next tiny action was.
- Treat Artifact History as the read-only local inspection layer for older generated outputs while keeping latest-artifact behavior unchanged and visually secondary.
- Treat Setup Doctor as the compact local runtime readiness layer: one clear setup status, one safe recommended setup action, and one first-run nudge toward Create App or the Sample App.
- Keep the selected project view visually ordered: App Draft summary first, Command Center next, Focus Session next, Activity Timeline compact, and advanced panels grouped under Execute, Advanced Build Controls, App Workspace, Feedback, Technical Details, and AI.
- Keep advanced tools available but visually secondary. The user should not need to understand Build Packs, Deploy Packs, pipeline reports, or workspace internals to see that SprintOS created an app. Do not add new user-facing feature surface until the simplified main lane has been tested.

## Local-First Constraint
- Keep the app fully usable without network access or third-party services.
- Keep Local Launcher behavior local-only, dependency-free, and centered on `python3 sprintos.py` plus local health/status checks.
- Store project state locally in SQLite and filesystem exports.
- Treat AI calls as optional augmentation, never as a required runtime dependency.
- Keep offline/template mode as the default.
- Support SprintOS AI provider modes as `offline`, `openai`, or `deepseek`.
- When AI is usable, SprintOS may generate local prototype app files, but those files must remain small, browser-previewable, and fully local-first.
- Read API keys only from the local environment or repo-root `.env`.
- Keep SprintOS AI config separate from any generated `ai_tool_stub` app runtime config. Generated apps may use only their own local `.env` beside the generated `app.py`.
- Keep OpenAI and DeepSeek keys separate. Never use `OPENAI_API_KEY` for DeepSeek or `DEEPSEEK_API_KEY` for OpenAI.
- AI provider routes may persist task/provider/model preferences only. They must never store keys.
- AI route resolution must preserve offline fallback even when a routed provider is missing a key or globally disabled.
- Provider evals must run local/offline by default. Live provider eval stays opt-in only and must never run in tests, smoke, or health.
- Never store API keys in SQLite, logs, exports, ZIPs, metadata JSON, or generated artifacts.
- Browser-side generated prototype files must never call OpenAI or DeepSeek directly, must never use external CDNs as a requirement, and must never embed hardcoded keys or obvious secret patterns.
- Treat `app_file_generation` as higher-budget than planning tasks. Recommended local values are `SPRINTOS_AI_TIMEOUT_SECONDS=90` and `SPRINTOS_AI_MAX_OUTPUT_TOKENS=6000`; generic planning tasks do not need to inherit a larger budget.
- Keep app-generation fallback policy scoped to `app_file_generation`. Default `SPRINTOS_APP_GENERATION_FALLBACK_MODE=template` preserves local template fallback; `report_only` is AI-only mode and must stop with a sanitized local failure report instead of writing offline app files.
- In `report_only` mode, schema or app-shape failures must say no app was created, no fallback was used, and no preview is available.
- Keep the `app_file_generation` provider contract shallow: top-level app metadata plus a `files` array limited to `index.html`, `style.css`, `app.js`, `README.md`, and `TEST_PLAN.md`; keep stronger file/app safety checks in SprintOS validation.
- Canonical app-shape contracts v1 must stay explicit in prompts and validation. Business idea scorer requires `idea-input`, `score-idea`, `idea-score`, `idea-risks`, `idea-smallest-test`, and `idea-next-action` with the expected template markers and local `app.js` updates. Budget calculator requires numeric `budget-income`, numeric expense inputs, `budget-run`, `budget-savings`, `budget-breakdown`, and `budget-recommendation` with the expected template markers and local `app.js` updates.
- `app_shape_validation_failed` means the AI returned app files, but the app did not include required app-specific surfaces. In `report_only`, stop with a sanitized failure report instead of silently using template fallback.
- OpenAI app generation must use Responses API `text.format` JSON Schema structured output. DeepSeek app generation must use JSON object mode and the same shared SprintOS validation path.
- Keep fallback apps app-specific for the canonical shapes: `Idea Scorecard`, `Budget Snapshot`, and `Study Card Builder`.
- Cost figures are local estimates only. Do not present them as provider billing truth.
- Never store raw prompts, raw provider responses, or keys in eval rows or diagnostics.
- AI-only failure reports may include safe validation details such as missing fields/files, invalid filenames, app-shape failures, and safety failure codes, but must never include API keys, `.env` contents, raw prompts, raw provider responses, Authorization headers, or full stack traces.
- Activity Timeline entries must stay local-only, best-effort, redacted, and free of `.env` contents, API keys, Authorization headers, raw prompts, raw provider responses, and full workspace file contents.
- Artifact History endpoints/exports must stay local-only, metadata-only, redacted, and free of `.env` contents, API keys, Authorization headers, raw prompts, raw provider responses, and full workspace file contents.
- Workspace exports are generated app workspaces, not SprintOS internals. Codex should keep app work inside the exported workspace folder instead of editing SprintOS-generated artifacts in place.
- Workspace release packs are local release candidates built from exported workspaces, not deployments or repo operations.
- Workspace release packs must never copy `.env` or `.env*` files, must never copy `.git` internals, and must never store secrets in release reports, metadata, or ZIPs.
- Generated app exports and ZIPs must never include `.env`, `.env*`, `.git`, obvious secrets, raw prompts, or raw provider responses.
- Workspace release packs must never run deployment actions, git, GitHub, or Codex automatically.
- Release feedback intake is local-only and must never send tester data externally.
- Release feedback intake may store manual notes or sanitized imported JSON only. It must never store `.env` contents, API keys, Authorization headers, raw prompts, or raw provider responses.
- Release iteration prompts are local planning artifacts for the exported workspace. They must never invoke Codex automatically.
- Workspace snapshots are local safety copies of exported workspaces, not a deployment or repo feature.
- Workspace snapshots must never copy `.env` or `.env*` files, must never copy `.git` internals, and must never store secrets in manifests or reports.
- Workspace restore must preserve an existing workspace `.env`, stay inside the workspace folder, and must not run commands, git, GitHub, or deployment actions.
- Local backups are local safety copies of SprintOS state, not sync, deployment, or hosting features.
- Local backups must never copy `.env` or `.env*` files, must never copy `.git` internals, must never include backup ZIP recursion, and must never store secrets in manifests or reports.
- Local backup restore must default to dry run, require explicit confirmation for real restore, preserve any existing `.env`, stay inside the SprintOS repo root, and must not run commands, git, GitHub, or deployment actions.
- Launcher and stop helpers must never print secrets, read/export `.env` contents, call external services, or kill arbitrary processes automatically.

## No Overbuilding
- Prefer one-file or one-function changes when they solve the problem cleanly.
- Avoid introducing frameworks, background workers, auth, sync, or cloud features.
- Keep workflows simple enough to verify manually in one local session.
- Prefer extracting shared helpers into `sprintos_core/` over continuing to grow `sprintos.py` when the behavior is already stable and duplicated.
- Future UI changes should prefer small rendering helpers in `sprintos_core/` over expanding `sprintos.py` inline.
- Preserve `python3 sprintos.py` as the main app entrypoint.
- Do not replace detailed panels with the Command Center; keep it as a thin layer above them.
- Do not replace detailed panels or latest-artifact summaries with Artifact History; keep history as a compact secondary inspection layer.
- Preserve vanilla HTML, CSS, and JS. Do not add frontend dependencies or a frontend framework.

## Standard Verification Commands
```bash
python3 scripts/test_fast.py
python3 scripts/test_full.py
python3 -m unittest
python3 scripts/smoke.py
python3 scripts/health.py
python3 -m py_compile sprintos.py tests/*.py scripts/*.py sprintos_core/*.py
```

## Recommended Verification Levels
During development:
- `python3 scripts/test_fast.py`
- `python3 scripts/smoke.py`

Before final report:
- `python3 scripts/test_full.py`
- `python3 -m py_compile sprintos.py tests/*.py scripts/*.py sprintos_core/*.py`

## Code Style Expectations
- Use Python standard library only unless the repo already depends on something else.
- Keep logic explicit and readable; avoid abstraction layers that hide the core flow.
- Prefer deterministic helpers over clever state machines.
- Sanitize filenames and preserve local export behavior.
- Schema-validate AI output before using it.
- Keep OpenAI on the existing Responses API path and DeepSeek on the Chat Completions path.
- Validate AI-generated app files before writing them: require the core local files, block path traversal, block external CDN/script URLs, block browser-side provider calls, and fall back offline on invalid output.
- Fall back to deterministic local output when AI output is missing, malformed, vague, or invalid for the requested task shape.
- Keep AI diagnostics redacted and never persist raw prompts or raw provider responses by default.

## Testing Expectations
- `python3 sprintos.py` must still work without an API key.
- AI provider tests must not make real network calls.
- OpenAI and DeepSeek tests must stay mocked/offline by default.
- AI route tests must not make real provider calls.
- Per-action offline mode must keep working even when AI is globally configured.
- Generated `ai_tool_stub` Build Pack smoke tests and Run & Verify checks must stay mocked/offline by default and must not require a real API key or real network call.
- Add or update unit tests for every behavior change in persistence, exports, and handoff generation.
- Add or update tests when prototype package generation, preview serving, or prototype ZIP behavior changes.
- Add or update tests when deploy-pack generation, readiness checks, deploy ZIP behavior, or deploy file serving changes.
- Add or update tests when Build Pack generation, Build Pack ZIP behavior, Build Pack file serving, or generated Build Pack smoke tests change.
- Add or update tests when one-click pipeline runs, pipeline reports, pipeline ZIP behavior, or pipeline file serving changes.
- Add or update tests when Quick Launch orchestration, report folders, Quick Launch ZIP behavior, or Quick Launch file serving changes.
- Add or update tests when Today Dashboard summaries, ranking, export behavior, API routes, or project-list badges change.
- Add or update tests when Run & Verify scopes, verification report folders, verification ZIP behavior, or verification file serving changes.
- Add or update tests when Focus Session persistence, report folders, ZIP behavior, or file serving changes.
- Add or update tests when Workspace Sync inspection, report folders, import-note behavior, ZIP behavior, or file serving changes.
- Add or update tests when Workspace Release Pack creation, copied-file rules, report folders, ZIP behavior, or file serving changes.
- Add or update tests when release feedback intake, release iteration summaries, release-iteration Codex prompts, or release-feedback export behavior changes.
- Add or update tests when Workspace Snapshot creation, compare, restore, ZIP behavior, or file serving changes.
- Add or update tests when Local Backup or Local Restore creation, verification, report generation, ZIP behavior, dashboard status, or file serving changes.
- Add or update tests when prototype feedback capture, import, summaries, or iteration briefs change.
- Keep the smoke script passing for end-to-end local verification.
- Preserve current sprint generation, Codex handoff generation, Markdown export, and ZIP export paths.
- Preserve the local-only prototype feedback loop and keep it backend-free by default.
- Keep Deploy Packs static, portable, and manually hostable without adding deployment APIs or cloud automation.
- Keep Codex Build Packs local, dependency-light, repo-style, and ready to hand to Codex without auto-creating repos or auto-deploying anything.
- Keep Workspace Export folders local, stable, and safe to hand to Codex without copying `.env`, auto-running git, auto-creating remotes, or auto-deploying anything.
- Keep Workspace Sync local-only, deterministic, and limited to safe file inspection plus known generated smoke tests.
- Keep Workspace Release Pack local-only, deterministic, path-safe, and limited to copied releasable files plus generated release/tester/deploy docs.
- Keep release feedback intake local-only, deterministic, path-safe, and limited to structured tester notes plus sanitized imported JSON.
- Keep Workspace Snapshot and Restore local-only, deterministic, path-safe, and metadata-only beyond the copied workspace files themselves.
- Keep Local Backup and Restore local-only, deterministic, path-safe, secret-scanned, and explicit about dry-run versus confirmed restore.
- Keep one-click pipeline runs synchronous, deterministic, local-first, and transparent about warnings/blockers.
- Keep Run & Verify deterministic, local-first, path-safe, and limited to known generated artifact checks.
- Only execute generated smoke tests from known generated Build Pack folders with explicit subprocess command lists, timeouts, captured output, and no `shell=True`.
- Keep Today Dashboard recommendations deterministic, local-only, and limited to one primary global next action.
- Use Activity Timeline as an additive recency/memory source for Today Dashboard and Command Center summaries without replacing their deterministic recommendation rules.
- Today Dashboard must never invoke Codex automatically, deploy automatically, call GitHub, run git, or read/export `.env` contents.
- Keep Project Command Center recommendations deterministic, local-only, and limited to one primary next action.
- Project Command Center must never invoke Codex automatically, deploy automatically, call GitHub, or read/export `.env` contents.
- Focus Session must stay local-only, must never invoke Codex automatically, and must never expose `.env` contents or API keys in its reports or ZIPs.
- Guided Demo runs must stay local-only, deterministic, offline-first, and limited to safe existing SprintOS flows plus demo reports. They must never call external APIs, invoke Codex, deploy, create GitHub repos, or copy `.env`.

## Review Checklist
- Does the change keep the app local-first?
- If Activity Timeline is touched, does it stay best-effort, redact secrets, avoid raw provider content, and preserve primary flows when event recording fails?
- Does optional AI still fall back cleanly to offline output?
- Is AI output schema-validated before it changes persisted/output state?
- Do invalid AI outputs fall back safely without breaking startup, tests, smoke, or health?
- Do AI routes avoid storing keys and preserve offline fallback when the routed provider is unusable?
- Are API keys kept out of code, logs, exports, and generated artifacts?
- Are diagnostics redacted and free of raw prompts/responses?
- Is the solution small enough for one PR and one verification pass?
- Are existing exports, sprint generation, and handoff flows preserved?
- If prototype packages are touched, do preview routes stay path-safe and backend-free?
- If deploy packs are touched, do readiness checks stay deterministic and do deploy routes stay path-safe and static-only?
- If Build Packs are touched, do build targets stay dependency-free by default and do build-pack routes stay path-safe?
- If the one-click pipeline is touched, does it preserve partial output, skip Deploy Pack generation when readiness blockers exist, and keep report routes path-safe?
- If Quick Launch is touched, does it create the project automatically, reuse the existing pipeline, preserve partial output, and keep Quick Launch report routes path-safe?
- If Run & Verify is touched, do verification runs stay local-only, keep report routes path-safe, and avoid executing arbitrary commands from metadata?
- If Workspace Export is touched, does it stay path-safe, avoid copying `.env`, avoid hardcoded keys, and avoid auto-running git helpers or creating remotes?
- If Workspace Release Pack is touched, does it stay path-safe, avoid copying `.env`, avoid `.git` internals, avoid secret export, and avoid deployment automation?
- If release feedback intake is touched, does it stay local-only, redact secrets, avoid raw provider content, and avoid external calls or command execution?
- If Workspace Snapshot or Restore is touched, are `.env` files excluded from snapshots, preserved on restore, and kept out of reports/exports?
- If Local Backup or Restore is touched, are `.env` files excluded, are backup ZIPs excluded from recursion/export, are secrets scanned/redacted, and is real restore still explicitly confirmed?
- If the feedback loop is touched, does it stay local-first and deterministic?
- If Today Dashboard is touched, does it still reduce decision fatigue to one clear global recommendation without replacing Create App or the Project Command Center?
- If Guided Demo is touched, does it still create a normal local SprintOS project/artifact chain rather than special-case runtime behavior after project creation?
- If the Project Command Center is touched, does it still reduce decision fatigue to one clear recommended next action without hiding the advanced panels?
- If browser UI state is added, does it stay browser-local only and avoid SQLite persistence?
- Are defaults safe for legacy data and missing fields?
- Are filenames, status values, and persisted fields normalized?

## Task Sizing
- Keep tasks PR-sized.
- Prefer the smallest shippable slice that improves restart momentum without creating a project-management system.
