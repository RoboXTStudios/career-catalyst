"""Signal-first application workflow helpers.

This module is deliberately read-only.  It translates the lossless tracker
record into dashboard recommendations and a privacy-limited integration
summary without touching generated materials, notes, or evidence.
"""

from __future__ import annotations

from datetime import date
import re
from typing import Any, Dict, Iterable, Mapping, Optional

try:
    from .application_tracker import (
        follow_up_action_state,
        get_record_status,
        is_active_prospect,
    )
except ImportError:
    from application_tracker import (
        follow_up_action_state,
        get_record_status,
        is_active_prospect,
    )


IN_FLIGHT_STATUSES = frozenset(
    {"Applied", "Under Consideration", "Interviewing", "Offer"}
)
CAREER_STATES = frozenset(
    {"Waiting", "In Flight", "Action Needed", "Interviewing", "Offer"}
)


def status_date(record: Mapping[str, Any]) -> str:
    """Return the most relevant application/status date without modifying it."""
    for field in (
        "status_updated_at",
        "submitted_date",
        "applied_date",
        "application_date",
        "created_at",
        "posting_date",
    ):
        value = str(record.get(field) or "").strip()
        if value:
            return value[:10]
    return ""


def _missing_portal(record: Mapping[str, Any]) -> bool:
    return get_record_status(dict(record)) in IN_FLIGHT_STATUSES and not str(
        record.get("application_portal_url") or ""
    ).strip()


def next_action_signal(
    record: Mapping[str, Any], today: Optional[date] = None
) -> Dict[str, Any]:
    """Return exactly one calm, contextual recommendation for a role."""
    values = dict(record)
    status = get_record_status(values)
    follow_up_action = follow_up_action_state(values, today)
    eligible = bool(follow_up_action["eligible"])
    follow_up_reason = str(follow_up_action["reason"])

    if eligible:
        return {
            "kind": "follow_up",
            "label": str(follow_up_action["label"]),
            "reason": follow_up_reason,
            "action": str(values.get("next_action") or follow_up_action["label"]),
            "action_key": "view_role",
            "needs_action": True,
            "rank": 0 if status == "Interviewing" else 1,
        }
    if status == "Interviewing":
        return {
            "kind": "interview",
            "label": "Interview Preparation",
            "reason": "Interview preparation is the highest-leverage action today.",
            "action": str(values.get("next_action") or "Prepare for the next interview stage."),
            "action_key": "view_role",
            "needs_action": True,
            "rank": 0,
        }
    if status == "Drafted":
        return {
            "kind": "drafted",
            "label": "Drafted",
            "reason": "This is the highest-fit unfinished application currently in the pipeline.",
            "action": str(values.get("next_action") or "Complete and review the application."),
            "action_key": "view_role",
            "needs_action": True,
            "rank": 3,
        }
    if status == "Offer":
        return {
            "kind": "offer",
            "label": "Offer",
            "reason": "An offer is the highest-leverage career decision in the pipeline.",
            "action": str(values.get("next_action") or "Review the offer and decision timeline."),
            "action_key": "view_role",
            "needs_action": True,
            "rank": 0,
        }
    if _missing_portal(values):
        return {
            "kind": "portal_correction",
            "label": "Application Link Needed",
            "reason": "The application portal URL is missing and needs a manual correction.",
            "action": "Add the employer application portal URL in Advanced Details.",
            "action_key": "view_role",
            "needs_action": True,
            "rank": 4,
        }
    if status in {"Rejected", "Withdrawn / Closed"}:
        return {
            "kind": "closed",
            "label": "No Action Today",
            "reason": "This application is closed.",
            "action": "No action needed.",
            "action_key": "",
            "needs_action": False,
            "rank": 99,
        }
    if follow_up_action["key"] == "check_application_status":
        return {
            "kind": "check_application_status",
            "label": str(follow_up_action["label"]),
            "reason": follow_up_reason,
            "action": "Check the employer application portal.",
            "action_key": "check_portal",
            "needs_action": True,
            "rank": 4,
        }
    return {
        "kind": "waiting",
        "label": str(follow_up_action["label"]),
        "reason": follow_up_reason,
        "action": "No follow-up action is needed today.",
        "action_key": "",
        "needs_action": False,
        "rank": 50,
    }


def select_todays_focus(
    records: Iterable[Mapping[str, Any]], today: Optional[date] = None
) -> Optional[Dict[str, Any]]:
    """Select no more than one role using deterministic operational ranking."""
    candidates = []
    for index, source in enumerate(records):
        record = dict(source)
        if record.get("show_on_dashboard") is False or not is_active_prospect(record):
            continue
        status = get_record_status(record)
        if status in {"Rejected", "Withdrawn / Closed"}:
            continue
        signal = next_action_signal(record, today)
        score = record.get("match_score")
        try:
            match_score = int(score)
        except (TypeError, ValueError):
            match_score = -1
        priority = {"High": 0, "Medium": 1, "Low": 2, "Do Not Pursue": 3}.get(
            str(record.get("priority") or "Medium"), 1
        )
        candidates.append(
            (
                (signal["rank"], priority, -match_score, status_date(record), index),
                {
                    "id": str(record.get("id") or ""),
                    "company": str(record.get("company") or "Unknown company"),
                    "role": str(record.get("role") or "Unknown role"),
                    "status": status,
                    "match_score": record.get("match_score"),
                    "priority": str(record.get("priority") or "Medium"),
                    **signal,
                },
            )
        )
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: candidate[0])[1]


def operational_signal_summary(
    records: Iterable[Mapping[str, Any]], today: Optional[date] = None
) -> Dict[str, Any]:
    """Return the privacy-limited, read-only Ground Control signal payload."""
    visible = [
        dict(item)
        for item in records
        if item.get("show_on_dashboard") is not False and is_active_prospect(dict(item))
    ]
    statuses = [get_record_status(item) for item in visible]
    focus = select_todays_focus(visible, today)
    follow_ups_due = sum(
        bool(follow_up_action_state(item, today)["eligible"]) for item in visible
    )
    if "Offer" in statuses:
        career_state = "Offer"
    elif "Interviewing" in statuses:
        career_state = "Interviewing"
    elif focus and focus["needs_action"]:
        career_state = "Action Needed"
    elif any(status in IN_FLIGHT_STATUSES for status in statuses):
        career_state = "In Flight"
    else:
        career_state = "Waiting"
    action = focus["action"] if focus else "No action today."
    action = re.sub(r"https?://\S+", "the employer portal", str(action))
    action = re.sub(r"\b[^\s@]+@[^\s@]+\b", "the saved contact", action)
    action = " ".join(action.split())[:180]
    return {
        "applications_in_flight": sum(status in IN_FLIGHT_STATUSES for status in statuses),
        "under_consideration": statuses.count("Under Consideration"),
        "interviews_scheduled": statuses.count("Interviewing"),
        "genuine_follow_ups_due": follow_ups_due,
        "todays_highest_leverage_action": action,
        "career_state": career_state,
    }
