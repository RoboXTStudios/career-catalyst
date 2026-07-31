# Sprint 32 maintenance

Run these commands only after Sprint 32 has merged and the production app is stopped. Audit and dry-run modes do not mutate data.

```bash
RUNTIME=/Users/trisha.lynch/.codex/.chatgpt-projects/g-p-6a5d817ef0788191bbc5427a19234f4c/main_runtime_60cca23
EXPORTS=/Users/trisha.lynch/Documents/career-catalyst/exports
ARCHIVE=/Users/trisha.lynch/Documents/career-catalyst/archive
REPORTS=/Users/trisha.lynch/Documents/career-catalyst/reports
REPOSITORY=/Users/trisha.lynch/Documents/career-catalyst

python3 -m scripts.sprint32_maintenance --runtime-root "$RUNTIME" --export-root "$EXPORTS" --archive-root "$ARCHIVE" --report-root "$REPORTS" audit
python3 -m scripts.sprint32_maintenance --runtime-root "$RUNTIME" --export-root "$EXPORTS" --archive-root "$ARCHIVE" migration
python3 -m scripts.sprint32_maintenance --runtime-root "$RUNTIME" --export-root "$EXPORTS" --archive-root "$ARCHIVE" cleanup --repository-root "$REPOSITORY"
```

Record the tracker SHA-256 printed or independently verified after the accepted dry run. Apply the lifecycle/archive migration first:

```bash
python3 -m scripts.sprint32_maintenance --runtime-root "$RUNTIME" --export-root "$EXPORTS" --archive-root "$ARCHIVE" migration --apply --confirm-app-stopped --expected-tracker-sha256 TRACKER_SHA256 --confirm "APPLY SPRINT32 MIGRATION"
```

Run audit and both dry runs again. Only after reviewing the cleanup plan, quarantine approved uncertain files and remove provably disposable caches:

```bash
python3 -m scripts.sprint32_maintenance --runtime-root "$RUNTIME" --export-root "$EXPORTS" --archive-root "$ARCHIVE" cleanup --repository-root "$REPOSITORY" --apply --confirm-app-stopped --confirm "QUARANTINE SPRINT32 CLEANUP"
```

Migration creates `/Users/trisha.lynch/Documents/career-catalyst/backups/pre_sprint32_<timestamp>/` before changing the tracker or archived package folders. Its `backup_manifest.json` records checksums and original package paths.

Rollback procedure:

1. Keep Career Catalyst stopped.
2. Copy the backed-up `data/application_tracker.yml` to the recorded runtime location using an atomic replacement.
3. Restore each package directory from `backup_manifest.json` to its recorded original path only if that path is absent.
4. Move newly created Sprint 32 archive bundles to a separate rollback holding folder; do not delete them.
5. Run the integrity audit before relaunching Career Catalyst.

Cleanup quarantine is reversible: use `cleanup_manifest.json` to move each quarantined path back to its recorded original path. Cache deletions are intentionally limited to reproducible cache or operating-system metadata files.
