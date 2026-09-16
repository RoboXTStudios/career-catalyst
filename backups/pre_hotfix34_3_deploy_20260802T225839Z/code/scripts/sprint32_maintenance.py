"""Safe post-merge Sprint 32 audit, migration, and cleanup entry point."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
from typing import Any, Optional

try:
    from .application_tracker import TRACKER_PATH, load_application_tracker, save_application_tracker
    from .materials_library import find_exact_role_package
    from .role_archive import archive_role
    from .role_integrity import audit_role_integrity, write_integrity_report
    from .role_lifecycle import migrate_legacy_statuses
    from .sprint32_cleanup import APPLY_CONFIRMATION, apply_storage_cleanup, plan_storage_cleanup
    from .storage_paths import (
        canonical_archive_root,
        canonical_export_root,
        canonical_quarantine_root,
        canonical_report_root,
    )
except ImportError:  # pragma: no cover
    from application_tracker import TRACKER_PATH, load_application_tracker, save_application_tracker
    from materials_library import find_exact_role_package
    from role_archive import archive_role
    from role_integrity import audit_role_integrity, write_integrity_report
    from role_lifecycle import migrate_legacy_statuses
    from sprint32_cleanup import APPLY_CONFIRMATION, apply_storage_cleanup, plan_storage_cleanup
    from storage_paths import canonical_archive_root, canonical_export_root, canonical_quarantine_root, canonical_report_root


MIGRATION_CONFIRMATION = "APPLY SPRINT32 MIGRATION"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def migration_plan(project_root: Path) -> dict[str, Any]:
    """Return an idempotent migration plan without writing."""
    records = load_application_tracker(project_root)
    migrated, report = migrate_legacy_statuses(records, migrated_at="dry-run")
    legacy_archives = [
        {
            "id": str(record.get("id") or ""),
            "status": str(record.get("status") or ""),
            "archive_reason": str(record.get("archive_reason") or ""),
        }
        for record in migrated
        if record.get("archived") is True
    ]
    return {
        "project_root": str(project_root.resolve()),
        "tracker_sha256": _sha256(project_root / TRACKER_PATH),
        **report,
        "legacy_archives": legacy_archives,
        "legacy_archive_count": len(legacy_archives),
        "would_mutate": bool(report["changed_count"] or legacy_archives),
    }


def create_migration_backup(
    project_root: Path,
    *,
    export_root: Path,
    backup_root: Path,
    timestamp: str,
) -> dict[str, Any]:
    """Back up the tracker and exact packages that migration may remove."""
    destination = backup_root / f"pre_sprint32_{timestamp}"
    if destination.exists():
        raise ValueError(f"Backup destination already exists: {destination}")
    destination.mkdir(parents=True)
    tracker_path = project_root / TRACKER_PATH
    tracker_target = destination / TRACKER_PATH
    tracker_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(tracker_path, tracker_target)
    records = load_application_tracker(project_root)
    package_backups: list[dict[str, str]] = []
    for record in records:
        if record.get("archived") is not True:
            continue
        package = find_exact_role_package(project_root, record, export_root=export_root)
        if not package.get("folder"):
            continue
        source = Path(package["folder"]).resolve()
        target = destination / "packages" / str(record.get("id") or source.name)
        shutil.copytree(source, target)
        package_backups.append(
            {"role_id": str(record.get("id") or ""), "source": str(source), "backup": str(target)}
        )
    files = [path for path in sorted(destination.rglob("*")) if path.is_file()]
    manifest = {
        "created_at": timestamp,
        "project_root": str(project_root),
        "export_root": str(export_root),
        "files": [
            {
                "path": str(path.relative_to(destination)),
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for path in files
        ],
        "package_backups": package_backups,
    }
    manifest_path = destination / "backup_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for item in manifest["files"]:
        path = destination / item["path"]
        if _sha256(path) != item["sha256"]:
            raise ValueError(f"Backup checksum verification failed: {path}")
    return {"backup_root": str(destination), "manifest_path": str(manifest_path), "manifest": manifest}


def apply_migration(
    project_root: Path,
    *,
    export_root: Path,
    archive_root: Path,
    backup_root: Path,
    confirmation: str,
    app_stopped: bool,
    expected_tracker_sha256: str = "",
    timestamp: Optional[str] = None,
) -> dict[str, Any]:
    """Apply the accepted migration after backup, drift, and schema checks."""
    if confirmation != MIGRATION_CONFIRMATION:
        raise ValueError(f"Migration apply requires exact confirmation: {MIGRATION_CONFIRMATION}")
    if not app_stopped:
        raise ValueError("Migration apply requires confirmation that Career Catalyst is stopped.")
    tracker_path = project_root / TRACKER_PATH
    current_fingerprint = _sha256(tracker_path)
    if expected_tracker_sha256 and current_fingerprint != expected_tracker_sha256:
        raise ValueError("Tracker fingerprint drifted after dry-run; refusing migration.")
    plan = migration_plan(project_root)
    if plan["unknown_statuses"]:
        raise ValueError("Unknown statuses must be resolved before migration apply.")
    stamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = create_migration_backup(
        project_root, export_root=export_root, backup_root=backup_root, timestamp=stamp
    )
    records = load_application_tracker(project_root)
    migrated, status_report = migrate_legacy_statuses(records, migrated_at=stamp)
    save_application_tracker(migrated, project_root)
    archived: list[str] = []
    for item in list(plan["legacy_archives"]):
        tracker_id = item["id"]
        archive_role(
            tracker_id,
            "Rejected" if str(item["status"]) == "Rejected" else "Withdrawn / Closed",
            project_root,
            export_root=export_root,
            archive_root=archive_root,
            allow_legacy_archived=True,
        )
        archived.append(tracker_id)
    post = migration_plan(project_root)
    if post["would_mutate"]:
        raise ValueError("Post-migration dry-run is not a no-op; use the recorded backup to roll back.")
    return {
        "backup": backup,
        "status_migration": status_report,
        "legacy_archives_migrated": archived,
        "pre_tracker_sha256": current_fingerprint,
        "post_tracker_sha256": _sha256(tracker_path),
        "post_migration_noop": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--export-root", type=Path)
    parser.add_argument("--archive-root", type=Path)
    parser.add_argument("--report-root", type=Path)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("audit")
    migration = subparsers.add_parser("migration")
    migration.add_argument("--apply", action="store_true")
    migration.add_argument("--confirm", default="")
    migration.add_argument("--confirm-app-stopped", action="store_true")
    migration.add_argument("--expected-tracker-sha256", default="")
    cleanup = subparsers.add_parser("cleanup")
    cleanup.add_argument("--repository-root", type=Path, required=True)
    cleanup.add_argument("--apply", action="store_true")
    cleanup.add_argument("--confirm", default="")
    cleanup.add_argument("--confirm-app-stopped", action="store_true")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = _parser().parse_args(argv)
    runtime = args.runtime_root.resolve()
    exports = args.export_root.resolve() if args.export_root else canonical_export_root(runtime)
    archives = args.archive_root.resolve() if args.archive_root else canonical_archive_root(runtime)
    reports = args.report_root.resolve() if args.report_root else canonical_report_root(runtime)
    if args.command == "audit":
        report = audit_role_integrity(runtime, export_root=exports, archive_root=archives)
        paths = write_integrity_report(report, report_root=reports)
        print(json.dumps({**report, "report_paths": paths}, indent=2, sort_keys=True))
        return 2 if report["critical_count"] else 0
    if args.command == "migration":
        plan = migration_plan(runtime)
        if not args.apply:
            print(json.dumps(plan, indent=2, sort_keys=True))
            return 2 if plan["unknown_statuses"] else 0
        backups = exports.parent / "backups"
        result = apply_migration(
            runtime,
            export_root=exports,
            archive_root=archives,
            backup_root=backups,
            confirmation=args.confirm,
            app_stopped=args.confirm_app_stopped,
            expected_tracker_sha256=args.expected_tracker_sha256,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    plan = plan_storage_cleanup(
        repository_root=args.repository_root,
        runtime_root=runtime,
        export_root=exports,
        archive_root=archives,
    )
    if not args.apply:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    result = apply_storage_cleanup(
        plan,
        quarantine_root=canonical_quarantine_root(runtime),
        confirmation=args.confirm,
        app_stopped=args.confirm_app_stopped,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
