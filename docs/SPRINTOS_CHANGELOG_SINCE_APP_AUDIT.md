# SprintOS Changelog Since App-Generation Audit

Date: 2026-05-08

## Evidence Note

This folder is not a git repository, so exact commits and diffs are unavailable. This changelog uses current file timestamps, source inspection, tests, and runtime behavior. If there is no direct evidence of a change after the app-generation audit timestamp, it is listed as unknown or unchanged.

## Code Changes

Evidence-supported code changes after the audit:

| Area | Evidence | Current behavior |
| --- | --- | --- |
| App-generation readiness | `sprintos.py` includes `app_generation_readiness_payload()` | `/api/ai_status` reports app-generation readiness separately from generic provider usability. |
| AI status fields | `ai_status_payload()` includes app-generation fields | Provider, budget, recent result, fallback reason, route mode, and route-use fields are exposed without keys. |
| Setup Doctor | app-generation checks visible in tests and endpoint output | Warns on timeout below 90s, max output tokens below 6000, and recent app-generation failures. |
| Fallback visibility | `app_generation_status_summary_from_metadata()` and App Draft renderer | App Draft/Create App result can show `AI app generation was unavailable, so SprintOS used the local template.` |
| Draft-level test | `build_app_state_summary()` enables `test_app` for prototype/deploy/build artifacts | Test App is available before workspace export from App State. |
| Download clarity | App State actions include `download_package` and `download_source_pack` | Download App and Download Source Pack are distinct. |
| Offline templates | `prototype_offline_app_file_generation_payload()` plus template shape helpers | Business idea scorer, budget calculator, flashcard helper, quiz recommender, and waitlist page templates exist. |
| Prompt contracts | `app_shape_prompt_contract()` | AI app generation receives shape-specific app requirements. |
| Shape validation | `validate_app_file_payload_for_shape()` | AI output can be rejected if it misses required app-shape surfaces. |
| App-specific verification | `sprintos_core/verification_utils.py` | Static checks cover scorer, budget, flashcard, quiz, and waitlist shapes. |
| Provider retry/repair | `generate_json_with_ai()` | `app_file_generation` retries once for invalid JSON, transient provider failure, or repairable JSON shape failure. |
| Live acceptance script | `scripts/live_app_generation_acceptance.py` | Opt-in live provider acceptance exists and refuses to run without explicit confirmation. |

## Documentation Changes

No existing required docs had a clear post-audit timestamp before this review.

This review adds:

- `docs/SPRINTOS_CURRENT_SYSTEM_REVIEW.md`
- `docs/SPRINTOS_CHANGELOG_SINCE_APP_AUDIT.md`
- `docs/SPRINTOS_CURRENT_RISK_REGISTER.md`
- `docs/SPRINTOS_CURRENT_OPPORTUNITIES.md`
- `docs/SPRINTOS_NEXT_CODEX_PROMPTS.md`

## Test Changes

Evidence-supported test changes after the audit:

| File | Evidence | Coverage now visible |
| --- | --- | --- |
| `tests/test_ai_providers.py` | Timestamp after audit; tests named for app-generation retry/readiness | Retry/repair, readiness status, redaction, provider fallback. |
| `tests/test_dashboard_flow.py` | Timestamp after audit | Setup Doctor app-generation warnings, fallback banner data, draft-level Test App. |
| `tests/test_sprintos.py` | Timestamp after audit | Offline shape templates, download/source split, app-specific verification, ZIP safety. |
| `tests/test_ui_helpers.py` | Timestamp after audit | Main app-first labels in HTML. |
| `scripts/test_fast.py` | Current fast suite includes 37 tests | Fast suite now includes AI provider retry/readiness tests. |

Baseline now observed:

- Fast suite: 37 tests passing.
- Full suite: 478 tests passing.

## UI Changes

Evidence-supported UI changes:

- README states the main lane as `Create App -> Open App Preview -> Prepare App for Codex -> Test App -> Create Testing Package`.
- App Draft hero shows preview/source/workspace/testing availability.
- Fallback banner is outside Technical Details.
- AI panel shows app-generation ready/warning/recent result.
- Today panel has compact `Today / Continue` framing.
- Classic planning is behind `Plan Only` disclosure in docs/current frontend.
- Project view places App Draft and Command Center ahead of advanced panels.
- Download App and Download Source Pack are explicitly explained.

Remaining UI inconsistency:

- Workspace lane still disables one `Test App` button until workspace export, while App State supports draft-level testing.

## Provider And App-Generation Changes

Improved:

- App-generation readiness is distinct.
- Low timeout/token budget is surfaced.
- Recent app-generation failure is surfaced.
- AI output validation is stricter and shape-aware.
- Retry/repair exists for `app_file_generation`.
- Live acceptance script exists but is opt-in only.

Current runtime:

- Provider: DeepSeek.
- Key present: true.
- Generic usable: true.
- App generation ready: false.
- Active budget: 20s timeout, 2000 output tokens.
- Latest app-generation result: timeout.
- Recent provider failures: timeout, 503, empty-message response.

## Unresolved Audit Issues

- Live provider reliability remains weak.
- Current runtime app-generation readiness is false.
- Fallback reasons can still be technical.
- Existing saved generated apps include generic older fallback shells.
- Full browser-level acceptance is not automatic.
- Public product readiness remains low.
- Advanced artifact vocabulary is still visible.
- Main app remains large and route-heavy.

## Resolved Or Partially Resolved Audit Issues

| Previous issue | Current status |
| --- | --- |
| Generic provider readiness did not equal app-generation readiness | Resolved in API/UI/Setup Doctor. |
| Fallback was not visible enough | Partially resolved with App Draft/Create App fallback banner. |
| Test App disabled before workspace export | Resolved in App State; partially inconsistent in workspace lane UI. |
| Download App vs Source Package unclear | Largely resolved with distinct App and Source Pack actions. |
| Offline fallback apps too generic | Partially resolved with shape-specific templates; older artifacts remain generic. |
| Verification only checked structure | Partially resolved with app-specific static checks. |
| AI invalid JSON/schema failure had no repair path | Partially resolved for `app_file_generation` retryable cases. |
| Live provider eval/acceptance manual | Partially resolved with opt-in script, not part of normal tests. |

## Unknowns

- Exact commit boundaries are unknown because there is no `.git` history.
- No live external provider call was made during this review.
- No browser automation was run against current previews during this review.
- Whether OpenAI performs better than DeepSeek in this local setup was not tested.
