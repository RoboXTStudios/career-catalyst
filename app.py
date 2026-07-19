"""Local Streamlit cockpit for Career Catalyst.

Run with: streamlit run app.py
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from scripts.application_tracker import (
    ACTIVE_STATUSES,
    HIDDEN_STATUSES,
    VALID_STATUSES,
    TrackerValidationError,
    follow_up_action_state,
    get_record_status,
    load_application_tracker,
    normalize_status,
    update_prospect,
    update_status,
    workflow_status_bucket,
)
from scripts.application_strategy import build_application_strategy, build_hiring_manager_lens
from scripts.dynamic_role_intelligence import get_effective_voice_profile
from scripts.filename_utils import build_upload_filename, company_display_name
from scripts.filename_utils import is_valid_role_title
from scripts.generate_dashboard import (
    ACTION_FILTERS,
    DASHBOARD_MODES,
    FOLLOW_UP_FILTERS,
    MATCH_TIER_FILTERS,
    SORT_OPTIONS,
    SOURCE_TYPE_FILTERS,
    STATUS_FILTERS,
    TRUST_LABEL_FILTERS,
    VERIFICATION_STATUS_FILTERS,
    filter_dashboard_records,
    generate_dashboard,
    prepare_dashboard_records,
    record_application_portal_url,
    record_dashboard_reference as dashboard_role_reference,
    record_posting_url,
    recommended_next_steps,
    select_dashboard_mode,
    source_verification_caution,
    sort_dashboard_records,
    structured_recommended_next_steps,
)
from scripts.career_signals import next_action_signal, select_todays_focus, status_date
from scripts.generate_followups import (
    FOLLOWUP_ELIGIBLE_STATUSES,
    FollowupGenerationError,
    generate_followups,
    generate_missing_followups,
)
from scripts.job_importer import (
    IMPORT_EXTRACTION_FALLBACK_MESSAGE,
    MINIMUM_DESCRIPTION_LENGTH,
    JobImportError,
    import_job_from_url,
    is_usable_job_description,
)
from scripts.job_identity import infer_job_fields_from_url, preferred_role_title
from scripts.job_freshness import detect_job_freshness
from scripts.hiring_manager_brief import brief_card_summary, build_hiring_manager_brief
from scripts.job_source_registry import normalize_job_source
from scripts.materials_library import (
    find_exact_role_package,
    material_route,
    move_role_package,
)
try:
    from scripts.job_source_registry import (
        VERIFICATION_STATUSES as CANONICAL_VERIFICATION_STATUSES,
    )
except (AttributeError, ImportError):
    CANONICAL_VERIFICATION_STATUSES = ()
from scripts.package_generator import (
    PackageGenerationError,
    build_package_context,
    generate_package,
    refresh_saved_package_context,
    resolve_job_reference,
)
from scripts.package_context import CONTEXT_MISMATCH_MESSAGE
from scripts.parse_job import extract_metadata, parse_job_description, salary_parsing_warning
from scripts.prospect_intake import ProspectIntakeError, create_prospect
from scripts.prospect_validation import compute_prospect_validation_state
from scripts.role_interpreter import ROLE_ARCHETYPES
from scripts.score_match import incomplete_match_report, score_job_data, score_job_match
from scripts.evidence_profile import (
    CONFIDENCE_LEVELS,
    EVIDENCE_CATEGORIES,
    RESUME_VISIBILITIES,
    USAGE_KEYS,
    VERIFICATION_STATUSES as EVIDENCE_VERIFICATION_STATUSES,
    add_discovery,
    confirm_discovery,
    discover_evidence,
    evidence_explorer_summary,
    query_evidence,
    reject_discovery,
    save_evidence_profile,
)
from scripts.capability_graph import (
    capability_explorer_summary,
    save_capability_review,
)
from scripts.evidence_summary import refresh_evidence_page_summary
from scripts.role_evidence_selection import update_selection_overrides
from scripts.role_evidence_selection import normalize_selection_overrides
from scripts.score_match import persisted_match_fields
from scripts.ui_performance import (
    invalidate_capability_cache,
    invalidate_evidence_caches,
    invalidate_tracker_cache,
    load_cached_application_tracker,
    load_cached_application_packages,
    load_cached_capability_graph,
    load_cached_evidence_page_summary,
    load_cached_evidence_profile,
)


PROJECT_ROOT = Path(__file__).resolve().parent
UI_DESCRIPTION = (
    "Add prospects, generate tailored application packages, track statuses, and manage "
    "job search materials from one local workspace."
)
TRACKER_GROUPS = VALID_STATUSES
CLEANUP_TRACKER_GROUPS = (
    "Needs decision",
    "Paused",
    "Passed",
    "Hidden / Invalid",
    "Stale / Cannot Verify",
)
PRIORITY_OPTIONS = ("High", "Medium", "Low", "Do Not Pursue")
FALLBACK_VERIFICATION_STATUSES = (
    "Not Verified",
    "Employer Source",
    "Verified Manually",
    "Needs Review",
    "Stale / Inactive",
)
OUTPUT_LABELS = {
    "job_file": "Job description",
    "resume_markdown": "Tailored resume",
    "styled_docx": "Styled resume",
    "ats_docx": "ATS resume",
    "cover_letter": "Cover letter",
    "cover_letter_text": "Cover letter text",
    "cover_letter_docx": "Cover letter DOCX",
    "resume_text": "Tailored resume text",
    "recruiter_message": "Recruiter message",
    "recruiter_message_text": "Recruiter message text",
    "hiring_manager_message": "Hiring manager message",
    "hiring_manager_message_text": "Hiring manager message text",
    "application_note": "Application note",
    "application_note_text": "Application note text",
    "strategy_pack": "Strategy pack",
    "strategy_pack_text": "Strategy pack text",
    "interview_prep": "Interview prep",
    "interview_prep_text": "Interview prep text",
    "package_summary": "Package quality summary",
    "package_summary_text": "Package quality summary text",
    "recruiter_followup": "Recruiter follow-up",
    "hiring_manager_followup": "Hiring manager follow-up",
    "warm_contact_message": "Warm contact message",
    "referral_ask": "Referral ask",
    "followup_strategy": "Follow-up strategy",
    "dashboard": "Dashboard",
}
PACKAGE_MATERIAL_LABELS = {
    "Job Description": "Job description",
    "Tailored Markdown Resume": "Tailored resume",
    "Styled DOCX": "Styled resume",
    "ATS DOCX": "ATS resume",
    "Cover Letter DOCX": "Cover letter",
    "Cover Letter Text": "Cover letter text",
    "Cover Letter": "Cover letter",
    "Recruiter Message": "Recruiter message",
    "Hiring Manager Message": "Hiring manager message",
    "Application Note": "Application note",
    "Strategy Pack": "Strategy pack",
    "Interview Prep": "Interview prep",
    "Package Summary": "Package summary",
    "Follow-Up Materials": "Follow-up materials",
    "Recruiter Follow-Up": "Recruiter follow-up",
    "Hiring Manager Follow-Up": "Hiring manager follow-up",
    "Warm Contact Message": "Warm contact message",
    "Referral Ask": "Referral ask",
    "PDF Resume": "PDF resume",
    "Resume Text": "Resume text",
}
MATERIAL_GROUPS = {
    "Resumes": ("ATS DOCX", "Styled DOCX", "PDF Resume", "Resume Text", "Tailored Markdown Resume"),
    "Letter/Application": ("Cover Letter DOCX", "Cover Letter Text", "Cover Letter", "Application Note"),
    "Outreach": ("Recruiter Message", "Hiring Manager Message"),
    "Strategy/Prep": ("Strategy Pack", "Interview Prep", "Package Summary"),
    "Follow-up": ("Follow-Up Materials", "Recruiter Follow-Up", "Hiring Manager Follow-Up", "Warm Contact Message", "Referral Ask"),
    "Source": ("Job Description",),
}
APP_CSS = """
<style>
  :root {
    --cc-background: #f3f5f6;
    --cc-surface: #ffffff;
    --cc-border: #d9dee2;
    --cc-ink: #20272d;
    --cc-muted: #68737d;
    --cc-accent: #176b5b;
    --cc-accent-soft: #e5f2ef;
    --cc-gold: #8b5d12;
    --cc-gold-soft: #f7edd7;
    --cc-red: #9d3941;
    --cc-red-soft: #fae9eb;
    --cc-blue: #2f5d8a;
    --cc-blue-soft: #e8f0f8;
  }
  .stApp { background: var(--cc-background); color: var(--cc-ink); }
  [data-testid="stHeader"] { background: rgba(243, 245, 246, 0.94); }
  [data-testid="stMainBlockContainer"] {
    max-width: 1180px;
    padding-top: 1.35rem;
    padding-bottom: 3rem;
  }
  .cc-header {
    display: flex;
    align-items: center;
    gap: 14px;
    margin-bottom: 1.2rem;
    border: 1px solid var(--cc-border);
    border-radius: 6px;
    padding: 16px 18px;
    background: var(--cc-surface);
  }
  .cc-brand-mark {
    display: grid;
    flex: 0 0 42px;
    width: 42px;
    height: 42px;
    place-items: center;
    border-radius: 6px;
    background: var(--cc-accent);
    color: #ffffff;
    font-size: 13px;
    font-weight: 700;
  }
  .cc-eyebrow {
    margin: 0 0 2px;
    color: var(--cc-accent);
    font-size: 12px;
    font-weight: 700;
    letter-spacing: .04em;
    text-transform: uppercase;
  }
  .cc-header h1 { margin: 0; color: var(--cc-ink); font-size: 24px; line-height: 1.2; }
  .cc-description { margin: 0 0 1.35rem; color: var(--cc-muted); font-size: 14px; }
  .stApp h2.cc-section-heading {
    margin: 0 0 .75rem;
    color: var(--cc-ink);
    font-size: 18px !important;
    line-height: 1.3 !important;
  }
  .cc-summary-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
    gap: 12px;
    margin-bottom: 1.8rem;
  }
  .cc-summary-card {
    min-height: 92px;
    border: 1px solid var(--cc-border);
    border-radius: 6px;
    padding: 16px;
    background: var(--cc-surface);
  }
  .cc-summary-value { display: block; color: var(--cc-ink); font-size: 26px; font-weight: 700; line-height: 1; }
  .cc-summary-label { display: block; margin-top: 8px; color: var(--cc-muted); font-size: 13px; }
  .cc-group-heading {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin: 1.15rem 0 .55rem;
  }
  .cc-group-title { color: var(--cc-ink); font-size: 15px; font-weight: 700; }
  .cc-group-count { color: var(--cc-muted); font-size: 13px; }
  div[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: var(--cc-border);
    border-radius: 6px;
    background: var(--cc-surface);
    box-shadow: none;
  }
  .cc-card-company { margin: 0 0 3px; color: var(--cc-accent); font-size: 13px; font-weight: 700; }
  .cc-card-role { margin: 0; color: var(--cc-ink); font-size: 19px; font-weight: 700; line-height: 1.3; }
  .cc-badges { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; }
  .cc-badge {
    display: inline-flex;
    align-items: center;
    min-height: 25px;
    border-radius: 999px;
    padding: 3px 9px;
    background: #eef1f3;
    color: #4c5963;
    font-size: 12px;
    font-weight: 700;
  }
  .cc-status-drafted { background: var(--cc-gold-soft); color: var(--cc-gold); }
  .cc-status-applied, .cc-status-under-consideration { background: var(--cc-blue-soft); color: var(--cc-blue); }
  .cc-status-interviewing, .cc-status-offer { background: var(--cc-accent-soft); color: var(--cc-accent); }
  .cc-status-rejected, .cc-status-withdrawn-closed { background: var(--cc-red-soft); color: var(--cc-red); }
  .cc-priority { border: 1px solid #e1c891; background: #ffffff; color: var(--cc-gold); }
  .cc-metadata {
    display: flex;
    flex-wrap: wrap;
    gap: 10px 24px;
    margin-top: 14px;
    border-top: 1px solid #e8ebed;
    padding-top: 12px;
  }
  .cc-meta-item { color: var(--cc-ink); font-size: 13px; }
  .cc-meta-label { margin-right: 5px; color: var(--cc-muted); font-weight: 700; }
  .cc-match-gate { margin-top: 14px; border: 1px solid #b8d7d0; border-radius: 6px; padding: 14px; background: var(--cc-accent-soft); }
  .cc-match-unscored { border-color: var(--cc-border); background: #f7f8f9; }
  .cc-match-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
  .cc-match-label { display: block; color: var(--cc-accent); font-size: 12px; font-weight: 700; text-transform: uppercase; }
  .cc-match-number { color: var(--cc-ink); font-size: 29px; font-weight: 700; line-height: 1.1; }
  .cc-match-number small { color: var(--cc-muted); font-size: 13px; }
  .cc-match-tier { border-radius: 999px; padding: 5px 10px; background: var(--cc-surface); color: var(--cc-accent); font-size: 13px; font-weight: 700; }
  .cc-match-action { display: flex; flex-wrap: wrap; gap: 6px 12px; margin-top: 7px; font-size: 13px; }
  .cc-match-action span { color: var(--cc-muted); }
  .cc-match-summary { margin: 8px 0 0; }
  .cc-match-details { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-top: 9px; font-size: 13px; }
  .cc-match-details strong { display: block; margin-bottom: 3px; }
  .cc-match-details ul { margin: 0; padding-left: 18px; }
  .cc-tracker-row { display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 12px; margin-top: 10px; font-size: 14px; }
  .cc-source-caution { margin: 10px 0 0; border-left: 3px solid var(--cc-gold); padding: 8px 10px; background: var(--cc-gold-soft); color: #69460e; font-size: 13px; }
  .cc-tracker-label { color: var(--cc-muted); font-size: 13px; font-weight: 700; }
  .cc-materials-label { margin: 13px 0 6px; color: var(--cc-ink); font-size: 13px; font-weight: 700; }
  .stTabs [data-baseweb="tab-list"] { gap: 6px; border-bottom: 1px solid var(--cc-border); }
  .stTabs [data-baseweb="tab"] { height: 42px; border-radius: 5px 5px 0 0; padding: 0 14px; color: var(--cc-muted); }
  .stTabs [aria-selected="true"] { background: var(--cc-surface); color: var(--cc-accent); font-weight: 700; }
  .stButton > button {
    min-height: 34px;
    border-color: #c9d1d6;
    border-radius: 5px;
    background: var(--cc-surface);
    color: #34414a;
    font-weight: 700;
  }
  .stButton > button:hover { border-color: var(--cc-accent); color: var(--cc-accent); }
  .stButton > button[kind="primary"] { border-color: var(--cc-accent); background: var(--cc-accent); color: #ffffff; }
  [data-testid="stTextInput"] input, [data-testid="stTextArea"] textarea,
  [data-testid="stSelectbox"] > div > div { border-color: var(--cc-border); background: var(--cc-surface); }
  [data-testid="stCode"] { border: 1px solid var(--cc-border); background: var(--cc-surface); }
  details { border-color: var(--cc-border) !important; border-radius: 6px !important; background: var(--cc-surface); }
  @media (max-width: 900px) { .cc-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  @media (max-width: 620px) {
    .cc-summary-grid { grid-template-columns: 1fr; }
    .cc-card-role { font-size: 17px; }
    .cc-badges { justify-content: flex-start; margin-top: 8px; }
    .cc-tracker-row { grid-template-columns: 1fr; gap: 2px; }
    .cc-match-details { grid-template-columns: 1fr; gap: 9px; }
  }
</style>
"""


def summarize_applications(applications: list[Dict[str, Any]]) -> Dict[str, int]:
    """Return concise, non-empty counts for the primary workflow statuses."""
    counts = {status: 0 for status in VALID_STATUSES}
    for application in applications:
        status = get_record_status(application)
        counts[status if status in counts else "Withdrawn / Closed"] += 1
    return {"Total": len(applications), **{key: value for key, value in counts.items() if value}}


def group_applications_by_status(
    applications: list[Dict[str, Any]],
    preserve_order: bool = False,
    mode: str = "All Mode",
) -> Dict[str, list[Dict[str, Any]]]:
    """Group tracker records for the interactive dashboard without changing order on disk."""
    labels = CLEANUP_TRACKER_GROUPS if mode == "Cleanup Mode" else TRACKER_GROUPS
    grouped = {label: [] for label in labels}
    for application in applications:
        status = get_record_status(application)
        stale_or_unverified = (
            application.get("verification_status")
            in {"Stale / Closed Risk", "Cannot Verify", "Not Verified"}
            or application.get("source_trust_label") == "Unknown Source"
            or str(application.get("posting_status") or "").lower() == "closed"
        )
        if mode == "Cleanup Mode" and stale_or_unverified:
            label = "Stale / Cannot Verify"
        elif mode == "Cleanup Mode":
            label = "Needs decision"
        else:
            label = status if status in grouped else "Withdrawn / Closed"
        grouped[label].append(application)
    if not preserve_order:
        for values in grouped.values():
            values.sort(
                key=lambda item: (
                    str(item.get("company") or "").lower(),
                    str(item.get("role") or "").lower(),
                )
            )
    return grouped


def status_options(current_status: Any) -> tuple[str, ...]:
    """Return safe status choices while preserving an unknown legacy value."""
    current = normalize_status(current_status)
    return VALID_STATUSES if current in VALID_STATUSES else (current,) + VALID_STATUSES


def resolve_selected_tracker_id(
    tracker_ids: list[str], selected_tracker_id: Any = None
) -> str:
    """Keep a stable tracker selection when labels or record order change."""
    selected = str(selected_tracker_id or "")
    if selected in tracker_ids:
        return selected
    return tracker_ids[0] if tracker_ids else ""


def find_dashboard_role(
    records: list[Dict[str, Any]], focused_reference: Any
) -> Dict[str, Any] | None:
    """Find a focused role by stable id, slug, then company/title fallback."""
    target = str(focused_reference or "").strip()
    if not target:
        return None
    for fields in (
        ("prospect_id", "record_id", "id"),
        ("stable_slug", "prospect_slug", "record_slug", "slug"),
    ):
        for record in records:
            if target in {str(record.get(field) or "").strip() for field in fields}:
                return record
    return next(
        (record for record in records if dashboard_role_reference(record) == target),
        None,
    )


def focus_dashboard_role(session_state: Any, role_reference: str) -> str:
    """Set focused role state using a durable id, slug, or role key."""
    stable_id = str(role_reference or "").strip()
    if stable_id:
        session_state["dashboard_focused_role_id"] = stable_id
        session_state["dashboard_compact_mode"] = False
    return stable_id


def clear_focused_dashboard_role(session_state: Any) -> None:
    """Clear focused role state without changing dashboard filters."""
    session_state.pop("dashboard_focused_role_id", None)
    session_state.pop("dashboard_materials_role_id", None)
    session_state.pop("dashboard_source_verification_role_id", None)


def collapse_dashboard_working_view(session_state: Any) -> None:
    """Collapse dashboard content while retaining the selected role and filters."""
    session_state["dashboard_compact_mode"] = True
    session_state["dashboard_next_steps_collapsed"] = True
    session_state.pop("dashboard_materials_role_id", None)
    session_state.pop("dashboard_source_verification_role_id", None)


def expand_focused_dashboard_role(session_state: Any) -> bool:
    """Expand only the current focused role, returning whether one exists."""
    if not str(session_state.get("dashboard_focused_role_id") or "").strip():
        return False
    session_state["dashboard_compact_mode"] = False
    return True


def expand_recommended_next_steps(session_state: Any) -> None:
    """Expand next-step navigation without changing role filters or card state."""
    session_state["dashboard_next_steps_collapsed"] = False


def reset_package_preview_for_selection(
    session_state: Any, prospect_id: str
) -> bool:
    """Discard stale package preview state when the selected prospect changes."""
    selected = str(prospect_id or "").strip()
    previous = str(session_state.get("package_preview_prospect_id") or "").strip()
    if previous == selected:
        return False
    invalidate_package_context_state(session_state)
    session_state["package_preview_prospect_id"] = selected
    return True


def invalidate_package_context_state(
    session_state: Any, prospect_id: str = ""
) -> None:
    """Discard only role-derived session state after a material prospect change."""
    for key in (
        "last_package_outputs",
        "last_package_result",
        "package_role_intelligence",
        "package_intelligence_preview",
        "package_suggested_cover_letter_angle",
        "package_suggested_proof_points",
        "package_company_voice",
        "package_company_category",
        "package_role_family",
        "package_context_recovery",
    ):
        session_state.pop(key, None)
    if prospect_id:
        session_state["package_preview_prospect_id"] = str(prospect_id)


def mark_prospect_intelligence_stale(session_state: Any) -> None:
    """Mark intake analysis stale after role-defining fields change."""
    session_state["prospect_intelligence_stale"] = True
    session_state.pop("prospect_match_report", None)
    session_state.pop("prospect_validation_state", None)
    session_state.pop("prospect_role_intelligence", None)
    invalidate_package_context_state(session_state)
    session_state["prospect_import_result"] = (
        "warning",
        "Role details changed. Re-parse to refresh the current analysis.",
    )


def focus_source_verification(session_state: Any, role_reference: str) -> str:
    """Focus one role and reveal its editable source-verification panel."""
    stable_id = focus_dashboard_role(session_state, role_reference)
    if stable_id:
        session_state["dashboard_source_verification_role_id"] = stable_id
        session_state["dashboard_compact_mode"] = False
    return stable_id


def needs_source_verification(record: Dict[str, Any]) -> bool:
    """Return whether a role needs a useful manual source/date check."""
    return bool(
        not record.get("posting_date")
        or str(record.get("freshness") or "").lower() in {"", "unknown freshness", "stale"}
        or record.get("verification_status")
        in {"Not Verified", "Cannot Verify", "Stale / Closed Risk"}
        or record.get("source_verified") is False
    )


def safe_source_metadata(record: Dict[str, Any]) -> Dict[str, str]:
    """Return display-safe source metadata for incomplete legacy records."""
    def text(field: str, fallback: str) -> str:
        value = record.get(field)
        if not isinstance(value, (str, int, float)):
            return fallback
        cleaned = str(value).strip()
        return cleaned if cleaned else fallback

    source = text("source_name", "") or text("source", "Unknown")
    if source.lower() == "unknown":
        source = text("source", "Unknown")
    return {
        "source": source,
        "source_type": text("source_type", "Unknown Source"),
        "verification_status": text("verification_status", "Not Verified"),
        "source_trust_label": text("source_trust_label", "Unknown Source"),
        "freshness_risk": text("freshness_risk", "Unknown"),
    }


def verification_status_options(current_status: Any = "") -> tuple[str, ...]:
    """Return canonical verification labels with a safe local fallback."""
    canonical = globals().get("CANONICAL_VERIFICATION_STATUSES", ())
    options = tuple(
        str(value).strip()
        for value in canonical
        if isinstance(value, str) and value.strip()
    )
    if not options:
        options = FALLBACK_VERIFICATION_STATUSES
    current = str(current_status or "").strip()
    if current and current not in options:
        options = (current,) + options
    return options


def _sync_persisted_widget_value(
    session_state: Any, widget_key: str, persisted_value: Any
) -> None:
    """Refresh a widget only when its persisted record value changed."""
    shadow_key = f"{widget_key}_persisted"
    if shadow_key not in session_state:
        session_state.setdefault(widget_key, persisted_value)
        session_state[shadow_key] = persisted_value
    elif session_state[shadow_key] != persisted_value:
        session_state[widget_key] = persisted_value
        session_state[shadow_key] = persisted_value


def apply_summary_navigation(session_state: Any, bucket: str) -> None:
    """Keep summary navigation and the status selectbox on one source of truth."""
    session_state["dashboard_status"] = bucket if bucket in VALID_STATUSES else "All"
    clear_focused_dashboard_role(session_state)


def clear_dashboard_filters(session_state: Any) -> None:
    """Reset every dashboard filter while preserving application data."""
    for key, value in (
        ("dashboard_status", "All"),
        ("dashboard_match_tier", "All"),
        ("dashboard_search", ""),
        ("dashboard_source_type", "All"),
        ("dashboard_verification_status", "All"),
        ("dashboard_trust_label", "All"),
    ):
        session_state[key] = value
    clear_focused_dashboard_role(session_state)


def update_dashboard_role(
    tracker_id: str,
    values: Dict[str, Any],
    project_root: Path = PROJECT_ROOT,
) -> Dict[str, Any]:
    """Persist dashboard card fields against one durable tracker id."""
    clean_id = str(tracker_id or "").strip()
    if not clean_id:
        raise TrackerValidationError("A stable tracker id is required for dashboard updates.")
    status = normalize_status(values.get("status"))
    updates: Dict[str, Any] = {}
    for field in (
        "priority",
        "notes",
        "next_action",
        "suggested_follow_up_date",
        "posting_date",
        "verification_status",
        "freshness",
        "verification_notes",
        "posting_url",
        "application_portal_url",
    ):
        if field in values:
            updates[field] = str(values.get(field) or "")
    if "show_on_dashboard" in values:
        updates["show_on_dashboard"] = bool(values["show_on_dashboard"])
    if "source_verified" in values:
        updates["source_verified"] = bool(values["source_verified"])
    if "follow_up_status" in values:
        follow_up_status = str(values.get("follow_up_status") or "").strip()
        updates["follow_up_status"] = (
            "" if follow_up_status == "Auto" else follow_up_status
        )
    # Workflow status is authoritative for dashboard visibility and grouping.
    if "status" in values:
        updates["show_on_dashboard"] = status not in HIDDEN_STATUSES
    if status in VALID_STATUSES:
        return update_status(clean_id, status, project_root, **updates)
    # Unknown legacy statuses remain readable and notes can still be edited safely.
    return update_prospect(clean_id, updates, project_root)


def move_dashboard_role_materials(
    tracker_id: str,
    *,
    archive: bool,
    project_root: Path = PROJECT_ROOT,
) -> Dict[str, Any]:
    """Archive or restore one exact role package and persist its manifest paths."""
    application = find_dashboard_role(load_application_tracker(project_root), tracker_id)
    if application is None:
        raise TrackerValidationError(f"Tracker entry not found: {tracker_id}")
    result = move_role_package(project_root, application, archive=archive)
    if not result.get("moved"):
        return result
    manifest = dict(result["manifest"])
    update_prospect(
        str(application["id"]),
        {
            "material_paths": dict(manifest.get("materials") or {}),
            "package_manifest": manifest,
        },
        project_root,
    )
    return result


def dashboard_status_actions(record: Dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """Return status-aware quick actions as label/action-key pairs."""
    status = get_record_status(record)
    active_label = (
        "Resume / Active"
        if status == "Paused"
        else "Reopen / Active"
        if status in HIDDEN_STATUSES
        else "Keep Active"
    )
    actions = [
        ("Mark Applied", "applied"),
        ("Mark Reviewed", "reviewed"),
        ("Pause", "paused"),
        ("Pass", "pass"),
        ("Hide / Invalid", "invalid_hidden"),
        (active_label, "active"),
    ]
    if status in {"Applied", "Follow-up", "Interviewing"}:
        actions.extend(
            (
                ("Follow-Up Sent", "follow_up_sent"),
                ("Follow-Up Needed", "follow_up_needed"),
            )
        )
    return tuple(actions)


def contextual_primary_actions(
    record: Dict[str, Any],
    has_materials: bool = False,
    has_posting_url: bool = False,
    mode: str = "All Mode",
) -> tuple[tuple[str, str], ...]:
    """Return at most four calm, status-specific primary card actions."""
    bucket = workflow_status_bucket(record)
    if record.get("match_score") is None and str(
        record.get("recommended_action") or ""
    ).startswith("Complete Import"):
        return (("Open posting", "open_posting"),) if has_posting_url else ()
    if mode == "Cleanup Mode" and bucket in {"Active", "Reviewed"}:
        return (
            ("Pass", "pass"),
            ("Hide / Invalid", "invalid_hidden"),
            ("Keep Active", "active"),
        )
    if bucket == "Paused":
        return (
            ("Resume / Active", "active"),
            ("Pass", "pass"),
            ("Hide / Invalid", "invalid_hidden"),
        )
    if bucket == "Pass":
        return (("Reopen / Active", "active"), ("Hide / Invalid", "invalid_hidden"))
    if bucket == "Hidden / Invalid":
        return (("Reopen / Active", "active"),)
    if bucket == "Reviewed":
        material_action = (
            ("Open materials", "open_materials")
            if has_materials
            else ("Generate package", "generate_package")
        )
        return (material_action, ("Mark Applied", "applied"), ("Pass", "pass"))
    if bucket == "Applied / Follow-up":
        actions = []
        if has_materials:
            actions.append(("Open materials", "open_materials"))
        if has_posting_url:
            actions.append(("Open posting", "open_posting"))
        if str(record.get("follow_up_status") or "") in {
            "Due soon",
            "Due now",
            "Overdue",
        }:
            actions.append(("Mark follow-up sent", "follow_up_sent"))
        return tuple(actions[:4])
    actions = []
    if has_posting_url:
        actions.append(("Open posting", "open_posting"))
    actions.extend(
        (("Generate package", "generate_package"), ("Mark Applied", "applied"))
    )
    return tuple(actions[:4])


def apply_dashboard_status_action(
    tracker_id: str,
    action: str,
    project_root: Path = PROJECT_ROOT,
) -> Dict[str, Any]:
    """Apply one named card action through the canonical dashboard update path."""
    action_updates: Dict[str, Dict[str, Any]] = {
        "applied": {"status": "Applied", "show_on_dashboard": True},
        "reviewed": {"status": "Drafted", "show_on_dashboard": True},
        "paused": {"status": "Withdrawn / Closed", "show_on_dashboard": False},
        "pass": {"status": "Withdrawn / Closed", "show_on_dashboard": False},
        "invalid_hidden": {"status": "Withdrawn / Closed", "show_on_dashboard": False},
        "active": {"status": "Drafted", "show_on_dashboard": True},
        "follow_up_sent": {
            "status": "Applied",
            "follow_up_status": "Follow-up sent",
            "show_on_dashboard": True,
        },
        "follow_up_needed": {
            "status": "Applied",
            "follow_up_status": "Due now",
            "show_on_dashboard": True,
        },
    }
    if action not in action_updates:
        raise TrackerValidationError(f"Unsupported dashboard status action: {action}")
    return update_dashboard_role(tracker_id, action_updates[action], project_root)


def build_prospect_payload(values: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize widget values without importing or executing Streamlit."""
    return {
        "posting_url": str(values.get("posting_url") or values.get("official_url") or "").strip(),
        "application_portal_url": str(values.get("application_portal_url") or "").strip(),
        "official_url": str(values.get("official_url") or "").strip(),
        "source_url": str(values.get("source_url") or values.get("official_url") or "").strip(),
        "original_source_url": str(values.get("original_source_url") or values.get("official_url") or "").strip(),
        "canonical_apply_url": str(values.get("canonical_apply_url") or values.get("official_url") or "").strip(),
        "job_id": str(values.get("job_id") or "").strip(),
        "company": str(values.get("company") or "").strip(),
        "job_title": str(values.get("job_title") or "").strip(),
        "location": str(values.get("location") or "").strip(),
        "salary_range": str(values.get("salary_range") or "").strip(),
        "salary_source": str(values.get("salary_source") or "").strip(),
        "posting_date": str(values.get("posting_date") or "").strip(),
        "source": str(values.get("source") or "Official career page").strip(),
        "priority": str(values.get("priority") or "Medium"),
        "status": str(values.get("status") or "Drafted"),
        "work_arrangement": str(values.get("work_arrangement") or "").strip(),
        "job_description": str(values.get("job_description") or "").strip(),
        "notes": str(values.get("notes") or "").strip(),
        "next_action": str(values.get("next_action") or "").strip(),
        "show_on_dashboard": bool(values.get("show_on_dashboard", True)),
        "role_interpretation": dict(values.get("role_interpretation") or {}),
        "evidence_selection_overrides": dict(
            values.get("evidence_selection_overrides") or {}
        ),
    }


def recent_output_files(
    project_root: Path = PROJECT_ROOT, limit: int = 15
) -> list[Path]:
    """Return the most recently modified generated files."""
    candidates: list[Path] = []
    for relative_directory in (
        "exports/docx",
        "exports/markdown",
        "exports/messages",
        "exports/strategy_packs",
        "exports/followups",
        "exports/dashboard",
    ):
        directory = project_root / relative_directory
        if directory.is_dir():
            candidates.extend(path for path in directory.iterdir() if path.is_file())
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[:limit]


def open_local_path(path: Path, project_root: Path = PROJECT_ROOT) -> tuple[bool, str]:
    """Open a safe project-local path through macOS Finder/default application."""
    resolved = path.resolve()
    root = project_root.resolve()
    if resolved != root and root not in resolved.parents:
        return False, "Career Catalyst only opens paths inside this project."
    if not resolved.exists():
        return False, f"Path does not exist: {resolved}"
    if sys.platform != "darwin":
        return False, f"Open this local path manually: {resolved}"
    try:
        subprocess.run(["open", str(resolved)], check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        return False, f"Could not open {resolved}: {error}"
    return True, str(resolved)


def _project_path(path: Any, project_root: Path) -> Path:
    """Resolve stored absolute or project-relative material paths consistently."""
    candidate = Path(str(path))
    return (candidate if candidate.is_absolute() else project_root / candidate).resolve()


def resolve_role_materials_target(
    application: Dict[str, Any],
    package: Dict[str, Any] | None = None,
    project_root: Path = PROJECT_ROOT,
) -> tuple[Path | None, str]:
    """Return the best existing package folder or legacy material for one role."""
    root = project_root.resolve()
    package = package or {}
    exact_package = find_exact_role_package(root, application)
    exact_files = {
        str(label): _project_path(path, root)
        for label, path in dict(exact_package.get("files") or {}).items()
        if _project_path(path, root).is_file()
    }
    exact_folder = exact_package.get("folder")
    if exact_folder and exact_files:
        folder = _project_path(exact_folder, root)
        if folder.is_dir():
            state = "archived " if exact_package.get("archived") else ""
            return folder, f"Opening the {state}application package folder."

    material_maps = (
        exact_files,
        dict(package.get("files") or {}),
        dict(application.get("_material_paths") or {}),
        dict(application.get("material_paths") or {}),
    )
    candidates: Dict[str, Path] = {}
    for paths in material_maps:
        for label, value in paths.items():
            normalized_label = re.sub(r"[^a-z0-9]+", " ", str(label).lower()).strip()
            if normalized_label in {"job description", "job file"}:
                continue
            path = _project_path(value, root)
            if path.is_file():
                candidates.setdefault(str(label), path)

    package_folder = package.get("package_folder")
    if package_folder and candidates:
        folder = _project_path(package_folder, root)
        if folder.is_dir():
            return folder, "Opening the application package folder."

    for label in PACKAGE_MATERIAL_LABELS:
        if label == "Job Description" or label not in candidates:
            continue
        return candidates[label], f"Opening {PACKAGE_MATERIAL_LABELS[label].lower()}."
    if candidates:
        return next(iter(candidates.values())), "Opening the available application material."
    return None, "No generated application materials exist for this role yet. Generate a package first."


def open_role_materials(
    st: Any,
    application: Dict[str, Any],
    package: Dict[str, Any] | None = None,
    project_root: Path = PROJECT_ROOT,
) -> bool:
    """Open one role's materials and always report success or actionable guidance."""
    target, guidance = resolve_role_materials_target(application, package, project_root)
    if target is None:
        st.warning(guidance)
        return False
    opened, message = open_local_path(target, project_root)
    (st.success if opened else st.warning)(guidance if opened else message)
    return opened


def _status_badges(application: Dict[str, Any]) -> str:
    status = get_record_status(application)
    priority = str(application.get("priority") or "").strip()
    status_class = re.sub(r"[^a-z0-9]+", "-", status.lower()).strip("-")
    badges = [
        f'<span class="cc-badge cc-status-{html.escape(status_class)}">'
        f"{html.escape(status)}</span>"
    ]
    if priority:
        badges.append(
            '<span class="cc-badge cc-priority">'
            f"{html.escape(priority)} priority</span>"
        )
    if application.get("match_score") is not None:
        badges.append(
            f'<span class="cc-badge">{html.escape(str(application["match_score"]))}/100</span>'
        )
    for value in (
        application.get("match_tier"),
        application.get("verification_status"),
    ):
        if value:
            badges.append(f'<span class="cc-badge">{html.escape(str(value))}</span>')
    return f'<div class="cc-badges">{"".join(badges)}</div>'


def _render_summary_metrics(st: Any, applications: list[Dict[str, Any]]) -> None:
    st.markdown('<h2 class="cc-section-heading">Application Summary</h2>', unsafe_allow_html=True)
    summary = summarize_applications(applications)
    navigation = [("All", summary["Total"])] + [
        (status, summary[status]) for status in VALID_STATUSES if summary.get(status)
    ]
    active_status = str(st.session_state.get("dashboard_status") or "All")
    for row_start in range(0, len(navigation), 4):
        columns = st.columns(4)
        for column, (status, count) in zip(columns, navigation[row_start : row_start + 4]):
            label = f"{status}\n{count}"
            if column.button(
                label,
                key=f"summary_{status.lower().replace(' ', '_').replace('/', '_')}",
                type="primary" if active_status == status else "secondary",
                use_container_width=True,
            ):
                apply_summary_navigation(st.session_state, status)
                st.rerun()


def _package_map(project_root: Path = PROJECT_ROOT) -> Dict[str, Dict[str, Any]]:
    package_data = load_cached_application_packages(project_root)
    return {
        str(package.get("tracker_id")): package
        for package in package_data["packages"]
        if package.get("tracker_id")
    }


def _saved_package_map(
    applications: list[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Build cheap dashboard package summaries from persisted tracker manifests."""
    result: Dict[str, Dict[str, Any]] = {}
    for application in applications:
        tracker_id = str(application.get("id") or "")
        if not tracker_id:
            continue
        manifest = dict(application.get("package_manifest") or {})
        files = dict(
            manifest.get("files")
            or manifest.get("materials")
            or application.get("material_paths")
            or {}
        )
        manifest_path = str(manifest.get("manifest_path") or "")
        package_folder = str(Path(manifest_path).parent) if manifest_path else ""
        result[tracker_id] = {
            **manifest,
            "tracker_id": tracker_id,
            "files": files,
            "package_folder": package_folder,
            "materials_archived": bool(manifest.get("archived")),
            "location": application.get("location"),
            "salary_range": application.get("salary_range"),
            "company_category": application.get("company_category"),
            "role_family": application.get("role_family"),
            "role_lens": application.get("role_lens"),
        }
    return result


def _saved_materials_target(package: Dict[str, Any]) -> Optional[Path]:
    """Resolve persisted materials without scanning every package directory."""
    folder = str(package.get("package_folder") or "")
    if folder and Path(folder).is_dir():
        return Path(folder)
    for value in (package.get("files") or {}).values():
        path = Path(str(value))
        if path.is_file():
            return path.parent
    return None


def _metadata_html(application: Dict[str, Any], package: Dict[str, Any]) -> str:
    humanize = lambda value: str(value).replace("_", " ").title()
    source_display = application.get("source_name")
    if not source_display or source_display == "Unknown":
        source_display = application.get("source") or "Unknown"
    metadata = (
        ("Location", application.get("location") or package.get("location")),
        ("Salary", application.get("salary_range") or package.get("salary_range")),
        ("Freshness", application.get("freshness_label") or application.get("freshness")),
        ("Posting date", application.get("posting_date") or "Posting date unknown"),
        ("Freshness Risk", application.get("freshness_risk") or "Unknown"),
        ("Posting Status", application.get("posting_status") or "Verify manually"),
        ("Source", source_display),
        ("Source Type", application.get("source_type") or "Unknown Source"),
        ("Trust Label", application.get("source_trust_label") or "Unknown Source"),
        ("Verification Status", application.get("verification_status") or "Not Verified"),
        ("Source Confidence", application.get("source_confidence")),
        ("Canonical Apply URL", application.get("canonical_apply_url")),
        ("Opportunity", f"{application.get('opportunity_score')}/100 - {application.get('apply_recommendation')}" if application.get("opportunity_score") is not None else None),
        ("Applied", application.get("submitted_date") or application.get("applied_date") or "No applied date"),
        (
            "Days since applied",
            application.get("days_since_applied")
            if application.get("days_since_applied") is not None
            else "Unknown",
        ),
        ("Follow-up", application.get("follow_up_status") or "No applied date"),
        ("Suggested follow-up", application.get("suggested_follow_up_date") or "Verify manually"),
        ("Materials", application.get("_materials_availability_label") or "Materials not verified"),
        (
            "Category",
            humanize(
                application.get("company_category")
                or package.get("company_category")
            )
            if application.get("company_category") or package.get("company_category")
            else None,
        ),
        (
            "Role family",
            humanize(application.get("role_family") or package.get("role_family"))
            if application.get("role_family") or package.get("role_family")
            else None,
        ),
    )
    items = "".join(
        '<span class="cc-meta-item">'
        f'<span class="cc-meta-label">{html.escape(label)}</span>'
        f"{html.escape(str(value))}</span>"
        for label, value in metadata
        if value
    )
    return f'<div class="cc-metadata">{items}</div>' if items else ""


def _primary_facts_html(application: Dict[str, Any], package: Dict[str, Any]) -> str:
    """Render only high-value, non-duplicative facts on the primary card."""
    status = get_record_status(application)
    relevant_follow_up = (
        application.get("follow_up_status")
        if status in {"Applied", "Follow-up", "Interviewing"}
        else None
    )
    facts = (
        ("Location", application.get("location") or package.get("location")),
        ("Work arrangement", application.get("work_arrangement")),
        ("Salary", application.get("salary_range") or package.get("salary_range")),
        ("Source type", application.get("source_type") or "Unknown Source"),
        ("Verification", application.get("verification_status") or "Not Verified"),
        ("Posting date", application.get("posting_date") or "Posting date unknown"),
        (
            "Applied / status date",
            application.get("submitted_date")
            or application.get("applied_date")
            or application.get("status_updated_at"),
        ),
        ("Follow-up", relevant_follow_up),
    )
    items = "".join(
        '<span class="cc-meta-item">'
        f'<span class="cc-meta-label">{html.escape(label)}</span>'
        f"{html.escape(str(value))}</span>"
        for label, value in facts
        if value
    )
    return f'<div class="cc-metadata">{items}</div>' if items else ""


def _match_score_html(
    report: Dict[str, Any],
    include_details: bool = True,
    include_tier: bool = True,
) -> str:
    score = report.get("match_score")
    if score is None:
        action = html.escape(
            str(report.get("recommended_action") or "Complete Import / Paste Job Description")
        )
        summary = html.escape(
            str(
                report.get("match_summary")
                or "Paste the job description and re-score before generating package."
            )
        )
        return (
            '<section class="cc-match-gate cc-match-unscored">'
            '<span class="cc-match-label">Match Score</span><strong>Not scored yet</strong>'
            f'<div class="cc-match-action"><span>Recommended action</span><strong>{action}</strong></div>'
            f'<p class="cc-match-summary">{summary}</p>'
            '</section>'
        )

    def render_list(label: str, key: str) -> str:
        values = report.get(key) or []
        if not isinstance(values, list) or not values:
            return ""
        items = "".join(f"<li>{html.escape(str(value))}</li>" for value in values)
        return f'<div><strong>{label}</strong><ul>{items}</ul></div>'

    details = (
        '<div class="cc-match-details">'
        f'{render_list("Top strengths", "match_strengths")}'
        f'{render_list("Fit gaps / cautions", "match_gaps")}'
        f'{render_list("Posting verification", "match_verification_notes")}'
        '</div>'
        if include_details
        else ""
    )
    tier = (
        f'<span class="cc-match-tier">{html.escape(str(report.get("match_tier") or "Not scored yet"))}</span>'
        if include_tier
        else ""
    )
    return (
        '<section class="cc-match-gate">'
        '<div class="cc-match-heading"><div>'
        '<span class="cc-match-label">Match Score</span>'
        f'<span class="cc-match-number">{html.escape(str(score))}<small>/100</small></span>'
        '</div>'
        f"{tier}</div>"
        '<div class="cc-match-action"><span>Recommended action</span>'
        f'<strong>{html.escape(str(report.get("recommended_action") or "Review First"))}</strong>'
        f'<span>Data confidence: {html.escape(str(report.get("data_confidence") or report.get("confidence") or "Low"))}</span></div>'
        f'<p class="cc-match-summary">{html.escape(str(report.get("match_summary") or "Review the fit before generating a package."))}</p>'
        f"{details}</section>"
    )


def _material_button_rows(
    st: Any,
    tracker_id: str,
    files: Dict[str, Path],
) -> None:
    materials = [
        (source_label, display_label, Path(files[source_label]))
        for source_label, display_label in PACKAGE_MATERIAL_LABELS.items()
        if source_label in files
        and Path(files[source_label]).exists()
        and Path(files[source_label]).suffix.lower() != ".md"
    ]
    if not materials:
        st.caption("No generated application materials yet.")
        return
    by_label = {source_label: (display_label, path) for source_label, display_label, path in materials}
    for group, labels in MATERIAL_GROUPS.items():
        grouped = [(label, *by_label[label]) for label in labels if label in by_label]
        if not grouped:
            continue
        st.markdown(f'<p class="cc-materials-label">{html.escape(group)}</p>', unsafe_allow_html=True)
        for row_start in range(0, len(grouped), 4):
            row = grouped[row_start : row_start + 4]
            columns = st.columns(4)
            for index, (source_label, label, path) in enumerate(row):
                if columns[index].button(
                    f"{label} .{path.suffix.lower().lstrip('.')}",
                    key=f"material_{tracker_id}_{source_label}_{row_start}_{index}",
                    use_container_width=True,
                    help=str(path),
                ):
                    opened, message = open_local_path(path)
                    (st.success if opened else st.warning)(message)


def _render_source_verification_panel(
    st: Any, application: Dict[str, Any], tracker_id: str
) -> None:
    """Render source verification safely for complete and legacy tracker records."""
    st.markdown("**Source Verification**")
    posting_url = record_posting_url(application)
    if not posting_url:
        st.caption("No posting URL stored.")
    verification_notes = str(
        application.get("verification_notes") or "Verify manually"
    )
    st.markdown(f"**Verification notes:** {html.escape(verification_notes)}")
    caution = source_verification_caution(application)
    if caution:
        st.warning(caution)
    field_warnings = []
    for warning_key in ("field_warnings", "source_warnings"):
        warning_values = application.get(warning_key)
        if isinstance(warning_values, list):
            field_warnings.extend(str(value) for value in warning_values if value)
        elif warning_values:
            field_warnings.append(str(warning_values))
    for warning in dict.fromkeys(field_warnings):
        st.caption(f"• {warning}")
    st.markdown("**Manual verification**")
    posting_date = st.text_input(
        "Posting date",
        value=str(application.get("posting_date") or ""),
        key=f"source_posting_date_{tracker_id}",
        placeholder="YYYY-MM-DD",
    )
    current_verification = str(
        application.get("verification_status") or "Not Verified"
    )
    verification_options = verification_status_options(current_verification)
    verified_status = st.selectbox(
        "Verified status",
        verification_options,
        index=verification_options.index(current_verification),
        key=f"source_verified_status_{tracker_id}",
    )
    source_verified = st.checkbox(
        "Source verified",
        value=bool(application.get("source_verified", False)),
        key=f"source_verified_{tracker_id}",
    )
    freshness_options = (
        "Unknown freshness",
        "Fresh",
        "Active",
        "Aging",
        "Stale",
    )
    current_freshness = str(application.get("freshness") or "Unknown freshness")
    if current_freshness not in freshness_options:
        freshness_options = (current_freshness,) + freshness_options
    freshness = st.selectbox(
        "Freshness",
        freshness_options,
        index=freshness_options.index(current_freshness),
        key=f"source_freshness_{tracker_id}",
    )
    source_notes = st.text_area(
        "Verification notes",
        value=str(application.get("verification_notes") or ""),
        key=f"source_notes_{tracker_id}",
    )
    if st.button(
        "Save source verification",
        key=f"source_save_{tracker_id}",
        use_container_width=True,
    ):
        update_dashboard_role(
            tracker_id,
            {
                "status": get_record_status(application),
                "posting_date": posting_date,
                "verification_status": verified_status,
                "source_verified": source_verified,
                "freshness": freshness,
                "verification_notes": source_notes,
            },
            PROJECT_ROOT,
        )
        st.session_state["dashboard_notice"] = "Source verification updated."
        st.rerun()


def _role_lens_for_card(
    application: Dict[str, Any], package: Dict[str, Any]
) -> Dict[str, Any]:
    """Resolve persisted role-lens metadata without recomputing role intelligence."""
    saved_lens = application.get("role_lens")
    if isinstance(saved_lens, dict) and saved_lens:
        return saved_lens

    package_lens = package.get("role_lens")
    if not saved_lens and isinstance(package_lens, dict) and package_lens:
        return package_lens

    primary = str(saved_lens or package_lens or "").strip()
    if not primary:
        return {}
    confidence = application.get("role_lens_confidence")
    confidence_label = "Medium"
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        confidence_label = (
            "High" if confidence >= 0.8 else "Medium" if confidence >= 0.6 else "Low"
        )
    return {
        "primary": primary,
        "secondary": application.get("secondary_role_lens"),
        "confidence": confidence,
        "confidence_label": confidence_label,
    }


def _render_role_card(
    st: Any,
    application: Dict[str, Any],
    package: Dict[str, Any],
    mode: str = "All Mode",
    compact: bool = False,
) -> None:
    tracker_id = str(application.get("id") or "application")
    if compact:
        with st.container(border=True):
            title_column, badge_column = st.columns((4, 2))
            title_column.markdown(
                '<p class="cc-card-company">'
                f"{html.escape(company_display_name(application.get('company') or 'Company not listed'))}</p>"
                '<p class="cc-card-role">'
                f"{html.escape(str(application.get('role') or 'Role not listed'))}</p>",
                unsafe_allow_html=True,
            )
            badge_column.markdown(_status_badges(application), unsafe_allow_html=True)
            brief_summary = brief_card_summary(application)
            compact_facts = [
                f"Status: {get_record_status(application)}",
                f"Match: {brief_summary['match_recommendation']}",
                f"Salary: {application.get('salary_range') or 'Not disclosed'}",
            ]
            st.caption(" · ".join(compact_facts))
            st.write(brief_summary["reason"])
            st.markdown(f"**Next:** {html.escape(brief_summary['next_action'])}")
            posting_url = record_posting_url(application)
            portal_url = record_application_portal_url(application)
            materials_target = _saved_materials_target(package)
            action_specs = [("view", "View Role", None)]
            if portal_url:
                action_specs.append(("portal", "Check Application Status", portal_url))
            if posting_url:
                action_specs.append(("posting", "Open Posting", posting_url))
            if materials_target:
                action_specs.append(("materials", "Open Materials", None))
            actions = st.columns(len(action_specs))
            action_columns = dict(zip((item[0] for item in action_specs), actions))
            if action_columns["view"].button(
                "View Role",
                key=f"compact_view_{tracker_id}",
                use_container_width=True,
            ):
                focus_dashboard_role(
                    st.session_state, dashboard_role_reference(application)
                )
                st.rerun()
            if posting_url:
                action_columns["posting"].link_button("Open Posting", posting_url, use_container_width=True)
            if portal_url:
                action_columns["portal"].link_button("Check Application Status", portal_url, use_container_width=True)
            if materials_target and action_columns["materials"].button(
                "Open Materials",
                key=f"compact_materials_{tracker_id}",
                use_container_width=True,
                help=str(materials_target),
            ):
                open_role_materials(st, application, package, PROJECT_ROOT)
        return
    with st.container(border=True):
        flash_key = f"dashboard_flash_{tracker_id}"
        if flash_key in st.session_state:
            st.success(st.session_state.pop(flash_key))
        persisted_widget_values = {
            f"dashboard_status_{tracker_id}": get_record_status(application),
            f"dashboard_priority_{tracker_id}": str(application.get("priority") or "Medium"),
            f"dashboard_notes_{tracker_id}": str(application.get("notes") or ""),
            f"dashboard_next_action_{tracker_id}": str(application.get("next_action") or "Review fit"),
        }
        for widget_key, persisted_value in persisted_widget_values.items():
            shadow_key = f"{widget_key}_persisted"
            if shadow_key not in st.session_state:
                st.session_state[shadow_key] = persisted_value
            elif st.session_state[shadow_key] != persisted_value:
                st.session_state[widget_key] = persisted_value
                st.session_state[shadow_key] = persisted_value
        st.markdown("#### Role Signal")
        title_column, badge_column = st.columns((4, 2))
        title_column.markdown(
            '<p class="cc-card-company">'
            f"{html.escape(company_display_name(application.get('company') or 'Company not listed'))}</p>"
            '<p class="cc-card-role">'
            f"{html.escape(str(application.get('role') or 'Role not listed'))}</p>",
            unsafe_allow_html=True,
        )
        badge_column.markdown(_status_badges(application), unsafe_allow_html=True)
        metadata = _primary_facts_html(application, package)
        if metadata:
            st.markdown(metadata, unsafe_allow_html=True)
        brief_summary = brief_card_summary(application)
        st.markdown(f"**{brief_summary['match_recommendation']}**")
        st.write(brief_summary["reason"])
        st.markdown("#### Next Action")
        st.markdown(f"**Next:** {html.escape(brief_summary['next_action'])}")
        if mode == "Cleanup Mode":
            st.info(recommended_next_steps([application], mode)[0])
        match_details = application.get("match_strengths") or application.get("match_gaps")
        if match_details:
            with st.expander("Match details", expanded=False):
                st.markdown(_match_score_html(application), unsafe_allow_html=True)

        source_panel_open = str(
            st.session_state.get("dashboard_source_verification_role_id") or ""
        ) in {tracker_id, dashboard_role_reference(application)}

        files = package.get("files", {})
        material_count = sum(Path(path).exists() for path in files.values())
        materials_focused = str(st.session_state.get("dashboard_materials_role_id") or "") == tracker_id
        st.markdown("#### Materials")
        with st.expander(f"Application materials ({material_count})", expanded=materials_focused):
            exact_package = find_exact_role_package(PROJECT_ROOT, application)
            archived_materials = bool(
                package.get("materials_archived") or exact_package.get("archived")
            )
            if archived_materials:
                st.caption("Archived materials available")
            elif material_count:
                st.caption("Current exact materials available")
            else:
                st.caption("No exact package materials yet")
            materials_label = str(
                application.get("_materials_availability_label")
                or "Materials not verified"
            )
            st.caption(materials_label)
            _material_button_rows(st, tracker_id, files)
            route = material_route(get_record_status(application))
            if route.get("archived") and material_count and not archived_materials:
                st.caption("Archive recommended")
            package_folder = exact_package.get("folder") or package.get("package_folder")
            if package_folder:
                library_actions = st.columns(2)
                if library_actions[0].button(
                    "Open Package Folder",
                    key=f"materials_open_folder_{tracker_id}",
                    use_container_width=True,
                ):
                    opened, message = open_local_path(Path(package_folder))
                    (st.success if opened else st.warning)(message)
                action_label = "Restore Materials" if archived_materials else "Archive Materials"
                if library_actions[1].button(
                    action_label,
                    key=f"materials_move_{tracker_id}",
                    use_container_width=True,
                ):
                    result = move_dashboard_role_materials(
                        tracker_id, archive=not archived_materials
                    )
                    if result.get("moved"):
                        st.session_state["dashboard_notice"] = (
                            "Materials archived."
                            if not archived_materials
                            else "Materials restored."
                        )
                        st.rerun()
                    else:
                        st.warning(str(result.get("reason") or "No exact package materials yet"))
            archive_candidates = int(application.get("_archive_candidate_count") or 0)
            if archive_candidates:
                st.caption(
                    f"{archive_candidates} older duplicate material(s) are archive candidates."
                )
            if application.get("_archived_materials_available"):
                st.caption("Archived materials exist.")

        history = application.get("application_history")
        st.markdown("#### Application History")
        if isinstance(history, list) and history:
            for event in history:
                if isinstance(event, dict):
                    st.caption(f"{event.get('date', '')} · {event.get('event', 'Update')} · {event.get('to', '')}")
        else:
            st.caption(f"{status_date(application) or 'Date not recorded'} · {get_record_status(application)}")
        posting_url = record_posting_url(application)
        portal_url = record_application_portal_url(application)
        materials_target, _ = resolve_role_materials_target(
            application, package, PROJECT_ROOT
        )
        primary_actions = contextual_primary_actions(
            application,
            has_materials=materials_target is not None,
            has_posting_url=posting_url is not None,
            mode=mode,
        )
        st.markdown("#### Application Links")
        link_columns = st.columns(2)
        if portal_url:
            link_columns[0].link_button("Check Application Status", portal_url, use_container_width=True)
        if posting_url:
            link_columns[1].link_button("Open Posting", posting_url, use_container_width=True)
            st.caption(f"Source URL: {posting_url}")
        recovered = _render_context_recovery_action(
            st,
            tracker_id,
            key=f"dashboard_context_recovery_{tracker_id}",
        )
        if recovered:
            st.session_state["dashboard_notice"] = (
                f"Refreshed role context and generated package for "
                f"{application.get('company')} — {application.get('role')}."
            )
            st.rerun()
        if primary_actions:
            action_columns = st.columns(len(primary_actions))
            for column, (label, action_key) in zip(action_columns, primary_actions):
                if action_key == "open_posting" and posting_url:
                    column.link_button(label, posting_url, use_container_width=True)
                    continue
                if not column.button(
                    label,
                    key=f"dashboard_quick_{tracker_id}_{action_key}",
                    use_container_width=True,
                    help=str(materials_target) if action_key == "open_materials" else None,
                ):
                    continue
                if action_key == "open_materials" and materials_target:
                    open_role_materials(st, application, package, PROJECT_ROOT)
                elif action_key == "generate_package":
                    try:
                        with st.spinner("Generating application package…"):
                            generate_package(tracker_id, PROJECT_ROOT)
                    except PackageGenerationError as error:
                        _remember_context_recovery(
                            st.session_state, tracker_id, error
                        )
                        st.error(
                            CONTEXT_MISMATCH_MESSAGE
                            if error.details.get("context_mismatch")
                            else str(error)
                        )
                    else:
                        st.session_state["dashboard_notice"] = (
                            f"Generated package for {application.get('company')} — "
                            f"{application.get('role')}."
                        )
                        st.rerun()
                else:
                    updated = apply_dashboard_status_action(
                        tracker_id, action_key, PROJECT_ROOT
                    )
                    st.session_state["dashboard_notice"] = (
                        f"Updated {updated.get('company')} — {updated.get('role')} "
                        f"to {get_record_status(updated)}."
                    )
                    st.rerun()

        with st.expander("Advanced Details", expanded=source_panel_open):
            raw_source_url = str(application.get("raw_source_url") or application.get("original_source_url") or "").strip()
            if raw_source_url:
                st.caption(f"Source URL: {raw_source_url}")
            _render_source_verification_panel(st, application, tracker_id)
            notes = str(application.get("notes") or "").strip()
            if notes:
                st.markdown("**Internal notes**")
                st.write(notes)
            legacy = str(application.get("legacy_status") or "").strip()
            if legacy:
                st.caption(f"Legacy status: {legacy}")

        with st.expander("More actions", expanded=False):
            more_columns = st.columns(4)
            bucket = workflow_status_bucket(application)
            if get_record_status(application) not in {"Rejected", "Withdrawn / Closed"} and more_columns[0].button(
                "Withdraw / Close",
                key=f"dashboard_more_pause_{tracker_id}",
                use_container_width=True,
            ):
                apply_dashboard_status_action(tracker_id, "paused", PROJECT_ROOT)
                st.session_state["dashboard_notice"] = "Role moved to Withdrawn / Closed."
                st.rerun()
            if more_columns[1].button(
                "Verify manually",
                key=f"dashboard_more_verify_{tracker_id}",
                use_container_width=True,
            ):
                focus_source_verification(
                    st.session_state, dashboard_role_reference(application)
                )
                st.rerun()
            if get_record_status(application) == "Drafted" and more_columns[2].button(
                "Keep Drafted",
                key=f"dashboard_more_reviewed_{tracker_id}",
                use_container_width=True,
            ):
                apply_dashboard_status_action(tracker_id, "reviewed", PROJECT_ROOT)
                st.session_state["dashboard_notice"] = "Role remains Drafted."
                st.rerun()
            follow_up_action = follow_up_action_state(application)
            if follow_up_action["eligible"] and more_columns[3].button(
                "Generate Follow-Up",
                key=f"dashboard_more_followup_{tracker_id}",
                use_container_width=True,
            ):
                try:
                    generate_followups(tracker_id, PROJECT_ROOT)
                except FollowupGenerationError as error:
                    st.error(str(error))
                else:
                    st.session_state["dashboard_notice"] = "Follow-up materials generated."
                    st.rerun()
            elif not follow_up_action["eligible"]:
                more_columns[3].caption(
                    f"{follow_up_action['label']}: {follow_up_action['reason']}"
                )

        with st.expander("Advanced edit role", expanded=False):
            current_status = get_record_status(application)
            choices = status_options(current_status)
            current_priority = str(application.get("priority") or "Medium")
            priority_choices = (
                PRIORITY_OPTIONS
                if current_priority in PRIORITY_OPTIONS
                else (current_priority,) + PRIORITY_OPTIONS
            )
            with st.form(key=f"dashboard_edit_{tracker_id}"):
                edit_columns = st.columns(2)
                edited_status = edit_columns[0].selectbox(
                    "Status",
                    choices,
                    index=choices.index(current_status),
                    key=f"dashboard_status_{tracker_id}",
                )
                edited_priority = edit_columns[1].selectbox(
                    "Priority",
                    priority_choices,
                    index=priority_choices.index(current_priority),
                    key=f"dashboard_priority_{tracker_id}",
                )
                edited_notes = st.text_area(
                    "Notes",
                    value=str(application.get("notes") or ""),
                    key=f"dashboard_notes_{tracker_id}",
                )
                edited_next_action = st.text_area(
                    "Next action",
                    value=str(application.get("next_action") or "Review fit"),
                    key=f"dashboard_next_action_{tracker_id}",
                )
                edited_posting_url = st.text_input("Posting URL", value=str(application.get("posting_url") or record_posting_url(application) or ""))
                edited_portal_url = st.text_input("Application/status portal URL", value=str(application.get("application_portal_url") or ""))
                st.caption(
                    "Visibility follows status: Pass and Invalid/Hidden stay in cleanup; "
                    "active workflow statuses remain visible."
                )
                save_clicked = st.form_submit_button(
                    "Save role updates", type="primary", use_container_width=True
                )
            if save_clicked:
                try:
                    update_dashboard_role(
                        tracker_id,
                        {
                            "status": edited_status,
                            "priority": edited_priority,
                            "notes": edited_notes,
                            "next_action": edited_next_action,
                            "posting_url": edited_posting_url,
                            "application_portal_url": edited_portal_url,
                        },
                        PROJECT_ROOT,
                    )
                except (TrackerValidationError, OSError) as error:
                    st.error(str(error))
                else:
                    message = "Role updates saved."
                    st.session_state[flash_key] = message
                    st.session_state["dashboard_notice"] = message
                    st.rerun()


def _render_application_tracker(
    st: Any,
    applications: list[Dict[str, Any]],
    packages: Dict[str, Dict[str, Any]],
    mode: str = "All Mode",
) -> None:
    st.markdown(
        '<h2 class="cc-section-heading">Applications in Flight</h2>',
        unsafe_allow_html=True,
    )
    if not applications:
        st.caption("No other roles match the current filters.")
        return
    for application in applications:
        _render_role_card(
            st,
            application,
            packages.get(str(application.get("id")), {}),
            mode,
            compact=True,
        )


def _render_recommended_next_steps(
    st: Any,
    applications: list[Dict[str, Any]],
    mode: str,
    packages: Dict[str, Dict[str, Any]],
    focus_records: list[Dict[str, Any]] | None = None,
) -> str:
    all_focus_records = focus_records if focus_records is not None else applications
    compact_mode = bool(st.session_state.get("dashboard_compact_mode", True))
    focus = select_todays_focus(applications)
    with st.container(border=True):
        st.markdown("### Today’s Focus")
        if not focus:
            st.markdown("**No Action Today**")
            st.caption("There are no open applications requiring attention today.")
        else:
            record = find_dashboard_role(applications, focus["id"]) or {}
            role_reference = dashboard_role_reference(record) or focus["id"]
            st.markdown(f"**{focus['company']} — {focus['role']}** · {focus['status']}")
            st.markdown(f"**{focus['label']}** — {focus['reason']}")
            st.markdown(html.escape(str(focus["action"])))
            action_specs = [("view", "View Role", None)]
            portal_url = record_application_portal_url(record)
            posting_url = record_posting_url(record)
            if portal_url:
                action_specs.append(("portal", "Check Application Status", portal_url))
            if posting_url:
                action_specs.append(("posting", "Open Posting", posting_url))
            focus_package = packages.get(str(record.get("id") or ""), {})
            materials_target, _ = resolve_role_materials_target(
                record, focus_package, PROJECT_ROOT
            )
            if materials_target:
                action_specs.append(("materials", "Open Materials", None))
            action_columns = st.columns(len(action_specs))
            for column, (key, label, url) in zip(action_columns, action_specs):
                if url:
                    column.link_button(label, url, use_container_width=True)
                elif column.button(label, key=f"next_{key}_{role_reference}", use_container_width=True):
                    if key == "materials":
                        open_role_materials(st, record, focus_package, PROJECT_ROOT)
                        continue
                    focus_dashboard_role(st.session_state, role_reference)
                    st.rerun()

    compact_mode = bool(st.session_state.get("dashboard_compact_mode", False if st.session_state.get("dashboard_focused_role_id") else True))
    focused_id = str(st.session_state.get("dashboard_focused_role_id") or "")
    focused = find_dashboard_role(all_focus_records, focused_id)
    if focused and not compact_mode:
        visible_references = {
            dashboard_role_reference(record) for record in applications
        }
        focus_heading, clear_column = st.columns((5, 1))
        focus_heading.markdown("### Focused Role Workspace")
        if clear_column.button(
            "Clear focus", key="dashboard_clear_focus", use_container_width=True
        ):
            clear_focused_dashboard_role(st.session_state)
            st.rerun()
        focused_reference = dashboard_role_reference(focused)
        if focused_reference not in visible_references:
            st.caption("Showing focused role outside current filters for convenience.")
        package = packages.get(str(focused.get("id") or ""), {})
        _render_role_card(st, focused, package, mode, compact_mode)
        return str(focused.get("id") or focused_reference)
    if focused_id and not focused:
        warning_column, clear_column = st.columns((5, 1))
        warning_column.warning(
            "Focused role could not be found. It may be hidden by current filters."
        )
        if clear_column.button(
            "Clear focus", key="dashboard_clear_missing_focus", use_container_width=True
        ):
            clear_focused_dashboard_role(st.session_state)
            st.rerun()
    return ""


def _application_label(application: Dict[str, Any]) -> str:
    return (
        f"{company_display_name(application.get('company', 'Company'))} — "
        f"{application.get('role', 'Role')} [{get_record_status(application)}]"
    )


def _application_selection_label(application: Dict[str, Any]) -> str:
    """Return a unique, status-independent label for role selection widgets."""
    tracker_id = str(application.get("id") or "unknown-id")
    return (
        f"{company_display_name(application.get('company', 'Company'))} — "
        f"{application.get('role', 'Role')} · {tracker_id}"
    )


def _show_open_button(st: Any, label: str, path: Path, key: str) -> None:
    if st.button(label, key=key):
        opened, message = open_local_path(path)
        (st.success if opened else st.warning)(message)


def _show_output_paths(st: Any, outputs: Dict[str, str], key_prefix: str) -> None:
    for label, value in outputs.items():
        path = Path(value)
        display_label = OUTPUT_LABELS.get(label, label.replace("_", " ").title())
        st.markdown(f"**{display_label}**")
        st.code(str(path), language=None)
        if path.exists():
            _show_open_button(
                st,
                f"Open {display_label.lower()}",
                path,
                f"{key_prefix}_{label}",
            )
        else:
            st.caption("Missing / not generated.")


def _render_package_summary(st: Any, package_result: Dict[str, Any]) -> None:
    """Show opportunity and quality checks before presenting export paths."""
    opportunity = package_result.get("opportunity", {})
    quality = package_result.get("package_quality", {})
    if opportunity:
        st.markdown(
            f"**Opportunity score:** {opportunity.get('overall_score')}/100  |  "
            f"**Recommendation:** {opportunity.get('apply_recommendation')}  |  "
            f"**Freshness:** {package_result.get('freshness', {}).get('label', 'Unknown freshness / Verify manually')}"
        )
    if quality:
        st.markdown("**Package quality check**")
        columns = st.columns(5)
        for column, (label, key) in zip(
            columns,
            (
                ("Resume tailoring", "resume_tailoring_score"),
                ("Cover letter", "cover_letter_score"),
                ("ATS keywords", "ats_keyword_match"),
                ("Voice match", "voice_match"),
                ("Confidence", "confidence_level"),
            ),
        ):
            value = quality.get(key, "—")
            column.metric(label, f"{value}/100" if isinstance(value, int) else value)
    checklist = package_result.get("package_checklist") or []
    if checklist:
        st.markdown("**Generated package checklist**")
        for index, item in enumerate(checklist):
            label = str(item.get("display_label") or item.get("material_type") or "Material")
            path_value = item.get("preferred_open_path")
            if item.get("exists") and path_value and Path(str(path_value)).is_file():
                path = Path(str(path_value))
                row = st.columns((3, 1))
                row[0].caption(f"Generated / available: {label} (.{path.suffix.lower().lstrip('.')})")
                _show_open_button(row[1], "Open", path, f"package_check_{index}_{label}")
            else:
                reason = str(item.get("missing_reason") or "Missing / not generated")
                st.caption(f"{reason}: {label}")


def _initialize_intake_state(st: Any) -> None:
    defaults = {
        "prospect_url": "",
        "prospect_url_input": "",
        "prospect_url_value": "",
        "prospect_import_url": "",
        "prospect_url_last_imported": "",
        "prospect_context_url": "",
        "prospect_original_source_url": "",
        "prospect_canonical_url": "",
        "prospect_job_id": "",
        "prospect_company": "",
        "prospect_role": "",
        "prospect_location": "",
        "prospect_salary": "",
        "prospect_posting_date": "",
        "prospect_source": "Official career page",
        "prospect_priority": "Medium",
        "prospect_status": "Drafted",
        "prospect_work_arrangement": "Not specified",
        "prospect_description": "",
        "prospect_notes": "",
        "prospect_next_action": "Review fit and generate application package.",
        "prospect_intelligence_stale": False,
        "prospect_description_source": "",
        "prospect_salary_source": "",
        "prospect_reviewed_fields": set(),
        "prospect_role_interpretation": {},
        "prospect_interpretation_feedback": "",
        "prospect_evidence_selection_overrides": {},
        "role_analysis_dirty": False,
        "score_dirty": False,
        "application_strategy_dirty": False,
        "hiring_manager_brief_dirty": False,
        "package_dirty": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def current_prospect_form_values(session_state: Any) -> Dict[str, Any]:
    """Return the reviewed intake form as the canonical scoring/save payload."""
    url = str(
        session_state.get("prospect_url_input")
        or session_state.get("prospect_url_value")
        or session_state.get("prospect_url")
        or ""
    ).strip()
    return {
        "posting_url": url,
        "application_portal_url": session_state.get("prospect_application_portal_url", ""),
        "official_url": url,
        "source_url": url,
        "original_source_url": url,
        "canonical_apply_url": session_state.get("prospect_canonical_url") or url,
        "job_id": session_state.get("prospect_job_id"),
        "company": session_state.get("prospect_company"),
        "job_title": session_state.get("prospect_role"),
        "location": session_state.get("prospect_location"),
        "salary_range": session_state.get("prospect_salary"),
        "salary_source": session_state.get("prospect_salary_source"),
        "posting_date": session_state.get("prospect_posting_date"),
        "source": session_state.get("prospect_source"),
        "priority": session_state.get("prospect_priority"),
        "status": session_state.get("prospect_status"),
        "work_arrangement": session_state.get("prospect_work_arrangement"),
        "job_description": session_state.get("prospect_description"),
        "description_source": session_state.get("prospect_description_source", ""),
        "notes": session_state.get("prospect_notes"),
        "next_action": session_state.get("prospect_next_action"),
        "role_interpretation": dict(
            session_state.get("prospect_role_interpretation") or {}
        ),
        "evidence_selection_overrides": dict(
            session_state.get("prospect_evidence_selection_overrides") or {}
        ),
    }


def refresh_prospect_preview_state(
    session_state: Any, reviewed_field: str = ""
) -> Optional[Dict[str, Any]]:
    """Mark edited intake analysis stale without doing expensive work in a callback."""
    if reviewed_field:
        reviewed = set(session_state.get("prospect_reviewed_fields") or ())
        reviewed.add(reviewed_field)
        session_state["prospect_reviewed_fields"] = reviewed
        if reviewed_field == "salary_range":
            session_state["prospect_salary_source"] = "manual"
        if reviewed_field == "job_description":
            session_state["prospect_description_source"] = "manual"
        if reviewed_field in {"company", "job_title", "job_description"}:
            session_state["prospect_role_interpretation"] = {}
            session_state["prospect_interpretation_feedback"] = ""
            session_state["prospect_evidence_selection_overrides"] = {}
    invalidate_package_context_state(session_state)
    values = current_prospect_form_values(session_state)
    session_state["prospect_intelligence_stale"] = True
    session_state["role_analysis_dirty"] = True
    session_state["score_dirty"] = True
    session_state["application_strategy_dirty"] = True
    session_state["hiring_manager_brief_dirty"] = True
    session_state["package_dirty"] = True
    session_state.pop("prospect_match_report", None)
    session_state.pop("prospect_role_intelligence", None)
    if not prospect_has_usable_job_content(values):
        session_state["prospect_validation_state"] = compute_prospect_validation_state(
            values, {"match_report": incomplete_match_report(values)}
        )
    else:
        session_state["prospect_validation_state"] = compute_prospect_validation_state(
            values, {"match_report": incomplete_match_report(values) or {}}
        )
        session_state["prospect_import_result"] = (
            "warning",
            "Role details changed. Analysis needs refresh.",
        )
    return None


def detect_prospect_intelligence(values: Dict[str, Any]) -> Dict[str, Any]:
    """Infer local company and role guidance from unsaved prospect fields."""
    reviewed_interpretation = (
        dict(values.get("role_interpretation") or {})
        if isinstance(values.get("role_interpretation"), dict)
        else {}
    )
    interpretation_overrides = dict(reviewed_interpretation.get("user_overrides") or {})
    if reviewed_interpretation.get("user_reviewed"):
        interpretation_overrides["user_reviewed"] = True
        if reviewed_interpretation.get("user_feedback"):
            interpretation_overrides["feedback"] = reviewed_interpretation["user_feedback"]
        for field in (
            "primary_archetype", "secondary_archetype", "plain_english_summary",
            "technical_depth",
            "people_management_expectation", "client_facing_expectation",
            "strategic_vs_execution_balance",
        ):
            if reviewed_interpretation.get(field) not in (None, ""):
                interpretation_overrides[field] = reviewed_interpretation[field]
    intelligence = get_effective_voice_profile(
        company_name=str(values.get("company") or ""),
        job_title=str(values.get("job_title") or values.get("role") or ""),
        job_description=str(values.get("job_description") or ""),
        source_url=str(values.get("official_url") or ""),
        role_interpretation_overrides=interpretation_overrides or None,
    )
    intelligence["freshness"] = detect_job_freshness(
        f"Posting date: {values.get('posting_date') or ''}\n{values.get('job_description') or ''}"
    )
    intelligence["source_verification"] = normalize_job_source(values)
    salary_value = str(values.get("salary_range") or "").strip()
    intelligence["salary_parsing_warning"] = bool(
        salary_parsing_warning(values.get("job_description"))
        and (not salary_value or re.fullmatch(r"\$\s*\d{1,2}", salary_value))
    )
    intelligence["match_report"] = (
        score_job_data(
            {
                **values,
                "role_interpretation": intelligence.get("role_interpretation") or {},
            },
            PROJECT_ROOT,
        )
        if prospect_has_usable_job_content(values)
        else incomplete_match_report(values)
    )
    intelligence["role_evidence_selection"] = dict(
        intelligence["match_report"].get("role_evidence_selection") or {}
    )
    role_interpretation = dict(intelligence.get("role_interpretation") or {})
    match_report = intelligence["match_report"]
    hiring_manager_lens = build_hiring_manager_lens(
        role_interpretation,
        list((match_report.get("capability_graph") or {}).get("alignment_matrix") or []),
        dict(match_report.get("evidence_gap_analysis") or {}),
    )
    proof_points = list(intelligence.get("proof_points_to_emphasize") or [])
    evidence_ids = list(intelligence.get("selected_evidence_ids") or [])
    evidence_cards = [
        {
            "id": evidence_id,
            "proof_points": [proof_points[index]] if index < len(proof_points) else [],
        }
        for index, evidence_id in enumerate(evidence_ids)
    ]
    intelligence["hiring_manager_lens"] = hiring_manager_lens
    intelligence["application_strategy"] = build_application_strategy(
        role_interpretation,
        hiring_manager_lens,
        intelligence["match_report"],
        evidence_cards,
    )
    intelligence["hiring_manager_brief"] = build_hiring_manager_brief(
        intelligence["match_report"],
        intelligence["role_evidence_selection"],
        hiring_manager_lens,
        intelligence["application_strategy"],
    )
    intelligence["job_description"] = str(values.get("job_description") or "")
    intelligence["location"] = str(values.get("location") or "")
    intelligence["work_arrangement"] = str(values.get("work_arrangement") or "")
    intelligence["validation_state"] = compute_prospect_validation_state(
        values, intelligence
    )
    return intelligence


def reparse_prospect_fields(values: Dict[str, Any]) -> Dict[str, Any]:
    """Refresh detected form metadata while preserving explicit user-entered identity."""
    refreshed = dict(values)
    description = str(values.get("job_description") or "")
    metadata = extract_metadata(description) if description else {}
    fallback = infer_job_fields_from_url(values.get("official_url"))
    refreshed["job_title"] = preferred_role_title(
        values.get("job_title"), metadata.get("job_title"), values.get("official_url")
    )
    for target, source in (
        ("company", "company"),
        ("location", "location"),
        ("salary_range", "salary_range"),
        ("posting_date", "posting_date"),
        ("work_arrangement", "work_arrangement"),
    ):
        current = str(refreshed.get(target) or "").strip()
        current_is_unknown = current.lower() in {
            "",
            "unknown",
            "not disclosed",
            "not specified",
            "n/a",
        }
        if current_is_unknown and metadata.get(source):
            refreshed[target] = metadata[source]
    for key in ("company", "location", "job_id", "source"):
        if not refreshed.get(key) and fallback.get(key):
            refreshed[key] = fallback[key]
    intelligence = detect_prospect_intelligence(refreshed)
    refreshed["match_report"] = intelligence["match_report"]
    refreshed["source_verification"] = intelligence["source_verification"]
    refreshed["validation_state"] = intelligence["validation_state"]
    refreshed["role_intelligence"] = intelligence
    return refreshed


def apply_manual_reparse_state(session_state: Any) -> Dict[str, Any]:
    """Reconcile intake state after a user-supplied description is parsed successfully."""
    session_state["prospect_role_interpretation"] = {}
    session_state["prospect_interpretation_feedback"] = ""
    session_state["prospect_evidence_selection_overrides"] = {}
    refreshed = reparse_prospect_fields(
        {
            "official_url": session_state.get("prospect_url_value")
            or session_state.get("prospect_url_input")
            or session_state.get("prospect_url"),
            "original_source_url": session_state.get("prospect_original_source_url"),
            "company": session_state.get("prospect_company"),
            "job_title": session_state.get("prospect_role"),
            "location": session_state.get("prospect_location"),
            "salary_range": session_state.get("prospect_salary"),
            "posting_date": session_state.get("prospect_posting_date"),
            "work_arrangement": session_state.get("prospect_work_arrangement"),
            "job_description": session_state.get("prospect_description"),
            "description_source": "manual",
        }
    )
    for state_key, value_key in (
        ("prospect_company", "company"),
        ("prospect_role", "job_title"),
        ("prospect_location", "location"),
        ("prospect_salary", "salary_range"),
        ("prospect_posting_date", "posting_date"),
        ("prospect_work_arrangement", "work_arrangement"),
    ):
        if refreshed.get(value_key):
            session_state[state_key] = refreshed[value_key]
    report = refreshed["match_report"]
    complete = report.get("match_score") is not None
    session_state["prospect_intelligence_stale"] = not complete
    session_state["prospect_description_source"] = "manual"
    session_state["prospect_match_report"] = report
    session_state["prospect_validation_state"] = refreshed["validation_state"]
    session_state["prospect_role_intelligence"] = refreshed["role_intelligence"]
    session_state["role_analysis_dirty"] = False
    session_state["score_dirty"] = False
    session_state["application_strategy_dirty"] = False
    session_state["hiring_manager_brief_dirty"] = False
    session_state["package_dirty"] = True
    invalidate_package_context_state(session_state)
    if complete:
        session_state.pop("prospect_import_result", None)
        session_state["prospect_next_action"] = "Review fit and generate application package."
    else:
        session_state["prospect_import_result"] = (
            "warning",
            IMPORT_EXTRACTION_FALLBACK_MESSAGE,
        )
    return refreshed


def persist_and_generate_prospect(
    values: Dict[str, Any],
    session_state: Any,
    project_root: Path = PROJECT_ROOT,
    *,
    creator: Any = None,
    generator: Any = None,
) -> Dict[str, Any]:
    """Persist the form first, invalidate derivatives, then generate from the saved ID."""
    create = creator or create_prospect
    generate = generator or generate_package
    intake = create(build_prospect_payload(values), project_root)
    tracker_id = str(intake["tracker_id"])
    session_state["last_saved_prospect_id"] = tracker_id
    invalidate_package_context_state(session_state, tracker_id)
    package = generate(tracker_id, project_root)
    return {"intake": intake, "package": package}


def refresh_role_context_and_retry(
    session_state: Any,
    tracker_id: str,
    project_root: Path = PROJECT_ROOT,
    *,
    prospect_values: Optional[Dict[str, Any]] = None,
    creator: Any = None,
    generator: Any = None,
    refresher: Any = None,
    **generation_options: Any,
) -> Dict[str, Any]:
    """Perform the supported one-action context refresh and one generation retry."""
    if prospect_values is not None:
        create = creator or create_prospect
        intake = create(build_prospect_payload(prospect_values), project_root)
        tracker_id = str(intake["tracker_id"])
        session_state["last_saved_prospect_id"] = tracker_id
    generate = generator or generate_package
    refresh = refresher or refresh_saved_package_context
    invalidate_package_context_state(session_state, tracker_id)
    refreshed = refresh(tracker_id, project_root)
    result = generate(
        tracker_id,
        project_root,
        _context_refresh_attempted=True,
        **generation_options,
    )
    result.setdefault("context_recovery", {})
    result["context_recovery"].update(
        {
            "automatic_refresh_attempted": True,
            "refreshed_validation_passed": True,
            "prospect_revision": refreshed.get("prospect_revision"),
        }
    )
    return result


def _remember_context_recovery(
    session_state: Any, tracker_id: str, error: PackageGenerationError
) -> None:
    if not error.details.get("context_mismatch"):
        return
    session_state["package_context_recovery"] = {
        "tracker_id": str(tracker_id),
        "message": CONTEXT_MISMATCH_MESSAGE,
    }


def _render_context_recovery_action(
    st: Any,
    tracker_id: str,
    *,
    key: str,
    prospect_values: Optional[Dict[str, Any]] = None,
    override_closed: bool = False,
) -> Optional[Dict[str, Any]]:
    recovery = st.session_state.get("package_context_recovery") or {}
    if str(recovery.get("tracker_id") or "") != str(tracker_id):
        return None
    st.warning(CONTEXT_MISMATCH_MESSAGE)
    if not st.button("Refresh Role Context & Try Again", key=key, type="primary"):
        return None
    try:
        with st.spinner("Refreshing the saved role context and trying once more…"):
            result = refresh_role_context_and_retry(
                st.session_state,
                tracker_id,
                PROJECT_ROOT,
                prospect_values=prospect_values,
                override_closed=override_closed,
            )
    except (ProspectIntakeError, PackageGenerationError, TrackerValidationError) as error:
        is_context_mismatch = isinstance(
            error, PackageGenerationError
        ) and error.details.get("context_mismatch")
        if isinstance(error, PackageGenerationError):
            _remember_context_recovery(st.session_state, tracker_id, error)
        st.error(CONTEXT_MISMATCH_MESSAGE if is_context_mismatch else str(error))
        if isinstance(error, PackageGenerationError) and error.checklist:
            _render_package_summary(st, {"package_checklist": error.checklist})
        return None
    st.session_state.pop("package_context_recovery", None)
    st.session_state["last_package_outputs"] = result["outputs"]
    st.session_state["last_package_result"] = result
    st.session_state["package_preview_prospect_id"] = tracker_id
    st.success("Career Catalyst refreshed the role context before generating this package.")
    return result


def prospect_has_usable_job_content(values: Dict[str, Any]) -> bool:
    """Gate parsing/scoring on a reliable identity and substantive description."""
    company = str(values.get("company") or "").strip()
    title = str(values.get("job_title") or values.get("role") or "").strip()
    description = values.get("job_description") or values.get("description") or ""
    return bool(
        company
        and is_valid_role_title(title)
        and is_usable_job_description(description)
    )


def import_failure_preview(url: str, error_message: str) -> Dict[str, Any]:
    """Preserve URL source trust when automated import needs a manual paste."""
    verification = normalize_job_source({"official_url": url})
    source_name = verification.get("source_name") or "Unknown"
    message = str(error_message or "").strip()
    if source_name == "Greenhouse":
        message = (
            "Greenhouse source verified, but the page did not provide a complete job "
            "description. Paste the job description manually before saving or generating a package."
        )
    elif verification.get("source_type") == "Direct Employer":
        message = IMPORT_EXTRACTION_FALLBACK_MESSAGE
    elif verification.get("source_type") in {
        "Industry Job Board",
        "Gaming Industry Job Board",
        "Music Industry Job Board",
        "Entertainment Job Board",
        "Startup / Tech Job Board",
    }:
        message = (
            f"{source_name} is a recognized industry job board. Paste the job "
            "description manually if the listing details are incomplete."
        )
    return {"message": message, "verification": verification}


def apply_prospect_url_import_state(
    session_state: Any, importer: Any = None
) -> Dict[str, Any]:
    """Run the shared Enter/button URL import path while preserving safe fallback state."""
    import_callable = importer or import_job_from_url
    url = str(
        session_state.get("prospect_url_input")
        or session_state.get("prospect_url_value")
        or session_state.get("prospect_import_url")
        or session_state.get("prospect_url")
        or ""
    ).strip()
    previous_context_url = session_state.get("prospect_context_url")
    if previous_context_url is not None and str(previous_context_url) != url:
        for key in (
            "prospect_company",
            "prospect_role",
            "prospect_location",
            "prospect_salary",
            "prospect_posting_date",
            "prospect_description",
            "prospect_job_id",
        ):
            session_state[key] = ""
        mark_prospect_intelligence_stale(session_state)
        session_state["prospect_reviewed_fields"] = set()
        session_state["prospect_salary_source"] = ""
        session_state["prospect_role_interpretation"] = {}
        session_state["prospect_interpretation_feedback"] = ""
        session_state["prospect_evidence_selection_overrides"] = {}
    session_state["prospect_context_url"] = url
    session_state["prospect_url_value"] = url
    session_state["prospect_import_url"] = url
    session_state["prospect_url_last_imported"] = url
    session_state["prospect_original_source_url"] = url
    invalidate_package_context_state(session_state)
    reviewed_fields = set(session_state.get("prospect_reviewed_fields") or ())
    fallback = infer_job_fields_from_url(url)
    verification = normalize_job_source({"official_url": url})
    canonical = str(verification.get("canonical_apply_url") or url)
    session_state["prospect_canonical_url"] = canonical
    if fallback.get("job_id"):
        session_state["prospect_job_id"] = fallback["job_id"]
    if (
        verification.get("source_name")
        and verification.get("source_name") != "Unknown"
        and "source" not in reviewed_fields
    ):
        session_state["prospect_source"] = verification["source_name"]
    for state_key, fallback_key in (
        ("prospect_company", "company"),
        ("prospect_location", "location"),
    ):
        if fallback.get(fallback_key) and not session_state.get(state_key):
            session_state[state_key] = fallback[fallback_key]
    current_title = session_state.get("prospect_role")
    fallback_title = preferred_role_title(current_title, "", url)
    if fallback_title:
        session_state["prospect_role"] = fallback_title

    try:
        imported = import_callable(url)
    except (JobImportError, OSError, ValueError) as error:
        partial_data = getattr(error, "partial_data", {})
        for state_key, imported_key in (
            ("prospect_company", "company"),
            ("prospect_role", "job_title"),
            ("prospect_location", "location"),
            ("prospect_salary", "salary_range"),
            ("prospect_posting_date", "posting_date"),
            ("prospect_job_id", "job_id"),
        ):
            if partial_data.get(imported_key) and not session_state.get(state_key):
                session_state[state_key] = partial_data[imported_key]
        if (
            is_usable_job_description(partial_data.get("job_description"))
            and "job_description" not in reviewed_fields
        ):
            session_state["prospect_description"] = partial_data["job_description"]
        message = IMPORT_EXTRACTION_FALLBACK_MESSAGE
        session_state["prospect_import_result"] = ("warning", message)
        session_state["prospect_next_action"] = (
            "Paste the job description and re-score before generating package."
        )
        session_state["prospect_intelligence_stale"] = True
        session_state.pop("prospect_match_report", None)
        failure_values = {
            "official_url": url,
            "original_source_url": url,
            "company": session_state.get("prospect_company"),
            "job_title": session_state.get("prospect_role"),
            "location": session_state.get("prospect_location"),
            "salary_range": session_state.get("prospect_salary"),
            "posting_date": session_state.get("prospect_posting_date"),
            "job_description": session_state.get("prospect_description"),
        }
        session_state["prospect_validation_state"] = compute_prospect_validation_state(
            failure_values,
            {
                "match_report": incomplete_match_report(failure_values),
                "source_verification": verification,
            },
        )
        return {"status": "partial", "message": message, "verification": verification}

    imported_title = imported.get("job_title")
    selected_title = preferred_role_title(current_title, imported_title, url)
    title_rejected = bool(imported_title and not is_valid_role_title(imported_title))
    if selected_title and "job_title" not in reviewed_fields:
        session_state["prospect_role"] = selected_title
    elif title_rejected and "job_title" not in reviewed_fields:
        session_state["prospect_role"] = ""
    for state_key, imported_key in (
        ("prospect_company", "company"),
        ("prospect_location", "location"),
        ("prospect_salary", "salary_range"),
        ("prospect_posting_date", "posting_date"),
        ("prospect_work_arrangement", "work_arrangement"),
        ("prospect_description", "job_description"),
        ("prospect_job_id", "job_id"),
    ):
        if imported.get(imported_key) and imported_key not in reviewed_fields:
            session_state[state_key] = imported[imported_key]
    if imported.get("salary_range") and "salary_range" not in reviewed_fields:
        session_state["prospect_salary_source"] = "imported"
    if (imported.get("source_name") or imported.get("source")) and "source" not in reviewed_fields:
        session_state["prospect_source"] = imported.get("source_name") or imported.get("source")
    if (
        is_usable_job_description(imported.get("job_description"))
        and "job_description" not in reviewed_fields
    ):
        session_state["prospect_description_source"] = "imported"
    incomplete = not prospect_has_usable_job_content(
        {
            "company": session_state.get("prospect_company"),
            "job_title": session_state.get("prospect_role"),
            "job_description": session_state.get("prospect_description"),
        }
    )
    message = (
        "Imported title looked like job description text. Please confirm the role title before saving."
        if title_rejected
        else IMPORT_EXTRACTION_FALLBACK_MESSAGE
        if incomplete
        else "Imported the role details. Review them before saving."
    )
    session_state["prospect_import_result"] = (
        "error" if title_rejected or incomplete else "success",
        message,
    )
    session_state["prospect_intelligence_stale"] = bool(title_rejected or incomplete)
    if not title_rejected and not incomplete:
        scoring_values = {
            "company": session_state.get("prospect_company"),
            "job_title": session_state.get("prospect_role"),
            "job_description": session_state.get("prospect_description"),
            "official_url": url,
        }
        scoring_values.update(
            {
                "original_source_url": url,
                "location": session_state.get("prospect_location"),
                "salary_range": session_state.get("prospect_salary"),
                "salary_source": session_state.get("prospect_salary_source"),
                "posting_date": session_state.get("prospect_posting_date"),
                "work_arrangement": session_state.get("prospect_work_arrangement"),
                "description_source": session_state.get("prospect_description_source"),
            }
        )
        intelligence = detect_prospect_intelligence(scoring_values)
        session_state["prospect_match_report"] = intelligence["match_report"]
        session_state["prospect_validation_state"] = intelligence["validation_state"]
        session_state["prospect_role_intelligence"] = intelligence
        session_state["prospect_role_interpretation"] = dict(
            intelligence.get("role_interpretation") or {}
        )
    else:
        session_state.pop("prospect_match_report", None)
        incomplete_values = {
            "official_url": url,
            "original_source_url": url,
            "company": session_state.get("prospect_company"),
            "job_title": session_state.get("prospect_role"),
            "salary_range": session_state.get("prospect_salary"),
            "posting_date": session_state.get("prospect_posting_date"),
            "job_description": session_state.get("prospect_description"),
        }
        session_state["prospect_validation_state"] = compute_prospect_validation_state(
            incomplete_values,
            {
                "match_report": incomplete_match_report(incomplete_values),
                "source_verification": normalize_job_source(incomplete_values),
            },
        )
    return {
        "status": "partial" if title_rejected or incomplete else "success",
        "message": message,
        "imported": imported,
    }


def prospect_warning_messages(intelligence: Dict[str, Any]) -> list[str]:
    """Return current posting observations for compatibility with older callers."""
    validation = intelligence.get("validation_state") or {}
    return [
        str(item.get("label"))
        for item in validation.get("posting_verification", [])
        if item.get("label")
    ]


def _humanize_taxonomy(value: Any) -> str:
    label = str(value or "").replace("_", " ").title()
    return label.replace("Ai ", "AI ").replace("Gtm ", "GTM ")


def _render_prospect_validation(st: Any, validation: Dict[str, Any]) -> None:
    """Render one calm, reconciled validation summary from current prospect data."""
    st.markdown(f"### Prospect health: {validation.get('health', 'Incomplete')}")
    st.markdown("**Content Analysis**")
    for item in validation.get("content_analysis", []):
        marker = "✓" if item.get("status") == "complete" else "○"
        st.markdown(f"{marker} {item.get('label')}")
    st.markdown("**Posting Verification**")
    for observation in validation.get("posting_verification", []):
        marker = "⚠" if observation.get("level") == "caution" else "•"
        st.caption(f"{marker} {observation.get('label')}")
    original_url = str(validation.get("original_posting_url") or "").strip()
    if original_url:
        st.link_button("Open Original Posting", original_url, use_container_width=False)


def apply_role_interpretation_feedback(
    session_state: Any,
    interpretation: Dict[str, Any],
    feedback: str,
    overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Store a lightweight user correction as the authoritative scoring input."""
    if feedback == "Reinterpret":
        session_state["prospect_role_interpretation"] = {}
        session_state["prospect_interpretation_feedback"] = ""
        return {}
    updated = dict(interpretation or {})
    applied = dict(updated.get("user_overrides") or {})
    applied.update(dict(overrides or {}))
    if feedback == "Too technical" and "technical_depth" not in applied:
        current = str(updated.get("technical_depth") or "Unclear")
        applied["technical_depth"] = {
            "High": "Moderate",
            "Moderate": "Low",
        }.get(current, "Low")
    if feedback == "Too operational" and "strategic_vs_execution_balance" not in applied:
        applied["strategic_vs_execution_balance"] = "Primarily strategic"
    updated.update(applied)
    updated["user_overrides"] = applied
    updated["user_reviewed"] = True
    updated["user_feedback"] = feedback
    session_state["prospect_role_interpretation"] = updated
    session_state["prospect_interpretation_feedback"] = feedback
    return updated


def _render_role_interpretation(
    st: Any, intelligence: Dict[str, Any], *, editable: bool = False
) -> None:
    interpretation = intelligence.get("role_interpretation") or {}
    if not isinstance(interpretation, dict) or not interpretation:
        return
    st.markdown("### What this role actually is")
    confidence = float(
        interpretation.get("interpretation_confidence")
        or interpretation.get("confidence")
        or 0
    )
    st.caption(
        f"Primary interpretation: {interpretation.get('primary_archetype', 'Unclear')} "
        f"· {round(confidence * 100)}% confidence · {interpretation.get('ambiguity_level', 'Low')} ambiguity"
    )
    st.markdown(str(interpretation.get("plain_english_summary") or ""))
    alternates = list(interpretation.get("secondary_interpretations") or [])
    if alternates:
        if interpretation.get("ambiguity_level") in {"Medium", "High"}:
            st.warning("Career Catalyst sees more than one plausible version of this role. The package will use the primary interpretation unless you confirm an alternate.")
        with st.expander("Alternate interpretations"):
            for index, alternate in enumerate(alternates):
                st.markdown(
                    f"**{index + 2}. {alternate.get('archetype')} — {alternate.get('confidence_percent', 0)}%**"
                )
                st.write(str(alternate.get("plain_english_description") or ""))
                signals = alternate.get("supporting_evidence_signals") or []
                if signals:
                    st.caption("Signals: " + ", ".join(str(value) for value in signals))
                if editable and st.button(
                    f"Use {alternate.get('archetype')}",
                    key=f"use_secondary_interpretation_{index}",
                ):
                    apply_role_interpretation_feedback(
                        st.session_state,
                        interpretation,
                        "Use the secondary interpretation",
                        {"primary_archetype": alternate.get("archetype")},
                    )
                    st.rerun()
            st.markdown("**What would change the answer?**")
            for question in interpretation.get("unresolved_questions") or []:
                st.markdown(f"- {question}")
    st.markdown("**The real business problem**")
    st.write(str(interpretation.get("core_mission") or "Not clear from the posting."))
    responsibilities = interpretation.get("likely_day_to_day") or interpretation.get("top_responsibilities") or []
    if responsibilities:
        st.markdown("**They need someone to:**")
        for item in responsibilities[:6]:
            st.markdown(f"- {item}")
    st.markdown("**The real candidate profile**")
    st.write(str(interpretation.get("candidate_profile") or "Verify the intended candidate profile."))
    _render_hiring_manager_lens(st, intelligence)
    st.markdown("### What determines whether this is a fit")
    st.markdown(
        f"Technical depth: **{interpretation.get('technical_depth', 'Unclear')}** · "
        f"Client-facing: **{interpretation.get('client_facing_expectation', 'Not indicated')}** · "
        f"People management: **{interpretation.get('people_management_expectation', 'Not indicated')}**"
    )
    questions = interpretation.get("major_fit_questions") or []
    if questions:
        st.markdown("**Verify before applying:**")
        for item in questions[:5]:
            st.markdown(f"- {item}")
    with st.expander("Deeper role interpretation"):
        st.markdown(
            f"**Primary archetype:** {interpretation.get('primary_archetype', 'Unclear')}  |  "
            f"**Secondary:** {interpretation.get('secondary_archetype') or 'None detected'}  |  "
            f"**Confidence:** {interpretation.get('confidence_label', 'Low')}"
        )
        st.markdown(
            f"**Technical depth:** {interpretation.get('technical_depth', 'Unclear')}  |  "
            f"**People management:** {interpretation.get('people_management_expectation', 'Not indicated')}  |  "
            f"**Client-facing:** {interpretation.get('client_facing_expectation', 'Not indicated')}"
        )
        must_haves = interpretation.get("true_must_haves") or []
        preferred = interpretation.get("preferred_or_trainable") or []
        generic = interpretation.get("generic_language") or []
        if must_haves:
            st.markdown("**True must-haves**")
            for item in must_haves:
                st.markdown(f"- {item}")
        if preferred:
            st.markdown("**Preferred or learnable**")
            for item in preferred:
                st.markdown(f"- {item}")
        if generic:
            st.caption("Generic language downweighted: " + ", ".join(generic))
        hidden = interpretation.get("hidden_hiring_criteria") or []
        if hidden:
            st.markdown("**Likely hidden hiring criteria (inferred)**")
            for item in hidden:
                st.markdown(f"- {item}")
        if st.session_state.get("debug_mode"):
            st.json(interpretation.get("diagnostics") or {})
    if not editable:
        return
    feedback_columns = st.columns(6)
    for column, label in zip(
        feedback_columns,
        ("This looks right", "Too technical", "Too operational", "Too broad", "Wrong role type", "Reinterpret"),
    ):
        if column.button(label, key=f"role_interpretation_{label.lower().replace(' ', '_')}"):
            apply_role_interpretation_feedback(
                st.session_state, interpretation, label
            )
            st.rerun()
    with st.expander("Correct the interpretation"):
        current_archetype = str(interpretation.get("primary_archetype") or ROLE_ARCHETYPES[0])
        archetype_index = ROLE_ARCHETYPES.index(current_archetype) if current_archetype in ROLE_ARCHETYPES else 0
        archetype = st.selectbox(
            "Primary role archetype",
            ROLE_ARCHETYPES,
            index=archetype_index,
            key="prospect_interpretation_archetype_override",
        )
        summary = st.text_area(
            "Plain-English role summary",
            value=str(interpretation.get("plain_english_summary") or ""),
            key="prospect_interpretation_summary_override",
        )
        technical_options = ("Low", "Moderate", "High", "Unclear")
        technical_value = str(interpretation.get("technical_depth") or "Unclear")
        technical = st.selectbox(
            "Technical depth",
            technical_options,
            index=technical_options.index(technical_value) if technical_value in technical_options else 3,
            key="prospect_interpretation_technical_override",
        )
        expectation_options = ("Required", "Likely", "Not indicated", "Unclear")
        people_value = str(interpretation.get("people_management_expectation") or "Not indicated")
        people = st.selectbox(
            "People-management expectation",
            expectation_options,
            index=expectation_options.index(people_value) if people_value in expectation_options else 2,
            key="prospect_interpretation_people_override",
        )
        client_value = str(interpretation.get("client_facing_expectation") or "Not indicated")
        client = st.selectbox(
            "Client-facing expectation",
            expectation_options,
            index=expectation_options.index(client_value) if client_value in expectation_options else 2,
            key="prospect_interpretation_client_override",
        )
        balance_options = (
            "Primarily strategic", "Balanced strategy and execution",
            "Primarily execution", "Unclear",
        )
        balance_value = str(
            interpretation.get("strategic_vs_execution_balance") or "Unclear"
        )
        balance = st.selectbox(
            "Strategy-versus-execution balance",
            balance_options,
            index=balance_options.index(balance_value) if balance_value in balance_options else 3,
            key="prospect_interpretation_balance_override",
        )
        if st.button("Apply interpretation corrections", key="apply_role_interpretation_corrections"):
            apply_role_interpretation_feedback(
                st.session_state,
                interpretation,
                "User correction",
                {
                    "primary_archetype": archetype,
                    "plain_english_summary": summary,
                    "technical_depth": technical,
                    "people_management_expectation": people,
                    "client_facing_expectation": client,
                    "strategic_vs_execution_balance": balance,
                },
            )
            st.rerun()


def _render_hiring_manager_lens(st: Any, intelligence: Dict[str, Any]) -> None:
    lens = intelligence.get("hiring_manager_lens") or {}
    if not isinstance(lens, dict) or not lens:
        return
    st.markdown("### What the hiring manager is probably trying to solve")
    st.write(str(lens.get("hiring_problem") or "Not clear from the posting."))
    yes_factors = list(lens.get("likely_yes_factors") or [])
    hesitations = list(lens.get("likely_hesitations") or [])
    if yes_factors:
        st.markdown("**Likely yes factors:** " + "; ".join(yes_factors[:3]))
    if hesitations:
        st.markdown("**Likely hesitation:** " + str(hesitations[0]))
    with st.expander("Detailed hiring-manager analysis"):
        for label, field in (
            ("Non-negotiables", "non_negotiables"),
            ("First resume scan", "first_scan_priorities"),
            ("Interview probes", "interview_probe_areas"),
            ("Application must prove", "application_proof_requirements"),
            ("Positioning risks", "application_positioning_risks"),
        ):
            values = lens.get(field) or []
            if values:
                st.markdown(f"**{label}**")
                for value in values:
                    st.markdown(f"- {value}")


def _render_application_strategy(st: Any, intelligence: Dict[str, Any]) -> None:
    strategy = intelligence.get("application_strategy") or {}
    if not isinstance(strategy, dict) or not strategy:
        return
    st.markdown("### Application strategy")
    warning = str(strategy.get("unconfirmed_interpretation_warning") or "")
    if warning:
        st.warning(warning)
    st.write(str(strategy.get("candidate_positioning") or ""))
    direct = strategy.get("strongest_direct_evidence") or []
    adjacent = strategy.get("strongest_adjacent_evidence") or []
    if direct:
        st.markdown("**Direct evidence:** " + "; ".join(str(value) for value in direct[:4]))
    if adjacent:
        st.markdown("**Strong adjacent evidence:** " + "; ".join(str(value) for value in adjacent[:4]))
    st.markdown("**Honest boundary:** " + str(strategy.get("honest_boundary") or "Keep ownership claims within verified evidence."))
    if st.session_state.get("debug_mode"):
        st.json(strategy)


def _render_role_evidence_selection(
    st: Any,
    intelligence: Dict[str, Any],
    *,
    tracker_id: str = "",
    editable: bool = False,
) -> None:
    """Show a compact automatic result; hydrate review controls only on request."""
    selection = dict(
        intelligence.get("role_evidence_selection")
        or (intelligence.get("match_report") or {}).get("role_evidence_selection")
        or {}
    )
    if not selection:
        return
    st.markdown("### Evidence Used for This Role")
    st.caption(
        "Selected automatically from verified evidence. You normally do not need to change it."
    )
    for heading, field in (
        ("Primary", "primary_evidence"),
        ("Supporting", "supporting_evidence"),
    ):
        items = list(selection.get(field) or [])
        if not items:
            continue
        st.markdown(f"**{heading}**")
        for item in items:
            st.markdown(f"- {item.get('title') or item.get('id')}")

    scope_key = tracker_id or "new_prospect"
    review_key = f"review_evidence_selection_{scope_key}"
    if st.button("Review Selection", key=f"open_{review_key}"):
        st.session_state[review_key] = not st.session_state.get(review_key, False)
        st.rerun()
    if not st.session_state.get(review_key, False):
        return

    st.markdown("#### Review Selection")
    st.caption("Changes apply only to this prospect and never edit the global Evidence Profile.")
    # This is the lazy-load boundary: the full profile is not read before Review Selection opens.
    profile = load_cached_evidence_profile(PROJECT_ROOT)
    library = {
        str(item.get("id")): item
        for item in profile.get("evidence") or []
        if item.get("verification_status") in {"Verified", "User Confirmed"}
        and item.get("evidence_type") not in {"Unsupported", "Inferred"}
    }
    pending_key = f"pending_evidence_overrides_{scope_key}"
    saved_overrides = normalize_selection_overrides(selection.get("overrides") or {})
    pending_overrides = (
        normalize_selection_overrides(st.session_state.get(pending_key) or {})
        if tracker_id and pending_key in st.session_state
        else saved_overrides
    )
    selection["overrides"] = pending_overrides
    relevant_capabilities = list(selection.get("important_capabilities") or [])
    if relevant_capabilities:
        st.markdown("**Relevant capabilities:** " + ", ".join(relevant_capabilities[:10]))

    if tracker_id and pending_overrides != saved_overrides:
        st.info(
            "Evidence changes are pending. Apply them to this prospect when ready."
        )
        apply_column, discard_column = st.columns(2)
        if apply_column.button(
            "Apply Evidence Changes",
            key=f"apply_evidence_changes_{scope_key}",
            type="primary",
            use_container_width=True,
        ):
            persist_evidence_overrides_if_changed(
                tracker_id,
                saved_overrides,
                pending_overrides,
                PROJECT_ROOT,
            )
            st.session_state.pop(pending_key, None)
            invalidate_package_context_state(st.session_state, tracker_id)
            st.rerun()
        if discard_column.button(
            "Discard Evidence Changes",
            key=f"discard_evidence_changes_{scope_key}",
            use_container_width=True,
        ):
            st.session_state.pop(pending_key, None)
            st.rerun()

    def apply_action(evidence_id: str, action: str, replacement_id: str = "") -> None:
        if tracker_id:
            stage_evidence_override(
                st.session_state,
                pending_key,
                selection.get("overrides") or {},
                evidence_id,
                action,
                replacement_id=replacement_id,
            )
        else:
            updated = update_selection_overrides(
                selection.get("overrides") or {}, evidence_id, action,
                replacement_id=replacement_id,
            )
            st.session_state["prospect_evidence_selection_overrides"] = updated
            st.session_state["prospect_evidence_dirty"] = True
            st.session_state["score_dirty"] = True
            st.session_state["application_strategy_dirty"] = True
            st.session_state["hiring_manager_brief_dirty"] = True
            st.session_state["package_dirty"] = True
            st.session_state["prospect_intelligence_stale"] = True
            invalidate_package_context_state(st.session_state)
        st.rerun()

    selected_ids = set(selection.get("selected_evidence_ids") or [])
    replacement_options = {
        evidence_id: str(item.get("title") or evidence_id)
        for evidence_id, item in library.items() if evidence_id not in selected_ids
    }
    for heading, field in (
        ("Primary", "primary_evidence"),
        ("Supporting", "supporting_evidence"),
    ):
        items = list(selection.get(field) or [])
        st.markdown(f"##### {heading}")
        if not items:
            st.caption("No evidence is currently assigned to this section.")
            continue
        for item in items:
            evidence_id = str(item.get("id"))
            with st.container(border=True):
                st.markdown(f"**{item.get('title')}**")
                st.write(str(item.get("description") or ""))
                with st.expander("Why Selected"):
                    for reason in item.get("why_selected") or []:
                        st.markdown(f"- {reason}")
                with st.expander("Source and usage"):
                    provenance = dict(item.get("provenance") or {})
                    st.markdown(
                        f"**Source:** {item.get('source') or 'Recorded career information'}"
                    )
                    if item.get("source_reference"):
                        st.write(str(item.get("source_reference")))
                    st.caption(
                        f"Confidence: {item.get('confidence') or 'Not specified'} · "
                        f"Recorded: {provenance.get('when') or item.get('updated_at') or 'Date unavailable'}"
                    )
                    uses = [
                        name.replace("_", " ")
                        for name, enabled in dict(item.get("recommended_usage") or {}).items()
                        if enabled
                    ]
                    if uses:
                        st.write("Used for: " + ", ".join(uses))
                source_key = f"show_evidence_source_{scope_key}_{evidence_id}"
                if st.session_state.get(source_key):
                    provenance = item.get("provenance") or {}
                    st.info(
                        f"Source: {item.get('source')} — {item.get('source_reference') or 'No reference supplied'}\n\n"
                        f"Provenance: {provenance.get('how') or 'Recorded'} · {provenance.get('when') or 'Date unavailable'}"
                    )
                if not editable:
                    continue
                controls = st.columns(2)
                if controls[0].button("Remove", key=f"exclude_{scope_key}_{evidence_id}"):
                    apply_action(evidence_id, "exclude")
                action_label = "Demote to Supporting" if field == "primary_evidence" else "Promote to Primary"
                action_name = "demote_supporting" if field == "primary_evidence" else "make_primary"
                if controls[1].button(action_label, key=f"level_{scope_key}_{evidence_id}"):
                    apply_action(evidence_id, action_name)
                if replacement_options:
                    replacement_id = st.selectbox(
                        "Replace Evidence",
                        tuple(replacement_options),
                        format_func=lambda value: replacement_options[value],
                        key=f"replacement_{scope_key}_{evidence_id}",
                    )
                    if st.button("Replace Evidence", key=f"replace_{scope_key}_{evidence_id}"):
                        apply_action(evidence_id, "replace", replacement_id)

    if editable and replacement_options:
        add_id = st.selectbox(
            "Add Evidence", tuple(replacement_options),
            format_func=lambda value: replacement_options[value],
            key=f"add_evidence_{scope_key}",
        )
        if st.button("Add Evidence", key=f"add_evidence_button_{scope_key}"):
            apply_action(add_id, "include")

    if editable and st.button("Reset to Automatic", key=f"reset_evidence_{scope_key}"):
        reset = update_selection_overrides(selection.get("overrides") or {}, "", "reset")
        if tracker_id:
            persist_evidence_overrides_if_changed(
                tracker_id, saved_overrides, reset, PROJECT_ROOT
            )
            st.session_state.pop(pending_key, None)
            applications = load_cached_application_tracker(PROJECT_ROOT)
            refresh_saved_application_analysis(tracker_id, applications, PROJECT_ROOT)
            invalidate_tracker_cache()
        else:
            st.session_state["prospect_evidence_selection_overrides"] = reset
            st.session_state["prospect_evidence_dirty"] = True
        st.rerun()

    # Legacy names retained only as migration vocabulary: Evidence Selected for This Role,
    # Primary Evidence,
    # Supporting Evidence, Transferable Evidence, Known Gaps, Excluded Evidence,
    # Make Primary, View Source, Include, Exclude.


def _render_hiring_manager_brief(st: Any, brief: Dict[str, Any]) -> None:
    """Render the five decisions a user needs without exposing analysis machinery."""
    st.markdown("## Hiring Manager Brief")
    if not brief:
        st.info(
            "This prospect predates Hiring Manager Briefs. Refresh Analysis to create one "
            "from the saved role and career information."
        )
        return
    st.markdown("### Overall Match")
    st.markdown(f"**{brief.get('match_recommendation') or 'Review This Role'}**")
    st.write(str(brief.get("match_summary") or "Review the role before deciding."))

    st.markdown("### Why You’re a Match")
    themes = list(brief.get("why_match") or [])
    if themes:
        for theme in themes:
            if not isinstance(theme, dict):
                continue
            st.markdown(f"**{theme.get('heading') or 'Relevant Experience'}**")
            st.write(str(theme.get("explanation") or ""))
    else:
        st.caption("Refresh the analysis to identify the strongest matching themes.")

    st.markdown("### What to Emphasize")
    for value in brief.get("what_to_emphasize") or []:
        st.markdown(f"- {value}")

    st.markdown("### What to Be Ready to Discuss")
    discussion = list(brief.get("what_to_discuss") or [])
    if discussion:
        for value in discussion:
            st.markdown(f"- {value}")
    else:
        st.caption("No material concerns were identified beyond normal interview preparation.")

    st.markdown("### Recommendation")
    st.markdown(f"**{brief.get('recommendation') or 'Consider'}**")
    st.markdown(
        f"**Next:** {brief.get('recommended_next_step') or 'Review the role and decide whether to continue.'}"
    )


def _render_intelligence_preview(
    st: Any,
    intelligence: Dict[str, Any],
    *,
    editable_interpretation: bool = False,
    evidence_tracker_id: str = "",
) -> None:
    with st.container(border=True):
        _render_hiring_manager_brief(
            st, dict(intelligence.get("hiring_manager_brief") or {})
        )
        scope_key = evidence_tracker_id or "new_prospect"
        explanation_key = f"advanced_conclusion_{scope_key}"
        if st.button(
            "How Career Catalyst Reached This Conclusion",
            key=f"open_{explanation_key}",
        ):
            st.session_state[explanation_key] = not st.session_state.get(
                explanation_key, False
            )
            st.rerun()
        if not st.session_state.get(explanation_key, False):
            return

        st.markdown("### Analysis Details")
        st.caption(
            "This optional view contains the role interpretation, experience used, "
            "requirement alignment, confidence, gaps, and prospect-only overrides."
        )
        freshness = intelligence.get("freshness")
        if freshness:
            st.markdown(
                f"Freshness: **{freshness['label']}**  |  Posting status: **{freshness['posting_status']}**"
            )
        verification = intelligence.get("source_verification")
        if verification:
            st.markdown(
                f"Job source: **{verification['source_name']}**  |  "
                f"Source type: **{verification['source_type']}**  |  "
                f"Recognition: **{verification.get('source_recognition', 'Unrecognized source')}**  |  "
                f"Metadata: **{verification.get('metadata_status', 'Metadata unavailable')}**"
            )
        _render_prospect_validation(st, intelligence.get("validation_state") or {})
        _render_role_interpretation(
            st, intelligence, editable=editable_interpretation
        )
        _render_role_evidence_selection(
            st,
            intelligence,
            tracker_id=evidence_tracker_id,
            editable=editable_interpretation or bool(evidence_tracker_id),
        )
        match_report = intelligence.get("match_report")
        if isinstance(match_report, dict):
            if st.session_state.get("debug_mode") and match_report.get(
                "interpretation_assessment"
            ):
                st.markdown("**Interpretation-to-score diagnostics**")
                st.json(match_report["interpretation_assessment"])
            st.markdown(_match_score_html(match_report), unsafe_allow_html=True)
        _render_application_strategy(st, intelligence)
        strategy = intelligence.get("application_strategy") or {}
        angle = str(strategy.get("cover_letter_thesis") or "")
        angles = intelligence.get("cover_letter_angle", [])
        if angle or angles:
            st.markdown(f"**Suggested cover letter angle:** {angle or angles[0]}")
        proof_points = strategy.get("cover_letter_proof_sequence") or intelligence.get("proof_points_to_emphasize", [])
        if proof_points:
            st.markdown(
                "**Suggested proof points:** " + "; ".join(str(value) for value in proof_points[:4])
            )


def _render_add_prospect(st: Any) -> None:
    st.markdown(
        '<h2 class="cc-section-heading">Add Prospect</h2>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Paste the listing URL and job description. Career Catalyst will classify the source and flag verification needs."
    )
    _initialize_intake_state(st)

    def trigger_url_import() -> None:
        apply_prospect_url_import_state(st.session_state)

    def refresh_reviewed_field(field: str) -> None:
        refresh_prospect_preview_state(st.session_state, field)

    if not st.session_state.get("prospect_url_input"):
        st.session_state["prospect_url_input"] = st.session_state.get("prospect_url_value", "")

    with st.form("prospect_url_import_form", clear_on_submit=False):
        st.text_input("Posting URL", key="prospect_url_input")
        url_import_submitted = st.form_submit_button("Try Import From URL")
    if url_import_submitted:
        trigger_url_import()
    import_result = st.session_state.get("prospect_import_result")
    if import_result:
        level, message = import_result
        (st.success if level == "success" else st.warning)(message)

    left, right = st.columns(2)
    with left:
        st.text_input(
            "Company", key="prospect_company", on_change=refresh_reviewed_field,
            args=("company",),
        )
        st.text_input(
            "Role title", key="prospect_role", on_change=refresh_reviewed_field,
            args=("job_title",),
        )
        st.text_input(
            "Location", key="prospect_location", on_change=refresh_reviewed_field,
            args=("location",),
        )
        st.text_input(
            "Salary range", key="prospect_salary", on_change=refresh_reviewed_field,
            args=("salary_range",),
        )
        st.text_input(
            "Posting date", key="prospect_posting_date", on_change=refresh_reviewed_field,
            args=("posting_date",),
        )
        st.text_input(
            "Source", key="prospect_source", on_change=refresh_reviewed_field,
            args=("source",),
        )
    with right:
        st.selectbox(
            "Priority",
            ("High", "Medium", "Low", "Do Not Pursue"),
            key="prospect_priority",
        )
        st.text_input("Application/status portal URL", key="prospect_application_portal_url")
        st.selectbox("Status", VALID_STATUSES, key="prospect_status")
        st.selectbox(
            "Work arrangement",
            ("Not specified", "Remote", "Hybrid", "On-site", "Flexible"),
            key="prospect_work_arrangement",
            on_change=refresh_reviewed_field,
            args=("work_arrangement",),
        )
        st.text_area("Notes", key="prospect_notes", height=104)
        st.text_area("Next action", key="prospect_next_action", height=104)

    st.text_area(
        "Job description text",
        key="prospect_description",
        height=360,
        help="Manual paste is always supported and is required when a career page blocks import.",
        on_change=refresh_reviewed_field,
        args=("job_description",),
    )

    def reparse_current_fields() -> None:
        apply_manual_reparse_state(st.session_state)

    st.button("Refresh Analysis", on_click=reparse_current_fields)

    values = current_prospect_form_values(st.session_state)
    match_report = None
    intelligence = None
    if prospect_has_usable_job_content(values):
        if not st.session_state.get("prospect_intelligence_stale"):
            stored_intelligence = st.session_state.get("prospect_role_intelligence")
            if isinstance(stored_intelligence, dict) and stored_intelligence:
                intelligence = stored_intelligence
                match_report = intelligence.get("match_report")
                _render_intelligence_preview(
                    st, intelligence, editable_interpretation=True
                )
        if intelligence is None:
            st.warning("Analysis needs refresh. Use Refresh Analysis when the role details are ready.")
    elif any(values.get(key) for key in ("official_url", "company", "job_title", "job_description")):
        validation = st.session_state.get("prospect_validation_state") or compute_prospect_validation_state(
            values,
            {"match_report": incomplete_match_report(values)},
        )
        with st.container(border=True):
            _render_prospect_validation(st, validation)
    title_is_valid = is_valid_role_title(values["job_title"])
    if values["job_title"] and not title_is_valid:
        st.warning("Please confirm the role title before saving.")
    if (
        values["company"]
        and title_is_valid
        and len(values["job_description"].strip()) < MINIMUM_DESCRIPTION_LENGTH
    ):
        st.warning("Paste the job description before generating a package.")
    complete_for_save = bool(
        values["company"]
        and title_is_valid
        and len(values["job_description"].strip()) >= MINIMUM_DESCRIPTION_LENGTH
    )
    pending_recovery = st.session_state.get("package_context_recovery") or {}
    pending_tracker_id = str(pending_recovery.get("tracker_id") or "")
    if pending_tracker_id:
        recovered_package = _render_context_recovery_action(
            st,
            pending_tracker_id,
            key=f"intake_context_recovery_{pending_tracker_id}",
            prospect_values=values,
        )
        if recovered_package:
            _render_package_summary(st, recovered_package)
            _show_output_paths(
                st, recovered_package["outputs"], "intake_recovery_output"
            )
            return
    save_column, generate_column = st.columns(2)
    save_clicked = save_column.button(
        "Save Prospect", use_container_width=True, disabled=not complete_for_save
    )
    generate_clicked = generate_column.button(
        "Save Prospect + Generate Materials", use_container_width=True, type="primary",
        disabled=not complete_for_save
        or not bool(
            intelligence
            and intelligence.get("validation_state", {}).get("package_ready")
        ),
    )
    if not (save_clicked or generate_clicked):
        return

    try:
        with st.spinner("Saving prospect…"):
            if generate_clicked:
                workflow = persist_and_generate_prospect(
                    values, st.session_state, PROJECT_ROOT
                )
                intake = workflow["intake"]
                package = workflow["package"]
                st.session_state["package_preview_prospect_id"] = intake["tracker_id"]
                st.session_state["last_package_outputs"] = package["outputs"]
                st.session_state["last_package_result"] = package
                focus_dashboard_role(st.session_state, intake["tracker_id"])
                st.session_state["dashboard_materials_role_id"] = intake["tracker_id"]
            else:
                intake = create_prospect(build_prospect_payload(values), PROJECT_ROOT)
                dashboard = generate_dashboard(PROJECT_ROOT)
                st.session_state["last_package_outputs"] = {
                    "job_file": intake["job_file_path"],
                    "dashboard": dashboard["output_path"],
                }
    except (ProspectIntakeError, PackageGenerationError, TrackerValidationError) as error:
        if isinstance(error, PackageGenerationError) and error.details.get(
            "context_mismatch"
        ):
            tracker_id = str(st.session_state.get("last_saved_prospect_id") or "")
            _remember_context_recovery(st.session_state, tracker_id, error)
            st.error(CONTEXT_MISMATCH_MESSAGE)
        else:
            st.error(str(error))
        return

    st.success(
        f"Saved {intake['tracker_id']}"
        + (" and generated the full package." if generate_clicked else ".")
    )
    if generate_clicked:
        if package.get("context_diagnostics", {}).get("automatic_refresh_attempted"):
            st.caption("Career Catalyst refreshed the role context before generating this package.")
        _render_package_summary(st, package)
    _show_output_paths(st, st.session_state["last_package_outputs"], "intake_output")


def _load_applications(st: Any) -> list[Dict[str, Any]]:
    try:
        return load_cached_application_tracker(PROJECT_ROOT)
    except TrackerValidationError as error:
        st.error(str(error))
        return []


ANALYSIS_DIRTY_FIELDS = (
    "prospect_evidence_dirty",
    "role_analysis_dirty",
    "score_dirty",
    "application_strategy_dirty",
    "hiring_manager_brief_dirty",
)


def application_analysis_is_dirty(application: Dict[str, Any]) -> bool:
    """Return whether saved analysis needs an explicit refresh."""
    return bool(
        any(application.get(field) for field in ANALYSIS_DIRTY_FIELDS)
        or application.get("match_score") is None
        or not (
            isinstance(application.get("role_interpretation"), dict)
            and application.get("role_interpretation")
        )
    )


def saved_application_voice(application: Dict[str, Any]) -> Dict[str, Any]:
    """Build a render-only intelligence view from persisted tracker fields."""
    role_lens = {
        "primary": application.get("role_lens") or "general_operations",
        "secondary": application.get("secondary_role_lens"),
        "confidence": application.get("role_lens_confidence") or "Medium",
    }
    match_report = persisted_match_fields(application)
    selection = dict(
        application.get("role_evidence_selection")
        or match_report.get("role_evidence_selection")
        or {}
    )
    selection["overrides"] = dict(
        application.get("evidence_selection_overrides")
        or selection.get("overrides")
        or {}
    )
    match_report["role_evidence_selection"] = selection
    freshness = {
        "label": application.get("freshness_label")
        or application.get("freshness")
        or "Not evaluated",
        "posting_status": application.get("posting_status") or "Unknown",
        "is_closed": str(application.get("posting_status") or "").lower()
        in {"closed", "inactive", "expired"},
    }
    return {
        "profile_name": application.get("company_voice_profile") or "saved_profile",
        "profile_label": application.get("company_voice_label")
        or application.get("company_voice_profile")
        or "Saved analysis",
        "source": application.get("company_voice_source") or "saved_tracker_analysis",
        "company_category": application.get("company_category") or "unknown",
        "company_category_label": application.get("company_category") or "Unknown",
        "role_family": application.get("role_family") or "unknown",
        "role_family_label": application.get("role_family") or "Unknown",
        "confidence_label": application.get("company_inference_confidence") or "Medium",
        "role_lens": role_lens,
        "requirement_map": list(application.get("requirement_map") or []),
        "role_interpretation": dict(application.get("role_interpretation") or {}),
        "hiring_manager_lens": dict(application.get("hiring_manager_lens") or {}),
        "application_strategy": dict(application.get("application_strategy") or {}),
        "hiring_manager_brief": dict(application.get("hiring_manager_brief") or {}),
        "proof_points_to_emphasize": list(
            application.get("proof_points_to_emphasize") or []
        ),
        "selected_evidence_ids": list(selection.get("selected_evidence_ids") or []),
        "role_evidence_selection": selection,
        "match_report": match_report,
        "freshness": freshness,
        "source_verification": normalize_job_source(application),
        "analysis_dirty": application_analysis_is_dirty(application),
    }


def persist_evidence_overrides_if_changed(
    tracker_id: str,
    current: Dict[str, Any],
    updated: Dict[str, Any],
    project_root: Path = PROJECT_ROOT,
    *,
    writer: Any = None,
) -> bool:
    """Persist one prospect override only when its normalized value changed."""
    before = normalize_selection_overrides(current)
    after = normalize_selection_overrides(updated)
    if before == after:
        return False
    write = writer or update_prospect
    write(
        tracker_id,
        {
            "evidence_selection_overrides": after,
            "prospect_evidence_dirty": True,
            "score_dirty": True,
            "application_strategy_dirty": True,
            "hiring_manager_brief_dirty": True,
            "package_dirty": True,
        },
        project_root,
    )
    invalidate_tracker_cache()
    return True


def stage_evidence_override(
    session_state: Any,
    pending_key: str,
    current: Dict[str, Any],
    evidence_id: str,
    action: str,
    *,
    replacement_id: str = "",
) -> Dict[str, Any]:
    """Stage a prospect choice in session state without persistence or analysis."""
    updated = update_selection_overrides(
        current,
        evidence_id,
        action,
        replacement_id=replacement_id,
    )
    session_state[pending_key] = updated
    return updated


def refresh_saved_application_analysis(
    tracker_id: str,
    applications: list[Dict[str, Any]],
    project_root: Path = PROJECT_ROOT,
    *,
    context_builder: Any = None,
    writer: Any = None,
) -> Dict[str, Any]:
    """Explicitly recompute and persist only one selected prospect's analysis."""
    build = context_builder or build_package_context
    write = writer or update_prospect
    context = build(tracker_id, applications, project_root)
    intelligence = dict(context["role_intelligence"])
    report = dict(context["match_report"])
    updates = {
        "company_category": intelligence.get("company_category"),
        "role_family": intelligence.get("role_family"),
        "role_lens": (intelligence.get("role_lens") or {}).get("primary"),
        "secondary_role_lens": (intelligence.get("role_lens") or {}).get("secondary"),
        "role_lens_confidence": (intelligence.get("role_lens") or {}).get("confidence"),
        "requirement_map": intelligence.get("requirement_map") or [],
        "role_interpretation": intelligence.get("role_interpretation") or {},
        "hiring_manager_lens": intelligence.get("hiring_manager_lens") or {},
        "application_strategy": intelligence.get("application_strategy") or {},
        "hiring_manager_brief": context.get("hiring_manager_brief")
        or intelligence.get("hiring_manager_brief")
        or {},
        "role_evidence_selection": context.get("role_evidence_selection") or {},
        "evidence_selection_overrides": context.get("evidence_selection_overrides") or {},
        "context_fingerprint": context.get("context_fingerprint"),
        "prospect_evidence_dirty": False,
        "role_analysis_dirty": False,
        "score_dirty": False,
        "application_strategy_dirty": False,
        "hiring_manager_brief_dirty": False,
        "package_dirty": True,
        **persisted_match_fields(report),
    }
    updated = write(tracker_id, updates, project_root)
    invalidate_tracker_cache()
    return updated


def submitted_applications(
    applications: list[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    """Return visible applications that are ready for follow-up outreach."""
    return [
        application
        for application in applications
        if get_record_status(application) in {"Applied", "Follow-up", "Interviewing"}
    ]


def networking_applications(
    applications: list[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    """Return visible roles eligible for follow-up or pre-application networking."""
    return [
        application
        for application in applications
        if get_record_status(application) in FOLLOWUP_ELIGIBLE_STATUSES
    ]


def _followup_strategy_path(application: Dict[str, Any]) -> Path:
    filename = build_upload_filename(
        "Trisha Lynch",
        str(application.get("role") or "Role"),
        str(application.get("company") or "Company"),
        "Followup Strategy",
        "md",
    )
    return PROJECT_ROOT / "exports" / "followups" / filename


def detected_application_voice(
    tracker_id: str,
    project_root: Path = PROJECT_ROOT,
) -> Dict[str, Any]:
    """Return the company voice and role family shown in the package workflow."""
    tracker = load_application_tracker(project_root)
    context = build_package_context(tracker_id, tracker, project_root)
    intelligence = dict(context["role_intelligence"])
    intelligence["profile_label"] = _humanize_taxonomy(
        intelligence["profile_name"]
    )
    intelligence["role_family_label"] = _humanize_taxonomy(
        intelligence.get("role_family_label") or intelligence["role_family"]
    )
    intelligence["freshness"] = detect_job_freshness(
        str(context["parsed_job"].get("raw_text") or "")
    )
    intelligence["match_report"] = context["match_report"]
    intelligence["role_evidence_selection"] = context["role_evidence_selection"]
    return intelligence


def _render_generate_package(st: Any) -> None:
    st.markdown(
        '<h2 class="cc-section-heading">Generate Materials</h2>',
        unsafe_allow_html=True,
    )
    applications = _load_applications(st)
    if not applications:
        st.info("Add a prospect first.")
        return
    by_id = {str(item["id"]): item for item in applications}
    tracker_id = st.selectbox(
        "Prospect",
        tuple(by_id),
        format_func=lambda value: _application_label(by_id[value]),
        key="package_tracker_id",
    )
    reset_package_preview_for_selection(st.session_state, tracker_id)
    application = by_id[tracker_id]
    voice_context = saved_application_voice(application)
    persisted_analysis_dirty = bool(voice_context.get("analysis_dirty"))
    pending_key = f"pending_evidence_overrides_{tracker_id}"
    pending_evidence_changes = bool(
        pending_key in st.session_state
        and normalize_selection_overrides(st.session_state.get(pending_key) or {})
        != normalize_selection_overrides(
            application.get("evidence_selection_overrides") or {}
        )
    )
    analysis_dirty = persisted_analysis_dirty or pending_evidence_changes
    if persisted_analysis_dirty:
        refresh_column, message_column = st.columns((1, 3))
        message_column.warning(
            "Analysis needs refresh. Package generation will refresh it automatically, or you can refresh it now."
        )
        if refresh_column.button(
            "Refresh Analysis",
            key=f"refresh_package_analysis_{tracker_id}",
            type="primary",
            use_container_width=True,
        ):
            try:
                with st.spinner("Refreshing analysis for this prospect…"):
                    refresh_saved_application_analysis(
                        tracker_id, applications, PROJECT_ROOT
                    )
            except Exception as error:
                st.error(f"Analysis refresh failed: {error}")
            else:
                st.rerun()
    elif pending_evidence_changes:
        st.info("Apply the pending evidence changes below before refreshing analysis.")
    _render_intelligence_preview(
        st, voice_context, evidence_tracker_id=tracker_id
    )
    public_transparency_requested = st.checkbox(
        "Include concise transparency language when a material limitation changes the hiring decision",
        value=False,
        key=f"package_transparency_{tracker_id}",
        help="Off by default. Public materials otherwise lead with the strongest truthful evidence without volunteering limitations.",
    )
    freshness = voice_context.get("freshness", {}) if "voice_context" in locals() else {}
    override_closed = False
    if freshness.get("is_closed"):
        override_closed = st.checkbox(
            "I verified this role is open; generate despite the closed-posting signal",
            value=False,
            key=f"package_closed_override_{tracker_id}",
        )
    _render_context_recovery_action(
        st,
        tracker_id,
        key=f"package_context_recovery_{tracker_id}",
        override_closed=override_closed,
    )
    if st.button(
        "Generate Materials",
        type="primary",
        disabled=pending_evidence_changes,
        help=(
            "Apply or discard pending review changes first."
            if pending_evidence_changes
            else "Uses the saved evidence set, creating or refreshing it automatically when needed."
        ),
    ):
        try:
            with st.spinner("Generating resumes, messages, strategy pack, and dashboard…"):
                result = generate_package(
                    tracker_id,
                    PROJECT_ROOT,
                    public_transparency_requested=public_transparency_requested,
                    override_closed=override_closed,
                )
        except PackageGenerationError as error:
            _remember_context_recovery(st.session_state, tracker_id, error)
            st.error(
                CONTEXT_MISMATCH_MESSAGE
                if error.details.get("context_mismatch")
                else str(error)
            )
            if error.checklist:
                _render_package_summary(
                    st, {"package_checklist": error.checklist}
                )
        else:
            if result.get("context_diagnostics", {}).get(
                "automatic_refresh_attempted"
            ):
                st.caption(
                    "Career Catalyst refreshed the role context before generating this package."
                )
            st.success(
                f"Generated {result['job_title']} at {result['company']} — status: {result['status']}."
            )
            st.metric("Match score", result.get("match_score") or "—")
            st.session_state["last_package_outputs"] = result["outputs"]
            st.session_state["last_package_result"] = result
            st.session_state["package_preview_prospect_id"] = tracker_id
            focus_dashboard_role(st.session_state, tracker_id)
            st.session_state["dashboard_materials_role_id"] = tracker_id
    package_result = st.session_state.get("last_package_result")
    if package_result and package_result.get("tracker_id") != tracker_id:
        package_result = None
    if package_result:
        _render_package_summary(st, package_result)
    outputs = st.session_state.get("last_package_outputs")
    if outputs:
        _show_output_paths(st, outputs, "generated_output")


FOLLOW_UP_SKIP_CATEGORIES = (
    "Closed or hidden",
    "Follow-up already sent",
    "No direct contact route",
    "Not yet eligible",
)


def _followup_skip_category(reason: Any) -> str:
    normalized = str(reason or "").lower()
    if "already sent" in normalized or "already been sent" in normalized:
        return "Follow-up already sent"
    if any(
        phrase in normalized
        for phrase in (
            "contact route",
            "direct follow-up path",
            "recruiter, hiring manager",
        )
    ):
        return "No direct contact route"
    if "waiting period" in normalized or "applied date" in normalized:
        return "Not yet eligible"
    return "Closed or hidden"


def _render_followup_bulk_summary(st: Any, summary: Dict[str, Any]) -> None:
    st.success(
        f"Generated {summary['generated_count']} · Skipped {summary['skipped_count']} "
        f"· Failed {summary['failed_count']}"
    )
    if summary["generated_roles"]:
        st.markdown("**Generated roles**")
        for role in summary["generated_roles"]:
            st.caption(f"{role['company']} · {role['role']}")

    skipped_roles = summary["skipped_roles"]
    if skipped_roles:
        grouped = {category: [] for category in FOLLOW_UP_SKIP_CATEGORIES}
        for role in skipped_roles:
            grouped[_followup_skip_category(role.get("reason"))].append(role)
        with st.expander("View skipped roles", expanded=False):
            for category in FOLLOW_UP_SKIP_CATEGORIES:
                roles = grouped[category]
                role_items = "".join(
                    "<li><strong>"
                    f"{html.escape(str(role['company']))} · {html.escape(str(role['role']))}"
                    "</strong><br>"
                    f"{html.escape(str(role['reason']))}</li>"
                    for role in roles
                )
                if not role_items:
                    role_items = "<li>No roles</li>"
                st.markdown(
                    "<details>"
                    f"<summary>{html.escape(category)} · {len(roles)}</summary>"
                    f"<ul>{role_items}</ul>"
                    "</details>",
                    unsafe_allow_html=True,
                )

    for tracker_id, error in summary["failed"].items():
        st.warning(f"{tracker_id}: {error}")


def _render_followups(st: Any) -> None:
    st.markdown(
        '<h2 class="cc-section-heading">Follow-Up</h2>',
        unsafe_allow_html=True,
    )
    bulk_column, folder_column = st.columns((3, 1))
    if bulk_column.button(
        "Generate eligible follow-ups",
        type="primary",
        use_container_width=True,
    ):
        with st.spinner("Generating eligible follow-up packages…"):
            summary = generate_missing_followups(PROJECT_ROOT)
        _render_followup_bulk_summary(st, summary)

    followup_directory = PROJECT_ROOT / "exports" / "followups"
    if folder_column.button("Open follow-up folder", use_container_width=True):
        if not followup_directory.exists():
            followup_directory.mkdir(parents=True, exist_ok=True)
        opened, message = open_local_path(followup_directory)
        (st.success if opened else st.warning)(message)

    applications = [
        application
        for application in _load_applications(st)
        if application.get("show_on_dashboard") is not False
    ]
    if not applications:
        st.info("No roles are available for follow-up review.")
        return

    by_id = {str(item["id"]): item for item in applications}
    tracker_id = st.selectbox(
        "Role",
        tuple(by_id),
        format_func=lambda value: _application_label(by_id[value]),
        key="followup_tracker_id",
    )
    application = by_id[tracker_id]
    status_column, mode_column = st.columns(2)
    status_column.markdown(
        f"**Current status:** {html.escape(str(application.get('status') or 'Not recorded'))}"
    )
    mode = (
        "Application follow-up"
        if get_record_status(application) in FOLLOWUP_ELIGIBLE_STATUSES
        else "Status guidance"
    )
    mode_column.markdown(f"**Outreach mode:** {mode}")
    follow_up_action = follow_up_action_state(application)
    generate_clicked = False
    if follow_up_action["eligible"]:
        st.caption(str(follow_up_action["reason"]))
        generate_clicked = st.button("Generate Follow-Up", type="primary")
    elif (
        follow_up_action["key"] == "check_application_status"
        and follow_up_action["portal_url"]
    ):
        st.caption(str(follow_up_action["reason"]))
        st.link_button(
            "Check Application Status",
            str(follow_up_action["portal_url"]),
            type="primary",
        )
    else:
        st.info(f"{follow_up_action['label']} · {follow_up_action['reason']}")
    saved_intelligence = saved_application_voice(application)
    if saved_intelligence.get("analysis_dirty"):
        st.warning("Analysis needs refresh before generating new role-specific materials.")
    _render_intelligence_preview(st, saved_intelligence)

    if generate_clicked:
        try:
            with st.spinner("Preparing role-specific follow-up messages and strategy…"):
                result = generate_followups(tracker_id, PROJECT_ROOT)
        except FollowupGenerationError as error:
            st.warning(str(error))
        else:
            st.success(
                f"Generated follow-up materials for {result['role']} at {result['company']}."
            )
            st.session_state["last_followup_tracker_id"] = tracker_id
            st.session_state["last_followup_outputs"] = result["outputs"]

    outputs = st.session_state.get("last_followup_outputs")
    if not outputs or st.session_state.get("last_followup_tracker_id") != tracker_id:
        return
    _show_output_paths(st, outputs, "followup_output")
    st.markdown("**Message previews**")
    for key in (
        "recruiter_followup",
        "hiring_manager_followup",
        "warm_contact_message",
        "referral_ask",
    ):
        path = Path(outputs[key])
        if not path.is_file():
            continue
        with st.expander(OUTPUT_LABELS[key], expanded=False):
            st.markdown(path.read_text(encoding="utf-8"))


def _render_update_status(st: Any) -> None:
    st.markdown(
        '<h2 class="cc-section-heading">Advanced Status Update</h2>',
        unsafe_allow_html=True,
    )
    applications = _load_applications(st)
    if not applications:
        return
    if "status_update_notice" in st.session_state:
        st.success(st.session_state.pop("status_update_notice"))
    by_id = {str(item["id"]): item for item in applications}
    tracker_ids = list(by_id)
    selected_id = resolve_selected_tracker_id(
        tracker_ids, st.session_state.get("status_tracker_id")
    )
    labels_by_id = {
        tracker_id: _application_selection_label(application)
        for tracker_id, application in by_id.items()
    }
    ids_by_label = {label: tracker_id for tracker_id, label in labels_by_id.items()}
    selection_key = "status_tracker_selection"
    _sync_persisted_widget_value(
        st.session_state, selection_key, labels_by_id[selected_id]
    )
    selected_label = st.selectbox(
        "Tracker entry",
        tuple(labels_by_id.values()),
        index=tracker_ids.index(selected_id),
        key=selection_key,
    )
    tracker_id = ids_by_label.get(selected_label, selected_id)
    st.session_state["status_tracker_id"] = tracker_id
    application = by_id[tracker_id]
    widget_prefix = f"status_{tracker_id}"
    current_status = get_record_status(application)
    choices = status_options(current_status)
    status_key = f"{widget_prefix}_value"
    priority_key = f"{widget_prefix}_priority"
    notes_key = f"{widget_prefix}_notes"
    next_action_key = f"{widget_prefix}_next_action"
    current_priority = str(application.get("priority") or "Medium")
    _sync_persisted_widget_value(st.session_state, status_key, current_status)
    _sync_persisted_widget_value(st.session_state, priority_key, current_priority)
    _sync_persisted_widget_value(
        st.session_state, notes_key, str(application.get("notes") or "")
    )
    _sync_persisted_widget_value(
        st.session_state,
        next_action_key,
        str(application.get("next_action") or ""),
    )
    status = st.selectbox(
        "Application status",
        choices,
        index=choices.index(current_status),
        key=status_key,
    )
    priority_options = (
        PRIORITY_OPTIONS
        if current_priority in PRIORITY_OPTIONS
        else (current_priority,) + PRIORITY_OPTIONS
    )
    priority = st.selectbox(
        "Priority",
        priority_options,
        index=priority_options.index(current_priority),
        key=priority_key,
    )
    notes = st.text_area(
        "Notes", value=str(application.get("notes") or ""), key=notes_key
    )
    next_action = st.text_area(
        "Next action",
        value=str(application.get("next_action") or ""),
        key=next_action_key,
    )
    source = safe_source_metadata(application)
    with st.expander("Source and verification", expanded=False):
        st.markdown(
            f"**Source:** {source['source']}  \n"
            f"**Source Type:** {source['source_type']}  \n"
            f"**Verification:** {source['verification_status']}  \n"
            f"**Trust Label:** {source['source_trust_label']}  \n"
            f"**Freshness Risk:** {source['freshness_risk']}"
        )
        posting_url = record_posting_url(application)
        if posting_url:
            st.link_button("Open posting", posting_url)
        else:
            st.caption("No posting URL stored.")
    st.caption(
        "Visibility follows status: Pass and Invalid/Hidden stay in cleanup; "
        "active workflow statuses remain visible."
    )
    if st.button("Save Status Update", type="primary"):
        try:
            updated = update_dashboard_role(
                tracker_id,
                {
                    "status": status,
                    "notes": notes,
                    "next_action": next_action,
                    "priority": priority,
                },
                PROJECT_ROOT,
            )
        except (TrackerValidationError, OSError) as error:
            st.error(str(error))
        else:
            submitted = (
                f" Submitted {updated['submitted_date']}." if updated.get("submitted_date") else ""
            )
            st.session_state["status_update_notice"] = (
                f"Updated {updated.get('company', 'Company')} — "
                f"{updated.get('role', tracker_id)} to {get_record_status(updated)}.{submitted}"
            )
            st.rerun()


def _render_dashboard(st: Any) -> None:
    dashboard_path = PROJECT_ROOT / "exports" / "dashboard" / "index.html"
    applications = _load_applications(st)
    if not applications:
        return
    packages = _saved_package_map(applications)

    heading_column, refresh_column, open_column = st.columns((3, 1, 1))
    heading_column.markdown(
        '<h2 class="cc-section-heading">Application Dashboard</h2>',
        unsafe_allow_html=True,
    )
    if refresh_column.button(
        "Regenerate HTML", type="primary", use_container_width=True
    ):
        try:
            result = generate_dashboard(PROJECT_ROOT)
        except Exception as error:
            st.error(str(error))
        else:
            st.success(
                f"Static HTML regenerated with {result['application_count']} tracked roles."
            )
    if open_column.button("Open HTML dashboard", use_container_width=True):
        opened, message = open_local_path(dashboard_path)
        (st.success if opened else st.warning)(message)
    st.caption(
        "Card updates refresh this live dashboard automatically. Regenerate HTML only "
        "when you want to update the separate static dashboard file. Restart the local "
        "app after code changes."
    )
    if "dashboard_notice" in st.session_state:
        st.success(st.session_state.pop("dashboard_notice"))

    st.session_state.setdefault("dashboard_status", "All")
    if st.session_state["dashboard_status"] not in ("All",) + VALID_STATUSES:
        st.session_state["dashboard_status"] = "All"
    _render_summary_metrics(st, applications)

    st.markdown(
        '<h2 class="cc-section-heading">Find Applications</h2>',
        unsafe_allow_html=True,
    )
    search = st.text_input(
        "Search company or role",
        key="dashboard_search",
    )
    filter_columns = st.columns(3)
    application_status = filter_columns[0].selectbox(
        "Application Status", ("All",) + VALID_STATUSES, key="dashboard_status"
    )
    match_tier = filter_columns[1].selectbox(
        "Match Tier", MATCH_TIER_FILTERS, key="dashboard_match_tier"
    )
    sort_by = filter_columns[2].selectbox("Sort by", SORT_OPTIONS, key="dashboard_sort")
    with st.expander("Advanced Search", expanded=False):
        source_columns = st.columns(3)
        source_type = source_columns[0].selectbox("Source Type", SOURCE_TYPE_FILTERS, key="dashboard_source_type")
        verification_status = source_columns[1].selectbox("Verification Status", VERIFICATION_STATUS_FILTERS, key="dashboard_verification_status")
        trust_label = source_columns[2].selectbox("Trust Label", TRUST_LABEL_FILTERS, key="dashboard_trust_label")
    active_filters = []
    if application_status != "All":
        active_filters.append(f"Status: {application_status}")
    if match_tier != "All":
        active_filters.append(f"Match: {match_tier}")
    if search:
        active_filters.append(f'Search: “{search}”')
    indicator, reset = st.columns((5, 1))
    indicator.caption("Active filters: " + (" · ".join(active_filters) if active_filters else "None"))
    reset.button(
        "Clear filters",
        key="dashboard_clear_filters",
        use_container_width=True,
        on_click=clear_dashboard_filters,
        args=(st.session_state,),
    )

    all_records = prepare_dashboard_records(applications, packages)
    records = list(all_records)
    if application_status == "All":
        records = [
            record for record in records
            if get_record_status(record) not in {"Rejected", "Withdrawn / Closed"}
            and record.get("show_on_dashboard") is not False
        ]
    records = filter_dashboard_records(
        records,
        match_tier=match_tier,
        application_status=application_status,
        search=search,
        source_type=source_type,
        verification_status=verification_status,
        trust_label=trust_label,
    )
    records = sort_dashboard_records(records, sort_by)
    st.session_state.setdefault("dashboard_compact_mode", True)
    has_focused_role = bool(
        str(st.session_state.get("dashboard_focused_role_id") or "").strip()
    )
    if has_focused_role and st.button("Clear Focus", key="dashboard_clear_focus_control"):
        clear_focused_dashboard_role(st.session_state)
        st.rerun()
    focused_id = _render_recommended_next_steps(
        st, records, "All Mode", packages, focus_records=all_records
    )
    st.caption(f"{len(records)} roles match the current filters.")
    tracker_records = [
        record for record in records if str(record.get("id") or "") != focused_id
    ]
    _render_application_tracker(st, tracker_records, packages, "All Mode")


def _render_recent_outputs(st: Any) -> None:
    """Render a compact material-library summary instead of every generated file."""
    st.markdown(
        '<h2 class="cc-section-heading">Materials Library</h2>',
        unsafe_allow_html=True,
    )
    applications = _load_applications(st)
    active_packages = []
    archived_packages = []
    for application in applications:
        package = find_exact_role_package(PROJECT_ROOT, application)
        if not package.get("folder"):
            continue
        entry = (application, package)
        (archived_packages if package.get("archived") else active_packages).append(entry)
    legacy_files = [
        path
        for relative in ("messages", "followups", "strategy_packs", "markdown")
        for path in (PROJECT_ROOT / "exports" / relative).glob("*")
        if path.is_file()
    ]
    metrics = st.columns(3)
    metrics[0].metric("Active packages", len(active_packages))
    metrics[1].metric("Archived packages", len(archived_packages))
    metrics[2].metric("Needs cleanup / legacy", len(legacy_files))

    st.markdown("**Active Materials**")
    if not active_packages:
        st.caption("No exact active package folders yet.")
    for application, package in active_packages:
        row = st.columns((5, 1))
        row[0].markdown(
            f"**{company_display_name(application.get('company'))} — {application.get('role')}**"
        )
        if row[1].button(
            "Open",
            key=f"library_active_{application.get('id')}",
            use_container_width=True,
        ):
            opened, message = open_local_path(Path(package["folder"]))
            (st.success if opened else st.warning)(message)

    with st.expander(f"Archived Packages ({len(archived_packages)})", expanded=False):
        if not archived_packages:
            st.caption("No archived package folders yet.")
        for application, package in archived_packages:
            row = st.columns((5, 1))
            row[0].markdown(
                f"**{company_display_name(application.get('company'))} — {application.get('role')}**"
            )
            if row[1].button(
                "Open",
                key=f"library_archive_{application.get('id')}",
                use_container_width=True,
            ):
                opened, message = open_local_path(Path(package["folder"]))
                (st.success if opened else st.warning)(message)

    with st.expander("Needs Cleanup / Legacy Materials", expanded=False):
        st.caption(
            f"{len(legacy_files)} legacy files remain outside exact role package folders."
        )


def _render_full_evidence_library(st: Any) -> None:
    """Hydrate and render the complete profile/graph after an explicit user action."""
    profile = load_cached_evidence_profile(PROJECT_ROOT)
    if st.button(
        "Recalculate Capabilities",
        key="recalculate_capability_graph",
        help="Explicitly rebuild the interpretation layer from the current Evidence Profile.",
    ):
        invalidate_capability_cache()
    graph = load_cached_capability_graph(PROJECT_ROOT)
    evidence_summary = evidence_explorer_summary(profile)
    capability_summary = capability_explorer_summary(graph)

    st.subheader("Evidence Profile & Career Knowledge Graph")
    st.caption(
        "Evidence records career facts with provenance. Capabilities are interpretations "
        "derived from those facts and stay separately reviewable."
    )
    metrics = st.columns(5)
    metrics[0].metric("Evidence", evidence_summary.get("total_evidence", 0))
    metrics[1].metric("Categories", len(evidence_summary.get("categories") or {}))
    metrics[2].metric("Awaiting review", len(evidence_summary.get("awaiting_confirmation") or []))
    metrics[3].metric("Capabilities", capability_summary.get("total_capabilities", 0))
    metrics[4].metric("Direct capabilities", capability_summary.get("direct", 0))

    evidence_view, capability_view = st.tabs(("Evidence Explorer", "Capability Explorer"))
    with evidence_view:
        recent_titles = [
            str(item.get("title")) for item in evidence_summary.get("recent_evidence") or []
        ]
        st.caption(
            f"Verified coverage: {evidence_summary.get('verified_count', 0)} of "
            f"{evidence_summary.get('total_evidence', 0)} · Not on resume: "
            f"{evidence_summary.get('not_on_resume_count', 0)}"
        )
        if recent_titles:
            st.markdown("**Recently updated:** " + "; ".join(recent_titles))
        with st.expander("Propose evidence for review", expanded=False):
            with st.form("evidence_discovery_form", clear_on_submit=True):
                title = st.text_input("Evidence title")
                description = st.text_area("What happened, what you owned, and the outcome")
                category = st.selectbox("Category", sorted(EVIDENCE_CATEGORIES))
                source_reference = st.text_input("Source reference (optional)")
                submitted = st.form_submit_button("Add for confirmation")
            if submitted:
                if not title.strip() or not description.strip():
                    st.warning("A title and description are required.")
                else:
                    proposal = discover_evidence(
                        title, description, category=category, source="Conversation",
                        source_reference=source_reference,
                    )
                    save_evidence_profile(add_discovery(profile, proposal), PROJECT_ROOT)
                    invalidate_evidence_caches()
                    st.success("Added as Medium-confidence evidence awaiting confirmation.")
                    st.rerun()

        awaiting = [
            item for item in profile.get("discoveries") or []
            if item.get("status") == "Awaiting Confirmation"
        ]
        if awaiting:
            st.markdown("#### Awaiting confirmation")
            for item in awaiting:
                discovery_id = str(item.get("id"))
                with st.expander(str(item.get("title") or "Evidence proposal")):
                    edited_title = st.text_input(
                        "Title", value=str(item.get("title") or ""),
                        key=f"evidence_title_{discovery_id}",
                    )
                    edited_description = st.text_area(
                        "Description", value=str(item.get("description") or ""),
                        key=f"evidence_description_{discovery_id}",
                    )
                    categories = sorted(EVIDENCE_CATEGORIES)
                    edited_category = st.selectbox(
                        "Category", categories,
                        index=categories.index(item.get("category"))
                        if item.get("category") in EVIDENCE_CATEGORIES else 0,
                        key=f"evidence_category_{discovery_id}",
                    )
                    confirm_col, reject_col = st.columns(2)
                    if confirm_col.button("Confirm evidence", key=f"confirm_{discovery_id}"):
                        updated = confirm_discovery(
                            profile, discovery_id,
                            {"title": edited_title, "description": edited_description, "category": edited_category},
                        )
                        save_evidence_profile(updated, PROJECT_ROOT)
                        invalidate_evidence_caches()
                        st.success("Confirmed as High-confidence user evidence.")
                        st.rerun()
                    if reject_col.button("Reject", key=f"reject_{discovery_id}"):
                        save_evidence_profile(reject_discovery(profile, discovery_id), PROJECT_ROOT)
                        invalidate_evidence_caches()
                        st.rerun()

        st.markdown("#### Search and filters")
        search = st.text_input("Search evidence", placeholder="Platform, skill, client, role, or proof")
        filter_row = st.columns(3)
        category_filter = filter_row[0].selectbox("Category", [""] + sorted(EVIDENCE_CATEGORIES))
        confidence_filter = filter_row[1].selectbox("Confidence", [""] + sorted(CONFIDENCE_LEVELS))
        verification_filter = filter_row[2].selectbox(
            "Verification", [""] + sorted(EVIDENCE_VERIFICATION_STATUSES)
        )
        filter_row_two = st.columns(3)
        source_options = sorted({str(item.get("source")) for item in profile.get("evidence") or [] if item.get("source")})
        source_filter = filter_row_two[0].selectbox("Source", [""] + source_options)
        visibility_filter = filter_row_two[1].selectbox(
            "Resume visibility", [""] + sorted(RESUME_VISIBILITIES)
        )
        usage_filter = filter_row_two[2].selectbox("Approved usage", [""] + list(USAGE_KEYS))
        filtered = query_evidence(
            profile, search=search, category=category_filter, confidence=confidence_filter,
            source=source_filter, resume_visibility=visibility_filter, usage=usage_filter,
            verification=verification_filter,
        )
        st.caption(f"Showing {len(filtered)} evidence item(s).")
        for item in filtered:
            with st.expander(f"{item.get('title')} · {item.get('confidence')}"):
                st.write(item.get("description") or "No description recorded.")
                st.caption(
                    f"{item.get('category')} · {item.get('verification_status')} · "
                    f"Resume: {item.get('resume_visibility')}"
                )
                st.markdown(f"**Source:** {item.get('source')} — {item.get('source_reference') or 'no reference supplied'}")
                if item.get("company") or item.get("role"):
                    st.markdown(
                        "**Career context:** "
                        + " · ".join(
                            str(value) for value in (item.get("company"), item.get("role"))
                            if value
                        )
                    )
                proof_signals = [
                    *(item.get("skills") or []), *(item.get("platforms") or [])
                ]
                if proof_signals:
                    st.markdown("**Skills and platforms:** " + ", ".join(proof_signals))
                provenance = dict(item.get("provenance") or {})
                if provenance:
                    st.markdown(
                        "**Provenance:** "
                        f"{provenance.get('how') or 'Recorded'} · "
                        f"{provenance.get('when') or 'date unavailable'}"
                    )
                enabled = [name for name, allowed in (item.get("recommended_usage") or {}).items() if allowed]
                if enabled:
                    st.markdown("**Approved uses:** " + ", ".join(enabled))
                related = item.get("related_evidence") or []
                if related:
                    st.markdown("**Related evidence:** " + ", ".join(str(value) for value in related))

    with capability_view:
        st.caption(
            "Confirm, reject, or recalibrate a derived capability. Reviews change the "
            "interpretation layer and never rewrite supporting evidence."
        )
        evidence_options = {
            str(item.get("id")): str(item.get("title"))
            for item in profile.get("evidence") or []
        }
        for capability in graph.get("capabilities") or []:
            capability_id = str(capability.get("id"))
            with st.expander(
                f"{capability.get('name')} · {capability.get('strength')} · {capability.get('confidence')}"
            ):
                st.write(capability.get("recommended_positioning") or capability.get("description"))
                st.caption(
                    f"{capability.get('derivation_type')} · review status: "
                    f"{capability.get('user_review_status')}"
                )
                applicable_roles = capability.get("applicable_role_archetypes") or []
                if applicable_roles:
                    st.markdown("**Applicable roles:** " + ", ".join(applicable_roles))
                supporting_ids = list(capability.get("supporting_evidence_ids") or [])
                st.markdown(
                    "**Supporting evidence:** "
                    + ", ".join(evidence_options.get(value, value) for value in supporting_ids)
                )
                limitations = st.text_area(
                    "Limitations (one per line)", value="\n".join(capability.get("limitations") or []),
                    key=f"capability_limitations_{capability_id}",
                )
                added_support = st.multiselect(
                    "Add supporting evidence", list(evidence_options),
                    format_func=lambda value: evidence_options.get(value, value),
                    key=f"capability_support_{capability_id}",
                )
                controls = st.columns(4)
                actions = (
                    ("Confirm", "Confirmed", capability.get("strength")),
                    ("Mark Direct", "Confirmed", "Direct Experience"),
                    ("Mark Adjacent", "Confirmed", "Strong Adjacent Experience"),
                    ("Reject", "Rejected", "Unsupported"),
                )
                for column, (button_label, review_status, strength) in zip(controls, actions):
                    if column.button(button_label, key=f"{button_label}_{capability_id}"):
                        save_capability_review(
                            capability_id,
                            {
                                "user_review_status": review_status,
                                "strength": strength,
                                "limitations": [line.strip() for line in limitations.splitlines() if line.strip()],
                                "supporting_evidence_ids": added_support,
                            },
                            PROJECT_ROOT,
                        )
                        invalidate_capability_cache()
                        st.rerun()


def _render_evidence_explorer(st: Any) -> None:
    """Render the summary aggregate first and lazy-load all detailed records."""
    summary = load_cached_evidence_page_summary(PROJECT_ROOT)
    st.subheader("Career Intelligence")
    st.caption(
        "A practical view of your professional identity, strongest positioning, and "
        "career information that needs attention."
    )
    if summary.get("summary_missing"):
        st.warning("The lightweight evidence summary has not been created yet.")
        if st.button("Create Evidence Summary", key="create_evidence_summary"):
            refresh_evidence_page_summary(PROJECT_ROOT)
            invalidate_evidence_caches()
            st.rerun()
    elif summary.get("summary_stale"):
        st.info("Evidence changed outside the app. Refresh the summary when convenient.")
        if st.button("Refresh Evidence Summary", key="refresh_evidence_summary"):
            refresh_evidence_page_summary(PROJECT_ROOT)
            invalidate_evidence_caches()
            st.rerun()

    profile_summary = dict(summary.get("profile_summary") or {})
    st.markdown("### Career Profile")
    career_profile = str(profile_summary.get("career_profile") or "").strip()
    if career_profile:
        st.write(career_profile)
    else:
        st.caption("Refresh the summary to create your grounded career profile.")
    strongest_areas = list(profile_summary.get("strongest_areas") or [])
    st.markdown("### Strongest Areas")
    if strongest_areas:
        for area in strongest_areas:
            st.markdown(f"- {area}")
    else:
        st.caption("No strongest areas are summarized yet.")
    featured = list(profile_summary.get("featured_projects_and_experience") or [])
    st.markdown("### Featured Projects and Experience")
    if featured:
        for item in featured:
            st.markdown(f"- {item}")
    else:
        st.caption("No featured projects or experience are summarized yet.")

    st.markdown("### Needs Review")
    needs_review = list(summary.get("needs_review") or [])
    if not needs_review:
        st.success("No evidence needs review.")
    else:
        for item in needs_review:
            with st.container(border=True):
                st.markdown(f"**{item.get('title')}**")
                st.write(str(item.get("issue") or "Review required."))

    st.markdown("### Advanced Library")
    st.caption(
        "Search, filters, provenance, capability relationships, and edit controls load only on request."
    )
    open_key = "full_evidence_library_open"
    # Backward-compatible test/migration vocabulary: "Open Full Evidence Library".
    if st.button("Open Advanced Library", key="open_full_evidence_library"):
        st.session_state[open_key] = True
        st.rerun()
    if st.session_state.get(open_key, False):
        if st.button("Close Advanced Library", key="close_full_evidence_library"):
            st.session_state[open_key] = False
            st.rerun()
        _render_full_evidence_library(st)


UI_PAGES = (
    "Dashboard",
    "Career Intelligence",
    "Add Prospect",
    "Generate Materials",
    "Follow-Up",
    "Advanced Status Update",
    "Outputs",
)


def render_active_page(
    st: Any,
    selected_page: str,
    renderers: Optional[Dict[str, Any]] = None,
) -> None:
    """Render only the selected page; passive navigation must not execute other pages."""
    page_renderers = renderers or {
        "Dashboard": _render_dashboard,
        "Career Intelligence": _render_evidence_explorer,
        "Evidence & Capabilities": _render_evidence_explorer,
        "Add Prospect": _render_add_prospect,
        "Generate Materials": _render_generate_package,
        "Generate Package": _render_generate_package,
        "Follow-Up": _render_followups,
        "Advanced Status Update": _render_update_status,
        "Outputs": _render_recent_outputs,
    }
    renderer = page_renderers.get(selected_page)
    if renderer is None:
        raise ValueError(f"Unknown UI page: {selected_page}")
    renderer(st)


def main() -> None:
    """Render the local application; importing this module has no Streamlit side effects."""
    import streamlit as st

    st.set_page_config(page_title="Career Catalyst", page_icon="🧭", layout="wide")
    st.markdown(APP_CSS, unsafe_allow_html=True)
    st.markdown(
        '<div class="cc-header">'
        '<div class="cc-brand-mark" aria-hidden="true">CC</div>'
        '<div><p class="cc-eyebrow">Career Catalyst</p>'
        '<h1>Trisha Lynch Application Cockpit</h1></div>'
        "</div>"
        f'<p class="cc-description">{html.escape(UI_DESCRIPTION)}</p>',
        unsafe_allow_html=True,
    )
    selected_page = st.segmented_control(
        "Workspace",
        UI_PAGES,
        default="Dashboard",
        key="active_workspace_page",
        label_visibility="collapsed",
    )
    render_active_page(st, str(selected_page or "Dashboard"))


if __name__ == "__main__":
    main()
