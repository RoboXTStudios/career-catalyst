"""Transactional Finder-accessible role archives and minimal archive ledger."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Dict, Iterable, Optional, Union
from uuid import uuid4

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
    from .materials_library import find_exact_role_package
    from .role_state_resolver import resolve_job_file
    from .storage_paths import (
        canonical_archive_root,
        canonical_export_root,
        require_beneath,
        require_beneath_export_root,
    )
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
    from materials_library import find_exact_role_package
    from role_state_resolver import resolve_job_file
    from storage_paths import (
        canonical_archive_root,
        canonical_export_root,
        require_beneath,
        require_beneath_export_root,
    )


PathInput = Union[str, Path]
ARCHIVE_REASONS = ("Rejected", "Withdrawn / Closed", "Hidden / Invalid")
ARCHIVE_SCHEMA_VERSION = 2


def infer_archive_reason(record: Dict[str, Any]) -> str:
    """Return a current archive reason without promoting legacy Passed."""
    if get_record_status(record) == "Rejected":
        return "Rejected"
    raw = normalize_tracker_value(legacy_status_value(record))
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


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-") or "unknown"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    )
    temporary = Path(handle.name)
    try:
        with handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _material_sources(
    root: Path,
    entry: Dict[str, Any],
    export_root: Path,
) -> tuple[list[tuple[str, Path]], Optional[Path]]:
    package = find_exact_role_package(root, entry, export_root=export_root)
    candidates: list[tuple[str, Any]] = []
    candidates.extend(dict(entry.get("material_paths") or {}).items())
    manifest = entry.get("package_manifest")
    if isinstance(manifest, dict):
        candidates.extend(dict(manifest.get("files") or {}).items())
        candidates.extend(dict(manifest.get("materials") or {}).items())
    candidates.extend(dict(package.get("files") or {}).items())
    sources: list[tuple[str, Path]] = []
    seen: set[Path] = set()
    for label, value in candidates:
        if not value:
            continue
        path = Path(str(value)).expanduser()
        if not path.is_absolute():
            path = root / path
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if not resolved.is_file() or resolved in seen:
            continue
        seen.add(resolved)
        sources.append((str(label), resolved))
    folder = Path(package["folder"]).resolve() if package.get("folder") else None
    return sorted(sources, key=lambda item: (item[0].lower(), str(item[1]))), folder


def _copy_materials(
    sources: list[tuple[str, Path]], destination: Path
) -> list[dict[str, Any]]:
    destination.mkdir(parents=True, exist_ok=True)
    copied: list[dict[str, Any]] = []
    used: set[str] = set()
    for label, source in sources:
        stem = _slug(label).replace("-", "_")
        suffix = source.suffix.lower()
        filename = f"{stem}{suffix}" if stem else source.name
        if filename in used:
            filename = f"{Path(filename).stem}_{_sha256(source)[:8]}{suffix}"
        used.add(filename)
        target = destination / filename
        shutil.copy2(source, target)
        digest = _sha256(target)
        if digest != _sha256(source):
            raise TrackerUpdateError(f"Archive copy verification failed for {source}.")
        copied.append(
            {
                "label": label,
                "filename": f"materials/{filename}",
                "source_path": str(source),
                "sha256": digest,
                "size": target.stat().st_size,
            }
        )
    return copied


def _notes_and_history(entry: Dict[str, Any]) -> str:
    lines = [f"Notes\n-----\n{entry.get('notes') or 'None'}", "", "Status history\n--------------"]
    history = entry.get("application_history") or []
    if not history:
        lines.append("None")
    else:
        for event in history:
            lines.append(json.dumps(event, sort_keys=True, ensure_ascii=False))
    return "\n".join(lines).rstrip() + "\n"


def _summary_html(manifest: Dict[str, Any]) -> str:
    material_links = "".join(
        f'<li><a href="{html.escape(item["filename"], quote=True)}">'
        f'{html.escape(item["label"])}</a></li>'
        for item in manifest.get("materials", [])
    ) or "<li>No generated materials existed at archive time.</li>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>{html.escape(manifest['company'])} — {html.escape(manifest['role_title'])}</title>
<style>body{{font:16px system-ui;max-width:850px;margin:40px auto;padding:0 20px;line-height:1.5}}dt{{font-weight:700}}dd{{margin-bottom:8px}}</style></head>
<body><h1>{html.escape(manifest['company'])}</h1><h2>{html.escape(manifest['role_title'])}</h2>
<dl><dt>Final status</dt><dd>{html.escape(manifest['final_status'])}</dd>
<dt>Archived</dt><dd>{html.escape(manifest['archived_at'])}</dd>
<dt>Match snapshot</dt><dd>{html.escape(str(manifest.get('match_score_snapshot') or 'Not scored'))} · {html.escape(str(manifest.get('match_tier_snapshot') or 'Not scored'))}</dd></dl>
<p><a href="job_posting.txt">Job posting</a> · <a href="notes_and_status_history.txt">Notes and status history</a> · <a href="role_manifest.json">Manifest</a></p>
<h3>Materials</h3><ul>{material_links}</ul></body></html>"""


def _index_payload(archive_root: Path) -> list[dict[str, Any]]:
    path = archive_root / "archive_index.json"
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return list(payload.get("archives") or []) if isinstance(payload, dict) else []


def _write_index(archive_root: Path, entries: list[dict[str, Any]]) -> None:
    _atomic_json(
        archive_root / "archive_index.json",
        {"schema_version": ARCHIVE_SCHEMA_VERSION, "archives": entries},
    )


def archive_role(
    tracker_id: str,
    archive_reason: str = "",
    project_root: Optional[PathInput] = None,
    *,
    export_root: Optional[PathInput] = None,
    archive_root: Optional[PathInput] = None,
    archived_at: Optional[str] = None,
    allow_legacy_archived: bool = False,
) -> Dict[str, Any]:
    """Create and verify a local bundle before removing one exact live role."""
    root = Path(project_root or Path.cwd()).resolve()
    exports = canonical_export_root(root, injected_root=export_root)
    archives = Path(archive_root).resolve() if archive_root else canonical_archive_root(root)
    applications = load_application_tracker(root)
    entry = _record(applications, tracker_id)
    legacy_archived = entry.get("archived") is True
    if not is_archive_eligible(entry) and not (allow_legacy_archived and legacy_archived):
        raise TrackerUpdateError(
            f"Role '{tracker_id}' with status {get_record_status(entry)} is not archive-eligible."
        )
    reason = str(archive_reason or infer_archive_reason(entry)).strip()
    if reason not in ARCHIVE_REASONS:
        raise TrackerUpdateError(f"Unsupported archive reason '{reason}'.")
    timestamp = archived_at or datetime.now(timezone.utc).isoformat()
    final_status = get_record_status(entry)
    date_part = timestamp[:10]
    directory_name = f"{date_part}_{_slug(entry.get('role'))}_{_slug(tracker_id)}"
    final_directory = require_beneath(
        archives / _slug(entry.get("company")) / directory_name,
        archives,
        label="Archive",
    )
    if final_directory.exists():
        raise TrackerUpdateError(f"Archive destination already exists: {final_directory}")
    archives.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".sprint32-archive-", dir=archives))
    staged_package: Optional[Path] = None
    staged_files: list[tuple[Path, Path]] = []
    package_folder: Optional[Path] = None
    tracker_saved = False
    old_index = _index_payload(archives)
    try:
        bundle = temporary / "bundle"
        bundle.mkdir()
        sources, package_folder = _material_sources(root, entry, exports)
        materials = _copy_materials(sources, bundle / "materials")
        job_result = resolve_job_file(entry, root)
        job_source = Path(str(job_result["path"])) if job_result.get("status") == "valid" else None
        if job_source and job_source.is_file():
            shutil.copy2(job_source, bundle / "job_posting.txt")
        else:
            (bundle / "job_posting.txt").write_text(
                str(entry.get("job_description") or ""), encoding="utf-8"
            )
        (bundle / "notes_and_status_history.txt").write_text(
            _notes_and_history(entry), encoding="utf-8"
        )
        legacy_reason = str(entry.get("archive_reason") or "")
        manifest = {
            "schema_version": ARCHIVE_SCHEMA_VERSION,
            "original_role_id": str(entry.get("id") or tracker_id),
            "company": str(entry.get("company") or ""),
            "role_title": str(entry.get("role") or ""),
            "location": str(entry.get("location") or ""),
            "source_url": str(entry.get("source_url") or entry.get("official_url") or ""),
            "application_url": str(entry.get("application_url") or entry.get("canonical_apply_url") or ""),
            "final_status": final_status,
            "legacy_status": legacy_status_value(entry),
            "legacy_archive_reason": legacy_reason if legacy_reason and legacy_reason != reason else "",
            "archive_reason": reason,
            "archived_at": timestamp,
            "match_score_snapshot": entry.get("match_score"),
            "match_tier_snapshot": entry.get("match_tier"),
            "source_metadata": {
                key: entry.get(key)
                for key in (
                    "source", "source_type", "source_name", "verification_status",
                    "source_trust_label", "job_id", "requisition_id",
                )
                if entry.get(key) not in (None, "")
            },
            "materials": materials,
            "job_posting_sha256": _sha256(bundle / "job_posting.txt"),
            "archive_folder": str(final_directory),
            "original_record": deepcopy(entry),
        }
        _atomic_json(bundle / "role_manifest.json", manifest)
        (bundle / "role_summary.html").write_text(_summary_html(manifest), encoding="utf-8")
        for item in materials:
            copied = bundle / item["filename"]
            if not copied.is_file() or _sha256(copied) != item["sha256"]:
                raise TrackerUpdateError(f"Archive verification failed for {copied}.")
        final_directory.parent.mkdir(parents=True, exist_ok=True)
        os.replace(bundle, final_directory)

        minimal = {
            "original_role_id": str(entry.get("id") or tracker_id),
            "company": str(entry.get("company") or ""),
            "role_title": str(entry.get("role") or ""),
            "final_status": final_status,
            "archived_at": timestamp,
            "archive_folder": str(final_directory),
            "manifest_path": str(final_directory / "role_manifest.json"),
        }
        _write_index(
            archives,
            sorted(old_index + [minimal], key=lambda item: (item["archived_at"], item["original_role_id"])),
        )

        staging_root = exports / ".sprint32_archive_staging"
        if package_folder and package_folder.exists():
            require_beneath_export_root(package_folder, exports)
            staging_root.mkdir(parents=True, exist_ok=True)
            staged_package = staging_root / f"{_slug(tracker_id)}-{uuid4().hex}"
            os.replace(package_folder, staged_package)

        other_references: set[Path] = set()
        for other in applications:
            if str(other.get("id")) == str(tracker_id):
                continue
            values = list(dict(other.get("material_paths") or {}).values())
            other_manifest = other.get("package_manifest")
            if isinstance(other_manifest, dict):
                values.extend(dict(other_manifest.get("files") or {}).values())
                values.extend(dict(other_manifest.get("materials") or {}).values())
            for value in values:
                if value:
                    other_references.add(Path(str(value)).expanduser().resolve())
        for _label, source in sources:
            if package_folder and (source == package_folder or package_folder in source.parents):
                continue
            if source in other_references:
                continue
            try:
                require_beneath_export_root(source, exports)
            except ValueError:
                continue
            if not source.exists():
                continue
            staging_root.mkdir(parents=True, exist_ok=True)
            staged = staging_root / f"legacy-{uuid4().hex}-{source.name}"
            os.replace(source, staged)
            staged_files.append((staged, source))

        remaining = [
            application
            for application in applications
            if str(application.get("id")) != str(tracker_id)
        ]
        save_application_tracker(remaining, root)
        tracker_saved = True
        if staged_package and staged_package.exists():
            shutil.rmtree(staged_package)
        for staged, _source in staged_files:
            staged.unlink(missing_ok=True)
        if staging_root.exists() and not any(staging_root.iterdir()):
            staging_root.rmdir()
        return {"archive": minimal, "manifest": manifest, "folder": str(final_directory)}
    except Exception as error:
        rollback_errors: list[str] = []
        if staged_package and staged_package.exists() and package_folder:
            try:
                package_folder.parent.mkdir(parents=True, exist_ok=True)
                os.replace(staged_package, package_folder)
            except OSError as rollback_error:
                rollback_errors.append(f"package restore failed: {rollback_error}")
        for staged, source in reversed(staged_files):
            if staged.exists():
                try:
                    source.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(staged, source)
                except OSError as rollback_error:
                    rollback_errors.append(f"material restore failed: {rollback_error}")
        if tracker_saved:
            try:
                save_application_tracker(applications, root)
            except Exception as rollback_error:
                rollback_errors.append(f"tracker restore failed: {rollback_error}")
        if final_directory.exists():
            try:
                shutil.rmtree(final_directory)
            except OSError as rollback_error:
                rollback_errors.append(f"archive bundle rollback failed: {rollback_error}")
        try:
            _write_index(archives, old_index)
        except Exception as rollback_error:
            rollback_errors.append(f"archive index rollback failed: {rollback_error}")
        if rollback_errors:
            raise TrackerUpdateError(
                f"Archive failed ({error}); rollback was incomplete: {'; '.join(rollback_errors)}"
            ) from error
        raise
    finally:
        shutil.rmtree(temporary, ignore_errors=True)


def list_archive_entries(
    archive_root: PathInput,
    *,
    query: str = "",
    final_status: str = "All",
) -> list[dict[str, Any]]:
    """Read the minimal archive ledger from verified local manifests."""
    root = Path(archive_root).expanduser().resolve()
    needle = query.strip().lower()
    entries: list[dict[str, Any]] = []
    if not root.is_dir():
        return entries
    for manifest_path in sorted(root.glob("*/*/role_manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            folder = require_beneath(manifest_path.parent, root, label="Archive")
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        entry = {
            "original_role_id": str(manifest.get("original_role_id") or ""),
            "company": str(manifest.get("company") or ""),
            "role_title": str(manifest.get("role_title") or ""),
            "final_status": str(manifest.get("final_status") or ""),
            "archived_at": str(manifest.get("archived_at") or ""),
            "archive_folder": str(folder),
            "manifest_path": str(manifest_path),
        }
        if needle and needle not in f"{entry['company']} {entry['role_title']}".lower():
            continue
        if final_status != "All" and entry["final_status"] != final_status:
            continue
        entries.append(entry)
    return entries


def open_archive_folder(
    path: PathInput,
    archive_root: PathInput,
    *,
    opener: Any = subprocess.run,
) -> tuple[bool, str]:
    """Open one existing archive folder without shell evaluation."""
    try:
        folder = require_beneath(path, archive_root, label="Archive")
    except ValueError as error:
        return False, str(error)
    if not folder.is_dir():
        return False, f"Archive folder is missing: {folder}"
    try:
        opener(["open", str(folder)], check=True, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as error:
        return False, f"Unable to open archive folder: {error}"
    return True, f"Opened {folder}"


def reopen_as_new_prospect(
    manifest_path: PathInput,
    project_root: PathInput,
    *,
    archive_root: Optional[PathInput] = None,
    request_id: str = "",
) -> Dict[str, Any]:
    """Create a fresh Prospect from allowed archive source fields only."""
    root = Path(project_root).resolve()
    archives = Path(archive_root).resolve() if archive_root else canonical_archive_root(root)
    path = require_beneath(manifest_path, archives, label="Archive")
    if not path.is_file():
        raise TrackerUpdateError(f"Archive manifest is missing: {path}")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    original_id = str(manifest.get("original_role_id") or "")
    applications = load_application_tracker(root)
    if request_id:
        existing = next(
            (
                item
                for item in applications
                if item.get("reopened_from_archive_id") == original_id
                and item.get("reopen_request_id") == request_id
            ),
            None,
        )
        if existing:
            return {"application": deepcopy(existing), "created": False}
    source = dict(manifest.get("original_record") or {})
    description_path = path.parent / "job_posting.txt"
    description = description_path.read_text(encoding="utf-8") if description_path.is_file() else ""
    base_id = f"{_slug(original_id).replace('-', '_')}_reopened_{datetime.now().strftime('%Y%m%d')}"
    used = {str(item.get("id") or "") for item in applications}
    tracker_id = base_id
    suffix = 2
    while tracker_id in used:
        tracker_id = f"{base_id}_{suffix}"
        suffix += 1
    try:
        from .prospect_intake import create_prospect
    except ImportError:  # pragma: no cover
        from prospect_intake import create_prospect
    created = create_prospect(
        {
            "tracker_id": tracker_id,
            "company": manifest.get("company"),
            "role": manifest.get("role_title"),
            "location": manifest.get("location"),
            "official_url": manifest.get("source_url"),
            "application_url": manifest.get("application_url"),
            "job_description": description,
            "salary_range": source.get("salary_range"),
            "compensation": source.get("compensation"),
            "source": (manifest.get("source_metadata") or {}).get("source"),
            "job_id": (manifest.get("source_metadata") or {}).get("job_id"),
            "status": "Prospect",
            "notes": f"Reopened as a new Prospect from archived role {original_id}.",
            "reopened_from_archive_id": original_id,
            "reopened_from_manifest": str(path),
            "reopen_request_id": request_id,
        },
        root,
    )
    return {"application": created["application"], "created": True}


def bulk_archive_roles(
    tracker_ids: Iterable[str],
    project_root: Optional[PathInput] = None,
    *,
    reasons: Optional[Dict[str, str]] = None,
    export_root: Optional[PathInput] = None,
    archive_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Archive only explicitly selected roles and report each transaction."""
    selected = list(dict.fromkeys(str(value) for value in tracker_ids if str(value)))
    result: Dict[str, Any] = {
        "selected_count": len(selected), "archived": [], "skipped": [], "failed": {}
    }
    root = Path(project_root or Path.cwd())
    for tracker_id in selected:
        try:
            applications = load_application_tracker(root)
            entry = _record(applications, tracker_id)
            if not is_archive_eligible(entry):
                result["skipped"].append(tracker_id)
                continue
            archive_role(
                tracker_id,
                (reasons or {}).get(tracker_id) or infer_archive_reason(entry),
                root,
                export_root=export_root,
                archive_root=archive_root,
            )
            result["archived"].append(tracker_id)
        except Exception as error:
            result["failed"][tracker_id] = str(error)
    result["archived_count"] = len(result["archived"])
    return result
