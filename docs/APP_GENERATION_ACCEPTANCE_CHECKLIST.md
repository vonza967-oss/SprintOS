# App Generation Acceptance Checklist

Date: 2026-05-08

SprintOS should not call app generation "working" until this checklist passes in one local session.

## Provider and Fallback

- [ ] `/api/server_status` reports the current running server and a fresh process.
- [ ] `/api/ai_status` reports provider, model, timeout, and max output tokens without exposing keys.
- [ ] App-generation readiness is clearly shown separately from generic provider readiness.
- [ ] `app_file_generation` route resolves to the intended provider/model or clearly resolves offline.
- [ ] If AI is unavailable, Create App clearly says fallback was used.
- [ ] Fallback reason is redacted and actionable.

## Create App Flow

- [ ] User can type one idea and click Create App.
- [ ] Create App completes without deployment, GitHub, or external repo actions.
- [ ] Generated app has an app name that is not just a truncated prompt.
- [ ] App Draft appears before advanced/technical panels.
- [ ] Open App Preview is the primary action when preview exists.

## Generated Files

- [ ] `index.html` exists.
- [ ] `style.css` exists.
- [ ] `app.js` exists.
- [ ] `README.md` exists.
- [ ] `TEST_PLAN.md` or `test-plan.md` exists.
- [ ] Generated filenames are path-safe.
- [ ] App files are small and understandable.

## Preview

- [ ] Preview route opens successfully.
- [ ] Preview is an app, not a report page.
- [ ] App has a clear input.
- [ ] App has one primary action.
- [ ] App has a visible output/result state.
- [ ] Result changes based on input or clearly explains deterministic/mock behavior.
- [ ] Mobile and desktop layout are usable.

## App-Specific Behavior

- [ ] Business idea scorer has textarea, score, risk breakdown, smallest testable version, and next action.
- [ ] Budget calculator has numeric income/expense inputs, calculate action, savings score, breakdown, and recommendation.
- [ ] Flashcard helper has textarea, generate action, question/answer cards, and a mocked/local limitation note if no AI is used.
- [ ] App does not present generic placeholder text as a finished app.
- [ ] App does not make misleading AI claims when behavior is mocked.

## Download and Package

- [ ] Clear `Download App` action exists.
- [ ] App ZIP contains actual app files.
- [ ] Source ZIP or source package is available for Codex work.
- [ ] README and test plan are included.
- [ ] ZIP excludes `.env` and `.env*`.
- [ ] ZIP excludes `.git` internals.
- [ ] ZIP contains no obvious secrets.

## Safety

- [ ] No browser-side OpenAI calls.
- [ ] No browser-side DeepSeek calls.
- [ ] No hardcoded API keys.
- [ ] No external CDN/script requirement.
- [ ] No unsafe `fetch`, XHR, or beacon calls in generated browser files.
- [ ] No raw prompts or raw provider responses are stored in diagnostics or artifacts.

## Test and Inspect

- [ ] Test App can run from App Draft state.
- [ ] Verification checks required files, preview route, source package, package safety, and app-specific behavior.
- [ ] Verification failure messages are understandable to non-experts.
- [ ] User can inspect source files without knowing internal Build Pack vocabulary.
- [ ] Prepare App for Codex creates a local workspace with run/test instructions.
- [ ] Codex handoff is app-specific and names the generated app files.

## Final User Goal

- [ ] A user can type an idea.
- [ ] A user can click Create App.
- [ ] A user can open a functioning local preview.
- [ ] A user can download the app package.
- [ ] A user can test the app.
- [ ] A user can inspect the source.
- [ ] A user can send the app to Codex for improvement.
