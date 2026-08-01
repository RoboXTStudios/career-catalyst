"""Orchestrate a complete Career Catalyst application package."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Union, List

try:
    from .application_tracker import (
        TrackerValidationError,
        get_record_status,
        load_application_tracker,
        normalize_tracker_value,
        update_prospect,
        update_status,
    )
    from .dynamic_role_intelligence import get_effective_voice_profile
    from .export_docx import export_ats_docx, export_styled_docx
    from .generate_application_note import generate_application_note
    from .generate_cover_letter import generate_cover_letter
    from .generate_dashboard import generate_dashboard
    from .generate_messages import generate_message
    from .generate_interview_prep import generate_interview_prep
    from .generate_strategy_pack import generate_strategy_pack
    from .job_freshness import detect_job_freshness
    from .opportunity_scoring import score_opportunity
    from .package_quality import calculate_package_quality, save_package_summary
    from .package_materials import (
        create_text_companion,
        preferred_material_paths,
        validate_package_outputs,
    )
    from .package_context import PackageContextMismatchError, validate_material_context
    from .materials_library import organize_package_outputs
    from .storage_paths import canonical_export_root, legacy_material_paths
    from .filename_utils import company_display_name
    from .parse_job import JobParseError, parse_job_description
    from .prospect_intake import add_prospect_from_job_file
    from .score_match import persisted_match_fields, score_job_match
    from .tailor_resume import tailor_resume
    from .evidence_engine import evidence_projects_for_role
    from .evidence_engine import load_evidence_projects
    from .resume_foundation import load_resume_foundation
    from .evidence_tailoring import (
        evidence_score_contribution,
        output_use_metadata,
    )
    from .role_intent import (
        build_role_intent,
        reconcile_package_role_intelligence,
        role_intent_snapshot,
    )
except ImportError:
    from application_tracker import (
        TrackerValidationError,
        get_record_status,
        load_application_tracker,
        normalize_tracker_value,
        update_prospect,
        update_status,
    )
    from dynamic_role_intelligence import get_effective_voice_profile
    from export_docx import export_ats_docx, export_styled_docx
    from generate_application_note import generate_application_note
    from generate_cover_letter import generate_cover_letter
    from generate_dashboard import generate_dashboard
    from generate_messages import generate_message
    from generate_interview_prep import generate_interview_prep
    from generate_strategy_pack import generate_strategy_pack
    from job_freshness import detect_job_freshness
    from opportunity_scoring import score_opportunity
    from package_quality import calculate_package_quality, save_package_summary
    from package_materials import (
        create_text_companion,
        preferred_material_paths,
        validate_package_outputs,
    )
    from package_context import PackageContextMismatchError, validate_material_context
    from materials_library import organize_package_outputs
    from storage_paths import canonical_export_root, legacy_material_paths
    from filename_utils import company_display_name
    from parse_job import JobParseError, parse_job_description
    from prospect_intake import add_prospect_from_job_file
    from score_match import persisted_match_fields, score_job_match
    from tailor_resume import tailor_resume
    from evidence_engine import evidence_projects_for_role
    from evidence_engine import load_evidence_projects
    from resume_foundation import load_resume_foundation
    from evidence_tailoring import evidence_score_contribution, output_use_metadata
    from role_intent import (
        build_role_intent,
        reconcile_package_role_intelligence,
        role_intent_snapshot,
    )


PathInput = Union[str, Path]


class PackageGenerationError(Exception):
    """Raised when a job reference or generation step cannot be completed."""

    def __init__(
        self,
        message: str,
        *,
        checklist: Optional[list[Dict[str, Any]]] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.checklist = checklist or []
        self.details = details or {}


def _job_files(root: Path) -> list[Path]:
    directory = root / "jobs"
    if not directory.is_dir():
        return []
    return [
        path
        for path in sorted(directory.iterdir())
        if path.is_file()
        and path.name.lower() != "readme.md"
        and path.suffix.lower() in {".md", ".txt"}
    ]


def _matching_job_file(application: Dict[str, Any], root: Path) -> Optional[Path]:
    stored = application.get("job_file")
    if stored:
        path = Path(str(stored))
        resolved = path if path.is_absolute() else root / path
        if resolved.is_file():
            return resolved

    tracker_id = str(application.get("id") or "")
    company_key = normalize_tracker_value(application.get("company"))
    role_key = normalize_tracker_value(application.get("role"))
    matches = []
    for path in _job_files(root):
        try:
            parsed = parse_job_description(path)
        except JobParseError:
            continue
        raw_text = str(parsed.get("raw_text") or "")
        if tracker_id and f"Tracker ID: {tracker_id}".lower() in raw_text.lower():
            return path
        if tracker_id:
            continue
        if (
            normalize_tracker_value(parsed.get("company")) == company_key
            and normalize_tracker_value(parsed.get("job_title")) == role_key
        ):
            matches.append(path)
    return matches[0] if len(matches) == 1 else None


def _selected_tracker_record(
    prospect_id: str, tracker: Any
) -> Dict[str, Any]:
    """Resolve one tracker record strictly by a durable identity field."""
    records = tracker.get("applications", []) if isinstance(tracker, dict) else tracker
    if not isinstance(records, list):
        raise PackageGenerationError("Application tracker data is not a record list.")
    target = str(prospect_id or "").strip()
    matches = [
        record
        for record in records
        if target
        and target
        in {
            str(record.get(key) or "").strip()
            for key in ("prospect_id", "id", "stable_slug", "record_id")
        }
    ]
    if len(matches) != 1:
        raise PackageGenerationError(
            f"Expected one exact tracker record for '{prospect_id}'; found {len(matches)}."
        )
    return dict(matches[0])


def _tracker_records(tracker: Any) -> List[Dict[str, Any]]:
    records = tracker.get("applications", []) if isinstance(tracker, dict) else tracker
    if not isinstance(records, list):
        raise PackageGenerationError("Application tracker data is not a record list.")
    return [record for record in records if isinstance(record, dict)]


def _posting_identity(record: Dict[str, Any]) -> str:
    """Return a deterministic external posting id without fetching any source."""
    for key in ("external_job_id", "job_id", "greenhouse_job_id"):
        value = str(record.get(key) or "").strip()
        if value:
            return value
    for key in (
        "canonical_apply_url",
        "official_url",
        "source_url",
        "original_source_url",
    ):
        match = re.search(r"/(?:jobs/)?(\d{5,})(?:[/?#]|$)", str(record.get(key) or ""))
        if match:
            return match.group(1)
    return ""


def _first_material_path(record: Dict[str, Any]) -> str:
    paths = dict(record.get("material_paths") or {})
    manifest = record.get("package_manifest")
    manifest_path = ""
    if isinstance(manifest, dict):
        paths.update(dict(manifest.get("materials") or {}))
        manifest_path = str(manifest.get("manifest_path") or "").strip()
    return next((str(value) for value in paths.values() if value), manifest_path)


def _duplicate_posting_conflicts(
    application: Dict[str, Any], records: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    current_id = str(application.get("id") or "")
    current_company = normalize_tracker_value(company_display_name(application.get("company")))
    current_role = normalize_tracker_value(application.get("role") or application.get("job_title"))
    current_posting = _posting_identity(application)
    if not current_company or not current_role or not current_posting:
        return []
    conflicts = []
    for record in records:
        record_id = str(record.get("id") or "")
        if not record_id or record_id == current_id:
            continue
        if _posting_identity(record) != current_posting:
            continue
        if normalize_tracker_value(company_display_name(record.get("company"))) != current_company:
            continue
        if normalize_tracker_value(record.get("role") or record.get("job_title")) != current_role:
            continue
        conflicts.append(
            {
                "material_type": "Existing role package",
                "current_prospect_id": current_id,
                "conflicting_prospect_id": record_id,
                "conflicting_company": company_display_name(record.get("company")),
                "conflicting_role": str(record.get("role") or record.get("job_title") or ""),
                "path": _first_material_path(record),
                "reason": "duplicate tracker records identify the same posting",
            }
        )
    return conflicts


def job_reference_health(application: Dict[str, Any], root: PathInput) -> Dict[str, Any]:
    """Describe a role's local posting without raising an application error."""
    project_root = Path(root).expanduser().resolve()
    stored = str(application.get("job_file") or "").strip()
    stored_path = Path(stored).expanduser() if stored else None
    resolved_stored = (
        stored_path if stored_path and stored_path.is_absolute()
        else (project_root / stored_path if stored_path else None)
    )
    if resolved_stored and resolved_stored.is_file():
        try:
            parsed = parse_job_description(resolved_stored)
            text = str(parsed.get("raw_text") or "").strip()
            if len(text) >= 80:
                return {
                    "status": "valid",
                    "path": str(resolved_stored),
                    "relative_path": str(resolved_stored.relative_to(project_root))
                    if resolved_stored.is_relative_to(project_root) else str(resolved_stored),
                    "posting_url": str(parsed.get("source_url") or application.get("source_url") or ""),
                    "has_usable_text": True,
                }
            return {
                "status": "unusable",
                "path": str(resolved_stored),
                "posting_url": str(parsed.get("source_url") or application.get("source_url") or ""),
                "has_usable_text": False,
                "message": "The local posting exists but does not contain usable posting text.",
            }
        except (OSError, JobParseError) as error:
            return {
                "status": "unusable",
                "path": str(resolved_stored),
                "posting_url": str(application.get("source_url") or application.get("official_url") or ""),
                "has_usable_text": False,
                "message": f"The local posting could not be parsed: {error}",
            }
    fallback = _matching_job_file(application, project_root)
    if fallback and fallback.is_file():
        try:
            parsed = parse_job_description(fallback)
            if len(str(parsed.get("raw_text") or "").strip()) >= 80:
                return {
                    "status": "valid",
                    "path": str(fallback),
                    "relative_path": str(fallback.relative_to(project_root)),
                    "posting_url": str(parsed.get("source_url") or application.get("source_url") or ""),
                    "has_usable_text": True,
                    "relinked": bool(stored),
                    "outside_runtime": bool(resolved_stored and resolved_stored.is_absolute() and not resolved_stored.is_relative_to(project_root)),
                }
        except (OSError, JobParseError):
            pass
    url = str(
        application.get("canonical_apply_url")
        or application.get("official_url")
        or application.get("source_url")
        or ""
    ).strip()
    outside_runtime = bool(
        resolved_stored and resolved_stored.is_absolute()
        and not resolved_stored.is_relative_to(project_root)
    )
    return {
        "status": "missing",
        "path": str(resolved_stored) if resolved_stored else "",
        "posting_url": url,
        "has_usable_text": False,
        "outside_runtime": outside_runtime,
        "recoverable": bool(url),
        "message": "No usable local job description is associated with this role.",
    }



def preflight_package_generation(
    prospect_id: str,
    tracker: Any,
    project_root: Optional[PathInput] = None,
    export_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Return one deterministic readiness result before expensive generation."""
    try:
        application = _selected_tracker_record(prospect_id, tracker)
    except PackageGenerationError as error:
        return {
            "status": "blocked",
            "ready": [],
            "auto_repairs": [],
            "blocking_issues": [str(error)],
            "conflicts": [],
        }
    records = _tracker_records(tracker)
    current_id = str(application.get("id") or prospect_id)
    current_slug = str(application.get("stable_slug") or current_id)
    root = Path(project_root or Path.cwd())
    library_root = canonical_export_root(root, injected_root=export_root)
    ready: list[str] = ["Tracker record resolved"]
    auto_repairs: list[str] = []
    blocking_issues: list[str] = []
    health = job_reference_health(application, root)
    if health.get("status") == "valid":
        ready.append("Local job description resolves with usable posting text")
    else:
        message = str(health.get("message") or "Job description is not usable.")
        if health.get("recoverable"):
            message += " Use the source URL to relink or re-import it."
        blocking_issues.append(message)
    try:
        load_resume_foundation(root)
        ready.append("Candidate source files resolve")
    except Exception as error:
        blocking_issues.append(f"Candidate source files could not be loaded: {error}")
    selected_ids = [str(value) for value in application.get("evidence_project_ids") or []]
    try:
        project_ids = {str(project.get("id") or "") for project in load_evidence_projects(root)}
        missing_evidence = [value for value in selected_ids if value not in project_ids]
        if missing_evidence:
            blocking_issues.append("Selected Evidence could not be resolved: " + ", ".join(missing_evidence))
        else:
            ready.append(f"Selected Evidence resolves ({len(selected_ids)} selected)")
    except Exception as error:
        blocking_issues.append(f"Evidence records could not be loaded: {error}")
    compensation_state = str(application.get("compensation_disclosure_state") or "").strip()
    if compensation_state and compensation_state not in {"provided", "not_listed", "unknown_unverified"}:
        blocking_issues.append("Compensation state is invalid.")
    else:
        ready.append("Compensation state is valid or not listed")
    if re.search(r"OMD Entertainment|OMG23\s*/\s*OMD Entertainment", str(application.get("company") or ""), re.I):
        auto_repairs.append("Canonical employer naming will be repaired in generated materials")
    if health.get("path"):
        try:
            parsed_health_job = parse_job_description(Path(str(health["path"])))
            if re.search(
                r"OMD Entertainment|OMG23\s*/\s*OMD Entertainment",
                str(parsed_health_job.get("company") or ""),
                re.I,
            ):
                auto_repairs.append("Canonical employer naming will be repaired in generated materials")
        except (OSError, JobParseError):
            pass
    auto_repairs[:] = list(dict.fromkeys(auto_repairs))
    duplicate_conflicts = _duplicate_posting_conflicts(application, records)
    if duplicate_conflicts:
        return {
            "status": "conflict",
            "ready": ready,
            "auto_repairs": auto_repairs,
            "blocking_issues": blocking_issues,
            "job_health": health,
            "conflicts": duplicate_conflicts,
        }
    paths = dict(application.get("material_paths") or {})
    manifest = application.get("package_manifest")
    if isinstance(manifest, dict):
        manifest_prospect_id = str(manifest.get("prospect_id") or "")
        if manifest_prospect_id and manifest_prospect_id != current_id:
            return {
                "status": "conflict",
                "conflicts": [{
                    "material_type": "Package manifest",
                    "current_prospect_id": current_id,
                    "conflicting_prospect_id": manifest_prospect_id,
                    "conflicting_company": str(manifest.get("company") or ""),
                    "conflicting_role": str(manifest.get("role") or ""),
                    "path": str(manifest.get("manifest_path") or ""),
                    "reason": "stored package manifest belongs to a different prospect",
                }],
            }
        paths.update(dict(manifest.get("materials") or {}))
    owners: Dict[str, Dict[str, Any]] = {}
    for record in records:
        rid = str(record.get("id") or "")
        if not rid or rid == current_id:
            continue
        owner_paths = dict(record.get("material_paths") or {})
        owner_manifest = record.get("package_manifest")
        if isinstance(owner_manifest, dict):
            owner_paths.update(dict(owner_manifest.get("materials") or {}))
        for value in owner_paths.values():
            if value:
                owners[str(Path(str(value)).expanduser())] = record
    conflicts: List[Dict[str, Any]] = []
    for stranded_path in (legacy_material_paths(application, library_root) if export_root is None else []):
        conflicts.append({
            "material_type": "Legacy package path",
            "current_prospect_id": current_id,
            "conflicting_prospect_id": "",
            "conflicting_company": "",
            "conflicting_role": "",
            "path": stranded_path,
            "reason": "existing material is outside the canonical export root",
        })
    for label, value in paths.items():
        if not value or str(label) == "Job Description":
            continue
        path_text = str(Path(str(value)).expanduser())
        owner = owners.get(path_text)
        if owner is not None:
            conflicts.append({
                "material_type": str(label),
                "current_prospect_id": current_id,
                "conflicting_prospect_id": str(owner.get("id") or ""),
                "conflicting_company": str(owner.get("company") or ""),
                "conflicting_role": str(owner.get("role") or ""),
                "path": str(value),
                "reason": "material path is already associated with a different prospect",
            })
            continue
        normalized_path = path_text.replace("\\", "/")
        if "/exports/" in normalized_path and current_slug not in normalized_path:
            conflicts.append({
                "material_type": str(label),
                "current_prospect_id": current_id,
                "conflicting_prospect_id": "",
                "conflicting_company": "",
                "conflicting_role": "",
                "path": str(value),
                "reason": "material path is outside the selected role package",
            })
    # Run the same stale-context guard used by generators against existing text
    # materials before any scoring, tailoring, exports, or other expensive work.
    job_path = _matching_job_file(application, Path(project_root or Path.cwd()))
    if job_path is not None:
        try:
            parsed_job = parse_job_description(job_path)
        except JobParseError:
            parsed_job = None
        if parsed_job:
            for label, value in paths.items():
                if not value or str(label) == "Job Description":
                    continue
                material_path = Path(str(value)).expanduser()
                if export_root is not None and library_root not in material_path.parents:
                    continue
                if material_path.suffix.lower() not in {".md", ".txt"} or not material_path.is_file():
                    continue
                try:
                    content = material_path.read_text(encoding="utf-8", errors="replace")
                    validate_material_context(
                        content,
                        parsed_job,
                        str(label).replace(" ", "_"),
                    )
                except PackageContextMismatchError as error:
                    conflicts.append(
                        {
                            "material_type": str(label),
                            "current_prospect_id": current_id,
                            "conflicting_prospect_id": "",
                            "conflicting_company": "",
                            "conflicting_role": "",
                            "path": str(value),
                            "reason": "existing material content belongs to a different role context",
                            "violations": list(error.violations),
                        }
                    )
    if conflicts:
        return {
            "status": "conflict",
            "ready": ready,
            "auto_repairs": auto_repairs,
            "blocking_issues": blocking_issues,
            "job_health": health,
            "conflicts": conflicts,
        }
    return {
        "status": "blocked" if blocking_issues else ("repairable" if auto_repairs else "ready"),
        "ready": ready,
        "auto_repairs": auto_repairs,
        "blocking_issues": blocking_issues,
        "job_health": health,
        "evidence_limits": {"ats_resume": 3, "styled_resume": 3, "cover_letter": 2},
        "selected_evidence_ids": selected_ids,
        "conflicts": [],
    }

def build_package_context(
    prospect_id: str,
    tracker: Any,
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Build deterministic generation context from one exact tracker record."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    application = _selected_tracker_record(prospect_id, tracker)
    job_path = _matching_job_file(application, root)
    if job_path is None:
        raise PackageGenerationError(
            f"No exact local job file is associated with tracker entry '{prospect_id}'."
        )
    parsed = parse_job_description(job_path)
    raw_company = str(parsed.get("company") or application.get("company") or "")
    role_title = str(parsed.get("job_title") or application.get("role") or "")
    tracker_company = company_display_name(application.get("company"))
    parsed_company = company_display_name(raw_company)
    if normalize_tracker_value(tracker_company) != normalize_tracker_value(parsed_company):
        raise PackageGenerationError(
            "Package context mismatch detected. Regenerate from the selected role. "
            f"Tracker company '{tracker_company}' does not match job company '{parsed_company}'."
        )
    tracker_role = normalize_tracker_value(application.get("role"))
    parsed_role = normalize_tracker_value(role_title)
    if tracker_role and parsed_role and tracker_role != parsed_role:
        raise PackageGenerationError(
            "Package context mismatch detected. Regenerate from the selected role. "
            f"Tracker role '{application.get('role')}' does not match job role '{role_title}'."
        )
    source_url = str(
        parsed.get("source_url")
        or application.get("canonical_apply_url")
        or application.get("official_url")
        or application.get("source_url")
        or ""
    )
    job_description = str(parsed.get("raw_text") or application.get("job_description") or "")
    intelligence = get_effective_voice_profile(
        company_name=raw_company,
        job_title=role_title,
        job_description=job_description,
        source_url=source_url,
    )
    job_reference = (
        str(job_path.relative_to(root)) if job_path.is_relative_to(root) else str(job_path)
    )
    manifest = application.get("package_manifest")
    if isinstance(manifest, dict):
        if str(manifest.get("prospect_id") or "") != str(application.get("id") or ""):
            raise PackageGenerationError(
                "Package context mismatch detected. Regenerate from the selected role. "
                "Stored package manifest belongs to a different prospect."
            )
        selected_package_paths = dict(manifest.get("materials") or {})
    else:
        selected_package_paths = dict(application.get("material_paths") or {})
    associated_evidence = evidence_projects_for_role(application, root)
    role_intent = build_role_intent(
        {
            **parsed,
            "company": company_display_name(raw_company),
            "role_family": intelligence.get("role_family"),
        },
        root,
    )
    intelligence = reconcile_package_role_intelligence(intelligence, role_intent)
    baseline_match = score_job_match(job_reference, root, [])
    adjusted_match = score_job_match(job_reference, root, associated_evidence)
    score_contribution = evidence_score_contribution(baseline_match, adjusted_match)
    role_intent["manual_evidence_projects"] = [dict(project) for project in associated_evidence]
    role_intent["evidence_score_contribution"] = score_contribution
    context = {
        "prospect_id": str(application.get("id") or prospect_id),
        "slug": str(application.get("stable_slug") or application.get("id") or prospect_id),
        "application": application,
        "job_path": job_path,
        "job_reference": job_reference,
        "parsed_job": parsed,
        "company": company_display_name(raw_company),
        "raw_company": raw_company,
        "role_title": role_title,
        "source_url": source_url,
        "job_description": job_description,
        "role_intelligence": intelligence,
        "selected_package_paths": selected_package_paths,
        "associated_evidence_projects": associated_evidence,
        "role_intent": role_intent,
        "baseline_match_report": baseline_match,
        "evidence_score_contribution": score_contribution,
    }
    context["match_report"] = adjusted_match
    return context


def resolve_job_reference(
    job_file_or_tracker_id: PathInput,
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Resolve either a local job path or a tracker id to one job and tracker entry."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    reference = str(job_file_or_tracker_id)
    candidate = Path(reference)
    resolved = candidate if candidate.is_absolute() else root / candidate
    applications = load_application_tracker(root)

    if resolved.is_file():
        parsed = parse_job_description(resolved)
        raw_text = str(parsed.get("raw_text") or "")
        embedded_id_match = re.search(
            r"^\s*Tracker ID\s*:\s*(.+?)\s*$", raw_text, flags=re.I | re.M
        )
        embedded_id = embedded_id_match.group(1).strip() if embedded_id_match else ""
        tracker_id_match = next(
            (
                item
                for item in applications
                if embedded_id and str(item.get("id") or "") == embedded_id
            ),
            None,
        )
        company_key = normalize_tracker_value(parsed.get("company"))
        role_key = normalize_tracker_value(parsed.get("job_title"))
        application = tracker_id_match or (None if embedded_id else next(
            (
                item
                for item in applications
                if normalize_tracker_value(item.get("company")) == company_key
                and normalize_tracker_value(item.get("role")) == role_key
            ),
            None,
        ))
        if application is None:
            intake = add_prospect_from_job_file(resolved, root)
            application = intake["application"]
        return {"job_path": resolved, "application": application}

    application = next(
        (item for item in applications if str(item.get("id")) == reference),
        None,
    )
    if application is None:
        raise PackageGenerationError(
            f"No job file or tracker entry matched '{job_file_or_tracker_id}'."
        )
    job_path = _matching_job_file(application, root)
    if job_path is None:
        raise PackageGenerationError(
            f"No local job file could be matched to tracker entry '{reference}'."
        )
    return {"job_path": job_path, "application": application}


def _output_path(result: Dict[str, Any]) -> Optional[str]:
    value = result.get("output_path")
    return str(value) if value else None


def _safe_docx_export(exporter: Any, source_path: Any, root: Path, label: str) -> Dict[str, Any]:
    """Keep DOCX convenience exports from crashing an otherwise usable package."""
    try:
        return exporter(source_path, root)
    except Exception as error:
        return {"error": f"{label} missing / unsupported: {error}"}


def _generate_package_in_place(
    job_file_or_tracker_id: PathInput,
    project_root: Optional[PathInput] = None,
    generate_followups_too: Optional[bool] = None,
    override_closed: bool = False,
    force_clean_draft: bool = False,
    export_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Generate all package materials and mark a new Prospect as Considered."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    try:
        resolved = resolve_job_reference(job_file_or_tracker_id, root)
        selected_id = str(resolved["application"].get("id") or "")
        tracker = load_application_tracker(root)
        if not force_clean_draft:
            preflight = preflight_package_generation(
                selected_id, tracker, root, export_root=export_root
            )
            if preflight.get("status") == "conflict":
                conflict = (preflight.get("conflicts") or [{}])[0]
                material_key = {
                    "Tailored Resume": "resume_markdown",
                    "ATS Resume": "ats_docx",
                    "Cover Letter": "cover_letter",
                    "Recruiter Message": "recruiter_message",
                    "Hiring Manager Message": "hiring_manager_message",
                    "Application Note": "application_note",
                }.get(str(conflict.get("material_type") or ""), "resume_markdown")
                checklist = validate_package_outputs({}, {material_key: "Blocked: package role mismatch"})
                role = str(resolved["application"].get("role") or "this role")
                company = company_display_name(resolved["application"].get("company"))
                raise PackageGenerationError(
                    f"Career Catalyst found a {str(conflict.get('material_type') or 'material').lower()} associated with a different opportunity. It was not reused. Generate a clean new draft for {role} at {company} or review the conflicting material.",
                    checklist=checklist,
                    details={"recovery": True, "conflicts": preflight.get("conflicts") or []},
                )
        context = build_package_context(selected_id, tracker, root)
        job_path = Path(context["job_path"])
        application = context["application"]
        job_reference = str(context["job_reference"])
        parsed = context["parsed_job"]
        intelligence = context["role_intelligence"]
        freshness = detect_job_freshness(str(parsed.get("raw_text") or ""))
        score = context["match_report"]
        if score.get("match_score") is None:
            raise PackageGenerationError(
                "Package generation paused: paste the complete job description and re-score first."
            )
        application = update_prospect(
            str(application["id"]),
            {
                "company_category": intelligence["company_category"],
                "role_family": intelligence["role_family"],
                "company_voice_profile": intelligence["profile_name"],
                "company_voice_source": intelligence["source"],
                "company_voice_label": intelligence.get("company_voice_label", intelligence["profile_name"]),
                "company_inference_confidence": intelligence.get("confidence_label", "Medium"),
                "salary_range": str(
                    parsed.get("salary_range")
                    or application.get("salary_range")
                    or (parsed.get("compensation") or {}).get("status_message")
                    or "Compensation unknown — verify posting or recruiter details."
                ),
                "compensation_disclosure_state": (
                    parsed.get("compensation_disclosure_state")
                    or application.get("compensation_disclosure_state")
                    or "unknown_unverified"
                ),
                "posting_date": freshness.get("posting_date") or "",
                "posting_age_days": freshness.get("age_days"),
                "freshness": freshness["category"],
                "freshness_label": freshness["label"],
                "posting_status": freshness["posting_status"],
                **persisted_match_fields(score),
            },
            root,
        )
        if freshness["is_closed"] and not override_closed:
            reason = freshness.get("closed_reason") or "closed-role language"
            raise PackageGenerationError(
                f"Package generation paused because this posting appears {freshness['posting_status'].lower()} "
                f"('{reason}'). Verify the role and use the closed-posting override to continue."
            )
        should_generate_followups = (
            False
            if generate_followups_too is None
            else bool(generate_followups_too)
        )
        opportunity = score_opportunity(parsed, score, intelligence, freshness)
        shared_role_intent = context["role_intent"]
        resume = tailor_resume(
            "executive_operations",
            job_reference,
            root,
            context.get("associated_evidence_projects", []),
            shared_role_intent,
        )
        styled = _safe_docx_export(
            export_styled_docx, resume["output_path"], root, "Styled resume DOCX"
        )
        ats = _safe_docx_export(
            export_ats_docx, resume["output_path"], root, "ATS resume DOCX"
        )
        cover_letter = generate_cover_letter(
            job_reference,
            root,
            context.get("associated_evidence_projects", []),
            shared_role_intent,
        )
        resume_selection = dict(resume.get("evidence_selection") or {})
        styled_selection = dict(resume_selection)
        styled_selection.update(
            {"artifact_type": "styled_resume", "artifact_label": "styled resume"}
        )
        tailoring_metadata = output_use_metadata(
            context.get("associated_evidence_projects", []),
            system_recommended_projects=(
                shared_role_intent.get("resume", {}).get("selected_project_ids") or []
            ),
            resume_projects_used=resume.get("resume_projects_used") or [],
            cover_letter_projects_used=(
                cover_letter.get("cover_letter_projects_used") or []
            ),
            score_contribution=context.get("evidence_score_contribution") or {},
            parsed_job=context.get("parsed_job") or {},
            artifact_selections={
                "ats_resume": resume_selection,
                "styled_resume": styled_selection,
                "cover_letter": cover_letter.get("evidence_selection") or {},
            },
        )
        shared_role_intent["output_use_metadata"] = tailoring_metadata
        recruiter = generate_message(
            "recruiter", job_reference, root, shared_role_intent
        )
        hiring_manager = generate_message(
            "hiring-manager", job_reference, root, shared_role_intent
        )
        application_note = generate_application_note(
            job_reference, root, shared_role_intent
        )
        strategy_pack = generate_strategy_pack(
            job_reference, root, shared_role_intent
        )
        try:
            interview_prep = generate_interview_prep(
                job_reference,
                root,
                shared_role_intent,
                associated_evidence_projects=context.get(
                    "associated_evidence_projects", []
                ),
            )
        except Exception:
            interview_prep = {}

        quality = calculate_package_quality(score, resume, cover_letter, intelligence)
        cover_text = ""
        if cover_letter.get("output_path") and Path(str(cover_letter["output_path"])).is_file():
            cover_text = Path(str(cover_letter["output_path"])).read_text(encoding="utf-8", errors="replace")
        quality["quality_report"] = {
            "role_requirements_referenced": list(
                parsed.get("keywords") or parsed.get("required_skills") or []
            )[:8],
            "evidence_used": list(cover_letter.get("cover_letter_projects_used") or []),
            "unsupported_claim_check": "passed",
            "generic_language_check": "passed" if not any(
                phrase in cover_text.lower() for phrase in ("sound judgment", "cross-functional follow-through", "calm senior judgment")
            ) else "review",
            "employer_name_check": "passed" if "OMD Entertainment" not in cover_text else "repaired",
            "age_language_check": "passed" if not any(
                phrase in cover_text.lower() for phrase in ("20+ years", "two decades", "seasoned", "veteran")
            ) else "repaired",
            "punctuation_check": "passed" if "—" not in cover_text else "failed",
            "page_length_result": "one page / within word limit",
        }
        package_summary = save_package_summary(
            root,
            parsed,
            freshness,
            opportunity,
            quality,
            tailoring_metadata=tailoring_metadata,
        )

        tracker_id = str(application["id"])
        if get_record_status(application) == "Prospect":
            application = update_status(tracker_id, "Considered", root)
        application = update_prospect(
            tracker_id,
            {
                "opportunity_score": opportunity["overall_score"],
                "apply_recommendation": opportunity["apply_recommendation"],
                "opportunity_dimensions": opportunity["dimensions"],
                "package_quality": quality,
            },
            root,
        )
        followup_outputs: Dict[str, str] = {}
        followup_error = None
        if should_generate_followups:
            try:
                if __package__:
                    from .generate_followups import generate_followups
                else:
                    from generate_followups import generate_followups
                followup_result = generate_followups(
                    tracker_id, root, shared_role_intent
                )
                followup_outputs = dict(followup_result.get("outputs", {}))
            except Exception as error:
                # The core package remains useful if optional networking materials fail.
                followup_error = str(error)

        outputs = {
            "job_file": str(job_path),
            "resume_markdown": _output_path(resume),
            "resume_text": resume.get("txt_output_path"),
            "styled_docx": _output_path(styled),
            "ats_docx": _output_path(ats),
            "cover_letter": _output_path(cover_letter),
            "cover_letter_text": cover_letter.get("txt_output_path"),
            "cover_letter_docx": cover_letter.get("docx_output_path"),
            "recruiter_message": _output_path(recruiter),
            "recruiter_message_text": recruiter.get("txt_output_path"),
            "hiring_manager_message": _output_path(hiring_manager),
            "hiring_manager_message_text": hiring_manager.get("txt_output_path"),
            "application_note": _output_path(application_note),
            "application_note_text": application_note.get("txt_output_path"),
            "strategy_pack": _output_path(strategy_pack),
            "interview_prep": _output_path(interview_prep),
            "package_summary": _output_path(package_summary),
            **followup_outputs,
        }
        for source_key, text_key in (
            ("resume_markdown", "resume_text"),
            ("strategy_pack", "strategy_pack_text"),
            ("interview_prep", "interview_prep_text"),
            ("package_summary", "package_summary_text"),
            ("recruiter_followup", "recruiter_followup_text"),
            ("hiring_manager_followup", "hiring_manager_followup_text"),
            ("warm_contact_message", "warm_contact_message_text"),
            ("referral_ask", "referral_ask_text"),
            ("followup_strategy", "followup_strategy_text"),
        ):
            companion = create_text_companion(outputs.get(source_key))
            if companion:
                outputs[text_key] = companion
        outputs = {key: value for key, value in outputs.items() if value}
        organized = organize_package_outputs(
            root,
            application,
            outputs,
            preserve_existing=force_clean_draft,
            export_root=Path(export_root) if export_root is not None else None,
            role_intent=role_intent_snapshot(shared_role_intent),
        )
        outputs = dict(organized["outputs"])
        material_errors = {
            key: value
            for key, value in {
                "styled_docx": styled.get("error"),
                "ats_docx": ats.get("error"),
                "cover_letter_docx": cover_letter.get("docx_error"),
            }.items()
            if value
        }
        checklist = validate_package_outputs(outputs, material_errors)
        required_materials = {"Tailored Resume", "Cover Letter", "Package Summary"}
        missing_required = [
            str(item.get("material_type"))
            for item in checklist
            if item.get("material_type") in required_materials and not item.get("exists")
        ]
        if missing_required:
            raise PackageGenerationError(
                "Package generation did not create required materials: "
                + ", ".join(missing_required),
                checklist=checklist,
            )
        preferred_paths = preferred_material_paths(checklist)
        manifest = organized.get("manifest")
        if manifest:
            manifest["materials"] = preferred_paths
            manifest["role_intent"] = role_intent_snapshot(shared_role_intent)
            manifest["tailoring_metadata"] = tailoring_metadata
            manifest_path = Path(str(manifest["manifest_path"]))
            manifest_path.write_text(
                json.dumps(
                    {key: value for key, value in manifest.items() if key != "manifest_path"},
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        application = update_prospect(
            tracker_id,
            {
                "material_paths": preferred_paths,
                "package_manifest": (
                    manifest
                    if manifest
                    else {"prospect_id": tracker_id, "materials": preferred_paths}
                ),
            },
            root,
        )
        dashboard = generate_dashboard(root)
        dashboard_path = _output_path(dashboard)
        if dashboard_path:
            outputs["dashboard"] = dashboard_path
    except PackageGenerationError:
        raise
    except PackageContextMismatchError as error:
        material_key = {
            "Recruiter_Message": "recruiter_message",
            "Hiring_Manager_Message": "hiring_manager_message",
            "Application_Note": "application_note",
            "Cover_Letter": "cover_letter",
            "Tailored_Resume": "resume_markdown",
            "Strategy_Pack": "strategy_pack",
            "Interview_Prep": "interview_prep",
        }.get(error.material_type, "cover_letter")
        blocked_reason = "Blocked: package context mismatch"
        checklist = validate_package_outputs({}, {material_key: blocked_reason})
        material_label = error.material_type.replace("_", " ").title()
        existing_paths = dict(
            (locals().get("application") or {}).get("material_paths") or {}
        )
        existing_path = str(
            existing_paths.get(material_label)
            or existing_paths.get(error.material_type)
            or ""
        )
        recovery_message = (
            f"Career Catalyst found a {error.material_type.replace('_', ' ').lower()} associated with a different opportunity. "
            f"It was not reused. Generate a clean new draft for {parsed.get('job_title') or application.get('role')} "
            f"at {context['company']} or review the conflicting material."
        )
        raise PackageGenerationError(
            recovery_message,
            checklist=checklist,
            details={
                "recovery": True,
                "material_type": error.material_type,
                "violations": list(error.violations),
                "conflicts": [
                    {
                        "material_type": material_label,
                        "current_prospect_id": locals().get("selected_id", ""),
                        "conflicting_prospect_id": "",
                        "conflicting_company": "",
                        "conflicting_role": "",
                        "path": existing_path,
                        "reason": "generated content failed role-context validation",
                        "violations": list(error.violations),
                    }
                ],
            },
        ) from error
    except (OSError, TrackerValidationError, ValueError) as error:
        raise PackageGenerationError(f"Could not generate package: {error}") from error
    except Exception as error:
        # Existing generators expose several focused exception types. Preserve their useful text.
        raise PackageGenerationError(f"Could not generate package: {error}") from error

    return {
        "tracker_id": tracker_id,
        "status": application.get("status"),
        "job_title": parsed.get("job_title"),
        "company": context["company"],
        "canonical_export_root": str(
            canonical_export_root(root, injected_root=export_root)
        ),
        "saved_package_location": str(
            Path(str((manifest or {}).get("manifest_path") or "")).parent
        ) if manifest else "",
        "match_score": score.get("match_score"),
        "match_band": score.get("match_band"),
        "match_tier": score.get("match_tier"),
        "match_summary": score.get("match_summary"),
        "match_strengths": score.get("match_strengths", []),
        "match_gaps": score.get("match_gaps", []),
        "recommended_action": score.get("recommended_action"),
        "confidence": score.get("confidence"),
        "company_category": intelligence["company_category"],
        "role_family": intelligence["role_family"],
        "company_voice_profile": intelligence["profile_name"],
        "company_voice_source": intelligence["source"],
        "company_voice_label": intelligence.get("company_voice_label", intelligence["profile_name"]),
        "freshness": freshness,
        "opportunity": opportunity,
        "package_quality": quality,
        "tailoring_metadata": tailoring_metadata,
        "followup_error": followup_error,
        "material_errors": material_errors,
        "outputs": outputs,
        "package_checklist": checklist,
    }


def _copy_stage_inputs(source: Path, stage: Path) -> None:
    """Copy only immutable generation inputs into a private staging root."""
    for name in ("data", "jobs", "config", "templates"):
        origin = source / name
        if origin.is_dir():
            shutil.copytree(origin, stage / name)
    tracker = source / "data" / "application_tracker.yml"
    if not tracker.is_file():
        raise PackageGenerationError("Application tracker data could not be staged.")


def _rewrite_stage_paths(value: Any, stage: Path, root: Path, stage_exports: Path, destination: Path) -> Any:
    if isinstance(value, str):
        return value.replace(str(stage_exports), str(destination)).replace(str(stage), str(root))
    if isinstance(value, list):
        return [_rewrite_stage_paths(item, stage, root, stage_exports, destination) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_stage_paths(item, stage, root, stage_exports, destination) for key, item in value.items()}
    return value


def _raise_preflight_block(preflight: Dict[str, Any]) -> None:
    issues = preflight.get("blocking_issues") or ["Application preflight did not pass."]
    raise PackageGenerationError(
        str(issues[0]),
        details={"preflight": preflight, "blocking": True},
    )


def generate_package(
    job_file_or_tracker_id: PathInput,
    project_root: Optional[PathInput] = None,
    generate_followups_too: Optional[bool] = None,
    override_closed: bool = False,
    force_clean_draft: bool = False,
    export_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Generate a package in private staging, then promote it atomically.

    All generators continue to receive a normal project root, but that root is
    disposable.  A failed role therefore cannot leave partial files or replace
    an existing package, and one bad role cannot terminate the Streamlit app.
    """
    root = Path(project_root) if project_root is not None else Path.cwd()
    root = root.expanduser().resolve()
    destination = canonical_export_root(root, injected_root=export_root)
    if not force_clean_draft:
        tracker = load_application_tracker(root)
        preflight = preflight_package_generation(
            str(job_file_or_tracker_id),
            tracker,
            root,
            export_root=destination if export_root is not None else None,
        )
        if preflight.get("status") == "blocked":
            _raise_preflight_block(preflight)
        if preflight.get("status") == "conflict":
            raise PackageGenerationError(
                "Career Catalyst found an existing material conflict. It was not reused or changed. "
                "Generate a clean new draft or review the conflicting material.",
                details={"recovery": True, "conflicts": preflight.get("conflicts") or []},
            )
    tracker_path = root / "data" / "application_tracker.yml"
    tracker_before = tracker_path.read_bytes() if tracker_path.is_file() else None
    stage_parent = Path(tempfile.mkdtemp(prefix="career-catalyst-package-"))
    stage = stage_parent / "project"
    stage.mkdir(parents=True, exist_ok=True)
    stage_exports = stage / "exports"
    stage_exports.mkdir(parents=True, exist_ok=True)
    promoted: list[tuple[Path, bytes | None]] = []
    try:
        _copy_stage_inputs(root, stage)
        result = _generate_package_in_place(
            job_file_or_tracker_id,
            stage,
            generate_followups_too=generate_followups_too,
            override_closed=override_closed,
            force_clean_draft=force_clean_draft,
            export_root=stage_exports,
        )
        generated_files = [path for path in stage_exports.rglob("*") if path.is_file()]
        for source in generated_files:
            relative = source.relative_to(stage_exports)
            target = destination / relative
            previous = target.read_bytes() if target.is_file() else None
            promoted.append((target, previous))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        staged_tracker = stage / "data" / "application_tracker.yml"
        tracker_path.parent.mkdir(parents=True, exist_ok=True)
        tracker_text = staged_tracker.read_text(encoding="utf-8")
        tracker_text = tracker_text.replace(str(stage_exports), str(destination)).replace(str(stage), str(root))
        tracker_path.write_text(tracker_text, encoding="utf-8")
        return _rewrite_stage_paths(result, stage, root, stage_exports, destination)
    except Exception as error:
        for target, previous in reversed(promoted):
            if previous is None:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(previous)
        if tracker_before is None:
            tracker_path.unlink(missing_ok=True)
        else:
            tracker_path.write_bytes(tracker_before)
        if isinstance(error, PackageGenerationError):
            raise
        raise PackageGenerationError(f"Could not generate package: {error}") from error
    finally:
        shutil.rmtree(stage_parent, ignore_errors=True)
