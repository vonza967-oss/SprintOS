# Backup And Git Baseline

The current local-only baseline workflow lives in `docs/BACKUP_AND_GIT_BASELINE.md`.

Common commands:

```bash
npm run backup
npm run safety:check
npm run baseline:report
```

These commands create a source-safe archive under `local_backups/`, check tracked and staged files for blocked local/runtime paths or obvious secrets, and print local status only. They do not push, create remotes, deploy, reset, clean, or remove files.
