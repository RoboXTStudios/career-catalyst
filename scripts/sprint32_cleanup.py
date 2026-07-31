"""Dry-run-first storage cleanup with quarantine for uncertain user files."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from typing import Any, Iterable, Mapping

try:
    from .application_tracker import load_application_tracker
except ImportError:  # pragma: no cover
    from application_tracker import load_application_tracker


APPLY_CONFIRMATION = "QUARANTINE SPRINT32 CLEANUP"
CACHE_DIRECTORY_NAMES = {"__pycache__", ".pytest_cache"}
SAFE_FILE_NAMES = {".DS_Store"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_fingerprint(path: Path) -> tuple[str, int]:
    """Hash directory membership and file content deterministically."""
    digest = hashlib.sha256()
    files = [item for item in sorted(path.rglob("*")) if item.is_file()]
    for item in files:
        relative = str(item.relative_to(path)).encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(_sha256(item)))
    return digest.hexdigest(), len(files)


def _entry(
    action: str,
    classification: str,
    path: Path,
    root_name: str,
    root: Path,
    reason: str,
    *,
    role_id: str = "",
) -> dict[str, Any]:
    payload = {
        "action": action,
        "classification": classification,
        "path": str(path),
        "root_name": root_name,
        "relative_path": str(path.relative_to(root)),
        "reason": reason,
        "role_id": role_id,
    }
    if path.is_file():
        payload["size"] = path.stat().st_size
        payload["sha256"] = _sha256(path)
    elif path.is_dir():
        payload["tree_sha256"], payload["file_count"] = _tree_fingerprint(path)
    return payload


def plan_storage_cleanup(
    *,
    repository_root: Path,
    runtime_root: Path,
    export_root: Path,
    archive_root: Path,
) -> dict[str, Any]:
    """Classify only provably disposable or clearly orphaned paths."""
    roots = {
        "repository": Path(repository_root).resolve(),
        "runtime": Path(runtime_root).resolve(),
        "exports": Path(export_root).resolve(),
    }
    try:
        tracker_records = load_application_tracker(roots["runtime"])
        live_ids = {
            str(record.get("id") or "")
            for record in tracker_records
            if record.get("archived") is not True
        }
    except Exception:
        tracker_records = []
        live_ids = set()
    referenced_paths: set[Path] = set()
    for record in tracker_records:
        values = list(dict(record.get("material_paths") or {}).values())
        manifest = record.get("package_manifest")
        if isinstance(manifest, dict):
            values.extend(dict(manifest.get("files") or {}).values())
            values.extend(dict(manifest.get("materials") or {}).values())
            values.append(manifest.get("manifest_path"))
        for value in values:
            if value:
                referenced_paths.add(Path(str(value)).expanduser().resolve())
    archive_ids: set[str] = set()
    archives = Path(archive_root).resolve()
    for manifest_path in sorted(archives.glob("*/*/role_manifest.json")) if archives.is_dir() else []:
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        archive_ids.add(str(payload.get("original_role_id") or ""))
        for item in payload.get("materials") or []:
            referenced_paths.add(
                (manifest_path.parent / str(item.get("filename") or "")).resolve()
            )

    actions: list[dict[str, Any]] = []
    preserve: list[dict[str, Any]] = []
    for root_name, root in roots.items():
        if not root.is_dir():
            continue
        for current, directories, files in os.walk(root):
            current_path = Path(current)
            kept_directories: list[str] = []
            for directory in sorted(directories):
                path = current_path / directory
                if directory in CACHE_DIRECTORY_NAMES:
                    actions.append(
                        _entry(
                            "delete",
                            "safe_immediate_deletion",
                            path,
                            root_name,
                            root,
                            "Provably disposable Python/test cache directory",
                        )
                    )
                else:
                    kept_directories.append(directory)
            directories[:] = kept_directories
            for filename in sorted(files):
                path = current_path / filename
                if filename in SAFE_FILE_NAMES:
                    actions.append(
                        _entry("delete", "safe_immediate_deletion", path, root_name, root, "Operating-system metadata file")
                    )
                elif path.stat().st_size == 0 and (
                    path.suffix.lower() in {".tmp", ".temp"} or filename.startswith("~$")
                ):
                    actions.append(
                        _entry("delete", "safe_immediate_deletion", path, root_name, root, "Zero-byte temporary file")
                    )
                else:
                    preserve.append(
                        _entry("preserve", "preserve", path, root_name, root, "No proven safe cleanup action")
                    )

    if roots["exports"].is_dir():
        for manifest_path in sorted(roots["exports"].glob("active/*/*/manifest.json")):
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            owner = str(payload.get("prospect_id") or "")
            folder = manifest_path.parent
            if owner not in live_ids and owner not in archive_ids:
                actions = [item for item in actions if not Path(item["path"]).is_relative_to(folder)]
                preserve = [item for item in preserve if not Path(item["path"]).is_relative_to(folder)]
                actions.append(
                    _entry(
                        "quarantine",
                        "quarantine_first",
                        folder,
                        "exports",
                        roots["exports"],
                        "Role package has no live or archive owner",
                        role_id=owner,
                    )
                )
        for directory_name in (
            "messages", "followups", "strategy_packs", "markdown", "docx", "pdf"
        ):
            directory = roots["exports"] / directory_name
            if not directory.is_dir():
                continue
            for path in sorted(candidate for candidate in directory.rglob("*") if candidate.is_file()):
                if path.resolve() in referenced_paths:
                    continue
                if any(Path(item["path"]) == path for item in actions):
                    continue
                preserve = [item for item in preserve if Path(item["path"]) != path]
                actions.append(
                    _entry(
                        "quarantine",
                        "quarantine_first",
                        path,
                        "exports",
                        roots["exports"],
                        "Legacy generated output is not referenced by a live role or archive manifest",
                    )
                )
    deduplicated: dict[Path, dict[str, Any]] = {}
    for item in actions:
        resolved = Path(item["path"]).resolve()
        existing = deduplicated.get(resolved)
        if existing is None or item["action"] == "quarantine":
            deduplicated[resolved] = item
    actions = list(deduplicated.values())
    action_paths = {Path(item["path"]).resolve() for item in actions}
    preserve = [
        item for item in preserve if Path(item["path"]).resolve() not in action_paths
    ]
    actions.sort(key=lambda item: (item["action"], item["root_name"], item["relative_path"]))
    preserve.sort(key=lambda item: (item["root_name"], item["relative_path"]))
    return {
        "schema_version": 1,
        "dry_run": True,
        "roots": {key: str(value) for key, value in roots.items()},
        "actions": actions,
        "preserve": preserve,
        "action_count": len(actions),
    }


def apply_storage_cleanup(
    plan: Mapping[str, Any],
    *,
    quarantine_root: Path,
    confirmation: str,
    app_stopped: bool,
    timestamp: str | None = None,
) -> dict[str, Any]:
    """Apply an accepted plan; uncertain files are moved, never deleted."""
    if confirmation != APPLY_CONFIRMATION:
        raise ValueError(f"Apply requires exact confirmation: {APPLY_CONFIRMATION}")
    if not app_stopped:
        raise ValueError("Cleanup apply requires confirmation that Career Catalyst is stopped.")
    stamp = timestamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination_root = Path(quarantine_root).resolve() / stamp
    completed: list[dict[str, Any]] = []
    roots = {
        name: Path(value).resolve()
        for name, value in dict(plan.get("roots") or {}).items()
    }
    for item in plan.get("actions") or []:
        source = Path(str(item["path"])).resolve()
        root = roots.get(str(item.get("root_name") or ""))
        if root is None or (source != root and root not in source.parents):
            raise ValueError(f"Cleanup action escaped its audited root: {source}")
        if not source.exists():
            raise ValueError(f"Cleanup source drifted after dry-run: {source}")
        if source.is_file() and item.get("sha256") != _sha256(source):
            raise ValueError(f"Cleanup source checksum drifted after dry-run: {source}")
        if source.is_dir() and item.get("tree_sha256") != _tree_fingerprint(source)[0]:
            raise ValueError(f"Cleanup directory drifted after dry-run: {source}")
    for item in plan.get("actions") or []:
        source = Path(str(item["path"])).resolve()
        if item["action"] == "delete":
            if source.is_dir():
                shutil.rmtree(source)
            else:
                source.unlink()
            completed.append(dict(item))
        elif item["action"] == "quarantine":
            destination = destination_root / item["root_name"] / item["relative_path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise ValueError(f"Quarantine destination already exists: {destination}")
            shutil.move(str(source), str(destination))
            result = dict(item)
            result["quarantine_path"] = str(destination)
            if destination.is_file() and result.get("sha256") != _sha256(destination):
                raise ValueError(f"Quarantine checksum verification failed: {destination}")
            if destination.is_dir() and result.get("tree_sha256") != _tree_fingerprint(destination)[0]:
                raise ValueError(f"Quarantine directory verification failed: {destination}")
            completed.append(result)
    destination_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "applied_at": stamp,
        "actions": completed,
    }
    manifest_path = destination_root / "cleanup_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    markdown = ["# Sprint 32 Cleanup Manifest", ""] + [
        f"- {item['action']}: `{item['path']}` — {item['reason']}" for item in completed
    ]
    (destination_root / "cleanup_manifest.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    return {
        "applied_count": len(completed),
        "quarantine_root": str(destination_root),
        "manifest_path": str(manifest_path),
    }
