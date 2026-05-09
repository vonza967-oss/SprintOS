# SprintOS App Generation Audit

Date: 2026-05-08

## Executive Summary

SprintOS is close to the target flow, but not yet reliable enough to trust as "type idea, click Create App, get a usable app" without caveats.

The local packaging and safety model are strong: generated apps are local static files, preview URLs work, ZIP packages exclude `.env`, source files are inspectable, and browser-side provider calls were not found in the tested outputs. The weak points are provider reliability, app-specific quality, visible fallback explanation, and verification depth.

Current verdict: **partially aligned**. SprintOS can create previewable/downloadable/testable/inspectable local app packages, but live AI app generation is not reliable enough today, and offline fallback often produces generic "score/tool" shells that pass structural checks without feeling like the requested app.

## Baseline Checks

Commands run:

| Command | Result |
| --- | --- |
| `python3 scripts/test_fast.py` | PASS, 33 tests in 1.903s |
| `python3 scripts/smoke.py` | PASS, `smoke ok` |
| `python3 scripts/health.py` | PASS, no obvious hardcoded API keys found |
| `python3 scripts/readiness.py` | PASS, warning: no local backup exists yet |
| `python3 scripts/test_full.py` | PASS, 457 tests plus smoke and health in 99.03s |

Runtime/API status:

| Endpoint | Finding |
| --- | --- |
| `/api/server_status` | Server running on `127.0.0.1:8844`, PID 12490, started `2026-05-08T11:01:37` |
| `/api/ai_status` | DeepSeek enabled, key present, model `deepseek-v4-flash`, timeout 90s, max output tokens 6000 |
| `/api/ai_routes` | `app_file_generation` resolves to DeepSeek via defaults; no per-task route override is enabled |
| `/api/setup_doctor` | Warning only: no local backup yet |
| `/api/today_dashboard` | App Draft Ready states surface Open App Preview, Prepare App for Codex, Test App, Download App Package |

Freshness: the server started after the current `sprintos_core/ai_provider.py` and `sprintos_core/ai_schemas.py` edits, so the running app was fresh enough for this audit.

Current config appears safe at the API level: provider key presence is reported as a boolean only, `.env` contents were not printed, health checks report `.env` ignored, and no obvious hardcoded keys were found.

## Live Provider Behavior

Recent successful context: an earlier DeepSeek run at `2026-05-08T11:04:17` completed `app_file_generation` with `used_ai=true` in 73.681s. It produced `index.html`, `style.css`, `app.js`, `README.md`, and `TEST_PLAN.md`.

Current audit behavior:

- A full `/api/quick_launch` app-first request with `generation_mode=ai` did not return within the diagnostic client's several-minute wait and ultimately timed out from the client side.
- Diagnostics recorded DeepSeek 503 responses for `sprint_generation` and `codex_handoff`.
- Three narrower app-generation pipeline tests requested AI app file generation, but all three fell back because DeepSeek returned HTTP 503 `service_unavailable_error`.
- `ai_status.usable=true` was therefore misleading for app creation readiness: the key was present, but the provider was not actually ready for current app-generation work.

## Generated App Test Results

Because full Quick Launch was blocked by live provider behavior, the three app tests used the narrower local pipeline path: offline sprint creation, then `run_testable_pipeline(... generation_mode="ai")`. This still exercised app file generation, preview, deploy package, Build Pack, and verification. All three attempted DeepSeek for `app_file_generation`; all three fell back offline due to 503.

| Test | AI Used | Preview | Files | ZIP Safety | Verify | App Quality Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| Business idea scorer | No, 503 fallback | Works | Required files present | No `.env`; app files present | Partial, no blockers | Structurally usable, but generic offline calculator |
| Personal budget calculator | No, 503 fallback | Works | Required files present | No `.env`; app files present | Partial, no blockers | Too generic; not enough real budget logic |
| Study flashcard helper | No, 503 fallback | Works | Required files present | No `.env`; app files present | Partial, no blockers | Simulated text tool, not a strong flashcard app |

Browser interaction checks:

- Business idea scorer opened and produced a result after input/action, but the visible result was generic scoring copy and did not visibly show risk breakdown.
- Budget calculator opened and produced a generic score/recommendation result, not a clear income/expense savings breakdown.
- Flashcard helper opened and produced a deterministic simulated result, but the visible result did not clearly render flashcard-style question/answer cards.

The generated apps were apps rather than static reports, but the fallback versions often felt like reusable SprintOS templates with idea words inserted.

## Quality Scores

Scores are 1-10.

| App | Idea specificity | Usefulness | UI clarity | Interaction | Preview reliability | Package quality | Codex handoff | Safety | Testability | Feels like app | Overall |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Business idea scorer | 6 | 6 | 7 | 6 | 9 | 9 | 7 | 9 | 7 | 6 | 7 |
| Personal budget calculator | 4 | 4 | 6 | 5 | 9 | 9 | 6 | 9 | 7 | 5 | 6 |
| Study flashcard helper | 4 | 4 | 6 | 5 | 9 | 9 | 6 | 9 | 7 | 4 | 5 |

## Preview, Download, Test, Inspect

Preview:

- Open App Preview exists and points to `/build_pack/{id}/src/index.html` for static Build Packs.
- Preview routes loaded successfully in the browser.
- The preview is a browser app, not just a report.
- Interaction exists, but offline fallback logic is generic.

Download:

- Download App Package exists and currently points first to Deploy Pack ZIP when available.
- Deploy ZIP contains `index.html`, `style.css`, `app.js`, `README.md`, deploy docs, feedback questions, test plan, and metadata.
- Build Pack ZIP contains source under `src/`, `CODEX_BUILD_PROMPT.md`, `TEST_PLAN.md`, `tests/smoke_static.py`, and support docs.
- Tested ZIPs did not include `.env`.

Test:

- Run & Verify can verify generated artifacts and package structure.
- Pipeline-created apps returned `partial` because no Quick Launch report existed, not because app files were broken.
- Verification does not prove app-specific behavior such as "budget calculator changes savings score when expenses change" or "flashcards render question/answer cards."

Inspect:

- Source files are accessible in Build Pack folders and ZIPs.
- Prepare App for Codex exists, but Test App is disabled until a workspace export exists.
- Technical details expose enough paths and IDs, but app source/download routes still require understanding Build Pack vs Deploy Pack semantics.

## Architecture Review

1. Is `app_file_generation` strict enough?

Mostly strict for file shape and safety. It requires exact required filenames, blocks path traversal, external URLs, provider endpoints, browser network calls, and secret-like patterns.

2. Is it too strict?

Somewhat. It requires `TEST_PLAN.md` from AI but writes prototype output as `test-plan.md`, while Build Pack restores `TEST_PLAN.md`. This works, but creates naming friction and cognitive overhead.

3. Are required files correct?

Yes for a local static app: `index.html`, `style.css`, `app.js`, `README.md`, `TEST_PLAN.md`. The system should standardize display and package naming.

4. Are app types sufficient?

Barely. `static_app`, `calculator`, `quiz`, `ai_text_tool`, and `landing_page` cover the basics, but budget calculators and flashcard helpers need stronger type-specific prompt requirements or templates.

5. Are validation errors clear?

For engineers, yes. For app creators, no. `deepseek_invalid_json`, provider 503, and schema fields are not translated into app-first language at the Create App result level.

6. Are fallback reasons actionable?

Diagnostics are actionable for engineers. The UI should summarize provider fallback as "AI was unavailable; SprintOS used the local template" and recommend retrying app generation or switching provider.

7. Are token/timeout defaults adequate?

The current live budget of 90s and 6000 tokens is more realistic than earlier defaults, but `app_file_generation` still consumes around 6.6k-6.9k estimated input tokens before output. It deserves app-specific readiness and budget guidance.

8. Does SprintOS persist the right metadata?

Mostly. Prototype metadata records provider, model, used_ai, fallback reason, generated files, run/test instructions, limitations, and mocked parts. Missing: a first-class "app generation readiness/result" summary that can distinguish provider-ready from app-generation-ready.

9. Does Build Pack preserve generated app files correctly?

Yes. Build Pack ZIP includes `src/index.html`, `src/style.css`, `src/app.js`, README, test plan, smoke test, and Codex prompt.

10. Does Verify App catch real app-breaking issues?

It catches missing files, unsafe network calls, broken package structure, and missing app interaction markers. It does not catch weak or generic business logic.

11. Does the generator produce working apps or pretty shells?

When AI succeeds, it can produce a working app. When fallback is used, it produces structurally working shells that often feel generic.

12. What would most improve usefulness?

Add app-type-specific generation requirements and acceptance checks for the top app categories, starting with idea scorer, calculator, and flashcards.

## User-Facing UX Findings

| Visible label/surface | Issue | Proposed replacement | Priority |
| --- | --- | --- | --- |
| `App Draft` | Good, but still sounds intermediate even when preview works | `Your App` or `App Preview Ready` after files exist | P1 |
| `Prepare App for Codex` | Clear for Codex users, but not for a user who wants source | `Open Source Workspace` after export, `Prepare Source for Codex` before export | P1 |
| `Test App` disabled until workspace export | The app can already be structurally verified before workspace export | Enable basic preview/package verification from draft state | P0 |
| `Download App Package` | Good label, but points to Deploy Pack while Build Pack has source and tests | Offer `Download App` and secondary `Download Source Pack` | P1 |
| `Technical Details` | Useful but contains provider internals and IDs that can dominate troubleshooting | Keep collapsed; add one plain fallback banner outside details | P1 |
| `Older Outputs` | Useful history, but artifact wording can pull user back into artifact manager mental model | `Previous Apps and Runs` | P2 |
| `Plan Only` | Correctly advanced, but still visible in first-open sidebar | Keep behind advanced disclosure; default focus remains Create App | P2 |

## Top Blockers

1. Live provider readiness is not equivalent to app-generation readiness.
2. Full Quick Launch can feel hung under provider load.
3. Provider 503/timeout/invalid JSON fallback is not visible enough in the app-first result.
4. Offline fallback apps are too generic for common app prompts.
5. Verify App passes structure but not app-specific usefulness.
6. `Test App` is disabled until workspace export even when a draft exists.
7. Download semantics blur Deploy Pack vs Build Pack vs source package.
8. `TEST_PLAN.md` vs `test-plan.md` naming is inconsistent across layers.
9. App names are often truncated raw ideas rather than product names.
10. Diagnostics are engineer-friendly but not creator-friendly.

## Top Risks

1. Users think AI created an app when fallback created a generic template.
2. Users abandon the flow during a long Quick Launch with no clear progress.
3. The app passes structural verification while failing the user's requested behavior.
4. Provider 503, balance, timeout, or invalid JSON causes inconsistent app quality.
5. Advanced artifact vocabulary obscures the core Create App result.

## Top Opportunities

1. Add an app-generation readiness check separate from generic AI status.
2. Add app-specific prompt contracts for calculator, idea scorer, and flashcard apps.
3. Add app-specific verification heuristics for input/action/output and expected domain terms.
4. Make fallback visible: "AI unavailable, local template used."
5. Simplify downloads into app package vs source package.

## Recommended Next Fix

Smallest next implementation PR: **App Generation Reliability v1**.

Scope:

- Add app-generation readiness to AI status/setup doctor.
- Give `app_file_generation` an explicit minimum budget warning.
- Surface fallback reason plainly in Create App and App Draft.
- Enable draft-level Test App verification without requiring workspace export.
- Add focused acceptance checks for the three common app shapes tested here.
