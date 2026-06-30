"""Orchestrate a complete Career Catalyst application package."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    from .application_tracker import (
        TrackerValidationError,
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
    from .parse_job import JobParseError, parse_job_description
    from .prospect_intake import add_prospect_from_job_file
    from .score_match import persisted_match_fields, score_job_match
    from .tailor_resume import tailor_resume
except ImportError:
    from application_tracker import (
        TrackerValidationError,
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
    from parse_job import JobParseError, parse_job_description
    from prospect_intake import add_prospect_from_job_file
    from score_match import persisted_match_fields, score_job_match
    from tailor_resume import tailor_resume


PathInput = Union[str, Path]


class PackageGenerationError(Exception):
    """Raised when a job reference or generation step cannot be completed."""


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
        if (
            normalize_tracker_value(parsed.get("company")) == company_key
            and normalize_tracker_value(parsed.get("job_title")) == role_key
        ):
            matches.append(path)
    return matches[0] if len(matches) == 1 else None


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
        company_key = normalize_tracker_value(parsed.get("company"))
        role_key = normalize_tracker_value(parsed.get("job_title"))
        application = next(
            (
                item
                for item in applications
                if normalize_tracker_value(item.get("company")) == company_key
                and normalize_tracker_value(item.get("role")) == role_key
            ),
            None,
        )
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


def generate_package(
    job_file_or_tracker_id: PathInput,
    project_root: Optional[PathInput] = None,
    generate_followups_too: Optional[bool] = None,
    override_closed: bool = False,
) -> Dict[str, Any]:
    """Generate all package materials and apply the safe Drafted-to-Reviewed transition."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    try:
        resolved = resolve_job_reference(job_file_or_tracker_id, root)
        job_path = Path(resolved["job_path"])
        application = resolved["application"]
        job_reference = str(job_path.relative_to(root)) if job_path.is_relative_to(root) else str(job_path)

        parsed = parse_job_description(job_path)
        intelligence = get_effective_voice_profile(
            company_name=str(parsed.get("company") or application.get("company") or ""),
            job_title=str(parsed.get("job_title") or application.get("role") or ""),
            job_description=str(parsed.get("raw_text") or ""),
            source_url=str(parsed.get("source_url") or application.get("official_url") or ""),
        )
        freshness = detect_job_freshness(str(parsed.get("raw_text") or ""))
        score = score_job_match(job_reference, root)
        application = update_prospect(
            str(application["id"]),
            {
                "company_category": intelligence["company_category"],
                "role_family": intelligence["role_family"],
                "company_voice_profile": intelligence["profile_name"],
                "company_voice_source": intelligence["source"],
                "company_voice_label": intelligence.get("company_voice_label", intelligence["profile_name"]),
                "company_inference_confidence": intelligence.get("confidence_label", "Medium"),
                "salary_range": str(parsed.get("salary_range") or application.get("salary_range") or "Not disclosed"),
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
            True
            if generate_followups_too is None
            else bool(generate_followups_too)
        )
        opportunity = score_opportunity(parsed, score, intelligence, freshness)
        resume = tailor_resume("executive_operations", job_reference, root)
        styled = export_styled_docx(resume["output_path"], root)
        ats = export_ats_docx(resume["output_path"], root)
        cover_letter = generate_cover_letter(job_reference, root)
        recruiter = generate_message("recruiter", job_reference, root)
        hiring_manager = generate_message("hiring-manager", job_reference, root)
        application_note = generate_application_note(job_reference, root)
        strategy_pack = generate_strategy_pack(job_reference, root)
        try:
            interview_prep = generate_interview_prep(job_reference, root)
        except Exception:
            interview_prep = {}

        quality = calculate_package_quality(score, resume, cover_letter, intelligence)
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
                followup_result = generate_followups(tracker_id, root)
                followup_outputs = dict(followup_result.get("outputs", {}))
            except Exception as error:
                # The core package remains useful if optional networking materials fail.
                followup_error = str(error)
        dashboard = generate_dashboard(root)
    except PackageGenerationError:
        raise
    except (OSError, TrackerValidationError, ValueError) as error:
        raise PackageGenerationError(f"Could not generate package: {error}") from error
    except Exception as error:
        # Existing generators expose several focused exception types. Preserve their useful text.
        raise PackageGenerationError(f"Could not generate package: {error}") from error

    outputs = {
        "job_file": str(job_path),
        "resume_markdown": _output_path(resume),
        "styled_docx": _output_path(styled),
        "ats_docx": _output_path(ats),
        "cover_letter": _output_path(cover_letter),
        "cover_letter_text": cover_letter.get("txt_output_path"),
        "recruiter_message": _output_path(recruiter),
        "hiring_manager_message": _output_path(hiring_manager),
        "application_note": _output_path(application_note),
        "strategy_pack": _output_path(strategy_pack),
        "interview_prep": _output_path(interview_prep),
        "package_summary": _output_path(package_summary),
        **followup_outputs,
        "dashboard": _output_path(dashboard),
    }
    return {
        "tracker_id": tracker_id,
        "status": application.get("status"),
        "job_title": parsed.get("job_title"),
        "company": parsed.get("company"),
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
        "followup_error": followup_error,
        "outputs": {key: value for key, value in outputs.items() if value},
    }
