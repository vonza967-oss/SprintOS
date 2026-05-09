# Next Recommended Codex Prompt

Audit SprintOS and implement a focused UX simplification PR only. Do not add new features.

Goal:
Reduce first-open confusion and make SprintOS feel like one guided lane instead of a control panel.

Constraints:
- Keep SprintOS local-first.
- Do not add dependencies.
- Preserve `python3 sprintos.py`.
- Do not add auth, cloud sync, deployment automation, GitHub automation, or automatic Codex execution.
- Do not change backup/snapshot/release behavior except for presentation and labeling.
- Keep existing routes and artifact behavior working unless a small rename or UI move requires a safe compatibility shim.

Required scope:

1. Simplify first open
- Make Quick Launch the only visible creation flow on first open.
- Move classic sprint generation behind an `Advanced` disclosure.
- Remove AI Status from the first-open sidebar.
- Reduce the sidebar to:
  - Today / Continue card
  - Quick Launch / Start Project
  - Projects list
  - compact support status only if needed

2. Unify action language
- Replace overlapping labels like `Run Today Action` and `Run Recommended Action` with one consistent primary label.
- Rename `Run Run & Verify` to something plain-English like `Verify Workspace`.
- Prefer plain-English labels over internal system names where possible.

3. Strengthen Command Center dominance
- In the selected project view, make the Project Command Center and Focus Session the clear primary surfaces.
- Demote report/ZIP/copy utility actions behind disclosures or smaller secondary controls.
- Keep advanced sections available, but visually secondary.

4. Preserve behavior
- Do not remove existing capabilities.
- Do not change the local-only safety model.
- Do not change the artifact chain logic.
- Do not change backup/snapshot restore semantics.

Deliverables:
- UI updates in the existing vanilla HTML/CSS/JS structure
- Updated tests for the changed labels and first-open layout expectations
- Small README adjustment only if needed to match the simplified first-open flow

Verification:
- `python3 scripts/test_fast.py`
- `python3 scripts/smoke.py`
- `python3 scripts/health.py`
- `python3 -m py_compile sprintos.py tests/*.py scripts/*.py sprintos_core/*.py`

Definition of done:
- A first-time user sees one dominant way to start.
- A returning user sees one dominant way to continue.
- A selected project shows one dominant next action.
- The app feels materially calmer without losing local-first capability.
