# SprintOS Next Codex Prompts

Date: 2026-05-08

## Decision

Recommended next implementation prompt: **App Quality Templates v1**.

Why this instead of App Generation Reliability v1:

- App Generation Reliability v1 appears mostly implemented in current code.
- App readiness, fallback visibility, draft-level testing, download/source clarity, and provider retry/repair now exist.
- The biggest remaining blocker is that the generated app must consistently feel like the requested app, especially in offline fallback.

## Exact Next Recommended Codex Prompt

Read `AGENTS.md` first and preserve all SprintOS local-first constraints.

Goal: implement **App Quality Templates v1** so Create App produces more useful local fallback apps for the canonical app shapes. This is an implementation task, not another audit.

Core user goal:

`idea -> Create App -> working preview -> download -> test -> inspect -> Codex handoff`

Scope:

1. Improve deterministic offline app templates for these app shapes only:
   - business idea scorer
   - budget calculator
   - flashcard helper

2. Make each template feel app-specific:
   - Business idea scorer must include an idea textarea, Score Idea action, score, risk breakdown, smallest testable version, and next action.
   - Budget calculator must include numeric income/expense inputs, Calculate Budget action, monthly savings, spending breakdown, and recommendation.
   - Flashcard helper must include study-notes textarea, Build Flashcards action, question/answer cards, and a clear note that generation is local/mocked.

3. Improve fallback app naming for those shapes:
   - Use concise names such as `Idea Scorecard`, `Budget Snapshot`, and `Study Card Builder`.
   - Do not use raw prompt fragments as app names.
   - Preserve safe behavior for legacy metadata.

4. Ensure generated README/test plan/Codex prompt match the app shape:
   - README should explain the actual local app flow.
   - Test plan should include app-specific manual checks.
   - Codex prompt should name the generated files and the app-specific next improvement task.

5. Keep behavior local-first and safe:
   - No external dependencies.
   - No external CDN.
   - No browser-side OpenAI or DeepSeek calls.
   - No API keys in generated files, metadata, ZIPs, logs, or diagnostics.
   - No deployment, GitHub, git, or automatic Codex invocation.

6. Add or update tests:
   - Offline business idea scorer template contains required UI and JS markers.
   - Offline budget calculator template contains required numeric inputs and result markers.
   - Offline flashcard helper template contains required notes/card surfaces and local/mock note.
   - App-specific verification passes for these templates.
   - App-specific verification fails when required surfaces are removed.
   - ZIP outputs still exclude `.env*` and obvious secrets.

Recommended files to inspect first:

- `sprintos.py`
- `sprintos_core/verification_utils.py`
- `sprintos_core/ai_schemas.py`
- `tests/test_sprintos.py`
- `tests/test_dashboard_flow.py`
- `docs/SPRINTOS_CURRENT_SYSTEM_REVIEW.md`
- `docs/SPRINTOS_CURRENT_RISK_REGISTER.md`

Verification before final report:

```bash
python3 scripts/test_fast.py
python3 scripts/smoke.py
python3 scripts/health.py
python3 -m py_compile sprintos.py tests/*.py scripts/*.py sprintos_core/*.py
```

Run this if reasonable:

```bash
python3 scripts/test_full.py
```

Acceptance criteria:

- A no-key/offline Create App flow produces app-specific behavior for the three canonical shapes.
- Existing AI fallback still works when providers fail.
- App Draft still shows fallback status when fallback happened.
- Preview/download/test/inspect paths still work.
- No secrets or raw provider responses are exposed.
- Existing tests pass.

## Follow-Up Prompts In Order

### 1. App-Specific Verify v1.5

Implement stronger deterministic verification for generated app behavior without adding dependencies or browser automation by default.

Acceptance criteria:

- Verification catches missing event handlers for scorer, budget, and flashcard shapes.
- Verification catches missing output update surfaces.
- Failure messages are app-first and understandable.
- Existing verification reports remain path-safe and local-only.

### 2. Create App Preflight Clarity v1

Use current app-generation readiness fields to make Create App mode and fallback likelihood clearer before the user starts a run.

Acceptance criteria:

- Preflight says whether AI is ready or likely to fall back.
- Low timeout/token budget is summarized plainly.
- Recent provider timeout/503/invalid-output is summarized without raw provider payloads.

### 3. Test App UI Consistency v1

Align every visible Test App button with draft-level verification availability.

Acceptance criteria:

- Workspace lane does not imply Test App requires workspace export when draft artifacts can be tested.
- Missing Quick Launch report remains a warning.
- App State and lane labels agree.

### 4. Fallback Reason Translation v1

Map provider/internal failure reasons to a compact user-facing reason taxonomy.

Acceptance criteria:

- User-facing reasons include provider busy, timed out, invalid AI output, safety validation failed, and offline template selected.
- Raw provider responses are not shown in App Draft.
- Technical diagnostics remain redacted and available behind Technical Details.

### 5. Live Acceptance Docs v1

Document the opt-in live app-generation acceptance script without making it part of tests or smoke.

Acceptance criteria:

- README explains when and how to run the script.
- Docs warn it can use live provider quota.
- The script remains opt-in only and redacted.

## What Not To Build Next

- More dashboards.
- More artifact types.
- More providers.
- Deployment automation.
- GitHub automation.
- Auth, accounts, billing, cloud sync, or SaaS features.
- Background workers.
- UI framework rewrites.
- Any automatic Codex invocation.
