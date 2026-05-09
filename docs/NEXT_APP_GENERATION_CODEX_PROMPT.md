# Next App Generation Codex Prompt

## Recommended PR

App Generation Reliability v1

## Prompt

Read `AGENTS.md` first and preserve SprintOS local-first constraints.

Goal: make SprintOS clearly and reliably handle app generation readiness and fallback for the Create App flow. Do not add features beyond this reliability slice.

Context from the 2026-05-08 audit:

- `python3 scripts/test_fast.py`, `python3 scripts/smoke.py`, `python3 scripts/health.py`, `python3 scripts/readiness.py`, and `python3 scripts/test_full.py` passed.
- A previous DeepSeek `app_file_generation` run succeeded with `used_ai=true` after increasing budget to `SPRINTOS_AI_TIMEOUT_SECONDS=90` and `SPRINTOS_AI_MAX_OUTPUT_TOKENS=6000`.
- During the audit, generic `/api/ai_status` still reported DeepSeek usable, but app generation fell back because DeepSeek returned HTTP 503.
- Full `/api/quick_launch` can feel stalled under provider load.
- Offline fallback still creates previewable/downloadable source packages, but the UI does not make fallback obvious enough.
- `Test App` is disabled until workspace export even though draft artifacts can already be verified.

Implement one focused PR:

1. Add app-generation readiness fields to `/api/ai_status`.
   - Include whether recent `app_file_generation` diagnostics show success, fallback, timeout, invalid JSON, or provider unavailable.
   - Include a redacted `app_generation_warning`.
   - Include budget fields: timeout seconds and max output tokens.
   - Do not expose keys, raw prompts, or raw provider responses.

2. Add Setup Doctor checks for app generation budget/readiness.
   - Warn if timeout is below 90 seconds.
   - Warn if max output tokens are below 6000.
   - Warn if the latest app generation fallback is provider availability, timeout, invalid JSON, or schema validation.
   - Keep offline mode acceptable.

3. Surface fallback clearly in Create App/App Draft UI.
   - Show a plain message outside Technical Details when fallback was used:
     `AI app generation was unavailable, so SprintOS used the local template.`
   - Include the redacted reason and a safe next action.
   - Keep Technical Details collapsed.

4. Enable draft-level Test App.
   - If prototype/build/deploy artifacts exist, allow `Test App` to run verification without requiring workspace export.
   - Keep Prepare App for Codex available as the source handoff path.
   - Verification may warn when no Quick Launch report exists, but should not block app testing only for that reason.

5. Add or update tests.
   - AI status includes app-generation readiness without secrets.
   - Setup Doctor warns on low app-generation budget.
   - App Draft shows fallback status when `app_file_generation` fell back.
   - Test App is enabled for draft state with generated artifacts.
   - Existing offline behavior still passes.

Constraints:

- Do not deploy.
- Do not call GitHub.
- Do not invoke Codex automatically.
- Do not add dependencies.
- Do not print or store `.env` contents.
- Do not store raw provider responses.
- Preserve `python3 sprintos.py`.
- Keep changes PR-sized.

Verification before final report:

```bash
python3 scripts/test_fast.py
python3 scripts/smoke.py
python3 scripts/health.py
python3 -m py_compile sprintos.py tests/*.py scripts/*.py sprintos_core/*.py
```

Run `python3 scripts/test_full.py` if reasonable.

Acceptance criteria:

- A user can tell whether Create App used AI or local fallback.
- A user can test a generated app draft before exporting a workspace.
- Setup Doctor can warn that generic provider readiness is not enough for app generation.
- No secrets or raw provider content are exposed.
- Existing tests and smoke checks pass.
