# Backup And Git Baseline

This workflow is local-only and non-destructive. It creates a source-safe archive, scans tracked and staged files for blocked local paths or obvious secrets, and prints the current git status. It does not push, create remotes, deploy, reset, clean, or remove files.

## Commands

Create a local backup:

```bash
npm run backup
```

Run the safety check:

```bash
npm run safety:check
```

Run both and print the current git status:

```bash
npm run baseline:report
```

The Makefile aliases use the same Node utilities:

```bash
make backup
make safety-check
make baseline-report
```

## What The Backup Includes

`scripts/create-local-backup.mjs` writes a timestamped archive to `local_backups/`:

```text
local_backups/sprintos-local-backup-YYYYMMDD-HHMMSS.tar.gz
```

The archive is meant to preserve the source baseline before product logic changes. It omits local runtime state, generated outputs, secrets, and backup recursion.

## What Is Excluded

The backup and safety baseline cover:

- `.env` and every `.env*` file
- `.git`, `.hg`, and `.svn` internals
- dependency folders such as `node_modules/`, `env/`, `venv/`, and `.venv/`
- caches such as `.cache/`, `.pytest_cache/`, `.ruff_cache/`, `.turbo/`, and Python bytecode
- build outputs such as `dist/`, `build/`, `coverage/`, `htmlcov/`, `out/`, `.next/`, and `.nuxt/`
- screenshots and browser test artifacts such as `screenshots/`, `.playwright-cli/`, `playwright-report/`, and `test-results/`
- runtime exports and generated workspaces under `exports/` and `workspaces/`
- local SQLite/runtime state under `data/`
- local backup folders such as `local_backups/` and `backups/`
- generated raw prompt/provider request/response/payload logs by filename pattern
- files with obvious API key or bearer-token patterns

The scripts print file paths and finding types only. They never print secret values.

## Safety Check Behavior

`scripts/pre-commit-secret-check.mjs` inspects tracked files plus staged files. It fails when git is already tracking, or is about to commit, any blocked env file, runtime/generated folder, generated payload log, local runtime file, or obvious non-placeholder secret pattern.

If it fails, remove the file from git tracking or replace real secrets with safe placeholders, then rerun:

```bash
npm run safety:check
```

Do not use destructive cleanup commands as part of this baseline. Avoid `git reset --hard`, `git clean`, force pushes, remote creation, deployment commands, or automatic repo publishing.

## Dev Safety Page

`npm run safety:check` and `npm run backup` update `public/dev/safety-report.json`. In a Vite dev session, open:

```text
/dev/safety
```

The page reads that local JSON report and shows ignored-path coverage, the latest secret-scan status, finding counts, and the last local backup archive path. It does not call remote services.

## Optional Local Hook

To run the safety check before each local commit:

```bash
git config core.hooksPath .githooks
```

This only changes local git hook configuration for this checkout.

## Suggested Baseline Flow

```bash
npm run baseline:report
git status --short
```

Review the paths listed by git. If you choose to make a local commit, add only source, docs, scripts, and intentionally reviewed config files. Keep runtime outputs, exports, local databases, backups, screenshots, generated payload logs, and secrets out of git.
