"""Load, update, and validate the Career Catalyst application tracker."""

from datetime import date, datetime
import re
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml

try:
    from .filename_utils import canonical_employer_name
except ImportError:
    from filename_utils import canonical_employer_name


PathInput = Union[str, Path]
TRACKER_PATH = "data/application_tracker.yml"
_SAFE_YAML_LOADER = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
_TRACKER_READ_CACHE: Dict[
    Path, Tuple[Tuple[int, int, int], List[Dict[str, Any]]]
] = {}
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
    "Applied",
    "Under Consideration",
    "Interviewing",
    "Offer",
    "Rejected",
    "Withdrawn / Closed",
)
LEGACY_STATUS_FIELDS = (
    "application_status",
    "submitted_status",
    "workflow_status",
    "dashboard_status",
    "stage",
)
STATUS_ALIASES = {
    "active": "Drafted",
    "in progress": "Drafted",
    "open": "Drafted",
    "reviewed": "Drafted",
    "review first": "Drafted",
    "manually reviewed": "Drafted",
    "verified": "Drafted",
    "paused": "Withdrawn / Closed",
    "submitted": "Applied",
    "application submitted": "Applied",
    "follow up": "Applied",
    "followup": "Applied",
    "follow up needed": "Applied",
    "follow up sent": "Under Consideration",
    "due now": "Under Consideration",
    "recruiter contacted": "Under Consideration",
    "hiring manager contacted": "Under Consideration",
    "under review": "Under Consideration",
    "on hold": "Under Consideration",
    "passed": "Withdrawn / Closed",
    "pass": "Withdrawn / Closed",
    "declined": "Withdrawn / Closed",
    "do not pursue": "Withdrawn / Closed",
    "hidden": "Withdrawn / Closed",
    "invalid": "Withdrawn / Closed",
    "invalid hidden": "Withdrawn / Closed",
    "archived": "Withdrawn / Closed",
    "closed": "Withdrawn / Closed",
    "stale closed risk": "Withdrawn / Closed",
}
ACTIVE_STATUSES = {"Applied", "Under Consideration", "Interviewing", "Offer"}
DRAFT_STATUSES = {"Drafted"}
HIDDEN_STATUSES = {"Rejected", "Withdrawn / Closed"}
INTAKE_PROTECTED_STATUSES = {
    "Active",
    "Applied",
    "Follow-up",
    "Interviewing",
    "Pass",
    "Rejected",
    "Invalid",
    "Invalid/Hidden",
    "Archived",
}
OPTIONAL_INTELLIGENCE_FIELDS = (
    "company_category",
    "role_family",
    "company_voice_profile",
    "company_voice_source",
)
VALID_MATCH_TIERS = (
    "Strong Match",
    "Good Match",
    "Stretch Match",
    "Weak Match",
    "Pass",
)
VALID_MATCH_ACTIONS = ("Generate Package", "Review First", "Pass")
VALID_MATCH_CONFIDENCE = ("Low", "Medium", "High")


class TrackerValidationError(Exception):
    """Raised when application tracker data is missing or invalid."""


class TrackerUpdateError(TrackerValidationError):
    """Raised when a requested tracker mutation cannot be completed."""


def normalize_tracker_value(value: Any) -> str:
    """Normalize tracker matching text across case, punctuation, and whitespace."""
    text = str(value or "").lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_status(value: Any) -> str:
    """Return a canonical status while safely preserving unknown legacy values."""
    clean = str(value or "").strip()
    if not clean:
        return "Drafted"
    normalized = normalize_tracker_value(clean)
    if normalized in STATUS_ALIASES:
        return STATUS_ALIASES[normalized]
    canonical = {
        normalize_tracker_value(status): status for status in VALID_STATUSES
    }
    return canonical.get(normalized, clean)


def get_record_status(record: Dict[str, Any]) -> str:
    """Read the primary status without mutating or discarding legacy data.

    Older ``Active`` and ``Reviewed`` records are promoted to ``Applied`` only
    when application evidence exists.  The raw value remains on the record and
    is available through :func:`legacy_status_value`.
    """
    if record.get("status") not in (None, ""):
        raw_status = str(record["status"]).strip()
        normalized = normalize_status(raw_status)
        if normalize_tracker_value(raw_status) in {
            "active",
            "reviewed",
            "review first",
            "manually reviewed",
        } and any(
            record.get(field)
            for field in ("submitted_date", "applied_date", "application_date")
        ):
            evidence = normalize_tracker_value(
                " ".join(
                    str(record.get(field) or "")
                    for field in ("portal_status", "employer_status", "next_action", "notes")
                )
            )
            if "interview" in evidence:
                return "Interviewing"
            if "offer" in evidence:
                return "Offer"
            if "under consideration" in evidence or "under review" in evidence:
                return "Under Consideration"
            return "Applied"
        return normalized
    for field in LEGACY_STATUS_FIELDS:
        if record.get(field) not in (None, ""):
            return normalize_status(record[field])
    return "Drafted"


def legacy_status_value(record: Dict[str, Any]) -> str:
    """Expose the stored pre-normalization value for audit/migration safety."""
    return str(record.get("legacy_status") or record.get("status") or "").strip()


def workflow_status_bucket(record: Dict[str, Any]) -> str:
    """Classify a record for legacy internal grouping.

    The returned labels are kept for compatibility with older renderers. New
    user-facing controls use :func:`get_record_status` directly.
    """
    status = get_record_status(record)
    if status in HIDDEN_STATUSES:
        return "Hidden / Invalid"
    if (
        record.get("verification_status") == "Stale / Closed Risk"
        and record.get("show_on_dashboard") is False
    ):
        return "Hidden / Invalid"
    if status in ACTIVE_STATUSES:
        return "Applied / Follow-up"
    return "Active"


def _has_contact_path(record: Dict[str, Any]) -> bool:
    """Return whether a direct or explicitly available follow-up path exists."""
    if (
        record.get("portal_only") is True
        or record.get("no_contact") is True
        or record.get("follow_up_possible") is False
    ):
        return False
    contact_fields = (
        "recruiter_contact",
        "recruiter_email",
        "recruiter_url",
        "hiring_manager_contact",
        "hiring_manager_email",
        "hiring_manager_url",
        "warm_contact",
        "warm_contact_email",
        "referral_contact",
        "contact_path",
    )
    if any(str(record.get(field) or "").strip() for field in contact_fields):
        return True
    return False


def _follow_up_already_sent_without_new_event(record: Dict[str, Any]) -> bool:
    state = normalize_tracker_value(record.get("follow_up_status"))
    explicitly_sent = state == "follow up sent" or record.get("follow_up_sent") is True
    history = record.get("application_history")
    if not isinstance(history, list):
        return explicitly_sent
    last_follow_up = -1
    last_new_event = -1
    for index, event in enumerate(history):
        if not isinstance(event, dict):
            continue
        event_type = normalize_tracker_value(event.get("event") or event.get("type"))
        if event_type in {"follow up sent", "followup sent"}:
            last_follow_up = index
        if event_type in {
            "employer response",
            "interview completed",
            "interview rescheduled",
            "interview scheduled",
        }:
            last_new_event = index
        if event_type == "status changed" and normalize_tracker_value(event.get("to")) in {
            "interviewing",
            "offer",
        }:
            last_new_event = index
    if last_new_event > last_follow_up:
        return False
    return explicitly_sent or (last_follow_up >= last_new_event and last_follow_up >= 0)


def _portal_url(record: Dict[str, Any]) -> str:
    return str(record.get("application_portal_url") or "").strip()


def _follow_up_wait_days(record: Dict[str, Any]) -> int:
    for field in (
        "follow_up_wait_days",
        "follow_up_waiting_days",
        "configured_follow_up_days",
    ):
        value = record.get(field)
        if value in (None, ""):
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return 5


def _under_consideration_response_required(record: Dict[str, Any]) -> bool:
    if (
        record.get("response_required") is True
        or record.get("follow_up_required") is True
    ):
        return True
    evidence = normalize_tracker_value(
        " ".join(
            str(record.get(field) or "")
            for field in ("response_action", "employer_response", "next_action")
        )
    )
    return any(
        phrase in evidence
        for phrase in (
            "reply",
            "respond",
            "send availability",
            "provide information",
            "action required",
        )
    )


def _interview_follow_up_trigger(record: Dict[str, Any]) -> bool:
    if (
        record.get("interview_follow_up_required") is True
        or record.get("follow_up_required") is True
    ):
        return True
    evidence = normalize_tracker_value(
        " ".join(
            str(record.get(field) or "")
            for field in (
                "follow_up_trigger",
                "follow_up_type",
                "interview_follow_up_type",
                "interview_action",
                "next_action",
            )
        )
    )
    if any(
        phrase in evidence
        for phrase in (
            "thank you",
            "schedule",
            "scheduling",
            "confirm interview",
            "send availability",
            "reply",
            "respond",
            "interview outreach",
        )
    ):
        return True
    history = record.get("application_history")
    if not isinstance(history, list):
        return False
    last_follow_up = -1
    last_trigger = -1
    for index, event in enumerate(history):
        if not isinstance(event, dict):
            continue
        event_type = normalize_tracker_value(event.get("event") or event.get("type"))
        if event_type in {"follow up sent", "followup sent"}:
            last_follow_up = index
        if event_type in {
            "employer response",
            "interview completed",
            "interview rescheduled",
            "interview scheduled",
        }:
            last_trigger = index
    return last_trigger > last_follow_up


def _follow_up_action(
    key: str,
    label: str,
    reason: str,
    status: str,
    portal_url: str = "",
) -> Dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "reason": reason,
        "eligible": key == "generate_follow_up",
        "status": status,
        "portal_url": portal_url,
    }


def follow_up_action_state(
    record: Dict[str, Any], today: Optional[date] = None
) -> Dict[str, Any]:
    """Return the one contextual follow-up action a role can show today."""
    status = get_record_status(record)
    portal_url = _portal_url(record)
    if record.get("show_on_dashboard") is False or legacy_status_value(record) in {
        "Invalid",
        "Invalid/Hidden",
    }:
        return _follow_up_action(
            "no_action_today",
            "No action today",
            "This role is closed or hidden, so no follow-up is needed.",
            status,
        )
    terminal_reasons = {
        "Drafted": "This role is still drafted and has not been applied to.",
        "Offer": "An offer does not need a generic application follow-up.",
        "Rejected": "This application was rejected, so no follow-up is needed.",
        "Withdrawn / Closed": "This application is closed, so no follow-up is needed.",
    }
    if status in terminal_reasons:
        return _follow_up_action(
            "no_action_today", "No action today", terminal_reasons[status], status
        )
    if status not in {"Applied", "Under Consideration", "Interviewing"}:
        return _follow_up_action(
            "no_action_today",
            "No action today",
            f"Status {status} does not support application follow-up.",
            status,
        )
    follow_up_state = normalize_tracker_value(record.get("follow_up_status"))
    if (
        follow_up_state in {"not applicable", "no follow up", "no follow up needed"}
        or record.get("follow_up_not_applicable") is True
    ):
        return _follow_up_action(
            "no_action_today",
            "No action today",
            "Follow-up is marked not applicable for this role.",
            status,
        )
    if _follow_up_already_sent_without_new_event(record):
        return _follow_up_action(
            "follow_up_already_sent",
            "Follow-up already sent",
            "A follow-up has already been sent, and no new stage-specific trigger is recorded.",
            status,
        )

    response_required = (
        status == "Under Consideration"
        and _under_consideration_response_required(record)
    )
    has_contact_path = _has_contact_path(record) or response_required
    if status == "Interviewing" and not _interview_follow_up_trigger(record):
        return _follow_up_action(
            "no_action_today",
            "No action today",
            "No interview thank-you, scheduling, or interview-related outreach is due today.",
            status,
        )
    if not has_contact_path:
        if portal_url:
            return _follow_up_action(
                "check_application_status",
                "Check Application Status",
                "No direct contact route is saved. Check the employer portal for status updates.",
                status,
                portal_url,
            )
        return _follow_up_action(
            "no_direct_follow_up_path",
            "No direct follow-up path",
            "No recruiter, hiring manager, referral, or warm-contact route is saved.",
            status,
        )
    if status == "Applied":
        applied_value = next(
            (
                record.get(key)
                for key in ("submitted_date", "applied_date", "application_date")
                if record.get(key)
            ),
            None,
        )
        if not applied_value:
            return _follow_up_action(
                "not_yet_eligible",
                "Not yet eligible",
                "An applied date is needed before the waiting period can be calculated.",
                status,
            )
        try:
            applied = date.fromisoformat(str(applied_value)[:10])
        except ValueError:
            return _follow_up_action(
                "not_yet_eligible",
                "Not yet eligible",
                "The applied date is invalid, so the waiting period cannot be calculated.",
                status,
            )
        wait_days = _follow_up_wait_days(record)
        elapsed = ((today or date.today()) - applied).days
        if elapsed < wait_days:
            remaining = wait_days - elapsed
            return _follow_up_action(
                "not_yet_eligible",
                "Not yet eligible",
                f"The follow-up waiting period has {remaining} day{'s' if remaining != 1 else ''} remaining.",
                status,
            )
    if status == "Interviewing":
        reason = "A stage-appropriate interview follow-up is due and a contact route is available."
    elif response_required:
        reason = "A specific employer response is required, so a follow-up can be prepared."
    else:
        reason = "The waiting period has elapsed and a direct contact route is available."
    return _follow_up_action(
        "generate_follow_up", "Generate Follow-Up", reason, status
    )


def follow_up_eligibility(record: Dict[str, Any], today: Optional[date] = None) -> Tuple[bool, str]:
    """Compatibility wrapper around the shared contextual action helper."""
    action = follow_up_action_state(record, today)
    return bool(action["eligible"]), str(action["reason"])


def make_tracker_id(company: Any, role: Any) -> str:
    """Build a stable, readable tracker id from company and role."""
    normalized = normalize_tracker_value(
        f"{canonical_employer_name(company)} {role}"
    ).replace(" ", "_")
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
    tracker_path = (root / TRACKER_PATH).resolve()
    if not tracker_path.is_file():
        raise TrackerValidationError(f"Application tracker file not found: {TRACKER_PATH}")

    stat = tracker_path.stat()
    signature = (stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size)
    cached = _TRACKER_READ_CACHE.get(tracker_path)
    if cached and cached[0] == signature:
        return deepcopy(cached[1])

    try:
        loaded = yaml.load(
            tracker_path.read_text(encoding="utf-8"),
            Loader=_SAFE_YAML_LOADER,
        )
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
    applications = loaded["applications"]
    _TRACKER_READ_CACHE[tracker_path] = (signature, deepcopy(applications))
    return deepcopy(applications)


def invalidate_application_tracker_cache(
    project_root: Optional[PathInput] = None,
) -> None:
    """Forget cached tracker data after an in-process write."""
    if project_root is None:
        _TRACKER_READ_CACHE.clear()
        return
    tracker_path = (Path(project_root) / TRACKER_PATH).resolve()
    _TRACKER_READ_CACHE.pop(tracker_path, None)


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
    invalidate_application_tracker_cache(root)
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
    raw_company = str(prospect.get("company") or "").strip()
    company = canonical_employer_name(raw_company)
    role = str(prospect.get("role") or prospect.get("job_title") or "").strip()
    if not company or not role:
        raise TrackerUpdateError("A prospect requires both company and role title.")

    tracker_id = str(prospect.get("id") or make_tracker_id(company, role)).strip()
    incoming = _clean_updates(dict(prospect))
    if "status" in incoming:
        raw_status = str(incoming["status"]).strip()
        incoming["status"] = normalize_status(raw_status)
        if incoming["status"] != raw_status:
            incoming.setdefault("legacy_status", raw_status)
    incoming["id"] = tracker_id
    incoming["company"] = company
    incoming["role"] = role
    incoming.pop("job_title", None)

    applications = load_application_tracker(project_root)
    existing = next(
        (application for application in applications if application.get("id") == tracker_id),
        None,
    )
    previous_company_aliases = (
        list(existing.get("company_aliases") or []) if existing else []
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

    aliases = list(
        dict.fromkeys(previous_company_aliases + list(entry.get("company_aliases") or []))
    )
    if raw_company and normalize_tracker_value(raw_company) != normalize_tracker_value(company):
        if raw_company not in aliases:
            aliases.append(raw_company)
    entry["company_aliases"] = aliases

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
    if "status" in cleaned:
        raw_status = str(cleaned["status"]).strip()
        cleaned["status"] = normalize_status(raw_status)
        if cleaned["status"] != raw_status and not entry.get("legacy_status"):
            cleaned["legacy_status"] = raw_status
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
    raw_status = str(status).strip()
    status = normalize_status(raw_status)
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

    previous_status = str(entry.get("status") or "Drafted")
    previous_primary_status = get_record_status(entry)
    if previous_status != previous_primary_status and not entry.get("legacy_status"):
        entry["legacy_status"] = previous_status
    if raw_status != status and not entry.get("legacy_status"):
        entry["legacy_status"] = raw_status
    entry["status"] = status
    entry.update(_explicit_updates(updates))
    if status != previous_status:
        entry["status_updated_at"] = datetime.now().isoformat(timespec="seconds")
    if status != previous_primary_status:
        history = entry.setdefault("application_history", [])
        if isinstance(history, list):
            history.append(
                {
                    "event": "status changed",
                    "from": previous_primary_status,
                    "to": status,
                    "date": date.today().isoformat(),
                }
            )
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

        status = get_record_status(application)
        if status not in VALID_STATUSES:
            warnings.append(
                f"{label} has unsupported status '{status}'. "
                "It is being preserved as a legacy status until explicitly updated."
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

        match_score = application.get("match_score")
        if match_score is not None and (
            isinstance(match_score, bool)
            or not isinstance(match_score, int)
            or not 0 <= match_score <= 100
        ):
            errors.append(f"{label} field match_score must be an integer from 0 to 100.")
        match_tier = application.get("match_tier")
        if match_tier is not None and match_tier not in VALID_MATCH_TIERS:
            errors.append(f"{label} field match_tier is not supported.")
        recommended_action = application.get("recommended_action")
        if recommended_action is not None and recommended_action not in VALID_MATCH_ACTIONS:
            errors.append(f"{label} field recommended_action is not supported.")
        confidence = application.get("confidence")
        if confidence is not None and confidence not in VALID_MATCH_CONFIDENCE:
            errors.append(f"{label} field confidence is not supported.")
        for list_field, minimum, maximum in (
            ("match_strengths", 3, 5),
            ("match_gaps", 1, 5),
        ):
            values = application.get(list_field)
            if values is not None and (
                not isinstance(values, list)
                or not minimum <= len(values) <= maximum
                or not all(isinstance(value, str) and value.strip() for value in values)
            ):
                errors.append(
                    f"{label} field {list_field} must contain {minimum}-{maximum} non-empty strings."
                )

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
