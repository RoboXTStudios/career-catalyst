"""Load, update, and validate the Career Catalyst application tracker."""

from datetime import date, datetime
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
    "withdrawn": "Withdrawn / Closed",
    "offer declined": "Withdrawn / Closed",
    "do not pursue": "Withdrawn / Closed",
    "hidden": "Withdrawn / Closed",
    "invalid": "Withdrawn / Closed",
    "invalid hidden": "Withdrawn / Closed",
    "archived": "Withdrawn / Closed",
    "closed": "Withdrawn / Closed",
    "posting closed": "Withdrawn / Closed",
    "role filled": "Withdrawn / Closed",
    "stale closed risk": "Withdrawn / Closed",
}
ACTIVE_STATUSES = {"Applied", "Under Consideration", "Interviewing", "Offer"}
DRAFT_STATUSES = {"Drafted"}
TERMINAL_ARCHIVE_STATUSES = {
    "Rejected",
    "Withdrawn / Closed",
}
HIDDEN_STATUSES = set(TERMINAL_ARCHIVE_STATUSES)
ACTIVE_WORK_STATUSES = set(VALID_STATUSES) - TERMINAL_ARCHIVE_STATUSES
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
DERIVED_PACKAGE_FIELDS = (
    "material_paths",
    "package_manifest",
    "package_quality",
    "opportunity_score",
    "apply_recommendation",
    "opportunity_dimensions",
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


def is_terminal_status(value: Any) -> bool:
    """Return whether a status represents a durable inactive lifecycle state."""
    return normalize_status(value) in TERMINAL_ARCHIVE_STATUSES


def is_archived(record: Dict[str, Any]) -> bool:
    """Read archive visibility without mutating legacy records."""
    return record.get("is_archived") is True


def is_active_prospect(record: Dict[str, Any]) -> bool:
    """Return whether a role belongs in current-work views."""
    return not is_archived(record) and get_record_status(record) not in TERMINAL_ARCHIVE_STATUSES


def _archive_reason(status: Any) -> str:
    token = normalize_tracker_value(status)
    normalized = normalize_status(status)
    if normalized == "Rejected":
        return "Rejected"
    if token in {"withdrawn", "offer declined"}:
        return "Withdrawn"
    if token in {"closed", "posting closed", "role filled"}:
        return "Closed"
    if normalized == "Withdrawn / Closed":
        return "Withdrawn" if "withdraw" in token else "Closed" if "closed" in token else "Other"
    return "Other"


def _apply_archive_lifecycle(
    entry: Dict[str, Any], previous_status: str = "", *, migrated: bool = False,
    archive_status: Any = None,
) -> bool:
    """Apply one idempotent archive or restore transition after an explicit save."""
    status = get_record_status(entry)
    changed = False
    if status in TERMINAL_ARCHIVE_STATUSES:
        if not is_archived(entry):
            archived_at = datetime.now().isoformat(timespec="seconds")
            entry["is_archived"] = True
            entry["archived_at"] = archived_at
            raw_archive_status = archive_status or entry.get("status") or status
            entry["archive_reason"] = _archive_reason(raw_archive_status)
            entry["archived_from_status"] = str(raw_archive_status)
            entry["show_on_dashboard"] = False
            history = entry.setdefault("archive_history", [])
            if isinstance(history, list):
                history.append(
                    {
                        "event": "archived",
                        "status": status,
                        "reason": entry["archive_reason"],
                        "date": date.today().isoformat(),
                        "migrated": bool(migrated),
                    }
                )
            changed = True
    elif is_archived(entry):
        entry["is_archived"] = False
        entry["restored_at"] = datetime.now().isoformat(timespec="seconds")
        entry["show_on_dashboard"] = True
        history = entry.setdefault("archive_history", [])
        if isinstance(history, list):
            history.append(
                {
                    "event": "restored",
                    "from_status": previous_status or entry.get("archived_from_status") or "",
                    "to_status": status,
                    "date": date.today().isoformat(),
                }
            )
        changed = True
    return changed


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


# Statuses that represent "waiting on the employer" rather than a resolved
# outcome. If one of these sits unchanged past STALE_STATUS_THRESHOLD_DAYS
# with no employer signal, it is functionally ghosted even though nothing
# ever explicitly marked it so — see the Live Nation Director, Concert
# Communications record, which sat at "Under Consideration" for two months
# with zero human review after the status was set on 2026-07-13.
WAITING_STATUSES = {"applied", "under consideration", "follow up"}
STALE_STATUS_THRESHOLD_DAYS = 21


def days_since_status_update(record: Dict[str, Any], today: Optional[date] = None) -> Optional[int]:
    """Days since status_updated_at (or submitted_date as a fallback). None if neither is present/parseable."""
    today = today or date.today()
    for field in ("status_updated_at", "submitted_date"):
        raw = record.get(field)
        if not raw:
            continue
        try:
            parsed = date.fromisoformat(str(raw).strip()[:10])
            return (today - parsed).days
        except ValueError:
            continue
    return None


def is_stale_waiting_status(record: Dict[str, Any], today: Optional[date] = None) -> bool:
    """True if a record is sitting in a 'waiting on employer' status well past a normal
    response window, with no explicit employer signal recorded. This is the check that
    would have caught the Live Nation record automatically instead of requiring a manual audit."""
    status = normalize_tracker_value(record.get("status"))
    if status not in WAITING_STATUSES:
        return False
    if _under_consideration_response_required(record):
        # Employer explicitly asked for something — not silently stale, it's actionable.
        return False
    elapsed = days_since_status_update(record, today=today)
    if elapsed is None:
        return False
    return elapsed >= STALE_STATUS_THRESHOLD_DAYS


def stale_waiting_records(records: List[Dict[str, Any]], today: Optional[date] = None) -> List[Dict[str, Any]]:
    """Returns every record that is likely silently stale, for surfacing in the dashboard
    or a periodic review command."""
    return [r for r in records if is_stale_waiting_status(r, today=today)]


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
    if is_archived(record) or record.get("show_on_dashboard") is False or legacy_status_value(record) in {
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
    migrate_application_evidence_selections(applications)
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


def migrate_application_evidence_selections(
    applications: List[Dict[str, Any]],
) -> int:
    """Add independent overrides to legacy records without rebuilding any selection."""
    try:
        from .role_evidence_selection import migrate_legacy_selection_to_overrides
    except ImportError:
        from role_evidence_selection import migrate_legacy_selection_to_overrides

    migrated = 0
    for application in applications:
        selection = application.get("role_evidence_selection")
        if not isinstance(selection, dict) or not selection:
            continue
        existing = application.get("evidence_selection_overrides")
        normalized = migrate_legacy_selection_to_overrides(
            selection,
            existing if isinstance(existing, dict) else None,
        )
        if existing != normalized:
            application["evidence_selection_overrides"] = normalized
            migrated += 1
    return migrated


def mark_role_evidence_selections_dirty(
    project_root: Optional[PathInput] = None,
) -> int:
    """Invalidate saved role selections after an explicit global evidence mutation."""
    applications = load_application_tracker(project_root)
    changed = 0
    for application in applications:
        if not application.get("role_evidence_selection"):
            continue
        updates = {
            "prospect_evidence_dirty": True,
            "score_dirty": True,
            "application_strategy_dirty": True,
            "hiring_manager_brief_dirty": True,
            "career_coach_dirty": True,
            "package_dirty": True,
        }
        if any(application.get(key) != value for key, value in updates.items()):
            application.update(updates)
            changed += 1
    if changed:
        save_application_tracker(applications, project_root)
    return changed


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


def _apply_context_revision(
    entry: Dict[str, Any], incoming: Dict[str, Any], *, created: bool = False
) -> bool:
    """Advance the saved revision and discard derived package state when context changes."""
    incoming_fingerprint = str(incoming.get("context_fingerprint") or "").strip()
    if not incoming_fingerprint:
        return False
    previous_fingerprint = str(entry.get("context_fingerprint") or "").strip()
    changed = bool(previous_fingerprint and previous_fingerprint != incoming_fingerprint)
    if created:
        incoming["prospect_revision"] = max(
            1, int(incoming.get("prospect_revision") or 1)
        )
    elif not previous_fingerprint:
        incoming["prospect_revision"] = max(
            1, int(entry.get("prospect_revision") or 0) + 1
        )
        changed = any(field in entry for field in DERIVED_PACKAGE_FIELDS)
        if changed:
            for field in DERIVED_PACKAGE_FIELDS:
                entry.pop(field, None)
    elif changed:
        incoming["prospect_revision"] = int(entry.get("prospect_revision") or 1) + 1
        incoming["career_coach_dirty"] = True
        for field in DERIVED_PACKAGE_FIELDS:
            entry.pop(field, None)
    else:
        incoming["prospect_revision"] = int(entry.get("prospect_revision") or 1)
    return changed


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
        _apply_context_revision(entry, incoming, created=True)
        entry.update(incoming)
        _apply_archive_lifecycle(entry)
        applications.append(entry)
    else:
        entry = existing
        original_status = str(existing.get("status") or "Drafted")
        _apply_context_revision(entry, incoming)
        entry.update(incoming)
        # Intake must never demote an application that has progressed beyond drafting.
        if original_status in INTAKE_PROTECTED_STATUSES or (
            original_status != "Drafted" and incoming.get("status") == "Drafted"
        ):
            entry["status"] = original_status
        entry.setdefault("company_aliases", [])
        entry.setdefault("role_aliases", [])
        entry.setdefault("show_on_dashboard", True)
        if "status" in incoming:
            _apply_archive_lifecycle(entry, original_status)

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
    _apply_context_revision(entry, cleaned)
    archive_status: Any = None
    if "status" in cleaned:
        raw_status = str(cleaned["status"]).strip()
        archive_status = raw_status
        cleaned["status"] = normalize_status(raw_status)
        if cleaned["status"] != raw_status and not entry.get("legacy_status"):
            cleaned["legacy_status"] = raw_status
    previous_primary_status = get_record_status(entry)
    entry.update(cleaned)
    if "status" in cleaned:
        _apply_archive_lifecycle(
            entry, previous_primary_status, archive_status=archive_status
        )
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
    _apply_archive_lifecycle(entry, previous_primary_status, archive_status=raw_status)
    save_application_tracker(applications, project_root)
    return dict(entry)


def archive_prospect(
    tracker_id: str,
    reason: str = "Other",
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Archive a role manually without changing its application status."""
    applications = load_application_tracker(project_root)
    entry = next(
        (application for application in applications if application.get("id") == tracker_id),
        None,
    )
    if entry is None:
        raise TrackerUpdateError(f"Tracker entry not found: {tracker_id}")
    if not is_archived(entry):
        status = get_record_status(entry)
        entry.update(
            {
                "is_archived": True,
                "archived_at": datetime.now().isoformat(timespec="seconds"),
                "archive_reason": str(reason or "Other").strip() or "Other",
                "archived_from_status": status,
                "show_on_dashboard": False,
            }
        )
        history = entry.setdefault("archive_history", [])
        if isinstance(history, list):
            history.append(
                {
                    "event": "archived",
                    "status": status,
                    "reason": entry["archive_reason"],
                    "date": date.today().isoformat(),
                    "migrated": False,
                }
            )
        save_application_tracker(applications, project_root)
    return dict(entry)


def restore_prospect(
    tracker_id: str,
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Restore archive visibility while preserving status, materials, and history."""
    applications = load_application_tracker(project_root)
    entry = next(
        (application for application in applications if application.get("id") == tracker_id),
        None,
    )
    if entry is None:
        raise TrackerUpdateError(f"Tracker entry not found: {tracker_id}")
    if is_archived(entry):
        status = get_record_status(entry)
        entry["is_archived"] = False
        entry["restored_at"] = datetime.now().isoformat(timespec="seconds")
        entry["show_on_dashboard"] = status in ACTIVE_WORK_STATUSES
        history = entry.setdefault("archive_history", [])
        if isinstance(history, list):
            history.append(
                {
                    "event": "restored",
                    "from_status": entry.get("archived_from_status") or status,
                    "to_status": status,
                    "date": date.today().isoformat(),
                }
            )
        save_application_tracker(applications, project_root)
    return dict(entry)


def migrate_closed_role_archives(
    project_root: Optional[PathInput] = None,
    *,
    apply: bool = False,
) -> Dict[str, Any]:
    """Report or idempotently archive existing terminal roles on explicit request."""
    applications = load_application_tracker(project_root)
    candidate_ids: list[str] = []
    for entry in applications:
        if (
            is_archived(entry)
            or entry.get("restored_at")
            or get_record_status(entry) not in TERMINAL_ARCHIVE_STATUSES
        ):
            continue
        candidate_ids.append(str(entry.get("id") or ""))
        if apply:
            _apply_archive_lifecycle(entry, migrated=True)
    if apply and candidate_ids:
        save_application_tracker(applications, project_root)
    return {
        "dry_run": not apply,
        "candidate_count": len(candidate_ids),
        "archived_count": len(candidate_ids) if apply else 0,
        "candidate_ids": candidate_ids,
        "total_records": len(applications),
    }


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
        if application.get("is_archived") is not None and not isinstance(
            application.get("is_archived"), bool
        ):
            errors.append(f"{label} field is_archived must be true or false when present.")
        if application.get("archive_history") is not None and not isinstance(
            application.get("archive_history"), list
        ):
            errors.append(f"{label} field archive_history must be a list when present.")

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
        context_fingerprint = application.get("context_fingerprint")
        if context_fingerprint is not None and not re.fullmatch(
            r"[a-f0-9]{64}", str(context_fingerprint)
        ):
            errors.append(
                f"{label} field context_fingerprint must be a SHA-256 hex digest."
            )
        prospect_revision = application.get("prospect_revision")
        if prospect_revision is not None and (
            isinstance(prospect_revision, bool)
            or not isinstance(prospect_revision, int)
            or prospect_revision < 1
        ):
            errors.append(
                f"{label} field prospect_revision must be a positive integer."
            )
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
