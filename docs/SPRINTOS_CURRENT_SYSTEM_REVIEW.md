# SprintOS Current System Review

Date: 2026-05-08

## Executive Summary

SprintOS has moved materially closer to the core goal:

> Type idea, click Create App, get a usable functioning prototype app.

The strongest current improvement is that the previous audit's reliability slice is now substantially represented in code and tests. Current code exposes app-generation readiness separately from generic AI status, shows fallback status in the app-first UI, splits Download App from Download Source Pack, enables draft-level Test App, adds app-shape-specific offline templates, adds app-specific verification heuristics, and adds one retry/repair path for `app_file_generation`.

The current system is still not fully reliable as an AI app generator. In the live local runtime inspected for this review, DeepSeek key presence was true and generic provider usability was true, but `/api/ai_status` correctly reported `app_generation_ready=false` because the active budget was `20s / 2000 tokens` and the latest app-generation result was a timeout. Recent diagnostics also showed DeepSeek timeout, 503 service unavailable, and empty-message failures. This means the earlier readiness problem is no longer hidden, but the provider path remains unreliable.

Current verdict: **partially aligned, improved since the app-generation audit, but still not ready to call reliable live AI app generation.**

## Current Verdict

SprintOS is now a stronger local app generator than the last audit described. Offline/template mode is safer and more app-specific, and the UI has better app-first status language. However, the tested runtime still defaults to a provider configuration that is not app-generation-ready, existing generated artifacts include generic older fallback apps, and the product still exposes too much internal machinery around the main lane.

Best current use: private local app drafting with clear fallback awareness.

Not ready for: public promise of reliable AI-generated apps from arbitrary prompts.

## Evidence Limits

This folder is not a git repository. `git status` and commit history were unavailable, so exact commit-level change attribution is impossible.

Evidence used instead:

- Required audit and roadmap documents.
- Current source, tests, scripts, README, and architecture docs.
- File timestamps.
- Current SQLite counts.
- Current generated artifacts under `exports/`.
- Baseline commands.
- Local API endpoint inspection from a fresh server process.

## What Changed Since The Last App-Generation Audit

### Code Changes

Evidence of source changes after the app-generation audit timestamp exists in:

- `sprintos.py` at `2026-05-08 15:09:28`
- `sprintos_core/ai_provider.py` at `2026-05-08 15:19:18`
- `sprintos_core/ai_schemas.py` at `2026-05-08 14:58:21`
- `sprintos_core/verification_utils.py` at `2026-05-08 14:58:44`
- `sprintos_core/constants.py` at `2026-05-08 14:40:57`

Substantive changes visible in current code:

- `app_generation_readiness_payload()` adds app-generation readiness separate from generic provider usability.
- `ai_status_payload()` includes app-generation budget, recent result, provider route, and fallback fields.
- `run_setup_doctor()` has app-generation timeout/token/recent-failure checks.
- `build_app_state_summary()` enables draft-level `Test App` when prototype/deploy/build artifacts exist.
- App state actions now include `Download App` and `Download Source Pack` as separate concepts.
- App Draft and Create App result rendering include fallback banner data outside Technical Details.
- Offline templates now include named app shapes: business idea scorer, budget calculator, flashcard helper, quiz recommender, and waitlist page.
- App-generation prompt instructions now include shape contracts.
- AI app output validation now checks shape-specific surfaces before accepting app files.
- `generate_json_with_ai()` now retries `app_file_generation` once for retryable provider failures, invalid JSON, and repairable JSON shape failures, but does not retry safety-validation failures.

### Doc Changes

Before this review, the required docs themselves did not show later modification timestamps than the app-generation audit docs. Existing README and architecture docs already described the app-first lane, but their timestamps predate the app-generation audit.

This review creates the current review documents listed below. Apart from these new files, there is no reliable evidence from git that docs changed after the last app-generation audit.

### Test Changes

Evidence of test changes after the app-generation audit timestamp exists in:

- `tests/test_dashboard_flow.py` at `2026-05-08 14:33:28`
- `tests/test_sprintos.py` at `2026-05-08 15:10:02`
- `tests/test_ui_helpers.py` at `2026-05-08 15:10:10`
- `tests/test_ai_providers.py` at `2026-05-08 15:17:07`

Current tests now cover:

- App-generation readiness fields in AI status.
- Setup Doctor warnings for low app-generation budget and recent failures.
- Fallback banner data in app state.
- Draft-level Test App enablement.
- Download App vs Download Source Pack labels and ZIP routing.
- Shape-specific offline templates.
- Shape-specific verification failures/warnings.
- App-generation retry/repair behavior.
- No retry for unsafe app output.

### UI/UX Changes

Evidence in current UI code and tests shows:

- Today/Continue and Create App are app-first in current copy.
- App Draft appears before detailed panels inside project rendering.
- Project Command Center appears before `Prepare App for Codex` and `Test App`.
- Fallback message is visible outside Technical Details.
- `Download App` and `Download Source Pack` are separately described.
- AI status shows `Create App: Ready` or `May use local template`.
- The workspace lane is more ordered, but a workspace-lane `Test App` button still remains gated by workspace export even though App State can test drafts.

### App-Generation Behavior Changes

Improved:

- Offline fallback can now generate app-shape-specific apps instead of only generic scoring/tool shells.
- AI output must satisfy required files plus app-shape-specific verification surfaces.
- App-specific verification exists for business idea scorers, budget calculators, flashcard helpers, quiz recommenders, and waitlist pages.
- App draft can be tested before workspace export.

Still weak:

- Current exported examples from earlier runs still include generic fallback apps with raw prompt-fragment names.
- Existing Quick Launch verification reports are `partial` because Quick Launch status was partial, even with no blockers.
- The current live provider path remains unreliable.

### Provider/OpenAI/DeepSeek Behavior Changes

Improved:

- App-generation readiness is now reported separately from provider key presence.
- Setup Doctor warns when app-generation budget is too low.
- Provider retry/repair exists for retryable app-generation failures.
- Diagnostics are still redacted and key-safe.

Still weak:

- Current runtime has DeepSeek enabled and key present, but app-generation readiness is false.
- Latest app-generation diagnostics include timeout.
- Recent diagnostics include DeepSeek 503 service unavailable and empty-message failures.
- Current route configuration has no enabled per-task route override for `app_file_generation`.

### What Did Not Change

- SprintOS remains local-first and stdlib-only.
- `python3 sprintos.py` remains the main entrypoint.
- State remains local SQLite plus filesystem exports.
- AI remains optional.
- DeepSeek/OpenAI tests remain mocked/offline by default.
- Generated apps are still static/local-first by default.
- There are still many API routes, artifact types, and advanced panels.
- `sprintos.py` remains large at 28,884 lines.
- Current database still has 25 local tables.

## Previous Audit Issues

### Still Open

- Live provider app generation is not reliable enough.
- Current runtime is not app-generation-ready despite generic provider usability.
- Recent provider diagnostics include timeout, 503, and empty-message failures.
- Existing generated artifacts still show generic older fallback app quality.
- Technical vocabulary still leaks through advanced panels and Technical Details.
- Full app quality is still not proven by live acceptance testing.
- App names can still be raw prompt fragments in existing artifacts.
- `TEST_PLAN.md` versus `test-plan.md` remains a cross-layer naming inconsistency.

### Resolved Or Partially Resolved

- App-generation readiness is now separate from generic AI status. Resolved in code/API.
- Setup Doctor now warns about low app-generation budget and recent app-generation failures. Resolved in code/API.
- Fallback is now visible in App Draft/Create App result. Partially resolved; current generated artifact metadata can still contain provider error text that is too technical.
- `Test App` can run from draft state. Resolved in App State; still partially inconsistent in the workspace lane UI button.
- Download App vs Source Pack is clearer. Resolved in App State and tests.
- Offline fallback templates are more app-specific. Partially resolved; current code supports stronger templates, but older/current saved artifacts still include generic outputs.
- App-specific verification exists. Partially resolved; it is heuristic/static and does not run a real browser interaction.
- Provider retry/repair exists. Partially resolved; it cannot solve sustained provider outage or insufficient timeout/token budget.

## What Improved

- Reliability visibility improved: SprintOS can now say when app generation is not ready even if the provider key is present.
- Fallback transparency improved: App Draft/Create App can show a plain local-template fallback banner.
- Testing improved: draft-level Test App is enabled from App State when generated artifacts exist.
- Download clarity improved: Download App and Download Source Pack are now separate.
- Offline app quality improved in current code: canonical templates now include app-shape-specific surfaces.
- Verification improved: app-specific static checks now exist.
- Provider handling improved: `app_file_generation` can retry/repair selected transient or shape failures once.
- Test coverage improved: full suite now includes 478 tests.

## What Got Worse

No clear evidence shows an app-generation behavior got worse since the last audit. The main negative finding is that the local live runtime was configured with a weaker budget than the app-generation threshold, so the current process is app-generation-not-ready even though the code can report that correctly.

The maintainability picture continues to worsen by accumulation: `sprintos.py` is now 28,884 lines, tests are broad, and route/UI complexity remains high. This is not necessarily a regression from the last audit, but it is a growing risk.

## What Remains Broken

- Live provider generation is not dependable.
- The active local provider budget is below the documented app-generation threshold.
- Existing saved generated apps include generic fallback output.
- Some user-facing fallback reasons are still provider/internal language.
- Verification still does not fully prove browser behavior.
- Technical panels still expose Build Pack, Deploy Pack, workspace, route, diagnostics, and report vocabulary.
- The workspace lane still visually gates Test App behind workspace export in one place.

## Baseline Checks

| Command | Result |
| --- | --- |
| `python3 scripts/test_fast.py` | PASS, 37 tests in 1.847s |
| `python3 scripts/smoke.py` | PASS, `smoke ok` |
| `python3 scripts/health.py` | PASS, no obvious API keys found |
| `python3 scripts/readiness.py` | PASS, warnings for no backup and low app-generation budget |
| `python3 scripts/test_full.py` | PASS, 478 tests plus smoke and health in 98.60s |

## Runtime And Endpoint Findings

Fresh server inspection:

- Server: running locally on `127.0.0.1:8844`
- PID during inspection: `24873`
- Started: `2026-05-08T15:28:41`
- AI provider mode: `deepseek`
- Latest backup status: `none`
- App appeared fresh during inspection.

AI status:

- Provider: DeepSeek
- Enabled: true
- Key present: true
- Generic usable: true
- Model: `deepseek-v4-flash`
- Timeout: 20 seconds
- Max output tokens: 2000
- App-generation ready: false
- Warning: timeout below 90s, tokens below 6000, recent app generation ended with timeout.
- App-generation route mode: auto
- Per-task route used: false

Diagnostics summary:

- Latest `app_file_generation`: timeout.
- One recent `app_file_generation`: AI success, but with very long duration.
- Earlier `app_file_generation`: DeepSeek 503 service unavailable.
- Recent `sprint_generation`, `codex_handoff`, and `quick_launch_summary` also showed timeout or empty-message fallback.

Setup Doctor:

- Status: warning
- Score: 68
- Warnings: no local backup, low app-generation timeout, low app-generation token budget, recent app-generation timeout.
- Blockers: none
- Recommended action: create first backup

Today Dashboard:

- Projects: 16 active
- Quick Launches: 9
- Active Focus Sessions: 1
- Recommended global action: continue focus session
- Setup status: warning

## App-Generation Goal Alignment

Goal: **Type idea, click Create App, get a usable functioning prototype app.**

Current alignment: **6.5/10**

Create App:

- Create App is clearly documented and present as the default creation path.
- It produces project/sprint/prototype/deploy/build artifacts in local mode.
- AI/fallback status is now visible.
- App-generation readiness is now clear in API/UI.
- It can still feel stalled if live provider calls are attempted with insufficient or unreliable provider conditions.

Preview:

- Open App Preview is the primary App State action when preview exists.
- Preview routes point to local generated app files.
- Current saved fallback examples open as apps, not reports, but older outputs are often generic.

Generated files:

- Prototype packages include `index.html`, `style.css`, `app.js`, `README.md`, `test-plan.md`, feedback files, Codex prompt, and metadata.
- AI schema requires `TEST_PLAN.md`; prototype package writes `test-plan.md`; Build Pack writes `TEST_PLAN.md`.
- Current code can generate app-specific offline logic, but existing saved artifacts still show generic opportunity-score and mocked-output apps.

Download:

- Download App now points to the runnable app package.
- Download Source Pack now points to editable source for Codex/workspace use.
- ZIP safety is covered by tests and health/smoke checks.

Test:

- Draft-level Test App is enabled when local artifacts exist.
- Verification now checks app-specific surfaces.
- Current verification is still mostly static/heuristic and does not prove real browser behavior changes across inputs.

Inspect:

- Source can be inspected through Build Pack/source package and workspace export.
- Codex handoff is present and app-specific enough for local iteration.
- Technical route/path details are still visible and can overwhelm non-technical users.

## Current Weaknesses

### Product / UX

- There are still too many concepts around the main lane: App Draft, Static App Package, Source Pack, Workspace, Check App Changes, Testing Package, Older Outputs, AI Routing, and Diagnostics.
- The main App State is clearer than the detailed panels below it.
- Duplicate or near-duplicate paths remain visible: app state actions, advanced build controls, workspace lane, and technical verification.
- App-first copy has improved, but advanced artifact language still leaks.
- The user can still be asked to understand source package/workspace distinctions too early.

### App-Generation Quality

- Existing saved outputs show raw prompt-fragment names.
- Older saved fallback examples still use opportunity-score and mocked-output shells.
- Shape-specific templates exist in current code, but they need current-session acceptance evidence.
- App-specific verification checks surfaces and terms, not true usefulness.
- Test plan naming remains inconsistent across prototype and Build Pack layers.

### Provider Reliability

- DeepSeek was configured and key-present, but not app-generation-ready.
- Recent diagnostics include timeout, service unavailable, and empty-message failures.
- Current active budget is below recommended thresholds.
- Route presets exist but no enabled per-task route override was active for app generation.
- Retry/repair helps transient failures but cannot fix sustained outage or weak budget.

### Safety / Security

- Secret handling remains strong, but route/package breadth is a standing risk.
- Browser-side provider calls are blocked by validation markers, but obfuscation is hard to prove away.
- `.env` packaging is tested, but every new export route must keep using shared safe helpers.
- Generated JavaScript safety is mostly denylist/heuristic based.

### Local Runtime

- Local server startup is safe, but port/stale-process ergonomics remain a known risk from previous audits.
- Setup Doctor accurately warned about no backup and weak app-generation budget.
- No local backup exists in the inspected persistent repo state.
- The server inspected for endpoints was fresh after manual start.

### Maintainability

- `sprintos.py` is the main engineering risk at 28,884 lines.
- The database has 25 tables.
- The API surface is broad.
- UI rendering, orchestration, persistence, and file serving remain tightly coupled.
- Tests are extensive and valuable but large enough to make simplification work slower.

### User Psychology / ADHD Fit

- The system is better at showing one main app state than before.
- It still risks decision fatigue because advanced controls are close to the main path.
- Visible progress is good when Create App completes.
- Provider delays or fallback without app-quality output can still break momentum.
- The product should keep reducing operational friction before adding surface area.

## Failures And Threats

### Active Failures

| Item | Severity | Likelihood | Evidence | Impact | Recommended fix | Blocks app-generation reliability |
| --- | --- | --- | --- | --- | --- | --- |
| Current runtime app-generation readiness is false | High | High | `/api/ai_status` showed low budget and recent timeout | AI Create App can fall back or stall | Make preflight guidance unavoidable when not ready | Yes |
| DeepSeek recent app-generation failures | High | High | Diagnostics include timeout and 503 | Live AI output cannot be trusted | Keep fallback, tune budget, consider provider route testing | Yes |
| Existing saved fallback apps are generic | High | Medium | Saved artifacts use generic score/tool shells | Users judge SprintOS as low quality | App Quality Templates v1 | Yes |
| No local backup exists | Medium | High | Setup Doctor warning | Local state loss risk | Create first backup | No |

### Latent Failures

| Item | Severity | Likelihood | Evidence | Impact | Recommended fix | Blocks app-generation reliability |
| --- | --- | --- | --- | --- | --- | --- |
| Verification can pass app shells that are not useful | High | Medium | Static checks are heuristic | User gets false confidence | Add behavior-oriented checks | Yes |
| Source/preview package divergence | Medium | Medium | Multiple artifact folders and ZIPs | User inspects a different thing than preview | Add manifest/checksum compare later | Partial |
| Stale process/config confusion | Medium | Medium | Prior audit found stale port risk | User audits wrong runtime | Improve launcher conflict messaging | No |

### High-Risk Design Choices

| Item | Severity | Likelihood | Evidence | Impact | Recommended fix | Blocks app-generation reliability |
| --- | --- | --- | --- | --- | --- | --- |
| Large monolith | High | High | `sprintos.py` 28,884 lines | Risky future changes | Extract stable helpers after reliability stabilizes | Indirect |
| Broad route/file-serving surface | High | Medium | Many artifact routes | Security regression risk | Centralize allowlists and keep tests strict | Indirect |
| Advanced controls near main flow | Medium | High | UI still exposes many panels | Decision fatigue | Keep advanced panels collapsed/secondary | Partial |

### User-Trust Risks

| Item | Severity | Likelihood | Evidence | Impact | Recommended fix | Blocks app-generation reliability |
| --- | --- | --- | --- | --- | --- | --- |
| User thinks AI made the app when fallback did | High | Medium | Fallback is visible now, but older artifacts are generic | Misplaced trust or disappointment | Keep banner and simplify reason copy | Yes |
| Technical fallback messages | Medium | High | Timeout/503 wording appears in metadata/diagnostics | Confusion | Translate to user-facing categories | Partial |
| App names look unfinished | Medium | Medium | Existing artifacts use prompt fragments | Product feels less real | Apply naming helper consistently | Partial |

### Cost Risks

| Item | Severity | Likelihood | Evidence | Impact | Recommended fix | Blocks app-generation reliability |
| --- | --- | --- | --- | --- | --- | --- |
| Long live provider attempts | Medium | Medium | One recent app-generation success took very long | Slow/costly iterations | Preflight and opt-in live acceptance only | Partial |
| Repeated retries under outage | Medium | Medium | Retry/repair exists | Can spend time/quota without quality | Retry once only and report fallback clearly | Partial |

### AI Reliability Risks

| Item | Severity | Likelihood | Evidence | Impact | Recommended fix | Blocks app-generation reliability |
| --- | --- | --- | --- | --- | --- | --- |
| Invalid JSON/schema output | High | Medium | Prior audit and retry tests | Fallback or bad app | Existing retry/repair plus schema checks | Partial |
| Provider outage/503 | High | High | Recent DeepSeek diagnostics | Fallback required | Offline templates must be good enough | Yes |
| Token budget too low | High | High | Runtime 2000 output tokens | Truncated/failed app files | Raise/recommend 6000 when using AI | Yes |

### Product-Direction Threats

| Item | Severity | Likelihood | Evidence | Impact | Recommended fix | Blocks app-generation reliability |
| --- | --- | --- | --- | --- | --- | --- |
| More features before reliability | High | Medium | Backlog and docs contain many advanced systems | Core promise remains weak | Build only app-quality/reliability slices | Yes |
| Dashboard/control-panel drift | Medium | Medium | Existing UI has many panels | Momentum loss | Keep app-first lane dominant | Partial |

### Maintainability Threats

| Item | Severity | Likelihood | Evidence | Impact | Recommended fix | Blocks app-generation reliability |
| --- | --- | --- | --- | --- | --- | --- |
| Tests become brittle around broad UI | Medium | Medium | Label-heavy UI tests exist | Slower safe cleanup | Test behavior/state, not incidental copy | Indirect |
| Schema/table complexity | Medium | High | 25 local tables | Persistence changes risk regressions | Avoid new tables for app quality work | Indirect |

## Scorecard

| Area | Score | Justification |
| --- | ---: | --- |
| App-generation reliability | 5 | Local fallback is reliable; live provider path is currently not app-generation-ready. |
| Generated app usefulness | 6 | Current code has stronger templates, but saved examples still show generic outputs. |
| Preview/download/test/inspect clarity | 7 | Main actions are clearer and draft testing exists; some lane inconsistency remains. |
| Fallback transparency | 8 | Fallback banner and readiness warnings exist; fallback reasons are still too technical. |
| Provider readiness clarity | 8 | API and Setup Doctor now separate app readiness from generic usability. |
| App-first UX | 7 | Create App/App Draft are stronger; advanced panels still crowd the experience. |
| Local safety | 9 | Local-first, ZIP exclusion, redaction, path safety, and no automatic deploy/git remain strong. |
| Codex handoff quality | 7 | Source packs and prompts are useful, but there are still many prompt/report surfaces. |
| Maintainability | 4 | `sprintos.py` remains a large monolith with broad route/UI/schema coupling. |
| Daily usability | 6 | Better guidance, but active setup warnings, focus sessions, and many panels add friction. |
| Public product readiness | 3 | Not ready for public users because live AI generation and UX clarity are not dependable enough. |

## Biggest Strengths

- Strong local-first safety posture.
- Broad test suite passing.
- Clear app-generation readiness now exists.
- Visible fallback messaging exists.
- Draft-level testing exists.
- App/source downloads are split.
- Offline templates can now be app-shape-specific.
- App-specific verification has begun.
- Codex handoff remains local and practical.
- No evidence of API key leakage in baseline checks.

## Biggest Blockers

1. Live provider app generation is currently not ready.
2. Default active budget is below the app-generation threshold.
3. Recent DeepSeek failures remain common.
4. Existing saved artifacts still demonstrate generic fallback quality.
5. Verification is still heuristic, not a real browser acceptance test.
6. UI still exposes too many technical concepts.
7. Workspace lane still gates Test App in one place even though draft testing is enabled elsewhere.
8. App naming and copied sprint language can still feel generic.
9. Test plan naming remains inconsistent.
10. Maintainability pressure is high because the main app is still very large.

## Current Recommended Next Action

The next implementation prompt should be **App Quality Templates v1**, not another readiness audit.

Reason: App Generation Reliability v1 appears mostly implemented. The next highest-leverage blocker is making offline fallback and accepted AI outputs consistently produce useful app-shaped behavior for the canonical app types. This directly improves the core promise even when providers are unavailable.
