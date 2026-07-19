"""Orchestrate a complete Career Catalyst application package."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    from .application_strategy import build_application_strategy, build_hiring_manager_lens
    from .application_tracker import (
        TrackerValidationError,
        load_application_tracker,
        normalize_tracker_value,
        update_prospect,
        update_status,
    )
    from .dynamic_role_intelligence import get_effective_voice_profile
    from .evidence_profile import evidence_as_card
    from .export_docx import export_ats_docx, export_styled_docx
    from .generate_application_note import generate_application_note
    from .generate_cover_letter import generate_cover_letter
    from .generate_dashboard import generate_dashboard
    from .generate_messages import generate_message
    from .generate_interview_prep import generate_interview_prep
    from .hiring_manager_brief import build_hiring_manager_brief
    from .generate_strategy_pack import generate_strategy_pack
    from .job_freshness import detect_job_freshness
    from .opportunity_scoring import score_opportunity
    from .package_quality import calculate_package_quality, save_package_summary
    from .package_materials import (
        create_text_companion,
        preferred_material_paths,
        validate_package_outputs,
    )
    from .package_context import (
        CONTEXT_MISMATCH_MESSAGE,
        PackageContextMismatchError,
        prospect_context_fingerprint,
    )
    from .materials_library import organize_package_outputs
    from .filename_utils import company_display_name
    from .parse_job import JobParseError, parse_job_description
    from .prospect_intake import add_prospect_from_job_file
    from .score_match import persisted_match_fields, score_job_match
    from .role_evidence_selection import selected_evidence
    from .tailor_resume import tailor_resume
except ImportError:
    from application_strategy import build_application_strategy, build_hiring_manager_lens
    from application_tracker import (
        TrackerValidationError,
        load_application_tracker,
        normalize_tracker_value,
        update_prospect,
        update_status,
    )
    from dynamic_role_intelligence import get_effective_voice_profile
    from evidence_profile import evidence_as_card
    from export_docx import export_ats_docx, export_styled_docx
    from generate_application_note import generate_application_note
    from generate_cover_letter import generate_cover_letter
    from generate_dashboard import generate_dashboard
    from generate_messages import generate_message
    from generate_interview_prep import generate_interview_prep
    from hiring_manager_brief import build_hiring_manager_brief
    from generate_strategy_pack import generate_strategy_pack
    from job_freshness import detect_job_freshness
    from opportunity_scoring import score_opportunity
    from package_quality import calculate_package_quality, save_package_summary
    from package_materials import (
        create_text_companion,
        preferred_material_paths,
        validate_package_outputs,
    )
    from package_context import (
        CONTEXT_MISMATCH_MESSAGE,
        PackageContextMismatchError,
        prospect_context_fingerprint,
    )
    from materials_library import organize_package_outputs
    from filename_utils import company_display_name
    from parse_job import JobParseError, parse_job_description
    from prospect_intake import add_prospect_from_job_file
    from score_match import persisted_match_fields, score_job_match
    from role_evidence_selection import selected_evidence
    from tailor_resume import tailor_resume


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
            CONTEXT_MISMATCH_MESSAGE,
            details={
                "context_mismatch": True,
                "mismatch_status": "confirmed",
                "mismatch_reason": "tracker_job_company_conflict",
                "selected_prospect_id": prospect_id,
                "conflicting_companies": [tracker_company, parsed_company],
            },
        )
    tracker_role = normalize_tracker_value(application.get("role"))
    parsed_role = normalize_tracker_value(role_title)
    if tracker_role and parsed_role and tracker_role != parsed_role:
        raise PackageGenerationError(
            CONTEXT_MISMATCH_MESSAGE,
            details={
                "context_mismatch": True,
                "mismatch_status": "confirmed",
                "mismatch_reason": "tracker_job_role_conflict",
                "selected_prospect_id": prospect_id,
                "conflicting_roles": [application.get("role"), role_title],
            },
        )
    source_url = str(
        parsed.get("source_url")
        or application.get("canonical_apply_url")
        or application.get("official_url")
        or application.get("source_url")
        or ""
    )
    job_description = str(
        parsed.get("raw_text") or application.get("job_description") or ""
    )
    saved_interpretation = (
        dict(application.get("role_interpretation") or {})
        if isinstance(application.get("role_interpretation"), dict)
        else {}
    )
    interpretation_overrides = dict(saved_interpretation.get("user_overrides") or {})
    if saved_interpretation.get("user_reviewed"):
        interpretation_overrides["user_reviewed"] = True
        if saved_interpretation.get("user_feedback"):
            interpretation_overrides["feedback"] = saved_interpretation["user_feedback"]
        for field in (
            "primary_archetype", "secondary_archetype", "plain_english_summary",
            "technical_depth",
            "people_management_expectation", "client_facing_expectation",
            "strategic_vs_execution_balance",
        ):
            if saved_interpretation.get(field) not in (None, ""):
                interpretation_overrides[field] = saved_interpretation[field]
    intelligence = get_effective_voice_profile(
        company_name=raw_company,
        job_title=role_title,
        job_description=job_description,
        source_url=source_url,
        role_interpretation_overrides=interpretation_overrides or None,
        role_interpretation_result=saved_interpretation or None,
    )
    job_reference = (
        str(job_path.relative_to(root)) if job_path.is_relative_to(root) else str(job_path)
    )
    saved_evidence_overrides = dict(
        application.get("evidence_selection_overrides")
        or (application.get("role_evidence_selection") or {}).get("overrides")
        or {}
    )
    match_report = score_job_match(
        job_reference,
        root,
        saved_interpretation or None,
        saved_evidence_overrides or None,
    )
    intelligence["role_interpretation"] = match_report.get("role_interpretation") or intelligence.get("role_interpretation", {})
    intelligence["role_evidence_selection"] = dict(
        match_report.get("role_evidence_selection") or {}
    )
    alignment_matrix = list((match_report.get("capability_graph") or {}).get("alignment_matrix") or [])
    gap_analysis = dict(match_report.get("evidence_gap_analysis") or {})
    intelligence["hiring_manager_lens"] = build_hiring_manager_lens(
        intelligence["role_interpretation"], alignment_matrix, gap_analysis
    )
    intelligence["application_strategy"] = build_application_strategy(
        intelligence["role_interpretation"],
        intelligence["hiring_manager_lens"],
        match_report,
        [
            evidence_as_card(item)
            for item in selected_evidence(intelligence["role_evidence_selection"])
        ],
    )
    intelligence["hiring_manager_brief"] = build_hiring_manager_brief(
        match_report,
        intelligence["role_evidence_selection"],
        intelligence["hiring_manager_lens"],
        intelligence["application_strategy"],
    )
    computed_fingerprint = prospect_context_fingerprint(
        {
            "prospect_id": str(application.get("id") or prospect_id),
            "company": raw_company,
            "job_title": role_title,
            "raw_text": job_description,
            "source_url": source_url,
            "location": parsed.get("location") or application.get("location"),
            "work_arrangement": parsed.get("work_arrangement") or application.get("work_arrangement"),
            "salary_range": parsed.get("salary_range") or application.get("salary_range"),
            "salary_source": parsed.get("salary_source") or application.get("salary_source"),
            "posting_date": parsed.get("posting_date") or application.get("posting_date"),
        },
        {**intelligence, "match_report": match_report},
    )
    stored_fingerprint = str(application.get("context_fingerprint") or "").strip()
    stored_revision = int(application.get("prospect_revision") or 0)
    current_revision = (
        stored_revision + 1
        if stored_fingerprint and stored_fingerprint != computed_fingerprint
        else max(1, stored_revision)
    )
    context_stale = stored_fingerprint != computed_fingerprint
    manifest = application.get("package_manifest")
    if isinstance(manifest, dict):
        if str(manifest.get("prospect_id") or "") != str(
            application.get("id") or ""
        ):
            raise PackageGenerationError(
                CONTEXT_MISMATCH_MESSAGE,
                details={
                    "context_mismatch": True,
                    "mismatch_status": "confirmed",
                    "mismatch_reason": "manifest_prospect_id_conflict",
                    "selected_prospect_id": str(application.get("id") or prospect_id),
                    "package_context_prospect_id": str(
                        manifest.get("prospect_id") or ""
                    ),
                    "selected_prospect_revision": current_revision,
                    "package_context_revision": manifest.get("prospect_revision"),
                    "prior_context_source": "package_manifest",
                },
            )
        manifest_fingerprint = str(manifest.get("context_fingerprint") or "").strip()
        manifest_revision = int(manifest.get("prospect_revision") or 0)
        manifest_stale = bool(
            (manifest_fingerprint and manifest_fingerprint != computed_fingerprint)
            or (manifest_revision and manifest_revision != current_revision)
            or (
                bool(manifest.get("materials"))
                and (not manifest_fingerprint or not manifest_revision)
            )
        )
        selected_package_paths = (
            {}
            if context_stale or manifest_stale
            else dict(manifest.get("materials") or {})
        )
    else:
        manifest_fingerprint = ""
        manifest_revision = 0
        manifest_stale = False
        legacy_paths_stale = bool(application.get("material_paths"))
        selected_package_paths = {}
    if isinstance(manifest, dict):
        legacy_paths_stale = False
    return {
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
        "match_report": match_report,
        "role_evidence_selection": intelligence["role_evidence_selection"],
        "hiring_manager_brief": intelligence["hiring_manager_brief"],
        "evidence_selection_overrides": saved_evidence_overrides,
        "selected_package_paths": selected_package_paths,
        "context_fingerprint": computed_fingerprint,
        "prospect_revision": current_revision,
        "context_stale": context_stale or manifest_stale or legacy_paths_stale,
        "context_diagnostics": {
            "selected_prospect_id": str(application.get("id") or prospect_id),
            "selected_prospect_revision": current_revision,
            "selected_prospect_fingerprint": computed_fingerprint,
            "package_context_prospect_id": (
                str(manifest.get("prospect_id") or "")
                if isinstance(manifest, dict)
                else ""
            ),
            "package_context_revision": manifest_revision,
            "package_context_fingerprint": manifest_fingerprint,
            "prior_context_source": (
                "package_manifest"
                if isinstance(manifest, dict)
                else "tracker_material_paths"
                if legacy_paths_stale
                else "none"
            ),
            "mismatch_reason": (
                "unversioned_material_paths"
                if legacy_paths_stale
                else "package_manifest_stale"
                if manifest_stale
                else "saved_context_changed"
                if context_stale
                else ""
            ),
        },
    }


def refresh_saved_package_context(
    prospect_id: str,
    project_root: Optional[PathInput] = None,
    *,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Bind the selected tracker record to its latest saved job and clear old derivatives."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    current = context or build_package_context(
        prospect_id, load_application_tracker(root), root
    )
    tracker_id = str(current["prospect_id"])
    fingerprint = str(current["context_fingerprint"])
    updated = update_prospect(
        tracker_id,
        {
            "context_fingerprint": fingerprint,
            "material_paths": {},
        },
        root,
    )
    revision = int(updated.get("prospect_revision") or current["prospect_revision"])
    update_prospect(
        tracker_id,
        {
            "package_manifest": {
                "prospect_id": tracker_id,
                "prospect_revision": revision,
                "context_fingerprint": fingerprint,
                "materials": {},
            },
            "material_paths": {},
        },
        root,
    )
    refreshed = build_package_context(
        tracker_id, load_application_tracker(root), root
    )
    refreshed["context_diagnostics"]["automatic_refresh_attempted"] = True
    refreshed["context_diagnostics"]["refreshed_validation_passed"] = not refreshed[
        "context_stale"
    ]
    return refreshed


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


def generate_package(
    job_file_or_tracker_id: PathInput,
    project_root: Optional[PathInput] = None,
    override_closed: bool = False,
    public_transparency_requested: bool = False,
    _context_refresh_attempted: bool = False,
) -> Dict[str, Any]:
    """Generate all package materials and apply the safe Drafted-to-Reviewed transition."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    try:
        resolved = resolve_job_reference(job_file_or_tracker_id, root)
        selected_id = str(resolved["application"].get("id") or "")
        context = build_package_context(selected_id, load_application_tracker(root), root)
        automatic_refresh_attempted = bool(_context_refresh_attempted)
        if context.get("context_stale"):
            context = refresh_saved_package_context(selected_id, root, context=context)
            automatic_refresh_attempted = True
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
                "role_lens": intelligence.get("role_lens", {}).get("primary"),
                "secondary_role_lens": intelligence.get("role_lens", {}).get("secondary"),
                "role_lens_confidence": intelligence.get("role_lens", {}).get("confidence"),
                "requirement_map": intelligence.get("requirement_map", []),
                "role_interpretation": score.get("role_interpretation")
                or intelligence.get("role_interpretation", {}),
                "hiring_manager_lens": intelligence.get("hiring_manager_lens", {}),
                "application_strategy": intelligence.get("application_strategy", {}),
                "hiring_manager_brief": context.get("hiring_manager_brief", {}),
                "role_evidence_selection": context.get("role_evidence_selection", {}),
                "evidence_selection_overrides": context.get("evidence_selection_overrides", {}),
                "company_voice_profile": intelligence["profile_name"],
                "company_voice_source": intelligence["source"],
                "company_voice_label": intelligence.get("company_voice_label", intelligence["profile_name"]),
                "company_inference_confidence": intelligence.get("confidence_label", "Medium"),
                "salary_range": str(parsed.get("salary_range") or application.get("salary_range") or "Not disclosed"),
                "salary_source": str(parsed.get("salary_source") or application.get("salary_source") or ""),
                "posting_date": freshness.get("posting_date") or "",
                "posting_age_days": freshness.get("age_days"),
                "freshness": freshness["category"],
                "freshness_label": freshness["label"],
                "posting_status": freshness["posting_status"],
                "prospect_evidence_dirty": False,
                "role_analysis_dirty": False,
                "score_dirty": False,
                "application_strategy_dirty": False,
                "hiring_manager_brief_dirty": False,
                "package_dirty": True,
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
        opportunity = score_opportunity(parsed, score, intelligence, freshness)
        material_context = {
            "role_interpretation": intelligence.get("role_interpretation", {}),
            "hiring_manager_lens": intelligence.get("hiring_manager_lens", {}),
            "application_strategy": intelligence.get("application_strategy", {}),
            "role_evidence_selection": context.get("role_evidence_selection", {}),
            "evidence_selection_overrides": context.get("evidence_selection_overrides", {}),
            "public_transparency_requested": bool(public_transparency_requested),
        }
        resume = tailor_resume("executive_operations", job_reference, root, material_context)
        styled = _safe_docx_export(
            export_styled_docx, resume["output_path"], root, "Styled resume DOCX"
        )
        ats = _safe_docx_export(
            export_ats_docx, resume["output_path"], root, "ATS resume DOCX"
        )
        cover_letter = generate_cover_letter(job_reference, root, material_context)
        if isinstance(cover_letter.get("application_strategy"), dict):
            intelligence["application_strategy"] = cover_letter["application_strategy"]
            material_context["application_strategy"] = cover_letter["application_strategy"]
        if isinstance(cover_letter.get("hiring_manager_lens"), dict):
            intelligence["hiring_manager_lens"] = cover_letter["hiring_manager_lens"]
            material_context["hiring_manager_lens"] = cover_letter["hiring_manager_lens"]
        recruiter = generate_message("recruiter", job_reference, root, material_context)
        hiring_manager = generate_message("hiring-manager", job_reference, root, material_context)
        application_note = generate_application_note(job_reference, root, material_context)
        strategy_pack = generate_strategy_pack(job_reference, root, material_context)
        try:
            interview_prep = generate_interview_prep(job_reference, root, material_context)
        except Exception:
            interview_prep = {}

        quality = calculate_package_quality(score, resume, cover_letter, intelligence)
        role_lens_quality = {
            label: result.get("role_lens_quality")
            for label, result in {
                "resume": resume,
                "cover_letter": cover_letter,
                "recruiter_message": recruiter,
                "hiring_manager_message": hiring_manager,
                "application_note": application_note,
                "strategy_pack": strategy_pack,
                "interview_prep": interview_prep,
            }.items()
            if isinstance(result, dict) and result.get("role_lens_quality")
        }
        package_summary = save_package_summary(root, parsed, freshness, opportunity, quality)

        tracker_id = str(application["id"])
        if application.get("status") == "Drafted":
            application = update_status(tracker_id, "Reviewed", root)
        application = update_prospect(
            tracker_id,
            {
                "opportunity_score": opportunity["overall_score"],
                "apply_recommendation": opportunity["apply_recommendation"],
                "opportunity_dimensions": opportunity["dimensions"],
                "package_quality": quality,
                "hiring_manager_lens": intelligence.get("hiring_manager_lens", {}),
                "application_strategy": intelligence.get("application_strategy", {}),
                "hiring_manager_brief": context.get("hiring_manager_brief", {}),
            },
            root,
        )
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
        }
        for source_key, text_key in (
            ("resume_markdown", "resume_text"),
            ("strategy_pack", "strategy_pack_text"),
            ("interview_prep", "interview_prep_text"),
            ("package_summary", "package_summary_text"),
        ):
            companion = create_text_companion(outputs.get(source_key))
            if companion:
                outputs[text_key] = companion
        outputs = {key: value for key, value in outputs.items() if value}
        organized = organize_package_outputs(root, application, outputs)
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
        preferred_paths = preferred_material_paths(checklist)
        manifest = organized.get("manifest")
        if manifest:
            manifest["materials"] = preferred_paths
            manifest["context_fingerprint"] = context["context_fingerprint"]
            manifest["prospect_revision"] = context["prospect_revision"]
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
                    else {
                        "prospect_id": tracker_id,
                        "prospect_revision": context["prospect_revision"],
                        "context_fingerprint": context["context_fingerprint"],
                        "materials": preferred_paths,
                    }
                ),
                "package_dirty": False,
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
        if not locals().get("automatic_refresh_attempted", _context_refresh_attempted):
            refresh_saved_package_context(
                locals().get("selected_id") or str(job_file_or_tracker_id), root
            )
            recovered = generate_package(
                job_file_or_tracker_id,
                root,
                override_closed=override_closed,
                _context_refresh_attempted=True,
            )
            recovered["context_recovery"] = {
                "automatic_refresh_attempted": True,
                "refreshed_validation_passed": True,
            }
            return recovered
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
        raise PackageGenerationError(
            CONTEXT_MISMATCH_MESSAGE,
            checklist=checklist,
            details={
                "context_mismatch": True,
                "mismatch_status": "confirmed",
                "material_type": error.material_type,
                "violations": list(error.violations),
                "mismatch_reason": "foreign_material_context",
                "selected_prospect_id": locals().get("selected_id", ""),
                "selected_prospect_revision": (
                    locals().get("context") or {}
                ).get("prospect_revision"),
                "package_context_prospect_id": (
                    locals().get("context") or {}
                ).get("prospect_id"),
                "package_context_revision": (
                    locals().get("context") or {}
                ).get("prospect_revision"),
                "prior_context_source": (
                    ((locals().get("context") or {}).get("context_diagnostics") or {}).get(
                        "prior_context_source"
                    )
                ),
                "conflicting_indicators": list(error.violations),
                "automatic_refresh_attempted": True,
                "refreshed_validation_passed": False,
                **error.diagnostics,
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
        "match_score": score.get("match_score"),
        "match_band": score.get("match_band"),
        "match_tier": score.get("match_tier"),
        "match_summary": score.get("match_summary"),
        "match_strengths": score.get("match_strengths", []),
        "match_gaps": score.get("match_gaps", []),
        "recommended_action": score.get("recommended_action"),
        "confidence": score.get("confidence"),
        "data_confidence": score.get("data_confidence") or score.get("confidence"),
        "match_verification_notes": score.get("match_verification_notes", []),
        "company_category": intelligence["company_category"],
        "role_family": intelligence["role_family"],
        "role_lens": intelligence.get("role_lens", {}),
        "requirement_map": intelligence.get("requirement_map", []),
        "company_voice_profile": intelligence["profile_name"],
        "company_voice_source": intelligence["source"],
        "company_voice_label": intelligence.get("company_voice_label", intelligence["profile_name"]),
        "freshness": freshness,
        "opportunity": opportunity,
        "package_quality": quality,
        "role_lens_quality": role_lens_quality,
        "material_errors": material_errors,
        "outputs": outputs,
        "package_checklist": checklist,
        "prospect_revision": context["prospect_revision"],
        "context_fingerprint": context["context_fingerprint"],
        "context_diagnostics": {
            **context.get("context_diagnostics", {}),
            "automatic_refresh_attempted": locals().get("automatic_refresh_attempted", False),
            "refreshed_validation_passed": True,
        },
    }
