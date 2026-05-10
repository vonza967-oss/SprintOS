# SprintOS Latest Opportunities

Date: 2026-05-08

These opportunities are limited to work that directly improves the core goal:

`idea -> Create App -> working preview -> download -> test -> inspect -> Codex handoff`

## 1. Live AI App Generation Acceptance Test v1

Why it matters: Current tests prove offline and mocked provider behavior. Recent local diagnostics show successful OpenAI app generation, but SprintOS needs a repeatable, opt-in way to prove live provider acceptance for canonical shapes before claiming reliability.

Effort: M

Expected impact: High

Files likely touched:

- `scripts/live_app_generation_acceptance.py`
- `README.md`
- `docs/APP_GENERATION_ACCEPTANCE_CHECKLIST.md`
- `docs/ARCHITECTURE.md`
- Maybe `tests/test_ai_providers.py` for offline-only guard assertions

Acceptance criteria:

- Script runs the canonical business idea scorer, budget calculator, and flashcard helper prompts.
- It verifies used-AI true, preview file exists, ZIP/package exists, safety checks pass, and required app-shape checks pass.
- It writes a redacted JSON and Markdown report.
- It refuses to run without explicit live-provider confirmation.
- It is documented as opt-in only and never part of smoke/full tests.
- No keys, raw prompts, raw provider responses, Authorization headers, or `.env` contents appear in reports.

## 2. App-Specific Verify v1.5

Why it matters: Current verification catches missing surfaces and obvious local-first violations, but the user needs higher confidence that the generated app actually changes output when used.

Effort: M

Expected impact: High

Files likely touched:

- `sprintos_core/verification_utils.py`
- `sprintos.py`
- `tests/test_testing_tools.py`
- `tests/test_sprintos.py`

Acceptance criteria:

- Business idea scorer verification catches missing click handler, score update, risk update, smallest-test update, and next-action update.
- Budget verification catches missing numeric reads and savings/breakdown/recommendation updates.
- Flashcard verification catches missing card rendering and local/mocked limitation note.
- Messages are app-first and understandable.
- No new external dependency or network call is introduced.

## 3. Create App Preflight Clarity v1

Why it matters: `/api/ai_status` already knows whether app generation is ready. The Create App form should make provider readiness, report-only mode, and fallback likelihood obvious before the user starts a long run.

Effort: S

Expected impact: Medium

Files likely touched:

- `sprintos.py`
- `tests/test_dashboard_flow.py`
- `tests/test_ui_helpers.py`

Acceptance criteria:

- Preflight says whether SprintOS expects AI generation, local template fallback, or AI-only failure report behavior.
- `report_only` explains that no app files are created if AI fails.
- Low budget, recent provider failure, and provider unavailable states are summarized in plain language.
- No provider key values or `.env` contents are exposed.

## 4. Fallback Reason Translation v1

Why it matters: Users should see creator-friendly reasons, while technical diagnostics stay available behind Technical Details.

Effort: S

Expected impact: Medium

Files likely touched:

- `sprintos.py`
- `sprintos_core/ai_diagnostics.py`
- `tests/test_ai_providers.py`
- `tests/test_dashboard_flow.py`

Acceptance criteria:

- User-facing fallback reasons map to a small taxonomy: provider busy, timed out, invalid AI output, app safety validation failed, app shape validation failed, offline template selected.
- App Draft does not show raw provider error strings.
- Technical diagnostics remain redacted and useful.

## 5. Download App vs Source Pack Confirmation v1

Why it matters: The labels are better now, but users still need confidence about which package to share and which package to hand to Codex.

Effort: S

Expected impact: Medium

Files likely touched:

- `sprintos.py`
- `tests/test_sprintos.py`
- `tests/test_dashboard_flow.py`

Acceptance criteria:

- Download App clearly describes the runnable local app package.
- Source Pack clearly describes editable source/Codex handoff files.
- Package summaries list primary files.
- `.env*`, `.git`, raw prompts, raw provider responses, and obvious secrets remain excluded.

## 6. Test App UI Consistency v1

Why it matters: The user should not need to understand whether testing is attached to prototype, deploy, build, workspace, or Quick Launch internals.

Effort: S

Expected impact: Medium

Files likely touched:

- `sprintos.py`
- `tests/test_dashboard_flow.py`

Acceptance criteria:

- Every visible Test App action agrees with App State availability.
- Draft testing uses the latest valid prototype/deploy/build artifact.
- Missing Quick Launch report remains a warning, not a blocker.
- No behavior changes outside labels and action availability.

## 7. Main-Lane Vocabulary Reduction v1

Why it matters: SprintOS still exposes too many internal artifact names. The main lane should read like an app workflow, not an export pipeline.

Effort: M

Expected impact: Medium

Files likely touched:

- `sprintos.py`
- `tests/test_ui_helpers.py`
- `tests/test_dashboard_flow.py`
- `README.md`

Acceptance criteria:

- Main lane uses: Create App, Open App Preview, Download App, Source Pack, Test App, Prepare App for Codex, Create Testing Package.
- Build Pack, Deploy Pack, pipeline, routes, diagnostics, and Artifact History stay behind advanced or technical disclosures.
- No generated package behavior changes.

## 8. App Naming Cleanup v1

Why it matters: Recent app names are better, but prototype titles can still combine good names with confusing prototype-type suffixes.

Effort: S

Expected impact: Medium

Files likely touched:

- `sprintos.py`
- `sprintos_core/text_utils.py`
- `tests/test_sprintos.py`

Acceptance criteria:

- Canonical app display names stay concise: `Idea Scorecard`, `Budget Snapshot`, `Study Card Builder`.
- Main UI title does not overemphasize internal prototype type when the app name is clear.
- Legacy metadata still loads safely.

## 9. App-Generation Runtime Sanity v1

Why it matters: Provider and `.env` changes can leave a running server in a stale state.

Effort: S

Expected impact: Medium

Files likely touched:

- `sprintos.py`
- `scripts/launch.py`
- `tests/test_dashboard_flow.py`

Acceptance criteria:

- Runtime status clearly shows provider mode, app-generation budget, fallback mode, and process start time.
- Create App preflight warns if settings appear stale or below recommended app-generation budget.
- No `.env` values are printed.

## 10. Git / Version-Control Safety

Why it matters: The current repo has no commits, which makes review and rollback unsafe once implementation resumes.

Effort: S

Expected impact: Medium

Files likely touched:

- Possibly docs only, unless the user explicitly requests a commit.

Acceptance criteria:

- The repo has a clean local baseline commit or a documented manual Git safety step.
- `.env`, data, exports, backups, and generated caches remain ignored.
- No GitHub remote, push, or automation is added.
