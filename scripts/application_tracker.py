"""Load and validate the Career Catalyst application tracker."""

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


class TrackerValidationError(Exception):
    """Raised when application tracker data is missing or invalid."""


def normalize_tracker_value(value: Any) -> str:
    """Normalize tracker matching text across case, punctuation, and whitespace."""
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


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
