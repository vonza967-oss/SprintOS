# SprintOS Fix Roadmap

## Priority 0 — Must Fix Before More Features

### 1. Remove duplicate start paths from first open
- Problem: First open exposes both Quick Launch and classic sprint generation.
- Why it matters: This creates immediate decision fatigue and weakens the product's primary promise.
- Proposed fix: Make Quick Launch the default first-open path and hide plan-only sprint generation under Advanced.
- Risk: Low
- Effort: M
- Expected user impact: High
- Files likely touched: `sprintos.py`, `sprintos_core/ui_helpers.py`, `tests/test_dashboard_flow.py`, `tests/test_sprintos.py`, `README.md`
- Acceptance criteria: First open presents one dominant creation action; plan-only flow remains available but secondary.

### 2. Unify recommendation language
- Problem: Dashboard and project view use overlapping but different action labels.
- Why it matters: Users cannot tell whether actions are different or just renamed copies.
- Proposed fix: Standardize on one primary action label pattern across Today and Command Center.
- Risk: Low
- Effort: S
- Expected user impact: High
- Files likely touched: `sprintos.py`, `tests/test_dashboard_flow.py`, `tests/test_ui_helpers.py`
- Acceptance criteria: One consistent action label is used for dashboard/project continuation.

### 3. Make Command Center the dominant project control
- Problem: Command Center is surrounded by competing controls and loses authority.
- Why it matters: The product feels like a toolbox instead of a guide.
- Proposed fix: Reorder and visually demote adjacent manual actions; keep Command Center and Focus Session first.
- Risk: Medium
- Effort: M
- Expected user impact: High
- Files likely touched: `sprintos.py`, `tests/test_dashboard_flow.py`, `tests/test_sprintos.py`
- Acceptance criteria: The first actionable control in a selected project is always the Command Center action.

### 4. Simplify the first-open sidebar
- Problem: Today Dashboard, Quick Launch, classic generation, AI status, and projects all compete in one narrow column.
- Why it matters: The user sees system complexity before understanding the product.
- Proposed fix: Reduce sidebar to Continue, Start Project, and Projects; move other surfaces into compact support affordances.
- Risk: Medium
- Effort: M
- Expected user impact: High
- Files likely touched: `sprintos.py`, `tests/test_dashboard_flow.py`, `README.md`
- Acceptance criteria: First-open sidebar has one guidance card, one creation card, and one project list.

### 5. Fix default-port conflict ergonomics
- Problem: `scripts/launch.py` and default startup fail unclearly when `8844` is occupied by a stale process.
- Why it matters: A local-only tool must be especially clear about runtime conflicts.
- Proposed fix: Detect occupied port separately from healthy current-instance detection and print explicit next steps.
- Risk: Low
- Effort: S
- Expected user impact: Medium
- Files likely touched: `scripts/launch.py`, `scripts/stop.py`, `tests/test_testing_tools.py`
- Acceptance criteria: Port conflict produces a clear human-readable explanation and identifies whether another SprintOS instance is likely running.

## Priority 1 — Fix Next

### 6. Linearize the workspace stage
- Problem: Export, Snapshot, Sync, Verify, Release, and Feedback all appear as peers.
- Why it matters: The user has to understand internal process design to move forward.
- Proposed fix: Present a single workspace lane in order and collapse later steps until prerequisites exist.
- Risk: Medium
- Effort: M
- Expected user impact: High
- Files likely touched: `sprintos.py`, `tests/test_workspace_flow.py`, `tests/test_release_flow.py`, `tests/test_sprintos.py`
- Acceptance criteria: Workspace actions appear in one ordered sequence with clear stage gating.

### 7. Collapse report / ZIP clutter
- Problem: Many panels expose multiple report/download/copy actions at once.
- Why it matters: Output utilities visually overpower the main work.
- Proposed fix: Group low-frequency export actions into compact details blocks.
- Risk: Low
- Effort: S
- Expected user impact: Medium
- Files likely touched: `sprintos.py`, `tests/test_sprintos.py`
- Acceptance criteria: Primary panels show one main action and optional secondary utilities behind disclosure.

### 8. Hide AI controls unless user opts in
- Problem: AI status, routing, and eval concepts appear too early.
- Why it matters: Most sessions do not need AI tuning, and the UI pays a complexity tax for showing it.
- Proposed fix: Collapse AI tools by default and remove global AI surface from the first-open sidebar.
- Risk: Low
- Effort: S
- Expected user impact: Medium
- Files likely touched: `sprintos.py`, `tests/test_ai_providers.py`, `tests/test_dashboard_flow.py`
- Acceptance criteria: AI controls are still available but never primary unless AI is explicitly being configured.

### 9. Demote Setup Doctor and Local Runtime
- Problem: Setup and runtime detail currently occupy too much strategic UI space.
- Why it matters: Operational data is crowding out action guidance.
- Proposed fix: Keep a compact warning/status line with review access instead of full panels in the main flow.
- Risk: Low
- Effort: S
- Expected user impact: Medium
- Files likely touched: `sprintos.py`, `tests/test_dashboard_flow.py`, `README.md`
- Acceptance criteria: Setup and runtime remain accessible without dominating the dashboard.

## Priority 2 — Polish

### 10. Reduce vocabulary complexity
- Problem: Too many subsystem names appear in the main flow.
- Why it matters: Product comprehension is slowed by terminology overhead.
- Proposed fix: Rename labels toward plain-English, user-goal language.
- Risk: Low
- Effort: M
- Expected user impact: High
- Files likely touched: `sprintos.py`, `README.md`, `docs/ARCHITECTURE.md`, tests touching labels
- Acceptance criteria: A new user can infer purpose from labels without reading docs.

### 11. Simplify README and operator docs
- Problem: Current docs foreground subsystem breadth over main usage.
- Why it matters: The docs reinforce the feeling of a complex platform.
- Proposed fix: Lead documentation with one core flow and move detailed capability inventory lower.
- Risk: Low
- Effort: S
- Expected user impact: Medium
- Files likely touched: `README.md`, `docs/ARCHITECTURE.md`
- Acceptance criteria: README explains how to start, continue, and finish one project before listing feature areas.

### 12. Split oversized test harnesses
- Problem: `tests/test_sprintos.py` and `scripts/smoke.py` are becoming maintenance choke points.
- Why it matters: Large files slow safe refactors and obscure intent.
- Proposed fix: Split by area while preserving existing coverage and commands.
- Risk: Medium
- Effort: M
- Expected user impact: Low direct, high engineering leverage
- Files likely touched: `tests/test_sprintos.py`, `scripts/smoke.py`, `scripts/test_full.py`
- Acceptance criteria: Coverage remains equivalent; files are smaller and area-focused.

## Priority 3 — Later

### 13. Continue extracting stable seams from `sprintos.py`
- Problem: Main app file combines route handling, DB schema, rendering, orchestration, and artifact generation.
- Why it matters: Future simplification work will get slower and riskier.
- Proposed fix: Move stable, low-risk slices into `sprintos_core/` without changing `python3 sprintos.py`.
- Risk: Medium
- Effort: L
- Expected user impact: Low immediate, high long-term
- Files likely touched: `sprintos.py`, `sprintos_core/*`, tests
- Acceptance criteria: Entry point unchanged; behavior unchanged; major domains have clearer boundaries.

### 14. Introduce explicit migration helpers
- Problem: Schema setup and migrations are still mixed inside `init_db()`.
- Why it matters: Future persistence changes are easy to mishandle.
- Proposed fix: Add explicit local migration helpers while keeping SQLite local-only behavior intact.
- Risk: Medium
- Effort: M
- Expected user impact: Low immediate
- Files likely touched: `sprintos.py`, `tests/test_sprintos.py`
- Acceptance criteria: Schema evolution logic is separated from baseline table creation.

### 15. Trim overhydrated project payloads
- Problem: Project responses carry a very large amount of nested state.
- Why it matters: UI complexity and coupling increase together.
- Proposed fix: Separate always-needed view state from on-demand detail state.
- Risk: Medium
- Effort: M
- Expected user impact: Medium
- Files likely touched: `sprintos.py`, `tests/test_dashboard_flow.py`, `tests/test_sprintos.py`
- Acceptance criteria: Main project view loads only the state needed for current presentation; advanced detail remains available on demand.
