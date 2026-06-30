"""Load, update, and validate the Career Catalyst application tracker."""

from datetime import date
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml


PathInput = Union[str, Path]
TRACKER_PATH = "data/application_tracker.yml"
REQUIRED_FIELDS = (
    "id",
    "company",
    "role",
    "status",
    "priority",
    "show_on_dashboard",
)
VALID_STATUSES = (
    "Drafted",
    "Reviewed",
    "Applied",
    "Follow-up",
    "Interviewing",
    "Paused",
    "Rejected",
    "Invalid",
    "Archived",
)
ACTIVE_STATUSES = {"Applied", "Follow-up", "Interviewing"}
DRAFT_STATUSES = {"Drafted", "Reviewed", "Paused"}
HIDDEN_STATUSES = {"Rejected", "Invalid", "Archived"}
INTAKE_PROTECTED_STATUSES = {
    "Applied",
    "Follow-up",
    "Interviewing",
    "Rejected",
    "Invalid",
    "Archived",
}
OPTIONAL_INTELLIGENCE_FIELDS = (
    "company_category",
    "role_family",
    "company_voice_profile",
    "company_voice_source",
)


class TrackerValidationError(Exception):
    """Raised when application tracker data is missing or invalid."""


class TrackerUpdateError(TrackerValidationError):
    """Raised when a requested tracker mutation cannot be completed."""


def normalize_tracker_value(value: Any) -> str:
    """Normalize tracker matching text across case, punctuation, and whitespace."""
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def make_tracker_id(company: Any, role: Any) -> str:
    """Build a stable, readable tracker id from company and role."""
    normalized = normalize_tracker_value(f"{company} {role}").replace(" ", "_")
    if not normalized:
        raise TrackerUpdateError("A tracker id requires a company and role title.")
    return normalized


def tracker_company_keys(application: Dict[str, Any]) -> set[str]:
    values = [application.get("company", "")]
    aliases = application.get("company_aliases", [])
    if isinstance(aliases, list):
        values.extend(aliases)
    return {normalize_tracker_value(value) for value in values if value}


def tracker_role_keys(application: Dict[str, Any]) -> set[str]:
    values = [application.get("role", "")]
    aliases = application.get("role_aliases", [])
    if isinstance(aliases, list):
        values.extend(aliases)
    return {normalize_tracker_value(value) for value in values if value}


def load_application_tracker(project_root: Optional[PathInput] = None) -> List[Dict[str, Any]]:
    """Load the normalized tracker schema from the project data directory."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    tracker_path = root / TRACKER_PATH
    if not tracker_path.is_file():
        raise TrackerValidationError(f"Application tracker file not found: {TRACKER_PATH}")

    try:
        loaded = yaml.safe_load(tracker_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise TrackerValidationError(
            f"Malformed YAML in {TRACKER_PATH}: {error}"
        ) from error
    except (OSError, UnicodeError) as error:
        raise TrackerValidationError(
            f"Unable to read application tracker {TRACKER_PATH}: {error}"
        ) from error

    if not isinstance(loaded, dict) or not isinstance(loaded.get("applications"), list):
        raise TrackerValidationError(
            f"Application tracker must contain a top-level applications list: {TRACKER_PATH}"
        )
    return loaded["applications"]


def load_tracker(project_root: Optional[PathInput] = None) -> List[Dict[str, Any]]:
    """Short alias used by the local UI and CLI workflows."""
    return load_application_tracker(project_root)


def save_application_tracker(
    applications: List[Dict[str, Any]],
    project_root: Optional[PathInput] = None,
) -> Path:
    """Validate and save tracker entries without reordering their fields."""
    report = validate_tracker_entries(applications)
    if report["errors"]:
        raise TrackerValidationError(" ".join(report["errors"]))

    root = Path(project_root) if project_root is not None else Path.cwd()
    tracker_path = root / TRACKER_PATH
    tracker_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        tracker_path.write_text(
            yaml.safe_dump(
                {"applications": applications},
                sort_keys=False,
                allow_unicode=True,
                width=1000,
            ),
            encoding="utf-8",
        )
    except OSError as error:
        raise TrackerUpdateError(
            f"Unable to save application tracker {TRACKER_PATH}: {error}"
        ) from error
    return tracker_path


def save_tracker(
    applications: List[Dict[str, Any]],
    project_root: Optional[PathInput] = None,
) -> Path:
    """Short alias used by the local UI and CLI workflows."""
    return save_application_tracker(applications, project_root)


def _clean_updates(values: Dict[str, Any]) -> Dict[str, Any]:
    """Drop absent values while retaining meaningful false values."""
    return {
        key: value
        for key, value in values.items()
        if value is not None and (not isinstance(value, str) or value.strip())
    }


def _explicit_updates(values: Dict[str, Any]) -> Dict[str, Any]:
    """Retain explicit empty strings so editable UI fields can be cleared."""
    return {key: value for key, value in values.items() if value is not None}


def add_prospect(
    prospect: Dict[str, Any],
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Add a prospect or safely enrich its existing tracker record."""
    company = str(prospect.get("company") or "").strip()
    role = str(prospect.get("role") or prospect.get("job_title") or "").strip()
    if not company or not role:
        raise TrackerUpdateError("A prospect requires both company and role title.")

    tracker_id = str(prospect.get("id") or make_tracker_id(company, role)).strip()
    incoming = _clean_updates(dict(prospect))
    incoming["id"] = tracker_id
    incoming["company"] = company
    incoming["role"] = role
    incoming.pop("job_title", None)

    applications = load_application_tracker(project_root)
    existing = next(
        (application for application in applications if application.get("id") == tracker_id),
        None,
    )
    created = existing is None
    if existing is None:
        entry: Dict[str, Any] = {
            "id": tracker_id,
            "company": company,
            "company_aliases": [],
            "role": role,
            "role_aliases": [],
            "status": str(incoming.get("status") or "Drafted"),
            "priority": str(incoming.get("priority") or "Medium"),
            "source": str(incoming.get("source") or "Official career page"),
            "notes": str(incoming.get("notes") or ""),
            "next_action": str(incoming.get("next_action") or ""),
            "show_on_dashboard": bool(incoming.get("show_on_dashboard", True)),
        }
        entry.update(incoming)
        applications.append(entry)
    else:
        entry = existing
        original_status = str(existing.get("status") or "Drafted")
        entry.update(incoming)
        # Intake must never demote an application that has progressed beyond drafting.
        if original_status in INTAKE_PROTECTED_STATUSES or (
            original_status != "Drafted" and incoming.get("status") == "Drafted"
        ):
            entry["status"] = original_status
        entry.setdefault("company_aliases", [])
        entry.setdefault("role_aliases", [])
        entry.setdefault("show_on_dashboard", True)

    save_application_tracker(applications, project_root)
    return {"tracker_id": tracker_id, "application": dict(entry), "created": created}


def update_prospect(
    tracker_id: str,
    updates: Dict[str, Any],
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Update selected fields while preserving every unspecified tracker value."""
    applications = load_application_tracker(project_root)
    entry = next(
        (application for application in applications if application.get("id") == tracker_id),
        None,
    )
    if entry is None:
        raise TrackerUpdateError(f"Tracker entry not found: {tracker_id}")

    cleaned = _explicit_updates(updates)
    cleaned.pop("id", None)
    entry.update(cleaned)
    save_application_tracker(applications, project_root)
    return dict(entry)


def update_status(
    tracker_id: str,
    status: str,
    project_root: Optional[PathInput] = None,
    **updates: Any,
) -> Dict[str, Any]:
    """Set application status and stamp the first Applied date when needed."""
    if status not in VALID_STATUSES:
        raise TrackerUpdateError(
            f"Unsupported status '{status}'. Valid statuses: {', '.join(VALID_STATUSES)}."
        )

    applications = load_application_tracker(project_root)
    entry = next(
        (application for application in applications if application.get("id") == tracker_id),
        None,
    )
    if entry is None:
        raise TrackerUpdateError(f"Tracker entry not found: {tracker_id}")

    entry["status"] = status
    entry.update(_explicit_updates(updates))
    if status == "Applied" and not entry.get("submitted_date"):
        entry["submitted_date"] = date.today().isoformat()
    save_application_tracker(applications, project_root)
    return dict(entry)


def hide_role(
    tracker_id: str,
    reason: str,
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Mark a role Invalid, hide it, and retain any existing notes."""
    applications = load_application_tracker(project_root)
    entry = next(
        (application for application in applications if application.get("id") == tracker_id),
        None,
    )
    if entry is None:
        raise TrackerUpdateError(f"Tracker entry not found: {tracker_id}")

    existing_notes = str(entry.get("notes") or "").strip()
    clean_reason = reason.strip()
    if clean_reason and clean_reason not in existing_notes:
        entry["notes"] = " ".join(value for value in (existing_notes, clean_reason) if value)
    entry["status"] = "Invalid"
    entry["show_on_dashboard"] = False
    save_application_tracker(applications, project_root)
    return dict(entry)


def validate_tracker_entries(
    applications: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Validate tracker fields, duplicate ids, and active duplicate records."""
    errors: List[str] = []
    warnings: List[str] = []
    seen_ids: Dict[str, int] = {}
    active_pairs: Dict[Tuple[str, str], str] = {}
    status_counts = Counter()

    for index, application in enumerate(applications, start=1):
        label = f"Tracker entry {index}"
        if not isinstance(application, dict):
            errors.append(f"{label} must be a dictionary.")
            continue

        missing = [
            field
            for field in REQUIRED_FIELDS
            if field not in application
            or (field != "show_on_dashboard" and not application.get(field))
        ]
        if missing:
            errors.append(f"{label} is missing required fields: {', '.join(missing)}.")
            continue

        tracker_id = str(application["id"])
        if tracker_id in seen_ids:
            errors.append(
                f"Duplicate tracker id '{tracker_id}' in entries "
                f"{seen_ids[tracker_id]} and {index}."
            )
        else:
            seen_ids[tracker_id] = index

        status = str(application["status"])
        if status not in VALID_STATUSES:
            errors.append(
                f"{label} has unsupported status '{status}'. "
                f"Valid statuses: {', '.join(VALID_STATUSES)}."
            )
        else:
            status_counts[status] += 1

        if not isinstance(application["show_on_dashboard"], bool):
            errors.append(f"{label} field show_on_dashboard must be true or false.")

        for aliases_field in ("company_aliases", "role_aliases"):
            aliases = application.get(aliases_field, [])
            if not isinstance(aliases, list) or not all(
                isinstance(alias, str) for alias in aliases
            ):
                errors.append(f"{label} field {aliases_field} must be a list of strings.")

        for metadata_field in OPTIONAL_INTELLIGENCE_FIELDS:
            value = application.get(metadata_field)
            if value is not None and not isinstance(value, str):
                errors.append(f"{label} field {metadata_field} must be a string when present.")

        if status in ACTIVE_STATUSES and application.get("show_on_dashboard") is True:
            pair = (
                normalize_tracker_value(application["company"]),
                normalize_tracker_value(application["role"]),
            )
            previous_id = active_pairs.get(pair)
            if previous_id:
                warnings.append(
                    f"Active tracker entries '{previous_id}' and '{tracker_id}' "
                    "have the same normalized company and role."
                )
            else:
                active_pairs[pair] = tracker_id

    return {
        "applications": applications,
        "errors": errors,
        "warnings": warnings,
        "status_counts": {
            status: status_counts.get(status, 0) for status in VALID_STATUSES
        },
    }


def validate_application_tracker(
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Load and validate the application tracker, raising on invalid data."""
    report = validate_tracker_entries(load_application_tracker(project_root))
    if report["errors"]:
        raise TrackerValidationError(" ".join(report["errors"]))
    return report
