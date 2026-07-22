"""Organize exact role materials into a safe active/archive library."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable

try:
    from .filename_utils import build_upload_filename
    from .storage_paths import (
        canonical_export_root,
        legacy_material_paths,
        require_beneath_export_root,
    )
except ImportError:  # pragma: no cover - direct script imports
    from filename_utils import build_upload_filename
    from storage_paths import canonical_export_root, legacy_material_paths, require_beneath_export_root


ACTIVE_ROUTES = {
    "applied": "active/applied_followup",
    "follow-up": "active/applied_followup",
    "follow up": "active/applied_followup",
    "interviewing": "active/applied_followup",
    "under consideration": "active/applied_followup",
    "offer": "active/applied_followup",
    "ready to apply": "active/ready_to_apply",
    "active": "active/ready_to_apply",
    "drafted": "active/in_progress",
    "reviewed": "active/in_progress",
    "paused": "active/in_progress",
}
ARCHIVE_ROUTES = {
    "passed": "archive/passed",
    "pass": "archive/passed",
    "rejected": "archive/rejected",
    "inactive": "archive/inactive",
    "hidden / invalid": "archive/hidden_invalid",
    "invalid/hidden": "archive/hidden_invalid",
    "invalid": "archive/hidden_invalid",
    "no longer pursuing": "archive/no_longer_pursuing",
    "closed": "archive/inactive",
    "withdrawn": "archive/no_longer_pursuing",
    "withdrawn / closed": "archive/no_longer_pursuing",
}

OUTPUT_FILENAMES = {
    "styled_docx": "styled_resume.docx",
    "ats_docx": "ats_resume.docx",
    "resume_text": "resume.txt",
    "cover_letter_docx": "cover_letter.docx",
    "cover_letter_text": "cover_letter.txt",
    "cover_letter": "cover_letter.txt",
    "application_note_text": "application_note.txt",
    "application_note": "application_note.txt",
    "recruiter_message_text": "recruiter_message.txt",
    "recruiter_message": "recruiter_message.txt",
    "hiring_manager_message_text": "hiring_manager_message.txt",
    "hiring_manager_message": "hiring_manager_message.txt",
    "followup_strategy_text": "followup_strategy.txt",
    "followup_strategy": "followup_strategy.txt",
    "recruiter_followup_text": "recruiter_followup.txt",
    "recruiter_followup": "recruiter_followup.txt",
    "hiring_manager_followup_text": "hiring_manager_followup.txt",
    "hiring_manager_followup": "hiring_manager_followup.txt",
    "referral_ask_text": "referral_ask.txt",
    "referral_ask": "referral_ask.txt",
    "warm_contact_message_text": "warm_contact_message.txt",
    "warm_contact_message": "warm_contact_message.txt",
    "strategy_pack_text": "strategy_pack.txt",
    "strategy_pack": "strategy_pack.txt",
    "interview_prep_text": "interview_prep.txt",
    "interview_prep": "interview_prep.txt",
    "package_summary_text": "package_summary.txt",
    "package_summary": "package_summary.txt",
}
MATERIAL_FILENAMES = {
    "ATS Resume": "ats_resume.docx",
    "Styled Resume": "styled_resume.docx",
    "Tailored Resume": "resume.txt",
    "Cover Letter": "cover_letter.docx",
    "Application Note": "application_note.txt",
    "Recruiter Message": "recruiter_message.txt",
    "Hiring Manager Message": "hiring_manager_message.txt",
    "Follow-Up Strategy": "followup_strategy.txt",
    "Recruiter Follow-Up": "recruiter_followup.txt",
    "Hiring Manager Follow-Up": "hiring_manager_followup.txt",
    "Referral Ask": "referral_ask.txt",
    "Warm Contact Message": "warm_contact_message.txt",
    "Strategy Pack": "strategy_pack.txt",
    "Interview Prep": "interview_prep.txt",
    "Package Summary": "package_summary.txt",
}

LEGACY_MARKDOWN_DIRS = (
    "exports/messages",
    "exports/followups",
    "exports/strategy_packs",
    "exports/markdown",
)


def _candidate_name(application: Dict[str, Any]) -> str:
    return str(
        application.get("candidate_name")
        or application.get("candidate")
        or "Trisha Lynch"
    )


def _role_title(application: Dict[str, Any]) -> str:
    return str(application.get("role") or application.get("job_title") or "Role")


def _company(application: Dict[str, Any]) -> str:
    return str(application.get("company") or "Company")


def standardized_material_filename(
    application: Dict[str, Any], material_type: str, extension: str
) -> str:
    """Return the active-package filename for a material.

    Standard: [company]_[role]_[candidate]_[material_type].[file_type]
    """
    return build_upload_filename(
        _candidate_name(application),
        _role_title(application),
        _company(application),
        material_type,
        extension,
    )


def _output_filename(application: Dict[str, Any], key: str, source: Path) -> str | None:
    generic = OUTPUT_FILENAMES.get(key)
    if not generic:
        return None
    material_type = Path(generic).stem
    return standardized_material_filename(
        application, material_type, source.suffix.lower().lstrip(".")
    )


def _material_filename(
    application: Dict[str, Any], label: str, source: Path
) -> str | None:
    generic = MATERIAL_FILENAMES.get(str(label))
    if not generic:
        return None
    material_type = Path(generic).stem
    return standardized_material_filename(
        application, material_type, source.suffix.lower().lstrip(".")
    )


def _key(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def material_route(status: Any) -> Dict[str, Any]:
    """Return a safe library route without guessing ambiguous statuses."""
    normalized = _key(status)
    if normalized in ACTIVE_ROUTES:
        return {
            "route": ACTIVE_ROUTES[normalized],
            "archived": False,
            "needs_review": False,
        }
    if normalized in ARCHIVE_ROUTES:
        return {
            "route": ARCHIVE_ROUTES[normalized],
            "archived": True,
            "needs_review": False,
        }
    return {"route": None, "archived": False, "needs_review": True}


def role_slug(application: Dict[str, Any]) -> str:
    """Return the stable tracker identity used as the package folder name."""
    value = (
        application.get("prospect_id")
        or application.get("id")
        or application.get("stable_slug")
    )
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _unique_destination(path: Path) -> Path:
    if not path.exists():
        return path
    index = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
        index += 1


def _move_file(source: Path, destination: Path) -> Path:
    source = source.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source == destination.resolve():
        return source
    target = _unique_destination(destination)
    shutil.move(str(source), str(target))
    return target.resolve()


def _plain_text(markdown: str) -> str:
    text = re.sub(r"^#{1,6}\s+", "", markdown, flags=re.MULTILINE)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.replace("**", "").rstrip() + "\n"


def write_role_manifest(
    folder: Path,
    application: Dict[str, Any],
    files: Dict[str, str],
    *,
    archived: bool,
    archive_reason: str = "",
    legacy_files_moved: Iterable[str] = (),
    preserve_existing: bool = False,
) -> Dict[str, Any]:
    """Write one exact role manifest and return its payload."""
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {
        "prospect_id": str(
            application.get("id") or application.get("prospect_id") or ""
        ),
        "slug": role_slug(application),
        "company": str(application.get("company") or ""),
        "role_title": str(
            application.get("role") or application.get("job_title") or ""
        ),
        "status": str(application.get("status") or ""),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "applied_date": str(
            application.get("submitted_date") or application.get("applied_date") or ""
        ),
        "status_date": str(application.get("status_date") or ""),
        "source_url": str(
            application.get("canonical_apply_url")
            or application.get("official_url")
            or application.get("source_url")
            or ""
        ),
        "files": dict(files),
        "archived": bool(archived),
        "archive_reason": archive_reason,
        "legacy_files_moved": list(legacy_files_moved),
    }
    manifest_path = folder / "manifest.json"
    if preserve_existing:
        manifest_path = _unique_destination(manifest_path)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path.resolve())
    return manifest


def organize_package_outputs(
    project_root: Path,
    application: Dict[str, Any],
    outputs: Dict[str, Any],
    *,
    preserve_existing: bool = False,
    export_root: Path | None = None,
) -> Dict[str, Any]:
    """Move exact package outputs to one role folder and archive transient Markdown."""
    root = Path(project_root).resolve()
    library_root = canonical_export_root(root, injected_root=export_root)
    routing = material_route(application.get("status"))
    if routing["needs_review"]:
        return {
            "outputs": dict(outputs),
            "manifest": None,
            "warnings": ["Ambiguous status; materials left in place."],
        }
    slug = role_slug(application)
    package_folder = require_beneath_export_root(
        library_root / str(routing["route"]) / slug, library_root
    )
    markdown_folder = require_beneath_export_root(
        library_root / "archive" / "old_generated_materials" / slug, library_root
    )
    updated = dict(outputs)
    files: Dict[str, str] = {}
    moved_sources: Dict[Path, Path] = {}
    legacy_moved = []
    for key, value in list(outputs.items()):
        source = Path(str(value))
        if not source.is_file() or key in {"job_file", "dashboard"}:
            continue
        source_resolved = source.resolve()
        if source_resolved in moved_sources:
            updated[key] = str(moved_sources[source_resolved])
            if key in OUTPUT_FILENAMES:
                files[key] = str(moved_sources[source_resolved])
            continue
        if source.suffix.lower() == ".md":
            target = _move_file(source, markdown_folder / source.name)
            moved_sources[source_resolved] = target
            updated[key] = str(target)
            legacy_moved.append(str(target))
            continue
        filename = _output_filename(application, key, source)
        if not filename:
            continue
        target = _move_file(source, package_folder / filename)
        moved_sources[source_resolved] = target
        updated[key] = str(target)
        files[key] = str(target)
    manifest = write_role_manifest(
        package_folder,
        application,
        files,
        archived=bool(routing["archived"]),
        archive_reason=(
            f"Status: {application.get('status')}" if routing["archived"] else ""
        ),
        legacy_files_moved=legacy_moved,
        preserve_existing=preserve_existing,
    )
    return {
        "outputs": updated,
        "manifest": manifest,
        "warnings": [],
        "canonical_export_root": str(library_root),
    }


def organize_exact_material_paths(
    project_root: Path, application: Dict[str, Any], *, export_root: Path | None = None
) -> Dict[str, Any]:
    """Move an existing tracker-owned material map into one exact role folder."""
    root = Path(project_root).resolve()
    library_root = canonical_export_root(root, injected_root=export_root)
    routing = material_route(application.get("status"))
    if routing["needs_review"]:
        return {
            "moved_count": 0,
            "manifest": None,
            "warnings": ["Ambiguous status; materials left in place."],
        }
    folder = require_beneath_export_root(
        library_root / str(routing["route"]) / role_slug(application), library_root
    )
    markdown_folder = (
        library_root / "archive/old_generated_materials" / role_slug(application)
    )
    materials: Dict[str, str] = {}
    legacy_moved = []
    moved_count = 0
    for label, value in dict(application.get("material_paths") or {}).items():
        if label == "Job Description":
            continue
        source = Path(str(value))
        if not source.is_file():
            continue
        if source.suffix.lower() == ".md":
            txt_source = source.with_suffix(".txt")
            if not txt_source.exists():
                txt_source.write_text(
                    _plain_text(source.read_text(encoding="utf-8")), encoding="utf-8"
                )
            legacy_moved.append(str(_move_file(source, markdown_folder / source.name)))
            source = txt_source
        filename = _material_filename(application, str(label), source)
        if not filename:
            continue
        target = _move_file(source, folder / filename)
        materials[str(label)] = str(target)
        moved_count += 1
    manifest = write_role_manifest(
        folder,
        application,
        materials,
        archived=bool(routing["archived"]),
        archive_reason=(
            f"Status: {application.get('status')}" if routing["archived"] else ""
        ),
        legacy_files_moved=legacy_moved,
    )
    manifest["materials"] = materials
    manifest_path = Path(manifest["manifest_path"])
    manifest_path.write_text(
        json.dumps(
            {key: value for key, value in manifest.items() if key != "manifest_path"},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"moved_count": moved_count, "manifest": manifest, "warnings": []}


def find_exact_role_package(
    project_root: Path, application: Dict[str, Any], *, export_root: Path | None = None
) -> Dict[str, Any]:
    """Find one package by stable role slug, preferring its manifest over legacy paths."""
    root = Path(project_root).resolve()
    library_root = canonical_export_root(root, injected_root=export_root)
    slug = role_slug(application)
    manifests = sorted(library_root.glob(f"active/*/{slug}/manifest.json"))
    manifests += sorted(library_root.glob(f"archive/*/{slug}/manifest.json"))
    if manifests:
        manifest_path = manifests[0]
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        if str(payload.get("prospect_id") or "") == str(application.get("id") or ""):
            files = {
                key: Path(value)
                for key, value in dict(payload.get("files") or {}).items()
                if Path(value).is_file()
            }
            return {
                "files": files,
                "folder": manifest_path.parent,
                "manifest": payload,
                "archived": bool(payload.get("archived")),
            }
    legacy = {
        str(label): Path(str(value))
        for label, value in dict(application.get("material_paths") or {}).items()
        if Path(str(value)).is_file()
    }
    return {
        "files": legacy,
        "folder": None,
        "manifest": None,
        "archived": False,
        "legacy_paths": legacy_material_paths(application, library_root),
        "canonical_export_root": str(library_root),
    }


def move_role_package(
    project_root: Path,
    application: Dict[str, Any],
    *,
    archive: bool,
    export_root: Path | None = None,
) -> Dict[str, Any]:
    """Archive or restore an exact package folder without changing role status."""
    found = find_exact_role_package(project_root, application, export_root=export_root)
    folder = found.get("folder")
    if not folder:
        return {"moved": False, "reason": "No exact package materials yet"}
    status_route = material_route(application.get("status"))
    route = (
        ARCHIVE_ROUTES.get(_key(application.get("status")), "archive/inactive")
        if archive
        else ACTIVE_ROUTES.get(_key(application.get("status")), "active/in_progress")
    )
    library_root = canonical_export_root(project_root, injected_root=export_root)
    destination = require_beneath_export_root(
        library_root / route / role_slug(application), library_root
    )
    target = _move_file(Path(folder), destination) if Path(folder).is_file() else None
    if target is None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        target = _unique_destination(destination)
        shutil.move(str(folder), str(target))
        target = target.resolve()
    manifest_path = target / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["archived"] = archive
    payload["archive_reason"] = (
        f"Status: {application.get('status')}" if archive else ""
    )
    payload["files"] = {
        key: str((target / Path(value).name).resolve())
        for key, value in dict(payload.get("files") or {}).items()
        if (target / Path(value).name).is_file()
    }
    payload["materials"] = {
        key: str((target / Path(value).name).resolve())
        for key, value in dict(payload.get("materials") or {}).items()
        if (target / Path(value).name).is_file()
    }
    manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    payload["manifest_path"] = str(manifest_path.resolve())
    return {"moved": True, "folder": target, "manifest": payload, "route": status_route}


def archive_legacy_markdown(
    project_root: Path, *, apply: bool = False
) -> Dict[str, Any]:
    """Archive generated Markdown, creating TXT companions when needed."""
    root = Path(project_root).resolve()
    planned = []
    moved = []
    companions = []
    for relative in LEGACY_MARKDOWN_DIRS:
        directory = root / relative
        if not directory.is_dir():
            continue
        for source in sorted(directory.glob("*.md")):
            destination = (
                root
                / "exports/archive/old_generated_materials"
                / Path(relative).name
                / source.name
            )
            txt_path = source.with_suffix(".txt")
            planned.append({"source": str(source), "destination": str(destination)})
            if not apply:
                continue
            if not txt_path.exists():
                archived_txt = _unique_destination(destination.with_suffix(".txt"))
                archived_txt.parent.mkdir(parents=True, exist_ok=True)
                archived_txt.write_text(
                    _plain_text(source.read_text(encoding="utf-8")), encoding="utf-8"
                )
                companions.append(str(archived_txt))
            moved.append(str(_move_file(source, destination)))
    return {
        "planned_count": len(planned),
        "moved_count": len(moved),
        "txt_companions_created": len(companions),
        "planned": planned,
        "moved": moved,
        "companions": companions,
    }


def archive_matching_legacy_text(
    project_root: Path, *, apply: bool = False
) -> Dict[str, Any]:
    """Move legacy TXT files whose matching Markdown is already archived."""
    root = Path(project_root).resolve()
    planned = []
    moved = []
    archive_root = root / "exports/archive/old_generated_materials"
    for relative in LEGACY_MARKDOWN_DIRS:
        legacy_dir = root / relative
        archived_dir = archive_root / Path(relative).name
        if not legacy_dir.is_dir() or not archived_dir.is_dir():
            continue
        archived_stems = {path.stem for path in archived_dir.glob("*.md")}
        for source in sorted(legacy_dir.glob("*.txt")):
            if source.stem not in archived_stems:
                continue
            destination = archived_dir / source.name
            planned.append({"source": str(source), "destination": str(destination)})
            if apply:
                moved.append(str(_move_file(source, destination)))
    return {"planned_count": len(planned), "moved_count": len(moved), "moved": moved}
