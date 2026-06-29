"""Orchestrate a complete Career Catalyst application package."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    from .application_tracker import (
        TrackerValidationError,
        load_application_tracker,
        normalize_tracker_value,
        update_status,
    )
    from .export_docx import export_ats_docx, export_styled_docx
    from .generate_application_note import generate_application_note
    from .generate_cover_letter import generate_cover_letter
    from .generate_dashboard import generate_dashboard
    from .generate_messages import generate_message
    from .generate_strategy_pack import generate_strategy_pack
    from .parse_job import JobParseError, parse_job_description
    from .prospect_intake import add_prospect_from_job_file
    from .score_match import score_job_match
    from .tailor_resume import tailor_resume
except ImportError:
    from application_tracker import (
        TrackerValidationError,
        load_application_tracker,
        normalize_tracker_value,
        update_status,
    )
    from export_docx import export_ats_docx, export_styled_docx
    from generate_application_note import generate_application_note
    from generate_cover_letter import generate_cover_letter
    from generate_dashboard import generate_dashboard
    from generate_messages import generate_message
    from generate_strategy_pack import generate_strategy_pack
    from parse_job import JobParseError, parse_job_description
    from prospect_intake import add_prospect_from_job_file
    from score_match import score_job_match
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
) -> Dict[str, Any]:
    """Generate all package materials and apply the safe Drafted-to-Reviewed transition."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    try:
        resolved = resolve_job_reference(job_file_or_tracker_id, root)
        job_path = Path(resolved["job_path"])
        application = resolved["application"]
        job_reference = str(job_path.relative_to(root)) if job_path.is_relative_to(root) else str(job_path)

        parsed = parse_job_description(job_path)
        score = score_job_match(job_reference, root)
        resume = tailor_resume("executive_operations", job_reference, root)
        styled = export_styled_docx(resume["output_path"], root)
        ats = export_ats_docx(resume["output_path"], root)
        cover_letter = generate_cover_letter(job_reference, root)
        recruiter = generate_message("recruiter", job_reference, root)
        hiring_manager = generate_message("hiring-manager", job_reference, root)
        application_note = generate_application_note(job_reference, root)
        strategy_pack = generate_strategy_pack(job_reference, root)

        tracker_id = str(application["id"])
        if application.get("status") == "Drafted":
            application = update_status(tracker_id, "Reviewed", root)
        dashboard = generate_dashboard(root)
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
        "dashboard": _output_path(dashboard),
    }
    return {
        "tracker_id": tracker_id,
        "status": application.get("status"),
        "job_title": parsed.get("job_title"),
        "company": parsed.get("company"),
        "match_score": score.get("match_score"),
        "match_band": score.get("match_band"),
        "outputs": {key: value for key, value in outputs.items() if value},
    }
