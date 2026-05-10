.PHONY: backup safety-check baseline-report

backup:
	node scripts/create-local-backup.mjs

safety-check:
	node scripts/pre-commit-secret-check.mjs

baseline-report: safety-check backup
	git status --short
