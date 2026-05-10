# Demo-ready SprintOS local app-generation baseline

## 1. What changed

This branch prepares SprintOS as a demo-ready local-first app-generation baseline. It keeps the default user path centered on Create App while adding the supporting review and guidance surfaces needed to explain, inspect, and improve generated local apps.

Key additions include:

- Canonical app-generation contracts and fallback templates for known app shapes.
- Generic/custom app-generation support for non-canonical ideas.
- Broad arbitrary prompt acceptance and stabilization.
- Example Prompt Gallery for demo-friendly starting points.
- App Intent Review for clarifying the app purpose before generation.
- Follow-Up Questions for improving ambiguous requests without blocking local operation.
- App Blueprint output for a compact explanation of the planned app shape.
- Demo readiness documentation and release-focused checks.

## 2. Product flow

The demo path remains:

1. Capture a messy idea in Create App.
2. Review the intent, follow-up questions, blueprint, or gallery examples as needed.
3. Generate a small local app workspace.
4. Open the preview and inspect the generated files.
5. Improve, test, package, or continue through the existing advanced panels.

The classic sprint-planning path remains available behind the advanced Plan Only disclosure. The Today Dashboard and Project Command Center continue to act as guidance layers rather than replacements for detailed panels.

## 3. App generation capabilities

SprintOS now supports:

- Canonical generation for explicit known shapes such as idea scoring, budgeting, study cards, decision matrices, and pricing ROI.
- Generic/custom generation for practical local tools that do not map to a canonical contract.
- Broad arbitrary prompt handling for a wider range of demo prompts.
- Structured validation before files are written.
- Deterministic offline fallback when provider output is missing, malformed, vague, unsafe, or unavailable.

Generated app workspaces keep the local-first file contract:

- `index.html`
- `style.css`
- `app.js`
- `README.md`
- `TEST_PLAN.md`

## 4. Acceptance evidence

Latest known acceptance state:

- Canonical acceptance: passing.
- Generic acceptance: passing.
- Broad arbitrary acceptance: 10/10 passing.

Live acceptance artifacts are intentionally not included in this summary. The branch keeps provider acceptance opt-in and does not require live network calls for normal tests, smoke, or health checks.

## 5. Demo readiness additions

Demo readiness work includes:

- A concise demo readiness document.
- Demo-oriented README updates.
- Prompt-gallery, intent-review, follow-up, and blueprint surfaces that make app generation easier to explain during a live walkthrough.
- Safer app-generation validation and fallback behavior that keeps demos productive even without API keys.

## 6. Safety/local-first constraints preserved

This baseline preserves the SprintOS local-first constraints:

- `python3 sprintos.py` remains the main app entrypoint.
- Offline/template mode remains usable without API keys.
- OpenAI and DeepSeek remain optional provider modes.
- Provider tests and route tests remain mocked/offline by default.
- API keys are read only from local environment or repo-root `.env`.
- Keys, `.env` contents, raw provider responses, raw prompts, generated acceptance report contents, and local database state are not included in this PR summary.
- Generated apps must not require browser-side provider calls or external CDNs.
- Exports, release packs, snapshots, and backups continue to exclude `.env`, `.env*`, `.git`, obvious secrets, raw prompts, and raw provider responses.

## 7. Tests run

Release-baseline verification run locally:

- `python3 -m unittest tests.test_dashboard_flow`
- `python3 -m unittest tests.test_ui_helpers`
- `python3 -m unittest tests.test_testing_tools`
- `python3 -m unittest tests.test_sprintos`
- `python3 -m unittest tests.test_ai_providers`
- `python3 scripts/test_fast.py`
- `python3 scripts/smoke.py`
- `python3 scripts/health.py`
- `python3 -m py_compile sprintos.py tests/*.py scripts/*.py sprintos_core/*.py`
- `python3 scripts/test_full.py`

Result: passing.

## 8. Known limitations

- Live provider acceptance remains opt-in and should not run as part of ordinary tests, smoke, or health checks.
- Cost figures remain local estimates only, not provider billing truth.
- Generated apps are intentionally small local prototypes, not production deployments.
- The local database and generated app workspaces are not part of this PR baseline.

## 9. What not included

This PR does not include:

- Deployment automation.
- GitHub repo creation for generated workspaces.
- Cloud sync, auth, background workers, or frontend framework migration.
- Raw prompts, raw provider payloads, generated live acceptance report contents, `.env` values, API keys, or local SQLite state.
- `data/`, `exports/`, `local_backups/`, caches, or logs.

## 10. Recommended next work

Recommended next task after this PR baseline:

Run a short manual demo pass from a clean local checkout using the Example Prompt Gallery, then capture only high-level demo notes and any reproducible local issues. Keep any live provider acceptance separate and opt-in.
