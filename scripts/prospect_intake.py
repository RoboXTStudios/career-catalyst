"""Create job files and tracker entries from local UI or CLI intake."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    from .application_tracker import add_prospect, make_tracker_id
    from .job_importer import (
        MINIMUM_DESCRIPTION_LENGTH,
        JobImportError,
        create_job_markdown,
        validate_official_url,
    )
    from .parse_job import JobParseError, parse_job_description
except ImportError:
    from application_tracker import add_prospect, make_tracker_id
    from job_importer import (
        MINIMUM_DESCRIPTION_LENGTH,
        JobImportError,
        create_job_markdown,
        validate_official_url,
    )
    from parse_job import JobParseError, parse_job_description


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


def create_prospect(
    job_data: Dict[str, Any],
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Create a clean job file and add or update its tracker entry."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    company = str(job_data.get("company") or "").strip()
    role = str(job_data.get("role") or job_data.get("job_title") or "").strip()
    description = str(job_data.get("job_description") or "").strip()
    try:
        official_url = validate_official_url(str(job_data.get("official_url") or ""))
    except JobImportError as error:
        raise ProspectIntakeError(str(error)) from error
    if not company or not role:
        raise ProspectIntakeError("Company and role title are required.")
    if len(description) < MINIMUM_DESCRIPTION_LENGTH:
        raise ProspectIntakeError(
            "Paste the job description text before saving (at least 80 characters)."
        )

    tracker_id = str(job_data.get("tracker_id") or make_tracker_id(company, role))
    normalized = dict(job_data)
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
            "salary_range": str(job_data.get("salary_range") or "").strip(),
            "work_arrangement": str(job_data.get("work_arrangement") or "").strip(),
            "notes": str(job_data.get("notes") or "").strip(),
            "next_action": str(job_data.get("next_action") or "").strip(),
            "show_on_dashboard": bool(job_data.get("show_on_dashboard", True)),
            "job_file": _project_relative(job_path, root),
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
            "salary_range": str(parsed.get("salary_range") or ""),
            "job_file": _project_relative(resolved, root),
            "show_on_dashboard": True,
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
