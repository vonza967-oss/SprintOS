# App Generation Fix Roadmap

Date: 2026-05-08

## Priority 0 - Must Fix Before Trusting App Generation

### App Generation Reliability v1

Problem: Generic AI status says the provider is usable, while current app generation falls back because DeepSeek returns 503.

Why it matters: Users need to know whether Create App is likely to use AI or local fallback before they wait.

Proposed fix: Add app-generation readiness to `/api/ai_status` and Setup Doctor using recent `app_file_generation` diagnostics, timeout, max output tokens, provider, model, and key presence.

Effort: M

Expected impact: Fewer confusing Create App runs and clearer fallback trust.

Files likely touched: `sprintos.py`, `sprintos_core/ai_provider.py`, `sprintos_core/ai_diagnostics.py`, `tests/test_ai_providers.py`, `tests/test_dashboard_flow.py`.

Acceptance criteria:

- AI status exposes `app_generation_ready`, `app_generation_warning`, and last app-generation fallback.
- Setup Doctor warns when app-generation budget is below recommended thresholds.
- No keys or raw provider responses are exposed.

### Visible Fallback Result

Problem: Create App can silently produce offline output after an AI request fails.

Why it matters: Users may judge the AI generator by generic fallback output without realizing fallback occurred.

Proposed fix: Show a plain result banner: `AI unavailable. SprintOS used the local template.` Include retry/provider next action.

Effort: S

Expected impact: Higher trust and easier debugging.

Files likely touched: `sprintos.py`, `sprintos_core/ui_helpers.py`, `tests/test_ui_helpers.py`.

Acceptance criteria:

- App Draft and Create App result show fallback status outside Technical Details.
- Message is redacted and does not include secrets or raw responses.

### Draft-Level Test App

Problem: `Test App` is disabled until Prepare App for Codex creates a workspace.

Why it matters: The user goal includes testing the generated app immediately after preview.

Proposed fix: Allow `run_verification` from App Draft state for latest prototype/deploy/build pack.

Effort: S

Expected impact: App-first flow becomes preview, test, download, inspect without an unnecessary workspace step.

Files likely touched: `sprintos.py`, `tests/test_dashboard_flow.py`, `tests/test_testing_tools.py`.

Acceptance criteria:

- App Draft `Test App` is enabled when prototype/build/deploy artifacts exist.
- Verification report explains missing Quick Launch only as a warning when applicable.

## Priority 1 - Next Improvement

### App Quality Prompt Tuning v1

Problem: Fallback and failed-AI outputs can be generic shells.

Why it matters: Users need a useful app, not a reusable scoring template.

Proposed fix: Add app-shape-specific instructions for idea scorer, budget calculator, and flashcard helper. Require visible domain outputs in `app.js`.

Effort: M

Expected impact: More outputs feel like real apps.

Files likely touched: `sprintos.py`, `sprintos_core/ai_schemas.py`, `tests/test_ai_providers.py`, `tests/test_sprintos.py`.

Acceptance criteria:

- Idea scorer includes textarea, score, risks, smallest testable version, next action.
- Budget calculator includes numeric income/expense inputs, savings score, breakdown, recommendation.
- Flashcard helper includes textarea, generate action, question/answer card output, clear mocked-local note.

### App-Specific Verify v1

Problem: Verification catches missing files but not weak behavior.

Why it matters: A broken or generic app can pass.

Proposed fix: Add lightweight static and smoke checks keyed by `app_type` plus detected domain terms.

Effort: M

Expected impact: Better quality gate without dependencies.

Files likely touched: `sprintos.py`, `sprintos_core/verification_utils.py`, `tests/test_testing_tools.py`.

Acceptance criteria:

- Verification flags flashcard apps without question/answer result surfaces.
- Verification flags budget apps without numeric inputs and spending/savings output terms.
- Verification flags idea scorer apps without risk and next-action output terms.

### Download Clarity v1

Problem: `Download App Package` can mean Deploy Pack while source/test files live in Build Pack.

Why it matters: Users need one clear package and one source package.

Proposed fix: Rename primary to `Download App` and add secondary `Download Source Pack`.

Effort: S

Expected impact: Less artifact confusion.

Files likely touched: `sprintos.py`, `tests/test_dashboard_flow.py`.

Acceptance criteria:

- Deploy ZIP is labeled as runnable app package.
- Build Pack ZIP is labeled as source package for Codex.
- Both exclude `.env*`.

## Priority 2 - Quality and Polish

### Deterministic App Naming

Problem: Fallback names are truncated prompt fragments.

Why it matters: App Draft should feel like a created app.

Proposed fix: Add a local app-name helper that maps common prompts to concise names.

Effort: S

Expected impact: Better first impression.

Files likely touched: `sprintos.py`, `sprintos_core/text_utils.py`, tests.

Acceptance criteria:

- Business prompt becomes a concise name like `Idea Score`.
- Budget prompt becomes `Budget Snapshot`.
- Flashcard prompt becomes `Study Cards`.

### Standardize Test Plan Naming

Problem: AI requires `TEST_PLAN.md`; prototype writes `test-plan.md`; Build Pack writes `TEST_PLAN.md`.

Why it matters: Naming inconsistency makes inspection and acceptance docs harder.

Proposed fix: Keep backward compatibility but standardize user-facing naming.

Effort: S

Expected impact: Cleaner packages and docs.

Files likely touched: `sprintos.py`, `sprintos_core/constants.py`, tests.

Acceptance criteria:

- Every user-facing package has one obvious test plan.
- Existing routes and older packages still work.

## Priority 3 - Later

### Extract App Generation Core Helpers

Problem: App generation, validation, packaging, UI state, and verification span the monolith.

Why it matters: Future changes are harder to reason about.

Proposed fix: Move stable app-generation helpers into `sprintos_core/app_generation.py` after behavior is stable.

Effort: L

Expected impact: Maintainability.

Files likely touched: `sprintos.py`, new `sprintos_core/app_generation.py`, tests.

Acceptance criteria:

- No behavior change.
- Existing commands and routes still pass.

### Opt-In Live Acceptance Script

Problem: Live provider acceptance is manual.

Why it matters: Budget, latency, and JSON reliability regressions can pass offline tests.

Proposed fix: Add `scripts/live_app_generation_acceptance.py` that is opt-in only and never run by smoke/health/tests.

Effort: M

Expected impact: Better release confidence for live AI mode.

Files likely touched: `scripts/live_app_generation_acceptance.py`, docs.

Acceptance criteria:

- Requires explicit env opt-in.
- Redacts diagnostics.
- Tests three canonical prompts and reports preview/package/safety results.
