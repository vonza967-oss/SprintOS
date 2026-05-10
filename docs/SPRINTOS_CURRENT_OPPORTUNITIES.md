# SprintOS Current Opportunities

Date: 2026-05-08

## Top Opportunities

### 1. App Quality Templates v1

Why it matters: The core promise survives provider outages only if offline fallback feels like the requested app, not a generic shell.

Effort: M

Expected impact: High

Files likely touched:

- `sprintos.py`
- `sprintos_core/verification_utils.py`
- `tests/test_sprintos.py`
- `tests/test_dashboard_flow.py`

Acceptance criteria:

- Business idea scorer renders idea input, score, risk breakdown, smallest testable version, and next action.
- Budget calculator renders income/expense inputs, savings, spending breakdown, and recommendation.
- Flashcard helper renders notes input and question/answer cards with clear local/mock note.
- Current fallback app names are concise and not raw prompt fragments.
- Verification commands pass.

### 2. App-Specific Verify v1.5

Why it matters: Current verification checks app surfaces, but it still does not prove the user can run the app and see behavior change.

Effort: M

Expected impact: High

Files likely touched:

- `sprintos_core/verification_utils.py`
- `sprintos.py`
- `tests/test_testing_tools.py`
- `tests/test_sprintos.py`

Acceptance criteria:

- Verification fails when canonical app shapes lack required output surfaces.
- Verification checks simple behavior markers for score/update/card generation.
- Failure messages are creator-friendly.
- No external network calls or new dependencies.

### 3. Create App Preflight Clarity

Why it matters: `/api/ai_status` now knows when app generation is not ready; the Create App form should make that hard to miss before a long run.

Effort: S

Expected impact: Medium

Files likely touched:

- `sprintos.py`
- `tests/test_dashboard_flow.py`
- `tests/test_ui_helpers.py`

Acceptance criteria:

- Preflight says when AI is likely to use local template.
- Low budget and recent failure are summarized in plain language.
- AI mode remains available but not misleading.

### 4. Fallback Reason Translation

Why it matters: Provider-level reasons like timeout, invalid JSON, and service unavailable should be turned into app-first messages.

Effort: S

Expected impact: Medium

Files likely touched:

- `sprintos.py`
- `sprintos_core/ai_diagnostics.py`
- `tests/test_ai_providers.py`
- `tests/test_dashboard_flow.py`

Acceptance criteria:

- User-facing fallback reason is one of a small set: provider busy, timed out, invalid AI output, app safety validation failed, offline template selected.
- Raw provider response text is not shown in App Draft.
- Diagnostics remain redacted for technical review.

### 5. Download And Source Confirmation

Why it matters: The labels are now better, but the actual packages can still feel abstract.

Effort: S

Expected impact: Medium

Files likely touched:

- `sprintos.py`
- `tests/test_sprintos.py`

Acceptance criteria:

- Download App clearly says it is the runnable local app package.
- Download Source Pack clearly says it is the editable Codex/source package.
- Both package summaries list the primary files.
- `.env*` and `.git` exclusions stay tested.

### 6. Test App UI Consistency

Why it matters: One UI surface now allows draft testing, while the workspace lane still says testing waits for Codex prep.

Effort: S

Expected impact: Medium

Files likely touched:

- `sprintos.py`
- `tests/test_dashboard_flow.py`

Acceptance criteria:

- Every visible Test App action agrees with App State availability.
- Draft testing uses latest prototype/deploy/build artifacts.
- Missing Quick Launch report remains a warning, not a blocker.

### 7. App Naming Cleanup

Why it matters: An app called `I want a simple app where users` feels like a generated report, not a product.

Effort: S

Expected impact: Medium

Files likely touched:

- `sprintos.py`
- `sprintos_core/text_utils.py`
- `tests/test_sprintos.py`

Acceptance criteria:

- Canonical fallback prompts generate names like `Idea Scorecard`, `Budget Snapshot`, and `Study Card Builder`.
- Names are under 48 characters and 2-5 words.
- Existing metadata still loads safely.

### 8. Provider Retry/Repair Telemetry Polish

Why it matters: Retry now exists, but users need to know whether a retry happened without seeing provider internals.

Effort: S

Expected impact: Medium

Files likely touched:

- `sprintos_core/ai_provider.py`
- `sprintos.py`
- `tests/test_ai_providers.py`

Acceptance criteria:

- App metadata records redacted retry category.
- App Draft can say `AI needed one repair pass` when applicable.
- No raw failed output is stored or shown.

### 9. Opt-In Live Acceptance Documentation

Why it matters: Normal tests must stay offline, but AI readiness claims need an intentional live check path.

Effort: S

Expected impact: Medium

Files likely touched:

- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/APP_GENERATION_ACCEPTANCE_CHECKLIST.md`

Acceptance criteria:

- Docs explain when to run `scripts/live_app_generation_acceptance.py --confirm-live-provider`.
- Docs state it may incur provider cost and must never be part of smoke/full tests.
- Output remains redacted.

### 10. Main-Lane Vocabulary Reduction

Why it matters: The app-first goal is still surrounded by artifact vocabulary that slows users down.

Effort: M

Expected impact: Medium

Files likely touched:

- `sprintos.py`
- `tests/test_ui_helpers.py`
- `tests/test_dashboard_flow.py`
- `README.md`

Acceptance criteria:

- Main lane uses App Draft, App Preview, Download App, Source Pack, Test App, Prepare App for Codex.
- Build Pack/Deploy Pack/route/diagnostics stay behind advanced or technical disclosures.
- No behavior changes.

## What To Avoid

- Do not add more providers.
- Do not add deployment automation.
- Do not add GitHub automation.
- Do not add dashboards.
- Do not add new artifact types.
- Do not expand the app surface before the main app generator is reliable.
