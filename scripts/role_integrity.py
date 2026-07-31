"""Deterministic non-mutating role, archive, and package integrity audit."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Optional, Union

try:
    from .application_tracker import load_application_tracker
    from .role_lifecycle import LIVE_STATUSES, canonical_status, filter_live_records, lifecycle_counts
    from .storage_paths import canonical_archive_root, canonical_export_root, canonical_report_root
except ImportError:  # pragma: no cover
    from application_tracker import load_application_tracker
    from role_lifecycle import LIVE_STATUSES, canonical_status, filter_live_records, lifecycle_counts
    from storage_paths import canonical_archive_root, canonical_export_root, canonical_report_root


PathInput = Union[str, Path]
VALID_ARCHIVE_REASONS = {"Rejected", "Withdrawn / Closed", "Hidden / Invalid"}


def _issue(code: str, severity: str, message: str, **details: Any) -> dict[str, Any]:
    return {"code": code, "severity": severity, "message": message, **details}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def audit_role_integrity(
    project_root: PathInput,
    *,
    export_root: Optional[PathInput] = None,
    archive_root: Optional[PathInput] = None,
) -> dict[str, Any]:
    """Return stable findings without changing tracker, archives, or materials."""
    root = Path(project_root).resolve()
    exports = canonical_export_root(root, injected_root=export_root)
    archives = Path(archive_root).resolve() if archive_root else canonical_archive_root(root)
    records = load_application_tracker(root)
    live = filter_live_records(records)
    live_ids = [str(record.get("id") or "") for record in live]
    issues: list[dict[str, Any]] = []

    seen: set[str] = set()
    for record in records:
        tracker_id = str(record.get("id") or "")
        raw_status = str(record.get("status") or "")
        status = canonical_status(raw_status)
        if tracker_id in seen:
            issues.append(_issue("duplicate_role_id", "critical", f"Duplicate role id: {tracker_id}", role_id=tracker_id))
        seen.add(tracker_id)
        if raw_status.strip().lower() == "paused":
            issues.append(_issue("legacy_paused_status", "critical", f"Paused role requires migration: {tracker_id}", role_id=tracker_id))
        if status not in LIVE_STATUSES:
            issues.append(_issue("unknown_status", "critical", f"Unknown status for {tracker_id}: {raw_status}", role_id=tracker_id, status=raw_status))
        if record.get("archived") is True:
            issues.append(_issue("legacy_full_archive_record", "critical", f"Archived role remains in live tracker: {tracker_id}", role_id=tracker_id))
            if record.get("package_manifest") or record.get("material_paths"):
                issues.append(_issue("archived_live_package_state", "critical", f"Archived role carries live package state: {tracker_id}", role_id=tracker_id))
        if record.get("show_on_dashboard") is False and status not in {"Rejected", "Withdrawn / Closed"}:
            issues.append(_issue("invisible_live_role", "critical", f"Live role is explicitly hidden: {tracker_id}", role_id=tracker_id))

    manifests = sorted(archives.glob("*/*/role_manifest.json")) if archives.is_dir() else []
    archive_owners: set[str] = set()
    archive_materials: set[Path] = set()
    for manifest_path in manifests:
        payload = _load_json(manifest_path)
        owner = str(payload.get("original_role_id") or "")
        archive_owners.add(owner)
        if not payload:
            issues.append(_issue("malformed_archive_manifest", "critical", f"Malformed archive manifest: {manifest_path}", path=str(manifest_path)))
            continue
        if str(payload.get("legacy_archive_reason") or "").strip().lower() == "passed":
            issues.append(_issue("legacy_passed_reason", "warning", f"Legacy archive reason Passed retained for {owner}", role_id=owner))
        archive_reason = str(payload.get("archive_reason") or "").strip()
        if archive_reason and archive_reason not in VALID_ARCHIVE_REASONS:
            issues.append(
                _issue(
                    "malformed_archive_reason",
                    "warning",
                    f"Archive reason is not canonical for {owner}: {archive_reason}",
                    role_id=owner,
                    archive_reason=archive_reason,
                )
            )
        final_status = str(payload.get("final_status") or "")
        legacy_status = str(payload.get("legacy_status") or "")
        if canonical_status(final_status) != final_status:
            issues.append(_issue("conflicting_archive_status", "warning", f"Archive final status is not canonical for {owner}", role_id=owner, final_status=final_status, legacy_status=legacy_status))
        for material in payload.get("materials") or []:
            candidate = (manifest_path.parent / str(material.get("filename") or "")).resolve()
            archive_materials.add(candidate)
            if not candidate.is_file():
                issues.append(_issue("archive_material_missing", "critical", f"Archive material is missing: {candidate}", role_id=owner, path=str(candidate)))

    if archives.is_dir():
        for folder in sorted(path for path in archives.glob("*/*") if path.is_dir()):
            if not (folder / "role_manifest.json").is_file():
                issues.append(_issue("archive_folder_missing_manifest", "critical", f"Archive folder has no manifest: {folder}", path=str(folder)))
        index_path = archives / "archive_index.json"
        if index_path.is_file():
            for entry in (_load_json(index_path).get("archives") or []):
                manifest_path = Path(str(entry.get("manifest_path") or ""))
                if not manifest_path.is_file():
                    issues.append(_issue("archive_index_missing_manifest", "critical", f"Archive index entry has no manifest: {manifest_path}", path=str(manifest_path)))

    package_owners: dict[str, list[str]] = {}
    referenced_materials: set[Path] = set(archive_materials)
    if exports.is_dir():
        for manifest_path in sorted(exports.glob("active/*/*/manifest.json")):
            payload = _load_json(manifest_path)
            owner = str(payload.get("prospect_id") or "")
            package_owners.setdefault(owner, []).append(str(manifest_path.parent))
            if owner not in live_ids:
                issues.append(_issue("orphan_package_folder", "warning", f"Package has no live or archive owner: {manifest_path.parent}", role_id=owner, path=str(manifest_path.parent)))
            for value in dict(payload.get("files") or {}).values():
                referenced_materials.add(Path(str(value)).resolve())
            for value in dict(payload.get("materials") or {}).values():
                referenced_materials.add(Path(str(value)).resolve())
        for owner, folders in package_owners.items():
            if owner and len(folders) > 1:
                issues.append(_issue("duplicate_package_directories", "warning", f"Multiple package directories for {owner}", role_id=owner, paths=folders))
        for record in live:
            owner = str(record.get("id") or "")
            if owner in package_owners:
                continue
            manifest = record.get("package_manifest")
            has_package_state = bool(record.get("material_paths")) or isinstance(manifest, dict)
            if has_package_state:
                issues.append(
                    _issue(
                        "live_package_folder_missing",
                        "warning",
                        f"Live role has package state but no package folder: {owner}",
                        role_id=owner,
                    )
                )
        for path in sorted(exports.rglob("*")):
            if path.is_file() and path.name != "manifest.json" and path.resolve() not in referenced_materials:
                issues.append(_issue("unreferenced_material", "warning", f"Material file is not referenced: {path}", path=str(path)))

    counts = lifecycle_counts(live)
    for status in LIVE_STATUSES:
        filtered = filter_live_records(live, status)
        if counts[status] != len(filtered):
            issues.append(_issue("summary_filter_mismatch", "critical", f"Summary/filter mismatch for {status}", status=status))
    all_ids = {str(record.get("id") or "") for record in filter_live_records(live)}
    for role_id in live_ids:
        if role_id not in all_ids:
            issues.append(_issue("unaddressable_live_role", "critical", f"Live role is absent from All: {role_id}", role_id=role_id))

    issues.sort(key=lambda item: (item["severity"], item["code"], item.get("role_id", ""), item.get("path", "")))
    return {
        "schema_version": 1,
        "project_root": str(root),
        "export_root": str(exports),
        "archive_root": str(archives),
        "live_role_count": len(live),
        "archive_manifest_count": len(manifests),
        "summary_counts": counts,
        "issues": issues,
        "critical_count": sum(item["severity"] == "critical" for item in issues),
        "warning_count": sum(item["severity"] == "warning" for item in issues),
    }


def write_integrity_report(
    report: dict[str, Any],
    *,
    report_root: PathInput,
    timestamp: Optional[str] = None,
) -> dict[str, str]:
    """Write JSON and Markdown audit reports outside Git."""
    root = Path(report_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    json_path = root / f"sprint32_integrity_{stamp}.json"
    md_path = root / f"sprint32_integrity_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Sprint 32 Integrity Report",
        "",
        f"- Live roles: {report['live_role_count']}",
        f"- Archive manifests: {report['archive_manifest_count']}",
        f"- Critical findings: {report['critical_count']}",
        f"- Warnings: {report['warning_count']}",
        "",
        "## Findings",
        "",
    ]
    lines.extend(
        f"- **{item['severity'].upper()} — {item['code']}**: {item['message']}"
        for item in report["issues"]
    )
    if not report["issues"]:
        lines.append("- No findings.")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"json": str(json_path), "markdown": str(md_path)}
