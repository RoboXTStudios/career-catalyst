"""Dry-run-first repair for stale durable role references."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import yaml

try:
    from .materials_library import find_exact_role_package, portable_manifest_paths
    from .role_state_resolver import resolve_job_file, tracker_records
except ImportError:  # pragma: no cover
    from materials_library import find_exact_role_package, portable_manifest_paths
    from role_state_resolver import resolve_job_file, tracker_records

CONFIRMATION = "APPLY HOTFIX 34.3 PATH REPAIR"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_report(runtime_root: Path, export_root: Path) -> Dict[str, Any]:
    runtime_root = runtime_root.expanduser().resolve()
    export_root = export_root.expanduser().resolve()
    tracker_path = runtime_root / "data" / "application_tracker.yml"
    tracker = yaml.safe_load(tracker_path.read_text(encoding="utf-8")) or {}
    records = tracker_records(tracker)
    roles, repaired = [], []
    for record in records:
        role_id = str(record.get("id") or record.get("prospect_id") or "")
        job = resolve_job_file(record, runtime_root)
        package = find_exact_role_package(runtime_root, record, export_root=export_root)
        manifest = package.get("manifest") or {}
        folder = package.get("folder")
        manifest_path = str(Path(folder) / "manifest.json") if folder and manifest else ""
        stale = []
        stored_job = str(record.get("job_file") or "")
        if job.get("status") == "valid" and stored_job:
            try:
                stored_path = Path(stored_job).expanduser()
                if not stored_path.is_absolute():
                    stored_path = runtime_root / stored_path
                if stored_path.resolve() != Path(str(job["path"])).resolve():
                    stale.append("job_file")
            except OSError:
                stale.append("job_file")
        for field in ("files", "materials"):
            for key, value in dict(manifest.get(field) or {}).items():
                if str(value).startswith(("/private/", "/tmp/", "/var/")):
                    stale.append(f"manifest.{field}.{key}")
        if stale:
            repaired.append(role_id)
        roles.append({"id": role_id, "job": {k: v for k, v in job.items() if k != "parsed"}, "package_folder": str(folder or ""), "manifest_path": manifest_path, "stale_fields": sorted(set(stale)), "selected_evidence_ids": [str(v) for v in record.get("evidence_project_ids") or []]})
    return {"schema": "career-catalyst/hotfix-34.3-path-repair", "generated_at": datetime.now(timezone.utc).isoformat(), "runtime_root": str(runtime_root), "export_root": str(export_root), "tracker_path": str(tracker_path), "tracker_sha256": _sha256(tracker_path), "record_count": len(records), "roles_with_repairs": len(repaired), "role_ids_with_repairs": repaired, "roles": roles, "apply": {"allowed": False, "confirmation": CONFIRMATION}}


def _apply(runtime_root: Path, export_root: Path, report: Dict[str, Any], backup_root: Path) -> Dict[str, Any]:
    backup_root.mkdir(parents=True, exist_ok=True)
    tracker_path = runtime_root / "data" / "application_tracker.yml"
    shutil.copy2(tracker_path, backup_root / "application_tracker.yml")
    tracker = yaml.safe_load(tracker_path.read_text(encoding="utf-8")) or {}
    records = tracker_records(tracker)
    for record, role in zip(records, report["roles"]):
        if not role.get("stale_fields"):
            continue
        job = resolve_job_file(record, runtime_root)
        if job.get("status") == "valid":
            record["job_file"] = str(Path(str(job["path"])).relative_to(runtime_root))
        manifest_path = Path(role.get("manifest_path") or "")
        if manifest_path.is_file():
            target = backup_root / "manifests" / manifest_path.relative_to(export_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(manifest_path, target)
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            payload["files"] = portable_manifest_paths(manifest_path.parent, payload.get("files") or {})
            payload["materials"] = portable_manifest_paths(manifest_path.parent, payload.get("materials") or {})
            manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tracker_path.write_text(yaml.safe_dump(tracker, sort_keys=False), encoding="utf-8")
    return {"backup_root": str(backup_root), "tracker_sha256": _sha256(tracker_path)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--export-root", required=True, type=Path)
    parser.add_argument("--report-json", required=True, type=Path)
    parser.add_argument("--report-md", type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--backup-root", type=Path)
    args = parser.parse_args(argv)
    report = build_report(args.runtime_root, args.export_root)
    if args.apply:
        if args.confirm != CONFIRMATION:
            parser.error(f"--apply requires --confirm {CONFIRMATION!r}")
        backup = args.backup_root or args.report_json.parent / ("path_repair_backup_" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
        report["apply"] = _apply(args.runtime_root.expanduser().resolve(), args.export_root.expanduser().resolve(), report, backup)
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.report_md:
        args.report_md.parent.mkdir(parents=True, exist_ok=True)
        lines = ["# Hotfix 34.3 durable path repair", "", f"Runtime: `{report['runtime_root']}`", f"Export root: `{report['export_root']}`", f"Records: {report['record_count']}", f"Roles requiring repair: {report['roles_with_repairs']}", "", "| Role | Job status | Stale fields |", "|---|---|---|"]
        lines.extend(f"| {role['id']} | {role['job'].get('status')} | {', '.join(role['stale_fields']) or 'none'} |" for role in report["roles"])
        args.report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
