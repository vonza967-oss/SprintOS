# SprintOS Latest Next Codex Prompts

Date: 2026-05-08

## Decision

Recommended next implementation prompt: **Live AI App Generation Acceptance Test v1**.

Why this is first:

- App-specific fallback templates now exist and are covered by tests.
- Canonical app-shape contracts now exist and are covered by tests.
- Report-only mode now correctly stops without creating fallback app files.
- Current local OpenAI runtime reports app-generation ready and recent canonical AI success.
- The remaining gap is repeatable evidence that live AI generation produces working, safe app outputs across the canonical shapes.

## 1. Live AI App Generation Acceptance Test v1

### Goal

Make SprintOS able to run a deliberate, opt-in live provider acceptance check for canonical app generation and produce a redacted report that proves whether AI Create App is currently reliable.

### Why Now

SprintOS is past basic app-generation plumbing. The next risk is claiming reliability without a repeatable live acceptance signal.

### Scope

Read `AGENTS.md` first and preserve all local-first constraints.

Improve `scripts/live_app_generation_acceptance.py` and documentation so an operator can intentionally run live app-generation acceptance for:

- Business idea scorer / `Idea Scorecard`
- Budget calculator / `Budget Snapshot`
- Flashcard helper / `Study Card Builder`

For each case, the script should verify:

- AI was actually used.
- The app package exists.
- `index.html`, `style.css`, `app.js`, `README.md`, and `TEST_PLAN.md` exist.
- Preview URL/path is available.
- Prototype ZIP can be built.
- Safety checks pass.
- Canonical app-shape verification passes.
- The redacted diagnostic includes provider/model/status/duration but no raw provider payload.

### Files Likely Touched

- `scripts/live_app_generation_acceptance.py`
- `README.md`
- `docs/APP_GENERATION_ACCEPTANCE_CHECKLIST.md`
- `docs/ARCHITECTURE.md`
- `tests/test_ai_providers.py` only if adding no-live-by-default guard coverage

### Acceptance Criteria

- Running without `--confirm-live-provider` refuses with a clear message.
- Running with `--confirm-live-provider` creates a timestamped folder under `exports/live_app_generation_acceptance/`.
- The report includes per-case pass/fail for AI usage, preview, package, safety, and app-shape checks.
- Failure output is actionable and redacted.
- Reports do not include API keys, `.env` contents, Authorization headers, raw prompts, raw provider responses, or full stack traces.
- Normal tests, smoke, health, and `scripts/test_full.py` do not make live provider calls.

### Tests To Run

```bash
python3 scripts/test_fast.py
python3 scripts/smoke.py
python3 scripts/health.py
python3 -m py_compile sprintos.py tests/*.py scripts/*.py sprintos_core/*.py
```

Run if reasonable:

```bash
python3 scripts/test_full.py
```

Manual opt-in only:

```bash
python3 scripts/live_app_generation_acceptance.py --confirm-live-provider --provider openai
```

### What Not To Change

- Do not make live provider calls part of tests, smoke, health, or startup.
- Do not store or print API key values.
- Do not store raw prompts or raw provider responses.
- Do not add deployment, GitHub, git, background workers, or automatic Codex invocation.
- Do not redesign the UI.

## 2. App-Specific Verify v1.5

### Goal

Strengthen deterministic Test App checks so SprintOS catches generated apps that have the right files but broken or missing core behavior.

### Why Now

Once live acceptance is repeatable, the next quality gate is stronger verification of the app's input/action/output behavior.

### Scope

- Improve business idea scorer checks.
- Improve budget calculator checks.
- Improve flashcard helper checks.
- Keep checks static or lightweight; no required browser dependency.
- Keep failure messages app-first.

### Files Likely Touched

- `sprintos_core/verification_utils.py`
- `sprintos.py`
- `tests/test_testing_tools.py`
- `tests/test_sprintos.py`

### Acceptance Criteria

- Missing event handlers fail.
- Missing output updates fail.
- Missing local/mocked limitation note warns or fails as appropriate.
- Existing valid canonical templates pass.
- Tests remain offline.

### Tests To Run

```bash
python3 scripts/test_fast.py
python3 scripts/smoke.py
python3 scripts/health.py
python3 -m py_compile sprintos.py tests/*.py scripts/*.py sprintos_core/*.py
```

### What Not To Change

- Do not add live provider calls.
- Do not add a frontend framework.
- Do not redesign Test App UI.

## 3. Create App Preflight Clarity v1

### Goal

Make Create App's expected generation mode clear before the user starts a run.

### Why Now

Current status fields already know whether AI is ready, fallback is likely, or report-only is active. The UI should use that signal plainly.

### Scope

- Add concise preflight copy to Create App.
- Explain `report_only` versus template fallback.
- Show low-budget/recent-failure/provider-unavailable warnings in user-facing language.

### Files Likely Touched

- `sprintos.py`
- `tests/test_dashboard_flow.py`
- `tests/test_ui_helpers.py`

### Acceptance Criteria

- AI-ready state says AI app generation is ready.
- Template fallback state says SprintOS may use the local template.
- Report-only state says no app files will be created if AI fails.
- No secrets or `.env` values are exposed.

### Tests To Run

```bash
python3 scripts/test_fast.py
python3 scripts/smoke.py
python3 scripts/health.py
python3 -m py_compile sprintos.py tests/*.py scripts/*.py sprintos_core/*.py
```

### What Not To Change

- Do not change provider routing behavior.
- Do not add new AI providers.
- Do not change fallback policy defaults without explicit product decision.

## 4. Fallback Reason Translation v1

### Goal

Translate technical provider and validation failures into a small creator-friendly reason taxonomy in user-facing app state.

### Why Now

Fallback/report-only behavior is mostly correct, but trust depends on explaining failures without infrastructure language.

### Scope

- Map provider/internal failures into plain categories.
- Keep detailed diagnostics behind Technical Details.
- Keep all redaction guarantees.

### Files Likely Touched

- `sprintos.py`
- `sprintos_core/ai_diagnostics.py`
- `tests/test_ai_providers.py`
- `tests/test_dashboard_flow.py`

### Acceptance Criteria

- User-facing categories include provider busy, timed out, invalid AI output, app-shape validation failed, app safety validation failed, and offline template selected.
- Raw provider response text is not shown.
- Diagnostics remain useful and redacted.

### Tests To Run

```bash
python3 scripts/test_fast.py
python3 scripts/smoke.py
python3 scripts/health.py
python3 -m py_compile sprintos.py tests/*.py scripts/*.py sprintos_core/*.py
```

### What Not To Change

- Do not remove diagnostics.
- Do not expose raw provider payloads.
- Do not change report-only semantics.

## 5. Download / Source Confirmation v1

### Goal

Make it unmistakable which package is the runnable app and which package is the editable Codex/source handoff.

### Why Now

The core flow includes preview, download, inspect, and handoff. Package confusion weakens that flow even when app generation succeeds.

### Scope

- Tighten package summaries.
- List primary included files.
- Preserve existing ZIP behavior and safety exclusions.

### Files Likely Touched

- `sprintos.py`
- `tests/test_sprintos.py`
- `tests/test_dashboard_flow.py`

### Acceptance Criteria

- Download App is described as the runnable local app.
- Source Pack is described as editable source for Codex/local continuation.
- Package summaries include primary files.
- `.env*`, `.git`, raw prompts, raw provider responses, and obvious secrets remain excluded.

### Tests To Run

```bash
python3 scripts/test_fast.py
python3 scripts/smoke.py
python3 scripts/health.py
python3 -m py_compile sprintos.py tests/*.py scripts/*.py sprintos_core/*.py
```

### What Not To Change

- Do not add deployment automation.
- Do not add GitHub actions.
- Do not change package contents beyond safe summary metadata/copy unless tests require it.

## 6. Main-Lane Vocabulary Reduction v1

### Goal

Reduce visible internal artifact vocabulary in the default user path.

### Why Now

After reliability acceptance, the next adoption blocker is comprehension: users should see app actions, not pipeline internals.

### Scope

- Keep advanced panels available.
- Move internal terms behind advanced/technical disclosures where possible.
- Preserve behavior.

### Files Likely Touched

- `sprintos.py`
- `tests/test_ui_helpers.py`
- `tests/test_dashboard_flow.py`
- `README.md`

### Acceptance Criteria

- Default lane reads: Create App, Open App Preview, Download App, Source Pack, Test App, Prepare App for Codex, Create Testing Package.
- Build Pack, Deploy Pack, pipeline, route, diagnostics, and Artifact History do not dominate the main lane.
- Existing tests pass.

### Tests To Run

```bash
python3 scripts/test_fast.py
python3 scripts/smoke.py
python3 scripts/health.py
python3 -m py_compile sprintos.py tests/*.py scripts/*.py sprintos_core/*.py
```

### What Not To Change

- Do not remove advanced controls.
- Do not redesign the UI.
- Do not add a frontend dependency.

## 7. Git Safety Setup

### Goal

Create a safe local version-control baseline before more implementation work.

### Why Now

The repo is inside a Git worktree, but there are no commits on `main`. That makes rollback and review unsafe.

### Scope

- Add or document a local Git baseline only when the user explicitly approves.
- Keep `.env`, data, exports, backups, caches, and generated runtime files ignored.

### Files Likely Touched

- `.gitignore`
- Possibly docs only

### Acceptance Criteria

- `git status` is understandable before implementation begins.
- No secrets are committed.
- No GitHub remote, push, repo creation, or automation is added.

### Tests To Run

```bash
python3 scripts/health.py
```

### What Not To Change

- Do not call GitHub.
- Do not push.
- Do not deploy.
- Do not run destructive Git commands.

## What Not To Build Next

- Deployment automation.
- GitHub automation.
- More AI providers.
- User accounts/auth.
- Billing.
- Cloud sync.
- Public SaaS features.
- Background workers.
- Advanced analytics.
- More dashboards.
- More artifact types.
- UI framework rewrite.
- Automatic Codex invocation.
- App pattern memory before outputs are reliably good.

Reason: each item adds surface area, security risk, or product confusion while the core output quality and live acceptance story are still the limiting factors.
