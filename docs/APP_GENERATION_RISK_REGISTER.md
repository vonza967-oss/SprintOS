# App Generation Risk Register

Date: 2026-05-08

| Risk | Category | Severity | Likelihood | Current Mitigation | Gap | Recommended Fix | Priority |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AI provider reports usable but app generation fails with 503 | AI/reliability | High | High | Offline fallback | Generic AI status hides app-specific readiness | Add app-generation readiness and recent provider failure banner | P0 |
| Full Create App request appears hung | Product/reliability | High | Medium | Long HTTP timeout and fallback | User sees little progress context during multi-task run | Add task-level progress and timeout/fallback messaging | P0 |
| Fallback app is structurally valid but generic | Product/AI quality | High | High | Deterministic offline templates | User asked for a specific app, gets a broad scoring/tool shell | Add app-type-specific fallback templates and checks | P0 |
| Invalid JSON from DeepSeek/OpenAI | AI | High | Medium | Schema validation and fallback | Retried/repair path is absent | Add one safe JSON repair/retry for app_file_generation | P1 |
| Timeout/token defaults too low in some environments | AI/reliability | High | Medium | Configurable env vars | Setup Doctor does not warn specifically for app generation | Add app-generation budget checks | P0 |
| High input token footprint | Cost/reliability | Medium | High | Local cost estimates | app_file_generation prompt plus fallback schema is large | Trim expected schema context and use tighter instructions | P1 |
| Provider balance/402 or 503 not creator-friendly | UX | High | Medium | Diagnostics store reason | Create App result does not clearly explain fallback | Plain fallback banner with retry/provider action | P0 |
| Browser-side provider calls in generated app | Security | Critical | Low | Schema validation blocks provider endpoint markers | Keyword coverage may miss obfuscated calls | Keep validation, add tests for more network APIs | P1 |
| API key leakage in generated artifacts | Security | Critical | Low | Secret regex checks, ZIP exclusions | Regex coverage is not exhaustive | Expand secret patterns and scan Build/Deploy ZIPs in verification | P1 |
| `.env` copied into packages | Security | Critical | Low | ZIP helpers exclude `.env`; health checks | Need regression coverage for every package route | Add package-level `.env*` assertions to verification | P1 |
| File-serving path traversal | Security | Critical | Low | Safe path helpers and tests | Route sprawl increases missed route risk | Keep route allowlists centralized | P2 |
| Generated malicious JS | Security | High | Medium | Blocks network calls and provider endpoints | Does not reason about destructive browser behavior | Add denylist for dangerous browser APIs where appropriate | P2 |
| Preview source and downloaded source diverge | Reliability | High | Medium | Build Pack copies generated files | Multiple artifact paths increase confusion | Add checksum/manifest compare between preview, deploy, build | P1 |
| Test App disabled before workspace export | UX/QA | Medium | High | Verification exists through API | User cannot test draft from main app-first lane | Enable draft-level verification action | P0 |
| Verify App misses app-specific behavior | QA | High | High | Structural checks | Does not test budget, flashcard, or scorer behavior | Add app-type-specific smoke assertions | P1 |
| Package naming mismatch `TEST_PLAN.md` vs `test-plan.md` | Maintainability/UX | Medium | Medium | Build Pack includes both contexts | Confusing for users and docs | Standardize display and source naming | P2 |
| App names are raw truncated prompts | UX/product | Medium | High | AI can provide `app_name` when it succeeds | Fallback names are poor | Add deterministic app naming helper | P1 |
| SprintOS feels like artifact manager | Product | Medium | Medium | App Draft hero and Today Dashboard | Technical labels still leak | Rename secondary surfaces and keep app actions first | P2 |
| `sprintos.py` monolith slows changes | Maintainability | Medium | High | Some helpers in `sprintos_core/` | App generation spans many functions/routes | Move stable app-generation helpers to `sprintos_core/` gradually | P3 |
| Route presets not enabled for app_file_generation | Reliability | Medium | Medium | Defaults resolve to provider | No per-task budget/provider override | Add task-specific route/budget defaults | P1 |
| Live acceptance not automated | QA | Medium | High | Manual diagnostics and provider evals | Regressions can pass offline tests | Add opt-in live app generation acceptance script | P1 |
