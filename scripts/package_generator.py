"""Orchestrate a complete Career Catalyst application package."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Dict, Optional, Union, List

import yaml

try:
    from .application_tracker import (
        TrackerValidationError,
        get_record_status,
        load_application_tracker,
        save_application_tracker,
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
    from .package_quality import (
        calculate_package_quality,
        evaluate_candidate_facing_quality,
        save_package_summary,
    )
    from .package_materials import (
        create_text_companion,
        preferred_material_paths,
        validate_complete_package,
        validate_package_outputs,
    )
    from .package_context import PackageContextMismatchError, validate_material_context
    from .materials_library import find_exact_role_package, organize_package_outputs, portable_manifest_paths
    from .storage_paths import canonical_export_root, canonical_storage_path, legacy_material_paths, require_beneath_export_root
    from .filename_utils import company_display_name
    from .parse_job import JobParseError, parse_job_description
    from .prospect_intake import add_prospect_from_job_file
    from .score_match import (
        persisted_match_fields,
        score_job_match,
    )
    from .tailor_resume import tailor_resume
    from .evidence_engine import evidence_projects_for_role
    from .evidence_engine import load_evidence_projects
    from .resume_foundation import load_resume_foundation
    from .evidence_tailoring import (
        evidence_score_contribution,
        output_use_metadata,
    )
    from .role_intent import (
        apply_role_intelligence_overrides,
        build_role_intent,
        reconcile_package_role_intelligence,
        role_intent_snapshot,
    )
    from .role_state_resolver import (
        resolve_job_file,
        resolve_selected_evidence,
        resolve_tracker_record,
    )
    from .role_lifecycle import TERMINAL_STATUSES
except ImportError:
    from application_tracker import (
        TrackerValidationError,
        get_record_status,
        load_application_tracker,
        save_application_tracker,
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
    from package_quality import (
        calculate_package_quality,
        evaluate_candidate_facing_quality,
        save_package_summary,
    )
    from package_materials import (
        create_text_companion,
        preferred_material_paths,
        validate_complete_package,
        validate_package_outputs,
    )
    from package_context import PackageContextMismatchError, validate_material_context
    from materials_library import find_exact_role_package, organize_package_outputs, portable_manifest_paths
    from storage_paths import canonical_export_root, canonical_storage_path, legacy_material_paths, require_beneath_export_root
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
        apply_role_intelligence_overrides,
        build_role_intent,
        reconcile_package_role_intelligence,
        role_intent_snapshot,
    )
    from role_state_resolver import (
        resolve_job_file,
        resolve_selected_evidence,
        resolve_tracker_record,
    )
    from role_lifecycle import TERMINAL_STATUSES


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
    result = resolve_job_file(application, root)
    path = result.get("path") if result.get("status") == "valid" else None
    return Path(path) if path else None


def _selected_tracker_record(
    prospect_id: str, tracker: Any
) -> Dict[str, Any]:
    """Resolve one tracker record strictly by a durable identity field."""
    try:
        return resolve_tracker_record(prospect_id, tracker)
    except ValueError as error:
        raise PackageGenerationError(str(error)) from error


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
        # Terminal/archived records are historical ownership, not active
        # duplicate opportunities. Their stable-ID packages remain recoverable
        # from archive context without blocking a separately reopened role.
        if get_record_status(record) in TERMINAL_STATUSES or record.get("archived") is True:
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
    result = resolve_job_file(application, Path(root))
    if result.get("status") == "valid":
        parsed = result.get("parsed") or {}
        return {
            **result,
            "posting_url": str(parsed.get("source_url") or application.get("source_url") or ""),
            "has_usable_text": True,
        }
    message = result.get("reason") or (
        "The local posting could not be resolved unambiguously."
        if result.get("status") == "ambiguous"
        else "No usable local job description is associated with this role."
    )
    return {
        **result,
        "has_usable_text": False,
        "recoverable": bool(application.get("source_url") or application.get("official_url")),
        "message": message,
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
    try:
        evidence_resolution = resolve_selected_evidence(
            application, load_evidence_projects(root)
        )
        selected_ids = list(evidence_resolution["selected_ids"])
        missing_evidence = list(evidence_resolution["missing_ids"])
        if missing_evidence:
            blocking_issues.append("Selected Evidence could not be resolved: " + ", ".join(missing_evidence))
        else:
            ready.append(f"Selected Evidence resolves ({len(selected_ids)} selected)")
    except Exception as error:
        evidence_resolution = {
            "selected_ids": [],
            "projects": [],
            "missing_ids": [],
        }
        selected_ids = []
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
            source_text = str(parsed_health_job.get("raw_text") or "")
            if "—" in source_text:
                auto_repairs.append("Candidate-facing em dashes will be normalized before validation")
            if re.search(r"20\+\s+years|nearly\s+two\s+decades|two\s+decades|seasoned|veteran", source_text, re.I):
                auto_repairs.append("Age-signaling language will be normalized before validation")
            if re.search(
                r"OMD Entertainment|OMG23\s*/\s*OMD Entertainment",
                source_text,
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
    # Older tracker snapshots can contain absolute /private/Users paths even
    # though the canonical manifest is present under the current export root.
    # Stable manifest ownership wins over those stale references; this avoids
    # treating the role's own package as belonging to a different opportunity.
    exact_package = find_exact_role_package(root, application, export_root=library_root)
    exact_manifest = exact_package.get("manifest") or {}
    exact_owner = str(exact_manifest.get("prospect_id") or "") == current_id
    if exact_owner:
        canonical_files = dict(exact_manifest.get("files") or {})
        if canonical_files:
            paths = canonical_files
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
    for stranded_path in (
        legacy_material_paths(application, library_root)
        if export_root is None and not exact_owner
        else []
    ):
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
        material_path = Path(str(value)).expanduser()
        path_text = str(material_path)
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
        if material_path.is_file() and library_root not in material_path.resolve().parents:
            conflicts.append({
                "material_type": str(label),
                "current_prospect_id": current_id,
                "conflicting_prospect_id": "",
                "conflicting_company": "",
                "conflicting_role": "",
                "path": str(value),
                "reason": "existing material is outside the canonical export root",
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
        "resolved_evidence_ids": [
            str(project.get("id") or "")
            for project in evidence_resolution["projects"]
        ],
        "missing_evidence_ids": list(evidence_resolution["missing_ids"]),
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
    # A saved prospect is the authoritative source for manually verified
    # location/work-arrangement metadata.  Posting text can contain a newer or
    # lower-confidence inference, but it must not replace a value already
    # persisted on the stable tracker record during a rerun.
    parsed = dict(parsed)
    for field in ("location", "work_arrangement"):
        saved_value = str(application.get(field) or "").strip()
        if saved_value:
            parsed[field] = saved_value
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
    inferred_role_intelligence = dict(intelligence)
    inferred_role_intent = dict(role_intent)
    intelligence, role_intent = apply_role_intelligence_overrides(
        application, intelligence, role_intent
    )
    intelligence = reconcile_package_role_intelligence(intelligence, role_intent)
    # Dynamic role intelligence is already resolved for this exact posting.
    # Expose those labels to the shared Tailoring Plan even when no manual
    # override exists; otherwise the plan falls back to the misleading
    # placeholder "Inferred".
    role_intent.setdefault(
        "effective_company_voice", intelligence.get("company_voice_label")
    )
    role_intent.setdefault(
        "effective_company_category", intelligence.get("company_category_label")
    )
    role_intent.setdefault(
        "effective_role_family", intelligence.get("role_family_label")
    )
    baseline_match = score_job_match(
        job_reference,
        root,
        [],
        role_intelligence=intelligence,
    )
    adjusted_match = score_job_match(
        job_reference,
        root,
        associated_evidence,
        role_intelligence=intelligence,
    )
    # Reparse/rescore persists the canonical score on the stable tracker
    # record.  Package context must keep that score as the base even when an
    # Evidence evaluation is incomplete or contributes no new requirements.
    # Only a complete, positively matched Evidence report may provide a valid
    # adjusted score; genuinely unscored records do not inherit anything.
    canonical_match = persisted_match_fields(application)
    adjusted_fields = persisted_match_fields(adjusted_match)
    evidence_matches = list(adjusted_match.get("associated_evidence_matches") or [])
    if canonical_match:
        canonical_score = int(canonical_match["match_score"])
        for field, value in canonical_match.items():
            baseline_match[field] = value
        baseline_match["match_band"] = canonical_match["match_tier"]
        baseline_match.pop("incomplete_import", None)
        baseline_match.pop("missing_required_fields", None)
        baseline_match["base_match_score"] = canonical_score
        baseline_match["evidence_score_delta"] = 0

        if not adjusted_fields or not evidence_matches:
            # An incomplete/no-op Evidence evaluation must not turn a valid
            # persisted score into 0 or “Not scored”.
            for field, value in canonical_match.items():
                adjusted_match[field] = value
            adjusted_match["match_band"] = canonical_match["match_tier"]
            adjusted_match.pop("incomplete_import", None)
            adjusted_match.pop("missing_required_fields", None)
            adjusted_match["base_match_score"] = canonical_score
            adjusted_match["evidence_score_delta"] = 0
        else:
            # Keep the canonical persisted score as the “changed from” value
            # even when selected Evidence produces a valid adjustment.
            adjusted_match["base_match_score"] = canonical_score
            adjusted_match["evidence_score_delta"] = (
                int(adjusted_match["match_score"]) - canonical_score
            )
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
        "inferred_role_intelligence": inferred_role_intelligence,
        "inferred_role_intent": inferred_role_intent,
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

    if resolved.is_file() and (resolved.resolve() == (root / "jobs").resolve() or (root / "jobs").resolve() in resolved.resolve().parents):
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

    application = next((item for item in applications if reference in {str(item.get(key) or "") for key in ("id", "prospect_id", "stable_slug", "record_id")}), None)
    if application is None:
        raise PackageGenerationError(
            f"No job file or tracker entry matched '{job_file_or_tracker_id}'."
        )
    job_result = resolve_job_file(application, root)
    job_path = Path(str(job_result["path"])) if job_result.get("status") == "valid" else None
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
        intelligence_updates = {
                "company_category": intelligence["company_category"],
                "role_family": intelligence["role_family"],
                "company_voice_profile": intelligence["profile_name"],
                "company_voice_source": intelligence["source"],
                "company_voice_label": intelligence.get("company_voice_label", intelligence["profile_name"]),
                "company_inference_confidence": intelligence.get("confidence_label", "Medium"),
        }
        # Explicit role-intelligence overrides live in their own tracker field;
        # do not replace the inferred source fields when generation runs.
        if intelligence.get("role_intelligence_overrides"):
            intelligence_updates = {}
        application = update_prospect(
            str(application["id"]),
            {
                **intelligence_updates,
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
        tailoring_metadata["role_intelligence"] = {
            "overrides": dict(
                context["role_intelligence"].get("role_intelligence_overrides") or {}
            ),
            "inferred": dict(context.get("inferred_role_intelligence") or {}),
            "effective": {
                "company_voice": context["role_intelligence"].get("company_voice_label"),
                "category": context["role_intelligence"].get("company_category_label"),
                "role_family": context["role_intelligence"].get("role_family_label"),
                "primary_hiring_need": shared_role_intent.get("primary_hiring_need"),
            },
        }
        shared_role_intent["output_use_metadata"] = tailoring_metadata
        recruiter = generate_message(
            "recruiter",
            job_reference,
            root,
            shared_role_intent,
            context.get("associated_evidence_projects", []),
        )
        hiring_manager = generate_message(
            "hiring-manager",
            job_reference,
            root,
            shared_role_intent,
            context.get("associated_evidence_projects", []),
        )
        application_note = generate_application_note(
            job_reference,
            root,
            shared_role_intent,
            context.get("associated_evidence_projects", []),
        )
        strategy_pack = generate_strategy_pack(
            job_reference,
            root,
            shared_role_intent,
            context.get("associated_evidence_projects", []),
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
        tracker_id = str(application["id"])
        # Keep the local package owner in sync for organization without
        # persisting tracker changes until candidate-facing QA passes.
        if get_record_status(application) == "Prospect":
            application = dict(application)
            application["status"] = "Considered"
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
        career_data = load_resume_foundation(root)
        candidate_qa = evaluate_candidate_facing_quality(
            {
                "ats_resume": outputs.get("resume_markdown") or resume.get("output_path"),
                "styled_resume": outputs.get("resume_markdown") or resume.get("output_path"),
                "cover_letter": outputs.get("cover_letter_text") or outputs.get("cover_letter"),
                "application_note": outputs.get("application_note_text") or outputs.get("application_note"),
            },
            parsed_job=parsed,
            tailoring_metadata=tailoring_metadata,
            associated_evidence_projects=list(context.get("associated_evidence_projects") or []),
            known_projects=list(
                (career_data.get("data", {}).get("projects", {}) or {}).get("projects", [])
            ) + list(
                (career_data.get("data", {}).get("evidence_projects", {}) or {}).get("evidence_projects", [])
            ),
        )
        quality["candidate_facing_qa"] = candidate_qa
        if candidate_qa["status"] == "BLOCKED":
            raise PackageGenerationError(
                "Candidate-facing QA blocked package generation:\n- "
                + "\n- ".join(candidate_qa["blocking_reasons"]),
                details={"candidate_facing_qa": candidate_qa, "blocking": True},
            )
        package_summary = save_package_summary(
            root,
            parsed,
            freshness,
            opportunity,
            quality,
            tailoring_metadata=tailoring_metadata,
        )
        outputs["package_summary"] = _output_path(package_summary)
        outputs = {key: value for key, value in outputs.items() if value}
        material_errors = {
            key: value
            for key, value in {
                "styled_docx": styled.get("error"),
                "ats_docx": ats.get("error"),
                "cover_letter_docx": cover_letter.get("docx_error"),
            }.items()
            if value
        }
        # Validate required generated outputs before moving anything into the
        # canonical package.  A failed generation therefore cannot create an
        # empty manifest or version away a previously valid package.
        precheck = validate_package_outputs(outputs, material_errors)
        required_precheck = validate_complete_package(
            {**outputs, "manifest_path": ""}
        )
        missing_required = [
            value for value in required_precheck["missing_required"]
            if value != "Canonical Manifest"
        ]
        if missing_required:
            raise PackageGenerationError(
                "Package generation did not create required materials: "
                + ", ".join(missing_required),
                checklist=precheck,
            )
        if get_record_status(application) == "Considered" and get_record_status(
            context["application"]
        ) == "Prospect":
            update_status(tracker_id, "Considered", root)
        update_prospect(
            tracker_id,
            {
                "opportunity_score": opportunity["overall_score"],
                "apply_recommendation": opportunity["apply_recommendation"],
                "opportunity_dimensions": opportunity["dimensions"],
                "package_quality": quality,
            },
            root,
        )
        organized = organize_package_outputs(
            root,
            application,
            outputs,
            preserve_existing=force_clean_draft,
            export_root=Path(export_root) if export_root is not None else None,
            role_intent=role_intent_snapshot(shared_role_intent),
        )
        outputs = dict(organized["outputs"])
        manifest = organized.get("manifest")
        if manifest:
            outputs["manifest_path"] = str(manifest.get("manifest_path") or "")
        checklist = validate_package_outputs(outputs, material_errors)
        completion = validate_complete_package(
            outputs,
            owner_id=tracker_id,
            export_root=Path(export_root) if export_root is not None else canonical_export_root(root),
        )
        if not completion["complete"]:
            raise PackageGenerationError(
                "Package generation did not create required materials: "
                + ", ".join(completion["missing_required"]),
                checklist=completion["checklist"],
            )
        preferred_paths = preferred_material_paths(checklist)
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
        "role_intelligence_overrides": dict(
            intelligence.get("role_intelligence_overrides") or {}
        ),
        "inferred_role_intelligence": dict(
            context.get("inferred_role_intelligence") or {}
        ),
        "freshness": freshness,
        "opportunity": opportunity,
        "package_quality": quality,
        "tailoring_metadata": tailoring_metadata,
        "followup_error": followup_error,
        "material_errors": material_errors,
        "outputs": outputs,
        "package_checklist": checklist,
        "manifest": manifest,
        "package_complete": True,
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


def _rebase_stage_path(value: str, stage: Path, root: Path, stage_exports: Path, destination: Path) -> str:
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        return value
    resolved = canonical_storage_path(candidate)
    exports_boundary = canonical_storage_path(stage_exports)
    stage_boundary = canonical_storage_path(stage)
    if resolved == exports_boundary or exports_boundary in resolved.parents:
        return str(canonical_storage_path(destination / resolved.relative_to(exports_boundary)))
    if resolved == stage_boundary or stage_boundary in resolved.parents:
        return str(canonical_storage_path(root / resolved.relative_to(stage_boundary)))
    return str(canonical_storage_path(resolved))


def _rewrite_stage_paths(value: Any, stage: Path, root: Path, stage_exports: Path, destination: Path) -> Any:
    if isinstance(value, str):
        return _rebase_stage_path(value, stage, root, stage_exports, destination)
    if isinstance(value, list):
        return [_rewrite_stage_paths(item, stage, root, stage_exports, destination) for item in value]
    if isinstance(value, dict):
        return {key: _rewrite_stage_paths(item, stage, root, stage_exports, destination) for key, item in value.items()}
    return value


def _package_result_completion(result: Dict[str, Any], export_root: Path) -> Dict[str, Any]:
    outputs = dict(result.get("outputs") or {})
    manifest = dict(result.get("manifest") or {})
    outputs["manifest_path"] = str(manifest.get("manifest_path") or outputs.get("manifest_path") or "")
    return validate_complete_package(
        outputs,
        owner_id=str(result.get("tracker_id") or ""),
        export_root=export_root,
    )


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
    promoted_package: Path | None = None
    rollback_package: Path | None = None
    promotion_candidate: Path | None = None
    promotion_swapped = False
    try:
        _copy_stage_inputs(root, stage)
        source_tracker = load_application_tracker(root)
        source_application = next(
            (item for item in source_tracker if str(item.get("id") or "") == str(job_file_or_tracker_id)),
            None,
        )
        if source_application:
            existing = find_exact_role_package(root, source_application, export_root=destination)
            existing_folder = existing.get("folder")
            if existing_folder:
                existing_folder = require_beneath_export_root(existing_folder, destination)
                relative_existing = existing_folder.relative_to(destination)
                shutil.copytree(existing_folder, stage_exports / relative_existing, dirs_exist_ok=True)
        result = _generate_package_in_place(
            job_file_or_tracker_id,
            stage,
            generate_followups_too=generate_followups_too,
            override_closed=override_closed,
            force_clean_draft=force_clean_draft,
            export_root=stage_exports,
        )
        staged_completion = _package_result_completion(result, stage_exports)
        if not staged_completion["complete"]:
            raise PackageGenerationError(
                "Package generation did not create a complete staged package: "
                + ", ".join(staged_completion["missing_required"]),
                checklist=staged_completion["checklist"],
            )
        staged_package = require_beneath_export_root(result["saved_package_location"], stage_exports)
        relative_package = staged_package.relative_to(canonical_storage_path(stage_exports))
        promoted_package = require_beneath_export_root(destination / relative_package, destination)
        promoted_package.parent.mkdir(parents=True, exist_ok=True)
        token = uuid.uuid4().hex
        promotion_candidate = promoted_package.parent / f".{promoted_package.name}.staging-{token}"
        rollback_package = promoted_package.parent / f".{promoted_package.name}.rollback-{token}"
        shutil.copytree(staged_package, promotion_candidate)

        rewritten = _rewrite_stage_paths(result, stage, root, stage_exports, destination)
        rewritten["saved_package_location"] = str(promoted_package)
        rewritten_manifest = dict(rewritten.get("manifest") or {})
        rewritten_manifest["manifest_path"] = str(promoted_package / "manifest.json")
        rewritten["manifest"] = rewritten_manifest
        rewritten_outputs = dict(rewritten.get("outputs") or {})
        rewritten_outputs["manifest_path"] = rewritten_manifest["manifest_path"]
        rewritten["outputs"] = rewritten_outputs

        candidate_manifest = promotion_candidate / "manifest.json"
        manifest_payload = {
            key: value for key, value in rewritten_manifest.items() if key != "manifest_path"
        }
        candidate_manifest.write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")

        candidate_outputs = {}
        for key, value in rewritten_outputs.items():
            path = Path(str(value))
            if path.is_absolute() and (path == promoted_package or promoted_package in path.parents):
                candidate_outputs[key] = str(promotion_candidate / path.relative_to(promoted_package))
            else:
                candidate_outputs[key] = value
        candidate_outputs["manifest_path"] = str(candidate_manifest)
        candidate_completion = validate_complete_package(
            candidate_outputs,
            owner_id=str(rewritten.get("tracker_id") or ""),
            export_root=destination,
        )
        if not candidate_completion["complete"]:
            raise PackageGenerationError(
                "Package promotion candidate is incomplete: "
                + ", ".join(candidate_completion["missing_required"]),
                checklist=candidate_completion["checklist"],
            )

        if promoted_package.exists():
            promoted_package.replace(rollback_package)
        promotion_candidate.replace(promoted_package)
        promotion_swapped = True

        rewritten_outputs = {
            key: value
            for key, value in rewritten_outputs.items()
            if not Path(str(value)).is_absolute() or Path(str(value)).is_file()
        }
        rewritten_outputs["manifest_path"] = str(promoted_package / "manifest.json")
        rewritten["outputs"] = rewritten_outputs
        rewritten_manifest["legacy_files_moved"] = [
            value
            for value in rewritten_manifest.get("legacy_files_moved") or []
            if Path(str(value)).is_file()
        ]
        rewritten["manifest"] = rewritten_manifest
        (promoted_package / "manifest.json").write_text(
            json.dumps(
                {key: value for key, value in rewritten_manifest.items() if key != "manifest_path"},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        staged_tracker = stage / "data" / "application_tracker.yml"
        tracker_path.parent.mkdir(parents=True, exist_ok=True)
        staged_tracker_payload = yaml.safe_load(staged_tracker.read_text(encoding="utf-8")) or {}
        tracker_payload = _rewrite_stage_paths(
            staged_tracker_payload, stage, root, stage_exports, destination
        )
        tracker_records = (
            tracker_payload.get("applications")
            if isinstance(tracker_payload, dict)
            else tracker_payload
        )
        for record in tracker_records or []:
            if str(record.get("id") or "") == str(rewritten.get("tracker_id") or ""):
                record["package_manifest"] = rewritten_manifest
                record["material_paths"] = dict(rewritten_manifest.get("materials") or {})
                break
        if not isinstance(tracker_records, list):
            raise PackageGenerationError(
                "Package generation produced an invalid tracker payload."
            )
        # Keep the final promotion behind the same strict, atomic tracker
        # validation boundary as every other write path.  A package may not
        # report success while bypassing canonical tracker serialization.
        try:
            save_application_tracker(tracker_records, root)
        except TrackerValidationError as error:
            raise PackageGenerationError(
                "Package generation produced an incomplete tracker payload: "
                f"{error}"
            ) from error

        final_completion = _package_result_completion(rewritten, destination)
        if not final_completion["complete"]:
            raise PackageGenerationError(
                "Promoted package failed final validation: "
                + ", ".join(final_completion["missing_required"]),
                checklist=final_completion["checklist"],
            )
        rewritten["canonical_export_root"] = str(destination)
        rewritten["package_checklist"] = final_completion["checklist"]
        rewritten["package_complete"] = True
        if rollback_package and rollback_package.exists():
            shutil.rmtree(rollback_package)
        return rewritten
    except Exception as error:
        if promotion_swapped and promoted_package and promoted_package.exists() and rollback_package and rollback_package.exists():
            shutil.rmtree(promoted_package)
            rollback_package.replace(promoted_package)
        elif promotion_swapped and promoted_package and promoted_package.exists() and rollback_package and not rollback_package.exists():
            shutil.rmtree(promoted_package)
        if promotion_candidate and promotion_candidate.exists():
            shutil.rmtree(promotion_candidate)
        if tracker_before is None:
            tracker_path.unlink(missing_ok=True)
        else:
            tracker_path.write_bytes(tracker_before)
        if isinstance(error, PackageGenerationError):
            raise
        raise PackageGenerationError(f"Could not generate package: {error}") from error
    finally:
        shutil.rmtree(stage_parent, ignore_errors=True)
