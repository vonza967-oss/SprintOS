# SprintOS Latest System Review

Date: 2026-05-08

## Executive Summary

SprintOS is now a local app-generation workbench, not just a sprint planner. The main product promise is:

`idea -> Create App -> working preview -> download -> test -> inspect source -> hand to Codex`

The current repo is materially on track. The app-generation system has real provider integration, strict app-file validation, canonical shape contracts, local fallback templates, report-only AI failure mode, app preview/download/source paths, Test App checks, and Codex handoff artifacts.

The largest remaining gap is not basic plumbing. It is proof of reliability and quality under live provider conditions. The local runtime inspected for this review is currently OpenAI-backed, has an API key present, uses the recommended app-generation budget of 90 seconds / 6000 output tokens, runs in `report_only` fallback mode, and reports `app_generation_ready=true`. Recent local diagnostics show successful OpenAI app generation for the three canonical shapes. That is a strong signal, but it is still local state rather than a repeatable acceptance baseline.

Current verdict: **promising and increasingly app-first, but not yet public-product reliable.**

Recommended next implementation task: **Live AI App Generation Acceptance Test v1**.

## Files Inspected

Present and inspected:

- `README.md`
- `AGENTS.md`
- `docs/ARCHITECTURE.md`
- `docs/CODE_REVIEW.md`
- `docs/CODEX_TASKS.md`
- `docs/SPRINTOS_CURRENT_SYSTEM_REVIEW.md`
- `docs/SPRINTOS_CURRENT_RISK_REGISTER.md`
- `docs/SPRINTOS_CURRENT_OPPORTUNITIES.md`
- `docs/SPRINTOS_NEXT_CODEX_PROMPTS.md`
- `sprintos.py`
- `sprintos_core/`
- `scripts/`
- `tests/`

Not present before this review:

- `docs/SPRINTOS_LATEST_SYSTEM_REVIEW.md`
- `docs/SPRINTOS_LATEST_RISK_REGISTER.md`
- `docs/SPRINTOS_LATEST_OPPORTUNITIES.md`
- `docs/SPRINTOS_LATEST_NEXT_CODEX_PROMPTS.md`

Those four `LATEST` docs were created by this audit.

## Baseline Checks

Initial baseline:

| Command | Result |
| --- | --- |
| `python3 scripts/test_fast.py` | PASS, 58 tests in 2.57s |
| `python3 scripts/smoke.py` | PASS, `smoke ok` |
| `python3 scripts/health.py` | PASS, no obvious API keys found |
| `python3 -m py_compile sprintos.py tests/*.py scripts/*.py sprintos_core/*.py` | PASS |
| `python3 scripts/test_full.py` | PASS, 521 tests plus smoke and health in 104.84s |

Final baseline after writing docs:

| Command | Result |
| --- | --- |
| `python3 scripts/test_fast.py` | PASS, 58 tests in 2.70s |
| `python3 scripts/smoke.py` | PASS, `smoke ok` |
| `python3 scripts/health.py` | PASS, no obvious API keys found |
| `python3 -m py_compile sprintos.py tests/*.py scripts/*.py sprintos_core/*.py` | PASS |
| `python3 scripts/test_full.py` | PASS, 521 tests plus smoke and health in 106.16s |

## Runtime Endpoint Snapshot

Endpoint inspection used the running local server at `http://127.0.0.1:8844`. No `.env` contents or key values were printed.

| Endpoint | Current finding |
| --- | --- |
| `/api/server_status` | Healthy local SprintOS server, PID present, started `2026-05-08T23:30:07`, AI provider mode `openai`, latest backup status `none` |
| `/api/ai_status` | Provider `openai`, enabled true, key present true, usable true, model `gpt-5.4-mini`, 90s timeout, 6000 max output tokens |
| `/api/ai_status` app generation | `app_generation_ready=true`, `app_generation_ai_ready=true`, likely local template false, fallback mode `report_only`, offline fallback disabled |
| `/api/ai_routes` | 6 task routes exist, 0 enabled overrides, includes `app_file_generation`, `sprint_generation`, `codex_handoff`, `quick_launch_summary`, `prototype_content`, and `resume_plan` |
| `/api/ai_diagnostics?limit=20` | 20 recent diagnostics; latest sampled entries were successful OpenAI calls including `app_file_generation` |
| `/api/setup_doctor` | Warning state, score 92, 0 blockers, 1 warning: no local backup exists yet |
| `/api/today_dashboard` | 26 active projects, 19 Quick Launches, 1 active Focus Session, 3 blocked projects, recommendation is to continue the active Focus Session |

Current local database evidence:

- 26 projects
- 24 prototypes
- 19 Quick Launches
- 98 AI diagnostics
- 21 Build Packs
- 20 Deploy Packs
- 9 verification runs
- 0 local backups

Recent prototypes include successful AI-generated canonical shapes:

- `Idea Scorecard`, OpenAI, `business_idea_scorer`, used AI true
- `Budget Snapshot`, OpenAI, `budget_calculator`, used AI true
- `Study Card Builder`, OpenAI, `flashcard_helper`, used AI true

Older prototypes still show historical failures or fallback output, including DeepSeek timeout and OpenAI validation failure cases.

## What SprintOS Currently Is

SprintOS is a local-first app-generation system wrapped in a project guidance interface. It stores local project state in SQLite and generated artifacts in local folders. It keeps `python3 sprintos.py` as the main entrypoint and avoids required network services.

Its current center of gravity is Create App:

1. User enters a rough idea.
2. SprintOS creates or updates a project.
3. SprintOS generates a small local prototype app.
4. The user can open the preview.
5. The user can download the runnable app package.
6. The user can create/download a source package.
7. The user can test the app locally.
8. The user can prepare a Codex handoff prompt/workspace.

It also still contains earlier execution-system layers: Today Dashboard, Project Command Center, Focus Session, Activity Timeline, Artifact History, Build Packs, Deploy Packs, Workspace Export, Workspace Sync, Release Packs, feedback intake, Local Backup/Restore, Setup Doctor, and Guided Demo.

## What SprintOS Is Trying To Become

SprintOS is trying to become a reliable personal execution engine where a non-technical or semi-technical user can turn a messy prompt into a small working prototype app, inspect the source, test it, package it, and hand it to Codex for improvement without needing cloud setup or project-management overhead.

The correct near-term target is not "full product builder." It is "small local prototype generator that reliably produces inspectable, testable outputs."

## Current App-Generation Capabilities

Implemented:

- AI app-file generation for `index.html`, `style.css`, `app.js`, `README.md`, and `TEST_PLAN.md`.
- OpenAI app generation via Responses API structured output.
- DeepSeek app generation via Chat Completions JSON object mode.
- Shared schema validation after provider responses.
- App-shape validation for canonical surfaces.
- Static safety checks that reject path traversal, external URLs, browser-side provider calls, browser network calls, and obvious secret patterns.
- App-specific offline fallback templates for `Idea Scorecard`, `Budget Snapshot`, and `Study Card Builder`.
- Additional heuristic shapes for quiz recommenders and waitlist pages.
- One retry/repair path for transient provider failures, invalid JSON, JSON shape failures, and app-shape failures.
- Report-only mode for true AI-only testing.
- Sanitized failure reports under `exports/app_generation_failures/`.

## AI And Provider Capabilities

Implemented:

- Provider modes: `offline`, `openai`, `deepseek`.
- API keys are read from local environment or repo-root `.env`.
- OpenAI and DeepSeek keys are separated.
- AI route preferences can be persisted without storing keys.
- App-generation readiness is separate from generic provider usability.
- App generation has higher default budget handling than planning tasks.
- Diagnostics are redacted and metadata-only.
- Provider evals/tests are mocked/offline by default.

Current runtime state:

- OpenAI provider is enabled and usable.
- API key presence is true; key value was not printed.
- App-generation budget is currently at the recommended 90s / 6000 tokens.
- Fallback mode is currently `report_only`.
- Recent app generation result is `ai_success`.

## Fallback And Report-Only Behavior

Implemented:

- Default `template` mode can produce deterministic local app files when AI is unavailable or invalid.
- `report_only` mode stops when AI generation fails and creates a sanitized report instead of pretending a fallback app was created.
- Failure reports state that no app was created and no preview is available.
- Failure summaries include safe validation details such as missing files, invalid filenames, shape failures, and safety failure codes.
- Raw prompts, raw provider responses, API keys, Authorization headers, `.env` contents, and full stack traces are excluded by design.

Current concern:

- `report_only` is correct for acceptance testing, but too strict as a default user mode if the user expects a local app every time. The UI must keep the distinction clear.

## Preview, Download, Test, Inspect

Implemented:

- Prototype preview routes for generated local apps.
- ZIP download for runnable prototype packages.
- Build/source packs for editable Codex handoff.
- Test App / verification runs over latest artifacts.
- Deployment/readiness checks for static packages.
- Source package and workspace routes are path-safe by design.
- Package generation excludes `.env`, `.env*`, `.git`, secrets, raw prompts, and raw provider responses.

Remaining gap:

- Verification is mostly static/heuristic. It checks files and markers, but it does not fully prove browser interaction across all generated apps.

## Codex Handoff Capabilities

Implemented:

- Generated Codex handoff prompts.
- Build Packs with README, AGENTS, acceptance criteria, test plan, and implementation prompt.
- Workspace export to a stable local folder.
- Workspace Sync and release iteration prompts.
- No automatic Codex invocation.
- No GitHub calls.
- No deployment automation.

This is a strength. SprintOS is a good local "prepare for Codex" layer as long as the generated app itself is useful.

## Local-Only And Safety Posture

Strong current posture:

- Core runtime works offline.
- Local SQLite and filesystem exports.
- No required frontend dependencies or frameworks.
- AI optional.
- Tests mock provider calls.
- Health check scans source and exports for obvious key patterns.
- `.env` exists locally but was not printed.
- `.env.example` and `.gitignore` exist.
- Generated app validation blocks browser-side provider calls and obvious secrets.

Weak current posture:

- The repo has a Git worktree but no commits. There is no version-control safety net.
- No local backups exist yet.
- Route and artifact surface area is large, increasing future audit burden.

## What Is Not Built And Should Not Be Implied

SprintOS is not currently:

- A hosted SaaS product.
- A deployment platform.
- A GitHub automation system.
- A multi-user app.
- A billing/auth/account system.
- A cloud sync tool.
- A reliable arbitrary app generator for every prompt.
- A browser-tested generated-app runtime for every shape.
- An automatic Codex runner.

It should not be marketed or treated as any of those yet.

## Core Goal Evaluation

Goal: **User enters idea -> SprintOS generates a working testable prototype app.**

Overall current score: **7/10**

| Dimension | Score | Rationale |
| --- | ---: | --- |
| AI app-generation reliability | 7 | Current OpenAI runtime is ready and recent canonical app generation succeeded. Historical DeepSeek timeouts, app-shape failures, and provider errors remain real risks. |
| Generated app usefulness | 7 | Canonical templates and recent app names are much better. Usefulness is still not proven across varied prompts or live acceptance reports. |
| App-shape validation quality | 8 | Strong file contract and shape-specific surface checks exist. Static validation can still miss poor semantics or broken edge-case behavior. |
| Fallback/report-only clarity | 8 | Report-only failure mode correctly avoids pretending an app was created. User-facing mode clarity still needs polish. |
| Preview clarity | 7 | Preview routes and app-state actions exist. Some artifact vocabulary still competes with the app-first path. |
| Download/source clarity | 7 | Download App and Source Pack are separated. More package-content confirmation would reduce confusion. |
| Test App usefulness | 6 | Verification exists and catches important static issues. It does not yet prove full browser behavior for all shapes. |
| Codex handoff quality | 8 | Build Packs, prompts, workspaces, and next prompts are robust and local-only. Quality depends on the generated app being worth improving. |
| UI/app-first clarity | 6 | Create App and app state are prominent, but Build Pack, Deploy Pack, Workspace, pipeline, diagnostics, and history terminology remain heavy. |
| Local safety/security | 9 | Local-first design, redaction, package exclusions, and tests are strong. Route sprawl keeps residual risk. |
| Maintainability | 5 | `sprintos.py` is about 30,067 lines. Helper modules exist, but the main file still owns many domains. |
| Daily usability | 6 | The core lane is usable, but active Focus Sessions, dashboards, setup warnings, and advanced panels can distract from simply making an app. |
| Public product readiness | 5 | Good internal MVP, not yet ready for public claims of reliable AI app generation. |

## Top Strengths

1. **Local-first runtime**
   - What it is: SprintOS runs from local Python, SQLite, and filesystem exports.
   - Why it matters: The core app works without cloud dependency.
   - Preserve: Yes.

2. **AI is optional**
   - What it is: Offline/template generation remains available.
   - Why it matters: Provider failures do not have to block app creation.
   - Preserve: Yes.

3. **OpenAI and DeepSeek separation**
   - What it is: Provider modes and key names are separate.
   - Why it matters: It reduces cross-provider secret and configuration mistakes.
   - Preserve: Yes.

4. **Structured OpenAI path**
   - What it is: App generation uses Responses API structured output.
   - Why it matters: It reduces malformed provider output.
   - Preserve: Yes.

5. **Strict app-file validation**
   - What it is: Required files, allowed filenames, local links, network/provider call blocks, and secret pattern checks.
   - Why it matters: Generated apps stay inspectable and local-first.
   - Preserve: Yes.

6. **Canonical app-shape validation**
   - What it is: Business idea scorer, budget calculator, and flashcard helper have explicit surfaces and JS wiring checks.
   - Why it matters: Valid JSON is not enough; SprintOS now checks app-specific behavior markers.
   - Preserve: Yes.

7. **Report-only failure mode**
   - What it is: AI-only failures stop with sanitized reports instead of silent fallback.
   - Why it matters: SprintOS does not pretend an app exists when AI failed.
   - Preserve: Yes.

8. **App-specific fallback templates**
   - What it is: `Idea Scorecard`, `Budget Snapshot`, and `Study Card Builder` are shape-specific local apps.
   - Why it matters: Offline mode can still produce useful prototypes.
   - Preserve: Yes.

9. **Preview/download/source/Codex chain**
   - What it is: Generated apps can be previewed, zipped, source-packed, and handed to Codex.
   - Why it matters: It matches the core user flow.
   - Preserve: Yes.

10. **Strong offline test baseline**
    - What it is: 521 tests pass, smoke passes, health passes, provider tests are mocked.
    - Why it matters: Regression confidence is high without live provider dependency.
    - Preserve: Yes.

## Top Weaknesses

| Weakness | Severity | Evidence | Impact | Recommended fix | Blocks core goal? |
| --- | --- | --- | --- | --- | --- |
| Live provider acceptance is not a routine baseline | High | `scripts/live_app_generation_acceptance.py` exists but was not run in baseline checks | SprintOS can pass tests without proving live AI app quality | Make an opt-in acceptance run the next implementation/review gate, still never part of smoke/full tests | Yes, for AI reliability claims |
| Historical provider instability remains | High | Older diagnostics/prototypes show DeepSeek timeout, OpenAI validation failure, and fallback | Users may wait and receive no app in report-only mode | Track live acceptance by provider/model and keep fallback/report messages plain | Yes |
| Static verification cannot fully prove app behavior | High | Verification checks markers and JS wiring, not real browser interaction | Broken or low-quality interactions can still pass | Add lightweight app-specific behavior verification, preferably deterministic and dependency-light | Partially |
| Report-only can stop too often for normal users | Medium | Runtime fallback mode is `report_only` | Users expecting a prototype may get a report instead | Keep report-only as AI acceptance/testing mode; make user mode explicit | Partially |
| UI still exposes too much artifact vocabulary | Medium | README/UI/docs include Build Pack, Deploy Pack, pipeline, workspace, sync, history, diagnostics | User may not know which action creates or opens the app | Continue main-lane vocabulary reduction after acceptance evidence | No, but hurts adoption |
| No local backup exists | Medium | Setup Doctor warning, `local_backups` count is 0 | Local state can be lost | Create first backup and keep warning visible until done | No, but safety issue |
| Git repo has no commits | Medium | `git log` reports current branch has no commits | Review and rollback safety are weak | Add local Git safety setup when code changes resume | No, but high workflow risk |
| `sprintos.py` is too large | Medium | `wc -l` reports 30,067 lines | Changes are slower and riskier | Extract stable app-generation/report helpers after reliability tasks | No immediate block |
| App names and prototype labels can conflict | Low | Recent titles include `Budget Snapshot - Landing page` or `Idea Scorecard - Calculator` | The prototype type suffix can make app identity feel odd | Clean display names after reliability work | No |
| Today Dashboard can steer away from Create App | Low | Current recommendation is active Focus Session | Correct for state, but can distract from app-generation testing | Keep Create App visually obvious even when a session exists | No |

## Top Risks And Threats

1. Live provider instability.
2. Valid JSON but invalid app shape.
3. Fallback hiding real AI failure.
4. Report-only stopping too often.
5. Generated app structurally passes but is not useful.
6. API key leakage.
7. Browser-side provider calls in generated apps.
8. `.env` packaging regression.
9. Stale process or wrong `.env` runtime.
10. Overbuilding dashboards/artifacts before app generation is reliable.

Full table: `docs/SPRINTOS_LATEST_RISK_REGISTER.md`.

## Top Opportunities

1. Live AI App Generation Acceptance Test v1.
2. App-Specific Verify v1.5.
3. Create App Preflight Clarity v1.
4. Fallback Reason Translation v1.
5. Download/Source Confirmation v1.
6. Test App UI Consistency v1.
7. Main-Lane Vocabulary Reduction v1.
8. App naming cleanup.
9. App-generation runtime sanity checks.
10. Git/version-control safety.

Full details: `docs/SPRINTOS_LATEST_OPPORTUNITIES.md`.

## Exact Next Codex Prompt

The next best implementation prompt is in:

`docs/SPRINTOS_LATEST_NEXT_CODEX_PROMPTS.md`

Title: **Live AI App Generation Acceptance Test v1**

Why now: the core templates, shape contracts, report-only mode, and readiness fields are implemented. The next risk is proving repeatable live provider success for the canonical user promise without making normal tests call providers.

## What Not To Build Next

Do not build these until app generation is reliably producing useful app outputs:

- Deployment automation: distracts from local prototype reliability and adds irreversible risk.
- GitHub automation: not needed for local handoff and violates the current manual/local constraint.
- More providers: current OpenAI/DeepSeek paths need reliability evidence first.
- User accounts/auth: irrelevant to the local prototype goal.
- Billing: premature public-product infrastructure.
- Cloud sync: conflicts with local-first simplicity.
- Public SaaS features: current app generator is not reliable enough to support them.
- Background workers: adds lifecycle complexity before the synchronous path is solid.
- Advanced analytics: does not help users get a working app.
- More dashboards: increases decision fatigue.
- More artifact types: worsens vocabulary and maintenance sprawl.
- UI framework rewrite: high-cost distraction from output quality.
- Automatic Codex invocation: violates explicit product safety boundaries.
- App pattern memory: premature until current outputs are reliably good.
