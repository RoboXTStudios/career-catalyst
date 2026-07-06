"""Generate a static local dashboard from Career Catalyst project files."""

import html
import json
import os
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
from urllib.parse import quote

if __package__:
    from .application_tracker import (
        ACTIVE_STATUSES,
        DRAFT_STATUSES,
        HIDDEN_STATUSES,
        VALID_STATUSES,
        TrackerValidationError,
        get_record_status,
        normalize_tracker_value,
        tracker_company_keys,
        tracker_role_keys,
        validate_application_tracker,
        workflow_status_bucket,
    )
    from .dynamic_role_intelligence import get_effective_voice_profile
    from .job_freshness import detect_job_freshness
    from .job_source_registry import (
        SOURCE_TYPES,
        TRUST_LABELS,
        VERIFICATION_STATUSES,
        normalize_job_source,
    )
    from .filename_utils import short_company_name, short_role_name
    from .parse_job import JobParseError, parse_job_description
else:
    from application_tracker import (
        ACTIVE_STATUSES,
        DRAFT_STATUSES,
        HIDDEN_STATUSES,
        VALID_STATUSES,
        TrackerValidationError,
        get_record_status,
        normalize_tracker_value,
        tracker_company_keys,
        tracker_role_keys,
        validate_application_tracker,
        workflow_status_bucket,
    )
    from dynamic_role_intelligence import get_effective_voice_profile
    from job_freshness import detect_job_freshness
    from job_source_registry import (
        SOURCE_TYPES,
        TRUST_LABELS,
        VERIFICATION_STATUSES,
        normalize_job_source,
    )
    from filename_utils import short_company_name, short_role_name
    from parse_job import JobParseError, parse_job_description


PathInput = Union[str, Path]
ASSET_DIRECTORIES = (
    "exports/markdown",
    "exports/docx",
    "exports/messages",
    "exports/strategy_packs",
    "exports/followups",
    "exports/pdf",
)
LINK_ORDER = (
    "Job Description",
    "Tailored Markdown Resume",
    "Styled DOCX",
    "ATS DOCX",
    "Cover Letter",
    "Recruiter Message",
    "Hiring Manager Message",
    "Application Note",
    "Strategy Pack",
    "Follow-Up Materials",
    "Recruiter Follow-Up",
    "Hiring Manager Follow-Up",
    "Warm Contact Message",
    "Referral Ask",
    "PDF Resume",
    "Resume Text",
)
FOLLOW_UP_ASSET_LABELS = {
    "Follow-Up Materials",
    "Recruiter Follow-Up",
    "Hiring Manager Follow-Up",
    "Warm Contact Message",
    "Referral Ask",
}
MATCH_TIER_FILTERS = (
    "All", "Strong Match", "Good Match", "Stretch Match", "Weak Match", "Pass", "Not scored yet"
)
ACTION_FILTERS = ("All", "Generate Package", "Review First", "Pass")
STATUS_FILTERS = (
    "All",
    "Active",
    "Applied / Follow-up",
    "Reviewed",
    "Paused",
    "Pass",
    "Invalid/Hidden",
) + tuple(
    status
    for status in VALID_STATUSES
    if status
    not in {"Active", "Reviewed", "Paused", "Pass", "Invalid/Hidden"}
)
FOLLOW_UP_FILTERS = (
    "All", "Not due yet", "Due soon", "Due now", "Overdue", "Follow-up sent", "No applied date"
)
SOURCE_TYPE_FILTERS = ("All",) + SOURCE_TYPES
VERIFICATION_STATUS_FILTERS = ("All",) + VERIFICATION_STATUSES
TRUST_LABEL_FILTERS = ("All",) + TRUST_LABELS
DASHBOARD_MODES = ("All Mode", "Apply Mode", "Follow-Up Mode", "Review Mode", "Cleanup Mode")
SORT_OPTIONS = (
    "Match Score: High to Low",
    "Match Score: Low to High",
    "Verification Quality: Best to Worst",
    "Applied/Submitted Date: Newest First",
    "Applied/Submitted Date: Oldest First",
    "Follow-Up Due Date: Soonest First",
    "Opportunity Score: High to Low",
    "Company A-Z",
)


class DashboardGenerationError(Exception):
    """Raised when a dashboard cannot be generated from local project files."""


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _display_taxonomy(value: Any) -> str:
    label = str(value or "").replace("_", " ").title()
    return label.replace("Ai ", "AI ").replace("Gtm ", "GTM ")


def _parse_dashboard_date(value: Any) -> Optional[date]:
    clean = str(value or "").strip()
    if not clean:
        return None
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(clean, pattern).date()
        except ValueError:
            continue
    return None


def _applied_date(record: Dict[str, Any]) -> Optional[date]:
    for key in ("submitted_date", "applied_date", "application_date"):
        parsed = _parse_dashboard_date(record.get(key))
        if parsed:
            return parsed
    return None


def _follow_up_was_sent(record: Dict[str, Any]) -> bool:
    if get_record_status(record) == "Follow-up":
        return True
    for key in ("follow_up_sent", "followup_sent"):
        value = record.get(key)
        if value is True or str(value or "").strip().lower() in {"yes", "sent", "true", "complete", "completed"}:
            return True
    for key in ("follow_up_status", "followup_status"):
        if "sent" in str(record.get(key) or "").lower():
            return True
    if any(record.get(key) for key in ("follow_up_sent_date", "followup_sent_date", "last_follow_up_date")):
        return True
    history = record.get("follow_up_history") or record.get("followup_history")
    if isinstance(history, list) and history:
        return True
    return False


def calculate_follow_up_timing(
    record: Dict[str, Any], today: Optional[date] = None
) -> Dict[str, Any]:
    """Compute non-persistent follow-up guidance from existing tracker dates."""
    reference_date = today or date.today()
    applied = _applied_date(record)
    explicit_status = str(record.get("follow_up_status") or "").strip()
    if _follow_up_was_sent(record):
        status = "Follow-up sent"
    elif explicit_status:
        status = explicit_status
    elif applied is None:
        status = "No applied date"
    else:
        days = (reference_date - applied).days
        if days < 3:
            status = "Not due yet"
        elif days <= 5:
            status = "Due soon"
        elif days <= 10:
            status = "Due now"
        else:
            status = "Overdue"

    existing_suggestion = next(
        (
            record.get(key)
            for key in ("suggested_follow_up_date", "follow_up_due_date", "next_follow_up_date", "follow_up_date")
            if record.get(key)
        ),
        None,
    )
    suggested = str(existing_suggestion) if existing_suggestion else (
        (applied + timedelta(days=5)).isoformat() if applied else None
    )
    return {
        "days_since_applied": (reference_date - applied).days if applied else None,
        "suggested_follow_up_date": suggested,
        "follow_up_status": status,
    }


def enrich_dashboard_record(
    record: Dict[str, Any], today: Optional[date] = None
) -> Dict[str, Any]:
    enriched = dict(record)
    verification = normalize_job_source(enriched, today)
    for key, value in verification.items():
        if (
            key in {
                "source_name",
                "source_domain",
                "source_type",
                "source_trust_label",
                "verification_status",
                "canonical_apply_url",
                "canonical_apply_domain",
                "verification_notes",
                "source_confidence",
                "source_warnings",
                "recommended_next_step",
            }
            and verification.get("source_confidence") == "High"
            and (enriched.get("original_source_url") or enriched.get("official_url"))
        ):
            enriched[key] = value
        else:
            enriched.setdefault(key, value)
    if verification.get("posting_status") != "Open" and (
        not record.get("posting_date")
        or verification.get("freshness_risk") == "High"
    ):
        enriched["posting_status"] = verification["posting_status"]
    enriched.update(calculate_follow_up_timing(record, today))
    if get_record_status(enriched) in HIDDEN_STATUSES:
        enriched["follow_up_status"] = "Not applicable"
        enriched["suggested_follow_up_date"] = None
    return enriched


def _verification_quality(record: Dict[str, Any]) -> int:
    if record.get("verification_status") == "Stale / Closed Risk":
        return 9
    if record.get("verification_status") == "Verified Active":
        return 2
    order = (
        ("source_trust_label", "Direct Employer"),
        ("source_trust_label", "Verified Company Source"),
        ("verification_status", "Employer Source"),
        ("source_trust_label", "Industry Job Board"),
        ("verification_status", "Possibly Active"),
        ("source_trust_label", "Aggregator - Verify First"),
        ("source_trust_label", "Gated Source"),
        ("source_trust_label", "Unknown Source"),
        ("source_trust_label", "Cannot Verify"),
        ("source_trust_label", "Stale Risk"),
    )
    for index, (field, value) in enumerate(order):
        if record.get(field) == value:
            return index
    return 8


def _date_ordinal(record: Dict[str, Any], key: str = "applied") -> Optional[int]:
    parsed = (
        _applied_date(record)
        if key == "applied"
        else _parse_dashboard_date(record.get("suggested_follow_up_date"))
    )
    return parsed.toordinal() if parsed else None


def sort_dashboard_records(
    records: Iterable[Dict[str, Any]], sort_by: str = SORT_OPTIONS[0]
) -> List[Dict[str, Any]]:
    """Sort dashboard records with missing values last and stable company fallback."""
    values = list(records)
    company = lambda item: normalize_tracker_value(item.get("company"))
    if sort_by == "Verification Quality: Best to Worst":
        key = lambda item: (_verification_quality(item), -(item.get("match_score") or 0), company(item))
    elif sort_by == "Match Score: Low to High":
        key = lambda item: (item.get("match_score") is None, item.get("match_score") or 0, company(item))
    elif sort_by == "Applied/Submitted Date: Newest First":
        key = lambda item: (_date_ordinal(item) is None, -(_date_ordinal(item) or 0), company(item))
    elif sort_by == "Applied/Submitted Date: Oldest First":
        key = lambda item: (_date_ordinal(item) is None, _date_ordinal(item) or 0, company(item))
    elif sort_by == "Follow-Up Due Date: Soonest First":
        key = lambda item: (_date_ordinal(item, "follow_up") is None, _date_ordinal(item, "follow_up") or 0, company(item))
    elif sort_by == "Opportunity Score: High to Low":
        key = lambda item: (item.get("opportunity_score") is None, -(item.get("opportunity_score") or 0), company(item))
    elif sort_by == "Company A-Z":
        key = lambda item: (company(item), normalize_tracker_value(item.get("role")))
    else:
        key = lambda item: (
            item.get("match_score") is None,
            -(item.get("match_score") or 0),
            _date_ordinal(item) is None,
            -(_date_ordinal(item) or 0),
            company(item),
        )
    return sorted(values, key=key)


def _is_hidden(record: Dict[str, Any]) -> bool:
    status = get_record_status(record)
    if status in HIDDEN_STATUSES:
        return True
    return status not in VALID_STATUSES and record.get("show_on_dashboard") is False


def _is_invalid_hidden(record: Dict[str, Any]) -> bool:
    """Return true for invalid workflow records without conflating explicit Pass."""
    status = get_record_status(record)
    return status in {"Invalid", "Invalid/Hidden", "Rejected", "Archived"} or (
        status not in VALID_STATUSES and record.get("show_on_dashboard") is False
    )


def filter_dashboard_records(
    records: Iterable[Dict[str, Any]],
    match_tier: str = "All",
    recommended_action: str = "All",
    application_status: str = "All",
    follow_up_status: str = "All",
    search: str = "",
    source_type: str = "All",
    verification_status: str = "All",
    trust_label: str = "All",
) -> List[Dict[str, Any]]:
    """Apply safe dashboard filters without requiring complete tracker records."""
    query = normalize_tracker_value(search)
    filtered = []
    for record in records:
        tier = str(record.get("match_tier") or "Not scored yet")
        if match_tier != "All" and tier != match_tier:
            continue
        if recommended_action != "All" and record.get("recommended_action") != recommended_action:
            continue
        status = get_record_status(record)
        bucket = workflow_status_bucket(record)
        if application_status == "Invalid/Hidden" and not _is_invalid_hidden(record):
            continue
        if application_status in {
            "Active",
            "Applied / Follow-up",
            "Reviewed",
            "Paused",
            "Pass",
        } and bucket != application_status:
            continue
        if application_status not in {
            "All",
            "Invalid/Hidden",
            "Active",
            "Applied / Follow-up",
            "Reviewed",
            "Paused",
            "Pass",
        } and status != application_status:
            continue
        if follow_up_status != "All" and record.get("follow_up_status") != follow_up_status:
            continue
        if source_type != "All" and record.get("source_type", "Unknown Source") != source_type:
            continue
        if verification_status != "All" and record.get("verification_status", "Not Verified") != verification_status:
            continue
        if trust_label != "All" and record.get("source_trust_label", "Unknown Source") != trust_label:
            continue
        if query:
            searchable = " ".join(
                str(record.get(key) or "")
                for key in ("company", "role", "job_title", "company_category", "role_family", "source", "source_name", "source_type", "location")
            )
            if query not in normalize_tracker_value(searchable):
                continue
        filtered.append(record)
    return filtered


def _needs_cleanup(record: Dict[str, Any]) -> bool:
    status = get_record_status(record)
    freshness = str(record.get("freshness") or record.get("freshness_label") or "").lower()
    posting_status = str(record.get("posting_status") or "").lower()
    salary = str(record.get("salary_range") or "").strip().lower()
    return bool(
        record.get("match_tier") in {"Weak Match", "Pass"}
        or record.get("recommended_action") == "Pass"
        or _is_hidden(record)
        or status == "Paused"
        or "closed" in posting_status
        or any(value in freshness for value in ("stale", "unknown"))
        or salary in {"", "not disclosed", "unknown"}
        or not record.get("source")
        or not record.get("location")
        or record.get("verification_status") in {
            "Aggregator Only", "Cannot Verify", "Not Verified", "Stale / Closed Risk"
        }
        or record.get("source_trust_label") == "Unknown Source"
    )


def select_dashboard_mode(
    records: Iterable[Dict[str, Any]], mode: str = "All Mode"
) -> List[Dict[str, Any]]:
    values = list(records)
    if mode == "Apply Mode":
        return [
            item for item in values
            if item.get("match_tier") in {"Strong Match", "Good Match"}
            and item.get("recommended_action") == "Generate Package"
            and workflow_status_bucket(item) == "Active"
            and not _is_hidden(item)
            and str(item.get("posting_status") or "").lower() != "closed"
            and item.get("verification_status") != "Stale / Closed Risk"
        ]
    if mode == "Follow-Up Mode":
        return [
            item for item in values
            if workflow_status_bucket(item) == "Applied / Follow-up"
            and not _is_hidden(item)
        ]
    if mode == "Review Mode":
        return [
            item
            for item in values
            if (
                workflow_status_bucket(item) == "Reviewed"
                or item.get("match_tier") == "Stretch Match"
                or item.get("recommended_action") == "Review First"
            )
            and not _is_hidden(item)
        ]
    if mode == "Cleanup Mode":
        return [item for item in values if _needs_cleanup(item)]
    return [item for item in values if not _is_hidden(item)]


def source_verification_caution(record: Dict[str, Any]) -> str:
    """Return concise dashboard caution copy for sources that need intervention."""
    status = str(record.get("verification_status") or "Not Verified")
    source_type = str(record.get("source_type") or "Unknown Source")
    trust_label = str(record.get("source_trust_label") or "Unknown Source")
    if status != "Stale / Closed Risk" and (
        source_type in {"Direct Employer", "Employer ATS"}
        or status == "Employer Source"
        or trust_label in {"Direct Employer", "Verified Company Source"}
    ):
        return ""
    if status == "Aggregator Only":
        return "Verify on the employer site before generating a package or applying."
    if status == "Industry Board" or source_type in {
        "Industry Job Board",
        "Gaming Industry Job Board",
        "Music Industry Job Board",
        "Entertainment Job Board",
        "Startup / Tech Job Board",
    }:
        return "Verify on employer site before generating package or applying."
    if status == "Gated / Limited Visibility":
        return "Limited visibility: verify the employer listing manually before investing time."
    if status == "Stale / Closed Risk":
        return "Posting may be stale or closed: verify it is active before generating a package."
    if status in {"Cannot Verify", "Not Verified"} or source_type == "Unknown Source":
        return "Source not verified: confirm the role and apply path manually."
    return ""


def _record_label(record: Dict[str, Any]) -> str:
    return f"{record.get('company') or 'Unknown company'} — {record.get('role') or record.get('job_title') or 'Unknown role'}"


def recommended_next_steps(
    records: Iterable[Dict[str, Any]], mode: str = "All Mode"
) -> List[str]:
    """Return practical, mode-specific actions for the visible dashboard records."""
    values = sort_dashboard_records(records)
    empty = {
        "Apply Mode": "No strong unapplied matches found.",
        "Follow-Up Mode": "No roles need follow-up right now.",
        "Review Mode": "No stretch or review-first roles found.",
        "Cleanup Mode": "No cleanup items found.",
        "All Mode": "No roles match the current dashboard filters.",
    }
    if not values:
        return [empty.get(mode, empty["All Mode"])]

    if mode == "Apply Mode":
        steps = []
        ordered = sorted(
            values,
            key=lambda item: (
                _verification_quality(item),
                -(item.get("match_score") or 0),
                -(item.get("opportunity_score") or 0),
                normalize_tracker_value(item.get("company")),
            ),
        )
        for item in ordered[:3]:
            caution = source_verification_caution(item)
            if item.get("verification_status") == "Aggregator Only":
                steps.append(f"Verify on employer site before package generation: {_record_label(item)}.")
                continue
            if item.get("verification_status") == "Industry Board":
                steps.append(f"Verify on employer site before generating package or applying: {_record_label(item)}.")
                continue
            if caution:
                steps.append(f"{caution} {_record_label(item)}.")
                continue
            if not item.get("_has_package"):
                action = "Generate package for"
            elif get_record_status(item) == "Reviewed":
                action = "Apply to"
            else:
                action = "Review and apply to"
            steps.append(f"{action} {_record_label(item)} ({item.get('match_tier')}, {item.get('match_score', 'Not scored')}/100).")
        return steps
    if mode == "Follow-Up Mode":
        priority = {"Overdue": 0, "Due now": 1, "Due soon": 2}
        ordered = sorted(values, key=lambda item: (priority.get(str(item.get("follow_up_status")), 9), _date_ordinal(item, "follow_up") or 9999999))
        steps = []
        for item in ordered[:5]:
            follow_up_state = str(item.get("follow_up_status") or "Not due yet")
            if follow_up_state == "Follow-up sent":
                steps.append(
                    f"Follow-up sent: {_record_label(item)}. Monitor for a response."
                )
                continue
            materials = item.get("_follow_up_materials_status")
            material_action = (
                "Use existing follow-up materials."
                if materials == "Available"
                else "Generate follow-up materials."
                if materials == "Missing"
                else "Follow-up materials not verified."
            )
            has_contact = any(
                item.get(key)
                for key in (
                    "recruiter_name", "recruiter_contact", "recruiter_email",
                    "hiring_manager_name", "hiring_manager_contact", "hiring_manager_email",
                )
            )
            contact_action = (
                "Send the recruiter or hiring manager follow-up."
                if has_contact
                else "Manually verify a recruiter or hiring manager contact."
            )
            source_action = (
                " Verify the employer record before follow-up."
                if item.get("verification_status") == "Aggregator Only"
                else ""
            )
            steps.append(
                f"{follow_up_state}: {_record_label(item)}. "
                f"{material_action} {contact_action}{source_action}"
            )
        return steps
    if mode == "Review Mode":
        steps = []
        for item in values[:5]:
            reason = str(
                (item.get("match_gaps") or [item.get("match_summary") or "Human judgment is needed."])[0]
            )
            upside = str(
                (item.get("match_strengths") or ["Company, industry, and strategic-doorway value may justify the stretch."])[0]
            )
            source_context = (
                " Direct or industry source supports review."
                if item.get("source_trust_label") in {"Direct Employer", "Verified Company Source", "Industry Job Board"}
                else " Verify the source before pursuing this stretch role."
            )
            steps.append(f"Review {_record_label(item)}: {reason} Weigh against: {upside}{source_context}")
        return steps
    if mode == "Cleanup Mode":
        steps = []
        for item in values[:5]:
            status = get_record_status(item)
            if status == "Pass":
                action = "Already passed; no action needed unless you want to reopen"
            elif _is_invalid_hidden(item):
                action = "Hidden from active workflow"
            elif status == "Paused":
                action = "Review later or mark pass"
            elif item.get("verification_status") == "Stale / Closed Risk":
                action = "Pass unless manually verified active"
            elif item.get("verification_status") in {"Aggregator Only", "Cannot Verify", "Not Verified"} or item.get("source_trust_label") == "Unknown Source":
                action = "Verify manually, then hide or pass if unresolved"
            elif item.get("match_tier") == "Pass":
                action = "Review the pass recommendation or keep active"
            elif str(item.get("freshness") or "").lower() in {"stale", "unknown freshness"}:
                action = "Verify posting freshness"
            elif not item.get("salary_range") or not item.get("source"):
                action = "Verify missing salary/source fields"
            else:
                action = "Pause or manually verify"
            steps.append(f"{action}: {_record_label(item)}.")
        return steps

    unapplied = next(
        (
            item
            for item in values
            if workflow_status_bucket(item) in {"Active", "Reviewed"}
        ),
        None,
    )
    urgent = next((item for item in values if item.get("follow_up_status") in {"Overdue", "Due now", "Due soon"}), None)
    if urgent:
        steps = [f"Act first on {_record_label(urgent)}; its follow-up is {urgent.get('follow_up_status').lower()}." ]
    elif unapplied:
        steps = [f"Act first on {_record_label(unapplied)}, the highest match not yet applied."]
    else:
        steps = [f"Act first on {_record_label(values[0])}, the highest-priority visible role."]
    if unapplied:
        steps.append(f"Highest match not yet applied: {_record_label(unapplied)} ({unapplied.get('match_score', 'Not scored')}/100).")
    if urgent:
        steps.append(f"Most urgent follow-up: {_record_label(urgent)} — {urgent.get('follow_up_status')}.")
    cleanup = next((item for item in values if _needs_cleanup(item)), None)
    if cleanup:
        steps.append(f"Verify cleanup item: {_record_label(cleanup)}.")
    return steps


def record_posting_url(record: Dict[str, Any]) -> Optional[str]:
    """Return the first stored posting URL without inventing a destination."""
    for key in (
        "canonical_apply_url",
        "original_source_url",
        "apply_url",
        "source_url",
        "job_url",
        "official_url",
    ):
        value = str(record.get(key) or "").strip()
        if value.startswith(("https://", "http://")):
            return value
    return None


def record_dashboard_reference(record: Dict[str, Any]) -> str:
    """Return a stable id, slug, or normalized company/title reference."""
    for field in ("prospect_id", "record_id", "id"):
        value = str(record.get(field) or "").strip()
        if value:
            return value
    for field in ("stable_slug", "prospect_slug", "record_slug", "slug"):
        value = str(record.get(field) or "").strip()
        if value:
            return value
    company_key = re.sub(
        r"[^a-z0-9]+", "-", str(record.get("company") or "").lower()
    ).strip("-")
    role_key = re.sub(
        r"[^a-z0-9]+",
        "-",
        str(record.get("role") or record.get("job_title") or "").lower(),
    ).strip("-")
    return f"role:{company_key}:{role_key}" if company_key and role_key else ""


def structured_recommended_next_steps(
    records: Iterable[Dict[str, Any]], mode: str = "All Mode"
) -> List[Dict[str, Any]]:
    """Return actionable next-step records keyed by durable tracker identity."""
    values = sort_dashboard_records(records)
    steps: List[Dict[str, Any]] = []
    for priority, record in enumerate(values[:5], start=1):
        bucket = workflow_status_bucket(record)
        if bucket == "Pass":
            action_type = "passed"
        elif bucket == "Hidden / Invalid":
            action_type = "hidden"
        elif bucket == "Paused":
            action_type = "review_later"
        elif mode == "Follow-Up Mode":
            action_type = "follow_up"
        elif mode == "Apply Mode" and not record.get("_has_package"):
            action_type = "generate_package"
        elif mode == "Cleanup Mode":
            action_type = "verify"
        else:
            action_type = "review"
        recommendation = recommended_next_steps([record], mode)[0]
        steps.append(
            {
                "tracker_id": record_dashboard_reference(record),
                "company": str(record.get("company") or "Unknown company"),
                "title": str(record.get("role") or record.get("job_title") or "Unknown role"),
                "recommendation": recommendation,
                "action_type": action_type,
                "priority": priority,
                "posting_url": record_posting_url(record),
                "material_paths": dict(record.get("_material_paths") or {}),
            }
        )
    return steps


def _first_heading(text: str) -> Optional[str]:
    for line in text.splitlines():
        match = re.match(r"^\s*#\s+(.+?)\s*$", line)
        if match:
            return match.group(1).strip()
    return None


def _scan_files(root: Path, relative_directory: str, suffixes: Iterable[str]) -> List[Path]:
    directory = root / relative_directory
    if not directory.is_dir():
        return []

    allowed_suffixes = {suffix.lower() for suffix in suffixes}
    return sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in allowed_suffixes
    )


def _load_jobs(root: Path) -> List[Dict[str, Any]]:
    packages: List[Dict[str, Any]] = []
    for path in _scan_files(root, "jobs", (".md", ".txt")):
        if path.name.lower() == "readme.md":
            continue

        parsed = parse_job_description(path)
        role = parsed.get("job_title") or _first_heading(parsed.get("raw_text", ""))
        company = parsed.get("company")
        if not role and not company:
            continue

        intelligence = get_effective_voice_profile(
            company_name=str(company or ""),
            job_title=str(role or ""),
            job_description=str(parsed.get("raw_text") or ""),
            source_url=str(parsed.get("source_url") or ""),
        )

        packages.append(
            {
                "company": str(company or "Company not listed"),
                "role": str(role or "Role not listed"),
                "location": parsed.get("location"),
                "salary_range": parsed.get("salary_range"),
                "freshness": detect_job_freshness(str(parsed.get("raw_text") or "")),
                "company_category": intelligence["company_category"],
                "role_family": intelligence["role_family"],
                "company_voice_profile": intelligence["profile_name"],
                "company_voice_source": intelligence["source"],
                "tracker_id": _tracker_id_from_job(parsed.get("raw_text", "")),
                "job_path": path,
                "tracker": {},
                "files": {"Job Description": path},
            }
        )
    return packages


def _tracker_id_from_job(raw_text: str) -> Optional[str]:
    match = re.search(r"^\s*Tracker ID\s*:\s*(.+?)\s*$", raw_text, flags=re.MULTILINE | re.IGNORECASE)
    return match.group(1).strip() if match else None


def _matching_package(
    packages: List[Dict[str, Any]], application: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    tracker_id = str(application.get("id") or "")
    if tracker_id:
        id_matches = [
            package for package in packages if package.get("tracker_id") == tracker_id
        ]
        if len(id_matches) == 1:
            return id_matches[0]

    company_key = normalize_tracker_value(application.get("company"))
    role_key = normalize_tracker_value(application.get("role"))
    exact_matches = [
        package
        for package in packages
        if normalize_tracker_value(package["company"]) == company_key
        and normalize_tracker_value(package["role"]) == role_key
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]

    company_keys = tracker_company_keys(application)
    role_keys = tracker_role_keys(application)
    alias_matches = [
        package
        for package in packages
        if normalize_tracker_value(package["company"]) in company_keys
        and normalize_tracker_value(package["role"]) in role_keys
    ]
    if len(alias_matches) == 1:
        return alias_matches[0]

    role_matches = [
        package
        for package in packages
        if normalize_tracker_value(package["role"]) in role_keys
    ]
    if len(role_matches) == 1:
        return role_matches[0]
    return None


def _merge_tracker(packages: List[Dict[str, Any]], tracker: List[Dict[str, Any]]) -> None:
    for application in tracker:
        company = str(application.get("company") or "Company not listed")
        role = str(application.get("role") or "Role not listed")
        package = _matching_package(packages, application)
        if package is None:
            intelligence = get_effective_voice_profile(
                company_name=company,
                job_title=role,
                job_description=str(application.get("job_description") or ""),
                source_url=str(application.get("official_url") or ""),
            )
            package = {
                "company": company,
                "role": role,
                "location": application.get("location"),
                "salary_range": application.get("salary_range"),
                "company_category": intelligence["company_category"],
                "role_family": intelligence["role_family"],
                "company_voice_profile": intelligence["profile_name"],
                "company_voice_source": intelligence["source"],
                "tracker_id": application.get("id"),
                "job_path": None,
                "tracker": {},
                "files": {},
            }
            packages.append(package)
        if not package.get("tracker"):
            package["tracker"] = application
            package["tracker_id"] = application.get("id")


def _asset_label(path: Path) -> Optional[str]:
    name = path.name.lower()
    parent = path.parent.name

    if parent == "markdown" and name.endswith("_resume.md"):
        return "Tailored Markdown Resume"
    if parent == "pdf" and name.endswith("_resume.pdf"):
        return "PDF Resume"
    if parent == "pdf" and name.endswith("_resume.txt"):
        return "Resume Text"
    if parent == "docx" and name.endswith("_styled.docx"):
        return "Styled DOCX"
    if parent == "docx" and name.endswith("_ats.docx"):
        return "ATS DOCX"
    if parent == "messages" and (
        name.endswith("_cover_letter.md") or name.endswith("_coverletter.md")
    ):
        return "Cover Letter"
    if parent == "messages" and (
        name.endswith("_recruiter_message.md") or name.endswith("_recruitermessage.md")
    ):
        return "Recruiter Message"
    if parent == "messages" and (
        name.endswith("_hiring_manager_message.md")
        or name.endswith("_hiringmanagermessage.md")
    ):
        return "Hiring Manager Message"
    if parent == "messages" and (
        name.endswith("_application_note.md") or name.endswith("_applicationnote.md")
    ):
        return "Application Note"
    if parent == "strategy_packs" and (
        name.endswith("_strategy_pack.md") or name.endswith("_strategypack.md")
    ):
        return "Strategy Pack"
    if parent == "strategy_packs" and (
        name.endswith("_interview_prep.md") or name.endswith("_interviewprep.md")
    ):
        return "Interview Prep"
    if parent == "strategy_packs" and (
        name.endswith("_package_summary.md") or name.endswith("_packagesummary.md")
    ):
        return "Package Summary"
    if parent == "followups" and (
        name.endswith("_followup_strategy.md")
        or name.endswith("_followupstrategy.md")
    ):
        return "Follow-Up Materials"
    if parent == "followups" and (
        name.endswith("_recruiter_followup.md")
        or name.endswith("_recruiterfollowup.md")
    ):
        return "Recruiter Follow-Up"
    if parent == "followups" and (
        name.endswith("_hiring_manager_followup.md")
        or name.endswith("_hiringmanagerfollowup.md")
    ):
        return "Hiring Manager Follow-Up"
    if parent == "followups" and (
        name.endswith("_warm_contact_message.md")
        or name.endswith("_warmcontactmessage.md")
    ):
        return "Warm Contact Message"
    if parent == "followups" and (
        name.endswith("_referral_ask.md") or name.endswith("_referralask.md")
    ):
        return "Referral Ask"
    return None


def _asset_match_key(value: Any) -> str:
    """Normalize both snake-case and compact generated names for asset matching."""
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def _package_for_asset(
    path: Path, packages: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    file_key = _asset_match_key(path.stem)
    candidates = [
        package
        for package in packages
        if any(
            key in file_key
            for key in (
                _asset_match_key(package["company"]),
                _asset_match_key(short_company_name(package["company"])),
            )
            if key
        )
    ]
    if not candidates:
        return None

    exact_role_matches = [
        package
        for package in candidates
        if any(
            key in file_key
            for key in (
                _asset_match_key(package["role"]),
                _asset_match_key(short_role_name(package["role"])),
            )
            if key
        )
    ]
    if len(exact_role_matches) == 1:
        return exact_role_matches[0]

    tracked_matches = [package for package in candidates if package.get("tracker")]
    if len(tracked_matches) == 1:
        return tracked_matches[0]

    if len(candidates) == 1:
        return candidates[0]
    return None


def _attach_assets(root: Path, packages: List[Dict[str, Any]]) -> List[Tuple[str, Path]]:
    """Attach the newest matching asset and retain older duplicates as archive candidates."""
    unassigned: List[Tuple[str, Path]] = []
    matches: Dict[Tuple[int, str], List[Path]] = {}
    packages_by_identity = {id(package): package for package in packages}
    for relative_directory in ASSET_DIRECTORIES:
        for path in _scan_files(
            root, relative_directory, (".md", ".docx", ".txt", ".pdf")
        ):
            label = _asset_label(path)
            if label is None:
                continue
            package = _package_for_asset(path, packages)
            if package is None:
                unassigned.append((label, path))
                continue
            matches.setdefault((id(package), label), []).append(path)
    for (package_identity, label), paths in matches.items():
        package = packages_by_identity[package_identity]
        existing = package["files"].get(label)
        candidates = list(dict.fromkeys([*(paths), *([existing] if existing else [])]))
        current = max(
            candidates,
            key=lambda path: (path.stat().st_mtime, path.name.lower()),
        )
        package["files"][label] = current
        for older in candidates:
            if older == current:
                continue
            package.setdefault("archive_candidates", []).append(
                {
                    "path": older,
                    "material_type": label,
                    "current_path": current,
                    "reason": "Older duplicate for the same role and material type.",
                }
            )
    return unassigned


def archived_materials_exist(root: Path, tracker_id: str) -> bool:
    """Check archive manifests without treating archived paths as current assets."""
    archive_root = root / "exports" / "archive"
    if not archive_root.is_dir() or not tracker_id:
        return False
    for manifest_path in archive_root.glob("*/archive_manifest.json"):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        entries = payload.get("archived", []) if isinstance(payload, dict) else []
        if any(str(entry.get("tracker_id") or "") == tracker_id for entry in entries):
            return True
    return False


def prepare_dashboard_records(
    applications: Iterable[Dict[str, Any]],
    packages: Optional[Dict[str, Dict[str, Any]]] = None,
    today: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Enrich tracker rows with package awareness and dynamic dashboard fields."""
    package_map = packages or {}
    records = []
    for application in applications:
        tracker_id = str(application.get("id") or "")
        package = package_map.get(tracker_id, {})
        record = dict(application)
        for key in ("location", "salary_range", "company_category", "role_family"):
            if not record.get(key) and package.get(key):
                record[key] = package[key]
        files = package.get("files") if isinstance(package, dict) else None
        if isinstance(files, dict):
            record["_material_paths"] = {
                str(label): str(path) for label, path in files.items()
            }
            record["_archive_candidate_count"] = len(
                package.get("archive_candidates", [])
            )
            record["_archived_materials_available"] = bool(
                package.get("archived_materials_available")
            )
            follow_up_available = bool(FOLLOW_UP_ASSET_LABELS.intersection(files))
            outreach_available = any(
                label in files
                for label in ("Recruiter Message", "Hiring Manager Message", "Application Note")
            )
            status = get_record_status(record)
            if status in HIDDEN_STATUSES:
                material_state = "Not applicable"
                material_label = "Cleanup state — follow-up not applicable"
            elif status in ACTIVE_STATUSES:
                material_state = "Available" if follow_up_available else "Missing"
                material_label = f"Follow-up materials {material_state.lower()}"
            elif follow_up_available:
                material_state = "Available"
                material_label = "Outreach materials available"
            elif outreach_available:
                material_state = "Available"
                material_label = "Application messages available"
            elif status == "Paused":
                material_state = "Missing"
                material_label = "Outreach materials missing"
            else:
                material_state = "Missing"
                material_label = "Application messages missing"
            record["_follow_up_materials_status"] = material_state
            record["_materials_availability_label"] = material_label
            record["_has_package"] = any(
                label != "Job Description" and label not in FOLLOW_UP_ASSET_LABELS
                for label in files
            )
        else:
            record["_follow_up_materials_status"] = "Not verified"
            record["_materials_availability_label"] = "Materials not verified"
            record["_has_package"] = bool(record.get("package_quality"))
        records.append(enrich_dashboard_record(record, today))
    return records


def _enrich_package_trackers(
    packages: List[Dict[str, Any]], today: Optional[date] = None
) -> None:
    package_map = {
        str(package.get("tracker_id")): package
        for package in packages
        if package.get("tracker_id")
    }
    applications = [package["tracker"] for package in packages if package.get("tracker")]
    enriched = {
        str(record.get("id")): record
        for record in prepare_dashboard_records(applications, package_map, today)
    }
    for package in packages:
        tracker_id = str(package.get("tracker_id") or "")
        if tracker_id in enriched:
            package["tracker"] = enriched[tracker_id]


def _relative_href(path: Path, dashboard_directory: Path) -> str:
    relative_path = os.path.relpath(path, dashboard_directory)
    return quote(Path(relative_path).as_posix(), safe="/._-")


def _status_class(status: str) -> str:
    known_statuses = {
        "applied",
        "archived",
        "drafted",
        "follow_up",
        "interviewing",
        "invalid",
        "invalid_hidden",
        "pass",
        "paused",
        "rejected",
        "reviewed",
    }
    normalized = _slug(status)
    return normalized if normalized in known_statuses else "default"


def _render_badges(tracker: Dict[str, Any]) -> str:
    badges = []
    status = get_record_status(tracker) if tracker else ""
    priority = str(tracker.get("priority") or "").strip()
    if status:
        badges.append(
            f'<span class="badge status-{_status_class(status)}">{html.escape(status)}</span>'
        )
    if priority:
        badges.append(f'<span class="badge priority">{html.escape(priority)} priority</span>')
    for value in (tracker.get("match_tier"), tracker.get("verification_status")):
        if value:
            badges.append(f'<span class="badge">{html.escape(str(value))}</span>')
    return "".join(badges)


def _render_metadata(package: Dict[str, Any], primary_only: bool = False) -> str:
    tracker = package.get("tracker", {})
    source_display = tracker.get("source_name")
    if not source_display or source_display == "Unknown":
        source_display = tracker.get("source") or "Unknown"
    values = (
        ("Location", package.get("location")),
        ("Work arrangement", tracker.get("work_arrangement")),
        ("Salary", tracker.get("salary_range") or package.get("salary_range")),
        ("Freshness", tracker.get("freshness_label") or tracker.get("freshness") or package.get("freshness", {}).get("label")),
        ("Freshness Risk", tracker.get("freshness_risk") or "Unknown"),
        ("Posting Status", tracker.get("posting_status") or "Verify manually"),
        ("Opportunity score", f"{tracker.get('opportunity_score')}/100" if tracker.get("opportunity_score") is not None else None),
        ("Recommendation", tracker.get("apply_recommendation")),
        ("Source", source_display),
        ("Source Type", tracker.get("source_type") or "Unknown Source"),
        ("Trust Label", tracker.get("source_trust_label") or "Unknown Source"),
        ("Verification Status", tracker.get("verification_status") or "Not Verified"),
        ("Source Confidence", tracker.get("source_confidence")),
        ("Canonical Apply URL", tracker.get("canonical_apply_url")),
        ("Applied", tracker.get("submitted_date") or tracker.get("applied_date") or "No applied date"),
        (
            "Days since applied",
            tracker.get("days_since_applied")
            if tracker.get("days_since_applied") is not None
            else "Unknown",
        ),
        ("Follow-up", tracker.get("follow_up_status") or "No applied date"),
        ("Suggested follow-up", tracker.get("suggested_follow_up_date") or "Verify manually"),
        ("Materials availability", tracker.get("_materials_availability_label") or "Materials not verified"),
        (
            "Company category",
            _display_taxonomy(
                tracker.get("company_category")
                or package.get("company_category")
            )
            if tracker.get("company_category") or package.get("company_category")
            else None,
        ),
        (
            "Role family",
            _display_taxonomy(tracker.get("role_family") or package.get("role_family"))
            if tracker.get("role_family") or package.get("role_family")
            else None,
        ),
    )
    items = []
    for label, value in values:
        if primary_only and label not in {
            "Location",
            "Work arrangement",
            "Salary",
            "Source Type",
            "Verification Status",
            "Applied",
            "Follow-up",
        }:
            continue
        if not value:
            continue
        rendered_value = html.escape(str(value))
        if label == "Canonical Apply URL":
            # Keep the static dashboard dependency-free while displaying the full URL.
            rendered_value = rendered_value.replace(":", "&#58;")
        items.append(
            f'<div class="meta-item"><dt>{label}</dt><dd>{rendered_value}</dd></div>'
        )
    if not items:
        return ""
    return f'<dl class="metadata">{"".join(items)}</dl>'


def _render_match_score(
    tracker: Dict[str, Any], include_details: bool = True
) -> str:
    score = tracker.get("match_score")
    if score is None:
        return (
            '<section class="match-gate match-unscored" aria-label="Match Score">'
            '<div><span class="match-label">Match Score</span>'
            '<strong>Not scored yet</strong></div>'
            '<p>Re-import or update this role to calculate the pre-package recommendation.</p>'
            '</section>'
        )

    tier = str(tracker.get("match_tier") or "Not scored yet")
    action = str(tracker.get("recommended_action") or "Review First")
    confidence = str(tracker.get("confidence") or "Low")
    summary = str(tracker.get("match_summary") or "Review the fit before generating a package.")
    strengths = tracker.get("match_strengths") or []
    gaps = tracker.get("match_gaps") or []

    def render_list(label: str, values: Any) -> str:
        if not isinstance(values, list) or not values:
            return ""
        items = "".join(f"<li>{html.escape(str(value))}</li>" for value in values)
        return f'<div class="match-list"><h4>{label}</h4><ul>{items}</ul></div>'

    details = (
        '<div class="match-details">'
        f'{render_list("Top strengths", strengths)}'
        f'{render_list("Gaps / cautions", gaps)}'
        '</div>'
        if include_details
        else ""
    )
    return (
        '<section class="match-gate" aria-label="Match Score">'
        '<div class="match-score-row">'
        '<div><span class="match-label">Match Score</span>'
        f'<strong class="match-number">{html.escape(str(score))}<small>/100</small></strong></div>'
        f'<span class="match-tier">{html.escape(tier)}</span>'
        '</div>'
        '<div class="match-action">'
        f'<span>Recommended action</span><strong>{html.escape(action)}</strong>'
        f'<span>Confidence: {html.escape(confidence)}</span>'
        '</div>'
        f'<p class="match-summary">{html.escape(summary)}</p>'
        f"{details}</section>"
    )


def _render_notes(tracker: Dict[str, Any]) -> str:
    rows = []
    for label, key in (("Notes", "notes"), ("Next action", "next_action")):
        value = tracker.get(key)
        if value:
            rows.append(
                '<div class="tracker-row">'
                f'<span class="tracker-label">{label}</span>'
                f'<p>{html.escape(str(value))}</p>'
                "</div>"
            )
    verification_notes = tracker.get("verification_notes") or "Verify manually"
    rows.append(
        '<div class="tracker-row">'
        '<span class="tracker-label">Verification notes</span>'
        f'<p>{html.escape(str(verification_notes))}</p></div>'
    )
    caution = source_verification_caution(tracker)
    if caution:
        rows.append(f'<p class="source-caution">{html.escape(caution)}</p>')
    warnings = []
    for key in ("field_warnings", "source_warnings"):
        values = tracker.get(key)
        if isinstance(values, list):
            warnings.extend(str(value) for value in values if value)
        elif values:
            warnings.append(str(values))
    warnings = list(dict.fromkeys(warnings))
    if warnings:
        items = "".join(f"<li>{html.escape(warning)}</li>" for warning in warnings)
        rows.append(
            '<div class="tracker-row"><span class="tracker-label">Field warnings</span>'
            f"<ul>{items}</ul></div>"
        )
    return "".join(rows)


def _render_links(files: Dict[str, Path], dashboard_directory: Path) -> str:
    links = []
    for label in LINK_ORDER:
        path = files.get(label)
        if path is None:
            continue
        href = html.escape(_relative_href(path, dashboard_directory), quote=True)
        links.append(
            f'<a class="file-link" href="{href}" target="_blank" rel="noopener">'
            f"{html.escape(label)}</a>"
        )
    if not links:
        return '<p class="empty-links">No generated files yet.</p>'
    return f'<div class="file-links">{"".join(links)}</div>'


def _render_package(package: Dict[str, Any], dashboard_directory: Path) -> str:
    tracker = package.get("tracker", {})
    return (
        '<article class="application-card">'
        '<div class="application-heading">'
        '<div class="application-title">'
        f'<p class="company">{html.escape(package["company"])}</p>'
        f'<h3>{html.escape(package["role"])}</h3>'
        "</div>"
        f'<div class="badges">{_render_badges(tracker)}</div>'
        "</div>"
        f"{_render_match_score(tracker, include_details=False)}"
        f"{_render_metadata(package, primary_only=True)}"
        f"{_render_notes(tracker)}"
        '<div class="materials"><h4>Application materials</h4>'
        f'{_render_links(package["files"], dashboard_directory)}</div>'
        "</article>"
    )


def _render_unassigned(
    files: List[Tuple[str, Path]], dashboard_directory: Path
) -> str:
    if not files:
        return ""
    links = []
    for label, path in files:
        href = html.escape(_relative_href(path, dashboard_directory), quote=True)
        links.append(
            f'<a class="file-link" href="{href}" target="_blank" rel="noopener">'
            f"{html.escape(label)}: {html.escape(path.name)}</a>"
        )
    return (
        '<section class="unassigned" aria-labelledby="unassigned-heading">'
        '<h2 id="unassigned-heading">Other Generated Files</h2>'
        f'<div class="file-links">{"".join(links)}</div></section>'
    )


def _partition_packages(
    packages: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List[Dict[str, Any]]] = {
        "active": [],
        "applied": [],
        "reviewed": [],
        "paused": [],
        "pass": [],
        "hidden": [],
    }
    for package in packages:
        tracker = package.get("tracker", {})
        bucket = workflow_status_bucket(tracker) if tracker else "Active"
        target = {
            "Active": "active",
            "Applied / Follow-up": "applied",
            "Reviewed": "reviewed",
            "Paused": "paused",
            "Pass": "pass",
            "Hidden / Invalid": "hidden",
        }[bucket]
        groups[target].append(package)
    for key, values in groups.items():
        ordered_trackers = sort_dashboard_records(
            [
                {
                    **package,
                    **package.get("tracker", {}),
                    "_package_identity": id(package),
                }
                for package in values
            ]
        )
        by_identity = {id(package): package for package in values}
        groups[key] = [by_identity[item["_package_identity"]] for item in ordered_trackers]
    return groups


def _summary_counts(
    root: Path,
    groups: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, int]:
    return {
        "Total": sum(len(values) for values in groups.values()),
        "Active": len(groups["active"]),
        "Applied / Follow-up": len(groups["applied"]),
        "Reviewed": len(groups["reviewed"]),
        "Paused": len(groups["paused"]),
        "Pass": len(groups["pass"]),
        "Hidden / Invalid": len(groups["hidden"]),
    }


def _render_group(
    title: str,
    group_id: str,
    packages: List[Dict[str, Any]],
    dashboard_directory: Path,
) -> str:
    role_label = "role" if len(packages) == 1 else "roles"
    cards = "".join(
        _render_package(package, dashboard_directory) for package in packages
    )
    if not cards:
        cards = '<p class="empty-state">No roles in this section.</p>'
    return (
        f'<section class="application-group" id="{group_id}" '
        f'aria-labelledby="{group_id}-heading">'
        '<div class="group-heading">'
        f'<h3 class="group-title" id="{group_id}-heading">{html.escape(title)}</h3>'
        f'<span class="section-count">{len(packages)} {role_label}</span>'
        "</div>"
        f'<div class="application-list">{cards}</div>'
        "</section>"
    )


def _render_hidden_group(
    packages: List[Dict[str, Any]], dashboard_directory: Path
) -> str:
    if not packages:
        return ""
    cards = "".join(
        _render_package(package, dashboard_directory) for package in packages
    )
    return (
        '<details class="hidden-group" id="hidden-invalid-roles">'
        f'<summary>Hidden / Invalid Roles ({len(packages)})</summary>'
        f'<div class="application-list hidden-list">{cards}</div>'
        "</details>"
    )


def _package_record(package: Dict[str, Any]) -> Dict[str, Any]:
    return {**package, **package.get("tracker", {})}


def _render_priority_queue(
    title: str, queue_id: str, packages: List[Dict[str, Any]], empty_message: str
) -> str:
    records = sort_dashboard_records([_package_record(package) for package in packages])
    if records:
        items = "".join(
            '<li><strong>'
            f'{html.escape(str(item.get("company") or "Unknown company"))} — '
            f'{html.escape(str(item.get("role") or "Unknown role"))}</strong>'
            '<span>'
            f'Match: {html.escape(str(item.get("match_score") if item.get("match_score") is not None else "Not scored yet"))}'
            f' · {html.escape(str(item.get("match_tier") or "Not scored yet"))}'
            f' · Action: {html.escape(str(item.get("recommended_action") or "Verify manually"))}'
            f' · Follow-up: {html.escape(str(item.get("follow_up_status") or "No applied date"))}'
            '</span></li>'
            for item in records
        )
    else:
        items = f'<li class="empty-state">{html.escape(empty_message)}</li>'
    return (
        f'<section class="priority-queue" id="{queue_id}">'
        f'<h3>{html.escape(title)}</h3><ul>{items}</ul></section>'
    )


def _render_priority_sections(groups: Dict[str, List[Dict[str, Any]]]) -> str:
    if "draft" in groups:
        visible = groups.get("active", []) + groups.get("draft", [])
    else:
        visible = (
            groups.get("active", [])
            + groups.get("applied", [])
            + groups.get("reviewed", [])
            + groups.get("paused", [])
        )
    all_packages = visible + groups.get("pass", []) + groups.get("hidden", [])
    visible_records = [_package_record(package) for package in visible]
    steps = recommended_next_steps(visible_records, "All Mode")
    rendered_steps = "".join(f"<li>{html.escape(step)}</li>" for step in steps)

    def matching(source: List[Dict[str, Any]], predicate: Any) -> List[Dict[str, Any]]:
        return [package for package in source if predicate(_package_record(package))]

    queues = (
        ("Verified / Employer Source Roles", "verified-employer-sources", matching(visible, lambda item: item.get("verification_status") in {"Verified Active", "Employer Source"} or item.get("source_trust_label") in {"Direct Employer", "Verified Company Source"}), "No verified employer-source roles found."),
        ("Industry Board Roles", "industry-board-sources", matching(visible, lambda item: item.get("verification_status") == "Industry Board"), "No industry-board roles found."),
        ("Aggregator - Verify First", "aggregator-verify-first", matching(all_packages, lambda item: item.get("verification_status") == "Aggregator Only"), "No aggregator-only roles found."),
        ("Gated / Limited Visibility", "gated-limited-visibility", matching(all_packages, lambda item: item.get("verification_status") == "Gated / Limited Visibility"), "No gated roles found."),
        ("Unknown / Cannot Verify", "unknown-cannot-verify", matching(all_packages, lambda item: item.get("verification_status") in {"Cannot Verify", "Not Verified"} or item.get("source_trust_label") == "Unknown Source"), "No unknown or unverifiable roles found."),
        ("Stale or Closed Risk", "stale-closed-risk", matching(all_packages, lambda item: item.get("verification_status") == "Stale / Closed Risk"), "No stale or closed-risk roles found."),
        ("Strong Matches", "strong-matches", matching(visible, lambda item: item.get("match_tier") == "Strong Match"), "No strong matches found."),
        ("Good Matches", "good-matches", matching(visible, lambda item: item.get("match_tier") == "Good Match"), "No good matches found."),
        ("Stretch Matches", "stretch-matches", matching(visible, lambda item: item.get("match_tier") == "Stretch Match"), "No stretch matches found."),
        ("Follow-Up Due", "follow-up-due", matching(visible, lambda item: item.get("follow_up_status") in {"Due soon", "Due now", "Overdue"}), "No roles need follow-up right now."),
        ("Review First", "review-first", matching(visible, lambda item: item.get("recommended_action") == "Review First"), "No review-first roles found."),
        ("Pass / Hidden / Invalid", "pass-hidden-invalid", matching(all_packages, lambda item: item.get("match_tier") == "Pass" or _is_hidden(item)), "No pass or hidden roles found."),
        ("Cleanup Needed", "cleanup-needed", matching(all_packages, _needs_cleanup), "No cleanup items found."),
    )
    rendered_queues = "".join(
        _render_priority_queue(title, queue_id, packages, empty_message)
        for title, queue_id, packages, empty_message in queues
    )
    return (
        '<section class="recommended-steps" aria-labelledby="recommended-next-steps">'
        '<h2 id="recommended-next-steps">Recommended Next Steps</h2>'
        f'<ol>{rendered_steps}</ol></section>'
        '<section class="priority-section" aria-labelledby="priority-queues">'
        '<h2 id="priority-queues">Priority Queues</h2>'
        f'<div class="priority-grid">{rendered_queues}</div></section>'
    )


def _render_html(
    groups: Dict[str, List[Dict[str, Any]]],
    counts: Dict[str, int],
    unassigned: List[Tuple[str, Path]],
    dashboard_directory: Path,
) -> str:
    summary_cards = "".join(
        '<div class="summary-card">'
        f'<span class="summary-value">{count}</span>'
        f'<span class="summary-label">{html.escape(label)}</span>'
        "</div>"
        for label, count in counts.items()
    )
    active_group = _render_group(
        "Active",
        "active",
        groups["active"],
        dashboard_directory,
    )
    applied_group = _render_group(
        "Applied / Follow-Up",
        "applied-follow-up",
        groups["applied"],
        dashboard_directory,
    )
    reviewed_group = _render_group(
        "Reviewed",
        "reviewed",
        groups["reviewed"],
        dashboard_directory,
    )
    paused_group = _render_group(
        "Paused",
        "paused",
        groups["paused"],
        dashboard_directory,
    )
    passed_group = _render_group(
        "Passed",
        "passed",
        groups["pass"],
        dashboard_directory,
    )
    hidden_group = _render_hidden_group(groups["hidden"], dashboard_directory)
    priority_sections = _render_priority_sections(groups)
    visible_count = sum(
        len(groups[key]) for key in ("active", "applied", "reviewed", "paused")
    )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Career Catalyst Dashboard</title>
  <style>
    :root {{
      color-scheme: light;
      --background: #f3f5f6;
      --surface: #ffffff;
      --border: #d9dee2;
      --ink: #20272d;
      --muted: #68737d;
      --accent: #176b5b;
      --accent-soft: #e5f2ef;
      --gold: #8b5d12;
      --gold-soft: #f7edd7;
      --red: #9d3941;
      --red-soft: #fae9eb;
      --blue: #2f5d8a;
      --blue-soft: #e8f0f8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--background);
      color: var(--ink);
      font-family: Arial, Helvetica, sans-serif;
      font-size: 15px;
      line-height: 1.45;
    }}
    a {{ color: inherit; }}
    .site-header {{
      border-bottom: 1px solid var(--border);
      background: var(--surface);
    }}
    .header-inner, .page {{
      width: min(1180px, calc(100% - 40px));
      margin: 0 auto;
    }}
    .header-inner {{
      display: flex;
      align-items: center;
      gap: 14px;
      min-height: 88px;
      padding: 16px 0;
    }}
    .brand-mark {{
      display: grid;
      flex: 0 0 42px;
      width: 42px;
      height: 42px;
      place-items: center;
      border-radius: 6px;
      background: var(--accent);
      color: #ffffff;
      font-size: 13px;
      font-weight: 700;
    }}
    .eyebrow {{
      margin: 0 0 2px;
      color: var(--accent);
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
    }}
    h1 {{ margin: 0; font-size: 24px; line-height: 1.2; }}
    .page {{ padding: 30px 0 48px; }}
    h2 {{ margin: 0; font-size: 18px; }}
    .summary-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
      gap: 12px;
      margin-top: 12px;
    }}
    .summary-card, .application-card {{
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--surface);
    }}
    .summary-card {{ min-height: 96px; padding: 16px; }}
    .summary-value {{ display: block; font-size: 26px; font-weight: 700; line-height: 1; }}
    .summary-label {{ display: block; margin-top: 8px; color: var(--muted); font-size: 13px; }}
    .recommended-steps, .priority-section {{ margin-top: 30px; }}
    .recommended-steps ol {{ margin: 10px 0 0; border: 1px solid var(--border); border-radius: 6px; padding: 16px 20px 16px 42px; background: var(--surface); }}
    .recommended-steps li + li {{ margin-top: 7px; }}
    .priority-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-top: 12px; }}
    .priority-queue {{ border: 1px solid var(--border); border-radius: 6px; padding: 15px; background: var(--surface); }}
    .priority-queue h3 {{ font-size: 15px; }}
    .priority-queue ul {{ margin: 9px 0 0; padding-left: 18px; }}
    .priority-queue li + li {{ margin-top: 8px; }}
    .priority-queue li span {{ display: block; color: var(--muted); font-size: 12px; }}
    .packages {{ margin-top: 34px; }}
    .section-heading {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }}
    .section-count {{ color: var(--muted); font-size: 13px; }}
    .application-group {{ margin-top: 22px; }}
    .group-heading {{
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }}
    .group-title {{ margin: 0; font-size: 15px; }}
    .application-list {{ display: grid; gap: 14px; }}
    .application-card {{ padding: 20px; }}
    .application-heading {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 20px;
    }}
    .application-title {{ min-width: 0; }}
    .company {{ margin: 0 0 4px; color: var(--accent); font-size: 13px; font-weight: 700; }}
    h3 {{ margin: 0; font-size: 19px; line-height: 1.3; overflow-wrap: anywhere; }}
    .badges {{ display: flex; flex: 0 0 auto; flex-wrap: wrap; justify-content: flex-end; gap: 6px; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      min-height: 25px;
      border-radius: 999px;
      padding: 3px 9px;
      background: #eef1f3;
      color: #4c5963;
      font-size: 12px;
      font-weight: 700;
    }}
    .status-drafted, .status-reviewed {{ background: var(--gold-soft); color: var(--gold); }}
    .status-active {{ background: #eef1f3; color: #4c5963; }}
    .status-applied, .status-follow_up {{ background: var(--blue-soft); color: var(--blue); }}
    .status-interviewing {{ background: var(--accent-soft); color: var(--accent); }}
    .status-rejected {{ background: var(--red-soft); color: var(--red); }}
    .status-paused {{ background: #eef1f3; color: #4c5963; }}
    .status-invalid {{ background: var(--red-soft); color: var(--red); }}
    .status-invalid_hidden, .status-pass {{ background: var(--red-soft); color: var(--red); }}
    .status-archived {{ background: #eef1f3; color: #4c5963; }}
    .priority {{ border: 1px solid #e1c891; background: #ffffff; color: var(--gold); }}
    .match-gate {{
      margin-top: 16px;
      border: 1px solid #b8d7d0;
      border-radius: 6px;
      padding: 15px;
      background: var(--accent-soft);
    }}
    .match-unscored {{ border-color: var(--border); background: #f7f8f9; }}
    .match-unscored div {{ display: flex; align-items: baseline; gap: 10px; }}
    .match-unscored p {{ margin: 6px 0 0; color: var(--muted); font-size: 13px; }}
    .match-score-row {{ display: flex; align-items: center; justify-content: space-between; gap: 12px; }}
    .match-label {{ display: block; color: var(--accent); font-size: 12px; font-weight: 700; text-transform: uppercase; }}
    .match-number {{ display: block; font-size: 30px; line-height: 1.1; }}
    .match-number small {{ color: var(--muted); font-size: 13px; }}
    .match-tier {{ border-radius: 999px; padding: 5px 10px; background: var(--surface); color: var(--accent); font-size: 13px; font-weight: 700; }}
    .match-action {{ display: flex; flex-wrap: wrap; gap: 6px 12px; margin-top: 8px; font-size: 13px; }}
    .match-action span {{ color: var(--muted); }}
    .match-summary {{ margin: 9px 0 0; }}
    .match-details {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; margin-top: 10px; }}
    .match-list h4 {{ margin-bottom: 4px; }}
    .match-list ul {{ margin: 0; padding-left: 18px; font-size: 13px; }}
    .match-list li + li {{ margin-top: 3px; }}
    .metadata {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px 24px;
      margin: 15px 0 0;
      padding-top: 13px;
      border-top: 1px solid #e8ebed;
    }}
    .meta-item {{ display: flex; gap: 6px; min-width: 0; }}
    dt {{ color: var(--muted); font-size: 13px; font-weight: 700; }}
    dd {{ margin: 0; font-size: 13px; overflow-wrap: anywhere; }}
    .tracker-row {{ display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 12px; margin-top: 12px; }}
    .tracker-label {{ color: var(--muted); font-size: 13px; font-weight: 700; }}
    .tracker-row p {{ margin: 0; }}
    .source-caution {{ margin: 12px 0 0; border-left: 3px solid var(--gold); padding: 8px 10px; background: var(--gold-soft); color: #69460e; font-size: 13px; }}
    .materials {{ margin-top: 16px; }}
    h4 {{ margin: 0 0 8px; font-size: 13px; }}
    .file-links {{ display: flex; flex-wrap: wrap; gap: 7px; }}
    .file-link {{
      display: inline-flex;
      align-items: center;
      min-height: 32px;
      border: 1px solid #c9d1d6;
      border-radius: 5px;
      padding: 6px 10px;
      background: #ffffff;
      color: #34414a;
      font-size: 13px;
      font-weight: 700;
      text-decoration: none;
    }}
    .file-link:hover, .file-link:focus-visible {{ border-color: var(--accent); color: var(--accent); }}
    .empty-links, .empty-state {{ margin: 0; color: var(--muted); }}
    .unassigned {{ margin-top: 28px; }}
    .unassigned h2 {{ margin-bottom: 12px; }}
    .hidden-group {{ margin-top: 26px; color: var(--muted); }}
    .hidden-group summary {{ cursor: pointer; font-size: 13px; font-weight: 700; }}
    .hidden-list {{ margin-top: 12px; }}
    @media (max-width: 900px) {{
      .summary-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .priority-grid {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 620px) {{
      .header-inner, .page {{ width: min(100% - 24px, 1180px); }}
      .page {{ padding-top: 22px; }}
      h1 {{ font-size: 21px; }}
      .summary-grid {{ grid-template-columns: 1fr; }}
      .summary-card {{ min-height: 82px; }}
      .application-card {{ padding: 16px; }}
      .application-heading {{ display: block; }}
      .badges {{ justify-content: flex-start; margin-top: 10px; }}
      .tracker-row {{ grid-template-columns: 1fr; gap: 2px; }}
      .match-details {{ grid-template-columns: 1fr; gap: 10px; }}
    }}
  </style>
</head>
<body>
  <header class="site-header">
    <div class="header-inner">
      <div class="brand-mark" aria-hidden="true">CC</div>
      <div>
        <p class="eyebrow">Career Catalyst Dashboard</p>
        <h1>Trisha Lynch Application Tracker</h1>
      </div>
    </div>
  </header>
  <main class="page">
    <section aria-labelledby="summary-heading">
      <h2 id="summary-heading">Workspace Summary</h2>
      <div class="summary-grid">{summary_cards}</div>
    </section>
    {priority_sections}
    <section class="packages" aria-labelledby="packages-heading">
      <div class="section-heading">
        <h2 id="packages-heading">Application Packages</h2>
        <span class="section-count">{visible_count} visible roles</span>
      </div>
      {active_group}
      {applied_group}
      {reviewed_group}
      {paused_group}
      {passed_group}
      {hidden_group}
    </section>
    {_render_unassigned(unassigned, dashboard_directory)}
  </main>
</body>
</html>
"""


def load_application_packages(project_root: PathInput = Path.cwd()) -> Dict[str, Any]:
    """Load tracker-backed application packages for local dashboard surfaces."""
    root = Path(project_root).resolve()
    packages = _load_jobs(root)
    tracker = validate_application_tracker(root)["applications"]
    _merge_tracker(packages, tracker)
    unassigned = _attach_assets(root, packages)
    for package in packages:
        package["archived_materials_available"] = archived_materials_exist(
            root, str(package.get("tracker_id") or "")
        )
    _enrich_package_trackers(packages)
    packages.sort(
        key=lambda item: (
            0 if item.get("tracker") else 1,
            _slug(item["company"]),
            _slug(item["role"]),
        )
    )
    return {
        "packages": packages,
        "unassigned": unassigned,
        "groups": _partition_packages(packages),
    }


def generate_dashboard(project_root: PathInput = Path.cwd()) -> Dict[str, Any]:
    """Build the local static dashboard and return generation details."""
    root = Path(project_root).resolve()
    dashboard_directory = root / "exports" / "dashboard"
    output_path = dashboard_directory / "index.html"

    try:
        package_data = load_application_packages(root)
        packages = package_data["packages"]
        unassigned = package_data["unassigned"]
        groups = package_data["groups"]
        counts = _summary_counts(root, groups)
        dashboard_directory.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            _render_html(groups, counts, unassigned, dashboard_directory),
            encoding="utf-8",
        )
    except (JobParseError, OSError, TrackerValidationError) as error:
        raise DashboardGenerationError(f"Could not generate dashboard: {error}") from error

    return {
        "output_path": str(output_path),
        "relative_output_path": output_path.relative_to(root).as_posix(),
        "application_count": len(packages),
        "summary": counts,
    }
