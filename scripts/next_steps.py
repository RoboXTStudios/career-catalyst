"""Deterministic, state-safe prospect recommendations."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

try:
    from .application_tracker import follow_up_action_state, get_record_status
except ImportError:
    from application_tracker import follow_up_action_state, get_record_status


FORBIDDEN_BY_STATUS = {
    "Applied": ("apply", "submit application", "generate package"),
    "Under Consideration": ("apply", "submit application", "initial application"),
    "Interviewing": ("apply", "submit application", "initial application"),
    "Rejected": ("apply", "generate", "follow up", "follow-up", "reopen"),
    "Withdrawn / Closed": ("apply", "generate", "follow up", "follow-up", "reopen"),
    "Offer": ("apply", "generate", "follow up", "follow-up"),
}


def _has_current_package(record: Mapping[str, Any]) -> bool:
    if record.get("_has_package") is True:
        return True
    values = list(dict(record.get("material_paths") or {}).values())
    manifest = record.get("package_manifest")
    if isinstance(manifest, dict):
        values.extend(dict(manifest.get("materials") or {}).values())
    return any(value and Path(str(value)).is_file() for value in values)


def _completed_categories(record: Mapping[str, Any]) -> set[str]:
    completed = {str(value) for value in record.get("completed_actions", []) if value}
    history = record.get("application_history")
    for event in history if isinstance(history, list) else []:
        if not isinstance(event, dict):
            continue
        event_text = str(event.get("event") or event.get("type") or "").lower()
        if "follow" in event_text and "sent" in event_text:
            completed.add("follow_up")
        if "interview" in event_text and "prepar" in event_text:
            completed.add("interview_prep")
    return completed


def _action(category: str, label: str, reason: str) -> Dict[str, str]:
    return {"category": category, "label": label, "reason": reason}


def deterministic_next_steps(
    record: Mapping[str, Any], today: Optional[date] = None
) -> list[Dict[str, str]]:
    """Return only actions permitted by saved application state."""
    values = dict(record)
    status = get_record_status(values)
    completed = _completed_categories(values)
    has_package = _has_current_package(values)
    missing_role_data = not str(values.get("company") or "").strip() or not str(
        values.get("role") or values.get("job_title") or ""
    ).strip()
    actions: list[Dict[str, str]] = []

    if status == "Drafted":
        if missing_role_data or str(values.get("recommended_action") or "").startswith("Complete Import"):
            actions.append(_action("complete_import", "Complete role details", "Required role facts are still missing."))
        actions.append(_action("review_fit", "Review fit and Evidence", "This saved prospect is still under consideration."))
        if not has_package:
            actions.append(_action("generate_materials", "Generate materials", "No current role-scoped package is saved."))
        actions.append(_action("apply_or_archive", "Apply or archive", "The next decision is whether to pursue this saved role."))
    elif status == "Applied":
        if values.get("portal_only") is True or (
            values.get("application_portal_url") and values.get("follow_up_possible") is False
        ):
            actions.append(_action("check_application_status", "Check Application Status", "This submitted role can only be tracked through the employer portal."))
        else:
            actions.append(_action("track_application", "Track application", "The application is already submitted."))
        follow_up = follow_up_action_state(values, today)
        if follow_up.get("eligible") and "follow_up" not in completed:
            actions.append(_action("follow_up", str(follow_up.get("label") or "Prepare follow-up"), str(follow_up.get("reason") or "The saved wait interval has elapsed.")))
        if values.get("interview_date") or values.get("interview_state"):
            actions.append(_action("interview_prep", "Prepare interview material", "An interview event is saved for this application."))
    elif status in {"Under Consideration", "Interviewing"}:
        actions.append(_action("interview_prep", "Interview Preparation", "The employer is actively considering this application; prepare for the next interview stage."))
        actions.append(_action("contact_strategy", "Review contact strategy", "Communication should support the active evaluation stage."))
        follow_up = follow_up_action_state(values, today)
        if follow_up.get("eligible") and "follow_up" not in completed:
            actions.append(_action("follow_up", str(follow_up.get("label") or "Prepare follow-up"), str(follow_up.get("reason") or "A saved follow-up trigger is active.")))
    elif status in {"Rejected", "Withdrawn / Closed"}:
        actions.append(_action("archive_learning", "Archive and capture learning", "This application is closed; no application or outreach action is appropriate."))
    elif status == "Offer":
        actions.append(_action("offer_decision", "Review offer and decision timeline", "An offer is saved, so decision support is the only primary action."))

    return [action for action in actions if action["category"] not in completed]


def safe_user_next_action(record: Mapping[str, Any]) -> str:
    """Return a user override only when it cannot contradict saved state."""
    text = " ".join(str(record.get("next_action") or "").split()).strip()
    status = get_record_status(dict(record))
    if not text:
        return ""
    normalized = re.sub(r"[^a-z0-9]+", " ", text.lower())
    if any(phrase in normalized for phrase in FORBIDDEN_BY_STATUS.get(status, ())):
        return ""
    return text


def constrain_ai_wording(record: Mapping[str, Any], proposed: str) -> str:
    """Reject AI wording that introduces a state-forbidden action."""
    candidate = dict(record)
    candidate["next_action"] = proposed
    return safe_user_next_action(candidate)
