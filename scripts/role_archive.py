"""Explicit, reversible tracker-level role archiving."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union

try:
    from .application_tracker import (
        TrackerUpdateError,
        get_record_status,
        is_archive_eligible,
        legacy_status_value,
        load_application_tracker,
        normalize_tracker_value,
        save_application_tracker,
    )
    from .materials_library import move_role_package
except ImportError:  # pragma: no cover
    from application_tracker import (
        TrackerUpdateError,
        get_record_status,
        is_archive_eligible,
        legacy_status_value,
        load_application_tracker,
        normalize_tracker_value,
        save_application_tracker,
    )
    from materials_library import move_role_package


PathInput = Union[str, Path]
ARCHIVE_REASONS = (
    "Rejected",
    "Withdrawn / Closed",
    "Passed",
    "Hidden / Invalid",
)


def infer_archive_reason(record: Dict[str, Any]) -> str:
    """Preserve useful legacy distinctions without changing canonical status."""
    if get_record_status(record) == "Rejected":
        return "Rejected"
    raw = normalize_tracker_value(legacy_status_value(record))
    if raw in {"pass", "passed", "declined", "do not pursue"}:
        return "Passed"
    if "hidden" in raw or "invalid" in raw:
        return "Hidden / Invalid"
    return "Withdrawn / Closed"


def _record(applications: list[Dict[str, Any]], tracker_id: str) -> Dict[str, Any]:
    entry = next(
        (item for item in applications if str(item.get("id")) == str(tracker_id)),
        None,
    )
    if entry is None:
        raise TrackerUpdateError(f"Tracker entry not found: {tracker_id}")
    return entry


def _apply_manifest_paths(entry: Dict[str, Any], manifest: Dict[str, Any]) -> None:
    entry["material_paths"] = dict(manifest.get("materials") or {})
    entry["package_manifest"] = dict(manifest)


def archive_role(
    tracker_id: str,
    archive_reason: str,
    project_root: Optional[PathInput] = None,
    *,
    export_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Archive one eligible record and move its exact package when present."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    applications = load_application_tracker(root)
    entry = _record(applications, tracker_id)
    if not is_archive_eligible(entry):
        raise TrackerUpdateError(
            f"Role '{tracker_id}' with status {get_record_status(entry)} is not archive-eligible."
        )
    reason = str(archive_reason or infer_archive_reason(entry)).strip()
    if reason not in ARCHIVE_REASONS:
        raise TrackerUpdateError(
            f"Unsupported archive reason '{reason}'."
        )
    previous_status = get_record_status(entry)
    moved = move_role_package(
        root,
        entry,
        archive=True,
        archive_reason=reason,
        export_root=Path(export_root) if export_root is not None else None,
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    entry.update(
        {
            "archived": True,
            "archived_at": timestamp,
            "archive_reason": reason,
            "pre_archive_status": previous_status,
        }
    )
    history = entry.setdefault("application_history", [])
    if isinstance(history, list):
        history.append(
            {
                "event": "role archived",
                "status": previous_status,
                "archive_reason": reason,
                "date": timestamp,
            }
        )
    if moved.get("manifest"):
        _apply_manifest_paths(entry, moved["manifest"])
    save_application_tracker(applications, root)
    return {"application": deepcopy(entry), "package": moved}


def restore_role(
    tracker_id: str,
    project_root: Optional[PathInput] = None,
    *,
    export_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Restore one archived role and package as Paused without regeneration."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    applications = load_application_tracker(root)
    entry = _record(applications, tracker_id)
    if entry.get("archived") is not True:
        raise TrackerUpdateError(f"Role '{tracker_id}' is not archived.")
    prior_status = str(entry.get("pre_archive_status") or get_record_status(entry))
    route_record = dict(entry)
    route_record["status"] = "Paused"
    moved = move_role_package(
        root,
        route_record,
        archive=False,
        export_root=Path(export_root) if export_root is not None else None,
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    entry.update(
        {
            "archived": False,
            "status": "Paused",
            "restored_from_status": prior_status,
            "status_updated_at": timestamp,
        }
    )
    history = entry.setdefault("application_history", [])
    if isinstance(history, list):
        history.append(
            {
                "event": "role restored as paused",
                "from": prior_status,
                "to": "Paused",
                "date": timestamp,
            }
        )
    if moved.get("manifest"):
        _apply_manifest_paths(entry, moved["manifest"])
    save_application_tracker(applications, root)
    return {"application": deepcopy(entry), "package": moved}


def bulk_archive_roles(
    tracker_ids: Iterable[str],
    project_root: Optional[PathInput] = None,
    *,
    reasons: Optional[Dict[str, str]] = None,
    export_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Archive only explicitly selected ids and report every outcome."""
    selected = list(dict.fromkeys(str(value) for value in tracker_ids if str(value)))
    result: Dict[str, Any] = {
        "selected_count": len(selected),
        "moved": [],
        "archived_without_materials": [],
        "skipped": [],
        "failed": {},
    }
    root = Path(project_root) if project_root is not None else Path.cwd()
    for tracker_id in selected:
        try:
            applications = load_application_tracker(root)
            entry = _record(applications, tracker_id)
            if not is_archive_eligible(entry):
                result["skipped"].append(tracker_id)
                continue
            archived = archive_role(
                tracker_id,
                (reasons or {}).get(tracker_id) or infer_archive_reason(entry),
                root,
                export_root=export_root,
            )
            if archived["package"].get("moved"):
                result["moved"].append(tracker_id)
            else:
                result["archived_without_materials"].append(tracker_id)
        except Exception as error:  # each explicit selection is reported independently
            result["failed"][tracker_id] = str(error)
    result["archived_count"] = len(result["moved"]) + len(
        result["archived_without_materials"]
    )
    return result
