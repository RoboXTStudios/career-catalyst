"""Create job files and tracker entries from local UI or CLI intake."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    from .application_tracker import add_prospect, make_tracker_id
    from .dynamic_role_intelligence import get_effective_voice_profile
    from .job_importer import (
        MINIMUM_DESCRIPTION_LENGTH,
        JobImportError,
        create_job_markdown,
        import_job_from_url,
        validate_official_url,
    )
    from .job_freshness import detect_job_freshness
    from .parse_job import JobParseError, extract_metadata, parse_job_description
except ImportError:
    from application_tracker import add_prospect, make_tracker_id
    from dynamic_role_intelligence import get_effective_voice_profile
    from job_importer import (
        MINIMUM_DESCRIPTION_LENGTH,
        JobImportError,
        create_job_markdown,
        import_job_from_url,
        validate_official_url,
    )
    from job_freshness import detect_job_freshness
    from parse_job import JobParseError, extract_metadata, parse_job_description


PathInput = Union[str, Path]


class ProspectIntakeError(Exception):
    """Raised when prospect intake is missing required local data."""


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").lower()).strip("_")


def _project_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _job_filename(role: str, company: str) -> str:
    clean = "_".join(value for value in (_slug(role), _slug(company)) if value)
    if not clean:
        raise ProspectIntakeError("A company and role title are required to name the job file.")
    return f"{clean}.md"


def _infer_pasted_identity(description: str) -> tuple[str, str]:
    """Infer common title/company layouts when a pasted posting has no labels."""
    metadata = extract_metadata(description)
    role = str(metadata.get("job_title") or "").strip()
    company = str(metadata.get("company") or "").strip()
    if role and company:
        return company, role

    lines = [
        re.sub(r"^[#*\-\s]+", "", line).strip()
        for line in description.splitlines()
        if line.strip()
    ]
    if lines:
        at_match = re.match(r"^(.{3,100}?)\s+at\s+(.{2,80})$", lines[0], re.I)
        if at_match:
            role = role or at_match.group(1).strip()
            company = company or at_match.group(2).strip()
    title_signals = (
        "director", "manager", "lead", "head", "president", "officer",
        "strategist", "operations", "producer", "executive",
    )
    if not role and lines and len(lines[0]) <= 100 and any(
        signal in lines[0].lower() for signal in title_signals
    ):
        role = lines[0]
    if not company and role and len(lines) > 1:
        candidate = lines[1]
        if len(candidate) <= 80 and not re.search(r"[.!?]$|\b(?:about|description|responsibilities)\b", candidate, re.I):
            company = re.sub(r"^(?:company|organization)\s*:\s*", "", candidate, flags=re.I)
    return company, role


def create_prospect(
    job_data: Dict[str, Any],
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Create a clean job file and add or update its tracker entry."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    normalized_input = dict(job_data)
    company = str(normalized_input.get("company") or "").strip()
    role = str(normalized_input.get("role") or normalized_input.get("job_title") or "").strip()
    description = str(normalized_input.get("job_description") or "").strip()
    raw_url = str(normalized_input.get("official_url") or "").strip()
    if raw_url and (not company or not role or len(description) < MINIMUM_DESCRIPTION_LENGTH):
        try:
            imported = import_job_from_url(raw_url)
        except JobImportError as error:
            if len(description) < MINIMUM_DESCRIPTION_LENGTH:
                raise ProspectIntakeError(str(error)) from error
        else:
            for key, value in imported.items():
                if value and not normalized_input.get(key):
                    normalized_input[key] = value
            company = str(normalized_input.get("company") or "").strip()
            role = str(normalized_input.get("role") or normalized_input.get("job_title") or "").strip()
            description = str(normalized_input.get("job_description") or "").strip()

    if description and (not company or not role):
        metadata = extract_metadata(description)
        inferred_company, inferred_role = _infer_pasted_identity(description)
        company = company or inferred_company
        role = role or inferred_role
        normalized_input.setdefault("posting_date", metadata.get("posting_date") or "")
        normalized_input.setdefault("location", metadata.get("location") or "")
        normalized_input.setdefault("salary_range", metadata.get("salary_range") or "")
    try:
        official_url = validate_official_url(raw_url) if raw_url else ""
    except JobImportError as error:
        raise ProspectIntakeError(str(error)) from error
    if not company or not role:
        raise ProspectIntakeError("Company and role title are required.")
    if len(description) < MINIMUM_DESCRIPTION_LENGTH:
        raise ProspectIntakeError(
            "Paste the job description text before saving (at least 80 characters)."
        )

    tracker_id = str(normalized_input.get("tracker_id") or make_tracker_id(company, role))
    normalized = dict(normalized_input)
    normalized.update(
        {
            "tracker_id": tracker_id,
            "company": company,
            "job_title": role,
            "job_description": description,
            "official_url": official_url,
        }
    )
    try:
        markdown = create_job_markdown(normalized)
    except Exception as error:
        raise ProspectIntakeError(str(error)) from error

    job_directory = root / "jobs"
    job_directory.mkdir(parents=True, exist_ok=True)
    job_path = job_directory / _job_filename(role, company)
    try:
        job_path.write_text(markdown, encoding="utf-8")
    except OSError as error:
        raise ProspectIntakeError(f"Unable to save job file {job_path}: {error}") from error

    intelligence = get_effective_voice_profile(
        company_name=company,
        job_title=role,
        job_description=description,
        source_url=official_url,
    )
    freshness = detect_job_freshness(markdown)

    tracker_result = add_prospect(
        {
            "id": tracker_id,
            "company": company,
            "role": role,
            "status": str(job_data.get("status") or "Drafted"),
            "priority": str(job_data.get("priority") or "Medium"),
            "source": str(job_data.get("source") or "Official career page"),
            "official_url": official_url,
            "location": str(job_data.get("location") or "").strip(),
            "salary_range": str(normalized_input.get("salary_range") or "Not disclosed").strip(),
            "work_arrangement": str(job_data.get("work_arrangement") or "").strip(),
            "notes": str(job_data.get("notes") or "").strip(),
            "next_action": str(job_data.get("next_action") or "").strip(),
            "show_on_dashboard": bool(job_data.get("show_on_dashboard", True)),
            "job_file": _project_relative(job_path, root),
            "company_category": intelligence["company_category"],
            "role_family": intelligence["role_family"],
            "company_voice_profile": intelligence["profile_name"],
            "company_voice_source": intelligence["source"],
            "company_voice_label": intelligence.get("company_voice_label", intelligence["profile_name"]),
            "company_inference_confidence": intelligence.get("confidence_label", "Medium"),
            "posting_date": freshness.get("posting_date") or "",
            "posting_age_days": freshness.get("age_days"),
            "freshness": freshness["category"],
            "freshness_label": freshness["label"],
            "posting_status": freshness["posting_status"],
        },
        root,
    )
    return {
        "tracker_id": tracker_id,
        "job_file_path": str(job_path),
        "relative_job_file_path": _project_relative(job_path, root),
        "tracker_created": tracker_result["created"],
        "application": tracker_result["application"],
    }


def add_prospect_from_job_file(
    job_file_path: PathInput,
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Register an existing local job file without duplicating its tracker record."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    path = Path(job_file_path)
    resolved = path if path.is_absolute() else root / path
    try:
        parsed = parse_job_description(resolved)
    except JobParseError as error:
        raise ProspectIntakeError(str(error)) from error

    company = str(parsed.get("company") or "").strip()
    role = str(parsed.get("job_title") or "").strip()
    if not company or not role:
        raise ProspectIntakeError(
            "The job file needs a # role heading and a Company: metadata line."
        )
    raw_text = str(parsed.get("raw_text") or "")
    tracker_match = re.search(
        r"^\s*Tracker ID\s*:\s*(.+?)\s*$", raw_text, flags=re.I | re.M
    )
    source_match = re.search(
        r"^\s*(?:Official source|Source)\s*:\s*(.+?)\s*$", raw_text, flags=re.I | re.M
    )
    tracker_id = tracker_match.group(1).strip() if tracker_match else make_tracker_id(company, role)
    intelligence = get_effective_voice_profile(
        company_name=company,
        job_title=role,
        job_description=raw_text,
        source_url=str(parsed.get("source_url") or ""),
    )
    freshness = detect_job_freshness(raw_text)
    tracker_result = add_prospect(
        {
            "id": tracker_id,
            "company": company,
            "role": role,
            "status": "Drafted",
            "priority": "Medium",
            "source": source_match.group(1).strip() if source_match else "Official career page",
            "official_url": str(parsed.get("source_url") or ""),
            "location": str(parsed.get("location") or ""),
            "salary_range": str(parsed.get("salary_range") or "Not disclosed"),
            "job_file": _project_relative(resolved, root),
            "show_on_dashboard": True,
            "company_category": intelligence["company_category"],
            "role_family": intelligence["role_family"],
            "company_voice_profile": intelligence["profile_name"],
            "company_voice_source": intelligence["source"],
            "company_voice_label": intelligence.get("company_voice_label", intelligence["profile_name"]),
            "company_inference_confidence": intelligence.get("confidence_label", "Medium"),
            "posting_date": freshness.get("posting_date") or "",
            "posting_age_days": freshness.get("age_days"),
            "freshness": freshness["category"],
            "freshness_label": freshness["label"],
            "posting_status": freshness["posting_status"],
        },
        root,
    )
    return {
        "tracker_id": tracker_id,
        "job_file_path": str(resolved),
        "relative_job_file_path": _project_relative(resolved, root),
        "tracker_created": tracker_result["created"],
        "application": tracker_result["application"],
    }
