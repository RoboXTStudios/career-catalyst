"""Local Streamlit cockpit for Career Catalyst.

Run with: streamlit run app.py
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

from scripts.application_tracker import (
    ACTIVE_STATUSES,
    HIDDEN_STATUSES,
    VALID_STATUSES,
    TrackerValidationError,
    follow_up_eligibility,
    get_record_status,
    load_application_tracker,
    normalize_status,
    update_prospect,
    update_status,
    workflow_status_bucket,
)
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
    load_application_packages,
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
from scripts.generate_followups import (
    FOLLOWUP_ELIGIBLE_STATUSES,
    FollowupGenerationError,
    generate_followups,
    generate_missing_followups,
)
from scripts.job_importer import MINIMUM_DESCRIPTION_LENGTH, JobImportError, import_job_from_url
from scripts.job_identity import infer_job_fields_from_url, preferred_role_title
from scripts.job_freshness import detect_job_freshness
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
    generate_package,
    resolve_job_reference,
)
from scripts.parse_job import extract_metadata, parse_job_description, salary_parsing_warning
from scripts.prospect_intake import ProspectIntakeError, create_prospect
from scripts.score_match import score_job_data, score_job_match


PROJECT_ROOT = Path(__file__).resolve().parent
UI_DESCRIPTION = (
    "Add prospects, generate tailored application packages, track statuses, and manage "
    "job search materials from one local workspace."
)
TRACKER_GROUPS = (
    "Applied / Follow-Up",
    "Active",
    "Reviewed",
    "Paused",
    "Passed",
    "Hidden / Invalid",
)
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
  .cc-status-drafted, .cc-status-reviewed { background: var(--cc-gold-soft); color: var(--cc-gold); }
  .cc-status-active, .cc-status-paused { background: #eef1f3; color: #4c5963; }
  .cc-status-applied, .cc-status-follow-up { background: var(--cc-blue-soft); color: var(--cc-blue); }
  .cc-status-interviewing { background: var(--cc-accent-soft); color: var(--cc-accent); }
  .cc-status-rejected, .cc-status-invalid, .cc-status-invalid-hidden, .cc-status-pass { background: var(--cc-red-soft); color: var(--cc-red); }
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
        counts[get_record_status(application)] += 1
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
        workflow_bucket = workflow_status_bucket(application)
        invalid_hidden = status in {"Invalid", "Invalid/Hidden", "Rejected", "Archived"} or (
            status not in VALID_STATUSES
            and application.get("show_on_dashboard") is False
        )
        stale_or_unverified = (
            application.get("verification_status")
            in {"Stale / Closed Risk", "Cannot Verify", "Not Verified"}
            or application.get("source_trust_label") == "Unknown Source"
            or str(application.get("posting_status") or "").lower() == "closed"
        )
        if workflow_bucket == "Paused":
            label = "Paused"
        elif workflow_bucket == "Pass":
            label = "Passed"
        elif workflow_bucket == "Hidden / Invalid" or invalid_hidden:
            label = "Hidden / Invalid"
        elif mode == "Cleanup Mode" and stale_or_unverified:
            label = "Stale / Cannot Verify"
        elif mode == "Cleanup Mode":
            label = "Needs decision"
        elif workflow_bucket == "Applied / Follow-up":
            label = "Applied / Follow-Up"
        elif workflow_bucket == "Reviewed":
            label = "Reviewed"
        elif workflow_bucket == "Active":
            label = "Active"
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
    ):
        session_state.pop(key, None)
    session_state["package_preview_prospect_id"] = selected
    return True


def mark_prospect_intelligence_stale(session_state: Any) -> None:
    """Mark intake analysis stale after role-defining fields change."""
    session_state["prospect_intelligence_stale"] = True
    session_state["prospect_import_result"] = (
        "error",
        "Role details changed. Re-parse and re-score before generating a package.",
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
    """Set predictable mode/filter state from a normalized summary bucket."""
    navigation = {
        "Total": ("All Mode", "All"),
        "Active": ("All Mode", "Active"),
        "Applied / Follow-up": ("Follow-Up Mode", "Applied / Follow-up"),
        "Reviewed": ("Review Mode", "Reviewed"),
        "Paused": ("All Mode", "Paused"),
        "Pass": ("Cleanup Mode", "Pass"),
        "Hidden / Invalid": ("Cleanup Mode", "Invalid/Hidden"),
    }
    mode, status_filter = navigation.get(bucket, navigation["Total"])
    session_state["dashboard_mode"] = mode
    session_state["dashboard_status"] = status_filter
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
        "reviewed": {"status": "Reviewed", "show_on_dashboard": True},
        "paused": {"status": "Paused", "show_on_dashboard": True},
        "pass": {"status": "Pass", "show_on_dashboard": False},
        "invalid_hidden": {"status": "Invalid/Hidden", "show_on_dashboard": False},
        "active": {"status": "Active", "show_on_dashboard": True},
        "follow_up_sent": {
            "status": "Follow-up",
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
        "posting_date": str(values.get("posting_date") or "").strip(),
        "source": str(values.get("source") or "Official career page").strip(),
        "priority": str(values.get("priority") or "Medium"),
        "status": str(values.get("status") or "Drafted"),
        "work_arrangement": str(values.get("work_arrangement") or "").strip(),
        "job_description": str(values.get("job_description") or "").strip(),
        "notes": str(values.get("notes") or "").strip(),
        "next_action": str(values.get("next_action") or "").strip(),
        "show_on_dashboard": bool(values.get("show_on_dashboard", True)),
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
    cards = "".join(
        '<div class="cc-summary-card">'
        f'<span class="cc-summary-value">{value}</span>'
        f'<span class="cc-summary-label">{html.escape(label)}</span>'
        "</div>"
        for label, value in summarize_applications(applications).items()
    )
    st.markdown(
        '<h2 class="cc-section-heading">Application Summary</h2>'
        f'<div class="cc-summary-grid">{cards}</div>',
        unsafe_allow_html=True,
    )
    navigation = tuple(
        (f"View {status}", status)
        for status, count in summarize_applications(applications).items()
        if status != "Total" and count
    )
    for row_start in range(0, len(navigation), 3):
        columns = st.columns(3)
        for column, (label, bucket) in zip(
            columns, navigation[row_start : row_start + 3]
        ):
            if column.button(
                label,
                key=f"summary_{bucket.lower().replace(' ', '_').replace('/', '_')}",
                use_container_width=True,
            ):
                apply_summary_navigation(st.session_state, bucket)


def _package_map(project_root: Path = PROJECT_ROOT) -> Dict[str, Dict[str, Any]]:
    package_data = load_application_packages(project_root)
    return {
        str(package.get("tracker_id")): package
        for package in package_data["packages"]
        if package.get("tracker_id")
    }


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
        f'{render_list("Gaps / cautions", "match_gaps")}'
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
        f'<span>Confidence: {html.escape(str(report.get("confidence") or "Low"))}</span></div>'
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
            title_column, badge_column, action_column = st.columns((4, 2, 1))
            title_column.markdown(
                '<p class="cc-card-company">'
                f"{html.escape(company_display_name(application.get('company') or 'Company not listed'))}</p>"
                '<p class="cc-card-role">'
                f"{html.escape(str(application.get('role') or 'Role not listed'))}</p>",
                unsafe_allow_html=True,
            )
            badge_column.markdown(_status_badges(application), unsafe_allow_html=True)
            compact_facts = [
                f"Status: {get_record_status(application)}",
                f"Match: {application.get('match_score') if application.get('match_score') is not None else 'Not scored'}",
                f"Priority: {application.get('priority') or 'Medium'}",
                f"Next: {application.get('next_action') or application.get('recommended_action') or 'Review role'}",
            ]
            st.caption(" · ".join(compact_facts))
            files = package.get("files", {})
            posting_url = record_posting_url(application)
            portal_url = record_application_portal_url(application)
            first_material = next(
                (
                    Path(path)
                    for path in files.values()
                    if Path(path).exists() and Path(path).suffix.lower() != ".md"
                ),
                None,
            )
            actions = st.columns(4)
            if actions[0].button(
                "View Role",
                key=f"compact_view_{tracker_id}",
                use_container_width=True,
            ):
                focus_dashboard_role(
                    st.session_state, dashboard_role_reference(application)
                )
                st.rerun()
            if posting_url:
                actions[1].link_button("Open Posting", posting_url, use_container_width=True)
            else:
                actions[1].button("Open Posting", key=f"compact_posting_missing_{tracker_id}", disabled=True, use_container_width=True)
            if portal_url:
                actions[2].link_button("Check application status", portal_url, use_container_width=True)
            else:
                actions[2].button("Check application status", key=f"compact_portal_missing_{tracker_id}", disabled=True, use_container_width=True)
            if first_material and actions[3].button(
                "Open Materials",
                key=f"compact_materials_{tracker_id}",
                use_container_width=True,
                help=str(first_material),
            ):
                focus_dashboard_role(st.session_state, dashboard_role_reference(application))
                st.session_state["dashboard_materials_role_id"] = tracker_id
                st.rerun()
            elif not first_material:
                actions[3].button("Open Materials", key=f"compact_materials_missing_{tracker_id}", disabled=True, use_container_width=True)
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
        st.markdown(
            _match_score_html(
                application, include_details=False, include_tier=False
            ),
            unsafe_allow_html=True,
        )
        next_action = str(application.get("next_action") or "").strip()
        if next_action:
            st.markdown(
                '<div class="cc-tracker-row"><span class="cc-tracker-label">Next action</span>'
                f"<span>{html.escape(next_action)}</span></div>",
                unsafe_allow_html=True,
            )
        if mode == "Cleanup Mode":
            st.info(recommended_next_steps([application], mode)[0])
        match_details = application.get("match_strengths") or application.get("match_gaps")
        if match_details:
            with st.expander("Match details", expanded=False):
                st.markdown(_match_score_html(application), unsafe_allow_html=True)

        source_panel_open = str(
            st.session_state.get("dashboard_source_verification_role_id") or ""
        ) in {tracker_id, dashboard_role_reference(application)}
        with st.expander("Advanced edit: source verification", expanded=source_panel_open):
            _render_source_verification_panel(st, application, tracker_id)

        notes = str(application.get("notes") or "").strip()
        if notes:
            with st.expander("Notes", expanded=False):
                st.write(notes)

        files = package.get("files", {})
        material_count = sum(Path(path).exists() for path in files.values())
        materials_focused = str(st.session_state.get("dashboard_materials_role_id") or "") == tracker_id
        with st.expander(
            f"Application & outreach materials ({material_count})", expanded=materials_focused
        ):
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

        st.caption(
            "Use quick actions for common workflow changes. Use Advanced edit only "
            "for manual corrections."
        )
        posting_url = record_posting_url(application)
        portal_url = record_application_portal_url(application)
        first_material = next(
            (
                Path(path)
                for path in files.values()
                if Path(path).exists() and Path(path).suffix.lower() != ".md"
            ),
            None,
        )
        primary_actions = contextual_primary_actions(
            application,
            has_materials=first_material is not None,
            has_posting_url=posting_url is not None,
            mode=mode,
        )
        if portal_url:
            st.link_button("Check application status", portal_url, use_container_width=True)
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
                    help=str(first_material) if action_key == "open_materials" else None,
                ):
                    continue
                if action_key == "open_materials" and first_material:
                    focus_dashboard_role(st.session_state, dashboard_role_reference(application))
                    st.session_state["dashboard_materials_role_id"] = tracker_id
                    st.rerun()
                elif action_key == "generate_package":
                    try:
                        with st.spinner("Generating application package…"):
                            generate_package(tracker_id, PROJECT_ROOT)
                    except PackageGenerationError as error:
                        st.error(str(error))
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

        with st.expander("More actions", expanded=False):
            more_columns = st.columns(4)
            bucket = workflow_status_bucket(application)
            if bucket not in {"Paused", "Pass", "Hidden / Invalid"} and more_columns[0].button(
                "Pause",
                key=f"dashboard_more_pause_{tracker_id}",
                use_container_width=True,
            ):
                apply_dashboard_status_action(tracker_id, "paused", PROJECT_ROOT)
                st.session_state["dashboard_notice"] = "Role paused."
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
            if bucket == "Active" and more_columns[2].button(
                "Mark Reviewed",
                key=f"dashboard_more_reviewed_{tracker_id}",
                use_container_width=True,
            ):
                apply_dashboard_status_action(tracker_id, "reviewed", PROJECT_ROOT)
                st.session_state["dashboard_notice"] = "Role marked reviewed."
                st.rerun()
            follow_up_allowed, _ = follow_up_eligibility(application)
            if follow_up_allowed and more_columns[3].button(
                "Generate Follow-Up Materials",
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
        '<h2 class="cc-section-heading">Application Tracker</h2>',
        unsafe_allow_html=True,
    )
    grouped = group_applications_by_status(
        applications, preserve_order=True, mode=mode
    )
    for label, group in grouped.items():
        count_label = "role" if len(group) == 1 else "roles"
        heading = (
            '<div class="cc-group-heading">'
            f'<span class="cc-group-title">{html.escape(label)}</span>'
            f'<span class="cc-group-count">{len(group)} {count_label}</span>'
            "</div>"
        )
        if label == "Hidden / Invalid" and mode != "Cleanup Mode":
            with st.expander(f"{label} ({len(group)})", expanded=False):
                for application in group:
                    _render_role_card(
                        st,
                        application,
                        packages.get(str(application.get("id")), {}),
                        mode,
                        compact=True,
                    )
            continue
        st.markdown(heading, unsafe_allow_html=True)
        if not group:
            st.caption("No roles in this group.")
        for application in group:
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
    steps = structured_recommended_next_steps(applications, mode)
    all_focus_records = focus_records if focus_records is not None else applications
    compact_mode = bool(st.session_state.get("dashboard_compact_mode", True))
    next_steps_collapsed = bool(
        st.session_state.get("dashboard_next_steps_collapsed", False)
    )
    with st.container(border=True):
        if next_steps_collapsed:
            heading, control = st.columns((5, 1))
            heading.markdown(f"**Recommended Next Steps ({len(steps)})**")
            if control.button(
                "Expand",
                key="dashboard_expand_next_steps",
                use_container_width=True,
            ):
                expand_recommended_next_steps(st.session_state)
                st.rerun()
        else:
            st.markdown(f"**Recommended Next Steps ({len(steps)})**")
            if not steps:
                st.caption(recommended_next_steps([], mode)[0])
        for step in (() if next_steps_collapsed else steps):
            tracker_id = step["tracker_id"]
            record = find_dashboard_role(applications, tracker_id) or {}
            role_reference = dashboard_role_reference(record) or tracker_id
            st.markdown(
                f"**{step['company']} — {step['title']}**  "
                f"\n{step['recommendation']}"
            )
            navigation_actions = st.columns(3)
            if navigation_actions[0].button(
                "View role",
                key=f"next_view_{role_reference}",
                use_container_width=True,
            ):
                focus_dashboard_role(st.session_state, role_reference)
                st.rerun()
            if step.get("posting_url"):
                navigation_actions[1].link_button(
                    "Open posting", step["posting_url"], use_container_width=True
                )
            material_paths = step.get("material_paths") or {}
            first_material = next(
                (
                    Path(path)
                    for path in material_paths.values()
                    if Path(path).exists() and Path(path).suffix.lower() != ".md"
                ),
                None,
            )
            if first_material and navigation_actions[2].button(
                "Open materials",
                key=f"next_materials_{tracker_id}",
                use_container_width=True,
                help=str(first_material),
            ):
                focus_dashboard_role(st.session_state, role_reference)
                st.session_state["dashboard_materials_role_id"] = tracker_id
                st.rerun()

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
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def detect_prospect_intelligence(values: Dict[str, Any]) -> Dict[str, Any]:
    """Infer local company and role guidance from unsaved prospect fields."""
    intelligence = get_effective_voice_profile(
        company_name=str(values.get("company") or ""),
        job_title=str(values.get("job_title") or values.get("role") or ""),
        job_description=str(values.get("job_description") or ""),
        source_url=str(values.get("official_url") or ""),
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
    intelligence["match_report"] = score_job_data(values, PROJECT_ROOT)
    intelligence["job_description"] = str(values.get("job_description") or "")
    intelligence["location"] = str(values.get("location") or "")
    intelligence["work_arrangement"] = str(values.get("work_arrangement") or "")
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
        if metadata.get(source):
            refreshed[target] = metadata[source]
    for key in ("company", "location", "job_id", "source"):
        if not refreshed.get(key) and fallback.get(key):
            refreshed[key] = fallback[key]
    refreshed["match_report"] = score_job_data(refreshed, PROJECT_ROOT)
    refreshed["source_verification"] = normalize_job_source(refreshed)
    return refreshed


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
        message = (
            "Import partially failed. The source URL was saved. Paste the job "
            "description below, then re-parse and re-score."
        )
    elif verification.get("source_type") in {
        "Industry Job Board",
        "Gaming Industry Job Board",
        "Music Industry Job Board",
        "Entertainment Job Board",
        "Startup / Tech Job Board",
    }:
        message = (
            f"Imported from {source_name}, an industry job board. Verify the role on "
            "the employer site before applying or generating a full package."
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
    session_state["prospect_context_url"] = url
    session_state["prospect_url_value"] = url
    session_state["prospect_import_url"] = url
    session_state["prospect_url_last_imported"] = url
    session_state["prospect_original_source_url"] = url
    fallback = infer_job_fields_from_url(url)
    verification = normalize_job_source({"official_url": url})
    canonical = str(verification.get("canonical_apply_url") or url)
    session_state["prospect_canonical_url"] = canonical
    if fallback.get("job_id"):
        session_state["prospect_job_id"] = fallback["job_id"]
    if verification.get("source_name") and verification.get("source_name") != "Unknown":
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
    except (JobImportError, OSError, ValueError):
        message = (
            "Import partially failed. The source URL was saved. Paste the job "
            "description below, then re-parse and re-score."
        )
        session_state["prospect_import_result"] = ("error", message)
        session_state["prospect_next_action"] = (
            "Paste the job description and re-score before generating package."
        )
        session_state["prospect_intelligence_stale"] = True
        return {"status": "partial", "message": message, "verification": verification}

    imported_title = imported.get("job_title")
    selected_title = preferred_role_title(current_title, imported_title, url)
    title_rejected = bool(imported_title and not is_valid_role_title(imported_title))
    if selected_title:
        session_state["prospect_role"] = selected_title
    elif title_rejected:
        session_state["prospect_role"] = ""
    for state_key, imported_key in (
        ("prospect_company", "company"),
        ("prospect_location", "location"),
        ("prospect_salary", "salary_range"),
        ("prospect_posting_date", "posting_date"),
        ("prospect_description", "job_description"),
        ("prospect_job_id", "job_id"),
    ):
        if imported.get(imported_key):
            session_state[state_key] = imported[imported_key]
    if imported.get("source_name") or imported.get("source"):
        session_state["prospect_source"] = imported.get("source_name") or imported.get("source")
    incomplete = bool(
        not session_state.get("prospect_company")
        or not session_state.get("prospect_role")
        or len(str(session_state.get("prospect_description") or "").strip())
        < MINIMUM_DESCRIPTION_LENGTH
    )
    message = (
        "Imported title looked like job description text. Please confirm the role title before saving."
        if title_rejected
        else "Import partially failed. Paste the job description below, then re-parse and re-score."
        if incomplete
        else "Imported the role details. Review them before saving."
    )
    session_state["prospect_import_result"] = (
        "error" if title_rejected or incomplete else "success",
        message,
    )
    session_state["prospect_intelligence_stale"] = bool(title_rejected or incomplete)
    return {
        "status": "partial" if title_rejected or incomplete else "success",
        "message": message,
        "imported": imported,
    }


def prospect_warning_messages(intelligence: Dict[str, Any]) -> list[str]:
    """Build visible, non-blocking source/freshness/compensation intake warnings."""
    messages = []
    verification = intelligence.get("source_verification") or {}
    freshness = intelligence.get("freshness") or {}
    source_type = str(verification.get("source_type") or "")
    description = str(intelligence.get("job_description") or "")
    if not str(intelligence.get("location") or "").strip():
        messages.append("Location was not detected. Review before saving.")
    if (
        verification.get("freshness_risk") == "High"
        or verification.get("verification_status") == "Stale / Closed Risk"
        or freshness.get("is_stale")
    ):
        messages.append(
            "Posting appears stale or older than 30 days. Verify the role is still active "
            "before generating a package."
        )
    if intelligence.get("salary_parsing_warning"):
        messages.append("Compensation not detected. Budget or spend figures were ignored.")
    if source_type in {
        "Industry Job Board",
        "Gaming Industry Job Board",
        "Music Industry Job Board",
        "Entertainment Job Board",
        "Startup / Tech Job Board",
    }:
        messages.append(
            f"Imported from {verification.get('source_name') or 'this source'}, an industry job board. "
            "Verify the role on the employer site before applying or generating a full package."
        )
    elif source_type in {
        "Generic Aggregator",
        "Remote Job Aggregator",
        "Compensation-Focused Aggregator",
        "Gated Source",
        "Unknown Source",
    }:
        messages.append("Verify on employer site before generating package or applying.")
    if verification.get("source_name") == "Greenhouse" and len(description) < MINIMUM_DESCRIPTION_LENGTH:
        messages.append(
            "Greenhouse source verified, but the page did not provide a complete job description. "
            "Paste the job description manually before saving or generating a package."
        )
    if verification.get("source_type") == "Direct Employer" and len(description) < MINIMUM_DESCRIPTION_LENGTH:
        messages.append(
            "Import partially failed. Official employer source detected. Paste the job "
            "description below, then re-parse and re-score."
        )
    if verification.get("source_type") == "Employer ATS" and (
        verification.get("freshness_risk") in {"Unknown", "High"}
    ):
        messages.append(
            "Source recognized as employer ATS. Verify posting freshness if the role is older "
            "or its date is missing."
        )
    messages.extend(str(value) for value in verification.get("source_warnings") or [])
    if intelligence.get("source") == "dynamic_inference":
        messages.append("Role family was inferred. Review if this is a strategic or product-ops role.")
    return list(dict.fromkeys(message for message in messages if message))


def _humanize_taxonomy(value: Any) -> str:
    label = str(value or "").replace("_", " ").title()
    return label.replace("Ai ", "AI ").replace("Gtm ", "GTM ")


def _render_intelligence_preview(st: Any, intelligence: Dict[str, Any]) -> None:
    with st.container(border=True):
        st.markdown("**Detected role intelligence**")
        st.markdown(
            f"Company voice: **{intelligence.get('company_voice_label') or _humanize_taxonomy(intelligence['profile_name'])}**  |  "
            f"Category: **{intelligence.get('company_category_label') or _humanize_taxonomy(intelligence['company_category'])}**  |  "
            f"Role family: **{intelligence.get('role_family_label') or _humanize_taxonomy(intelligence['role_family'])}**  |  "
            f"Source: **{str(intelligence['source']).replace('_', ' ')}**  |  "
            f"Confidence: **{intelligence.get('confidence_label', 'Medium')}**"
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
                f"Trust: **{verification.get('source_trust_label', 'Unknown Source')}**  |  "
                f"Verification: **{verification['verification_status']}**  |  "
                f"Source confidence: **{verification.get('source_confidence', 'Low')}**"
            )
        for warning in prospect_warning_messages(intelligence):
            st.warning(warning)
        angles = intelligence.get("cover_letter_angle", [])
        if angles:
            st.markdown(f"**Suggested cover letter angle:** {angles[0]}")
        proof_points = intelligence.get("proof_points_to_emphasize", [])
        if proof_points:
            st.markdown(
                "**Suggested proof points:** " + "; ".join(proof_points[:4])
            )
        match_report = intelligence.get("match_report")
        if isinstance(match_report, dict):
            st.markdown(_match_score_html(match_report), unsafe_allow_html=True)


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

    def mark_intelligence_stale() -> None:
        mark_prospect_intelligence_stale(st.session_state)

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
            "Company", key="prospect_company", on_change=mark_intelligence_stale
        )
        st.text_input(
            "Role title", key="prospect_role", on_change=mark_intelligence_stale
        )
        st.text_input("Location", key="prospect_location")
        st.text_input("Salary range", key="prospect_salary")
        st.text_input("Source", key="prospect_source")
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
        )
        st.text_area("Notes", key="prospect_notes", height=104)
        st.text_area("Next action", key="prospect_next_action", height=104)

    st.text_area(
        "Job description text",
        key="prospect_description",
        height=360,
        help="Manual paste is always supported and is required when a career page blocks import.",
        on_change=mark_intelligence_stale,
    )

    def reparse_current_fields() -> None:
        refreshed = reparse_prospect_fields(
            {
                "official_url": st.session_state["prospect_url_value"],
                "company": st.session_state["prospect_company"],
                "job_title": st.session_state["prospect_role"],
                "location": st.session_state["prospect_location"],
                "salary_range": st.session_state["prospect_salary"],
                "posting_date": st.session_state["prospect_posting_date"],
                "work_arrangement": st.session_state["prospect_work_arrangement"],
                "job_description": st.session_state["prospect_description"],
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
                st.session_state[state_key] = refreshed[value_key]
        report = refreshed["match_report"]
        st.session_state["prospect_import_result"] = (
            "success" if report.get("match_score") is not None else "error",
            "Re-parsed current fields and refreshed the match score."
            if report.get("match_score") is not None
            else "Import partially failed. Paste the job description below, then re-parse and re-score.",
        )
        st.session_state["prospect_intelligence_stale"] = bool(
            report.get("match_score") is None
        )

    st.button("Re-parse details and re-score", on_click=reparse_current_fields)

    values = {
        "posting_url": st.session_state["prospect_url_value"],
        "application_portal_url": st.session_state.get("prospect_application_portal_url", ""),
        "official_url": st.session_state["prospect_url_value"],
        "source_url": st.session_state["prospect_url_value"],
        "original_source_url": st.session_state["prospect_original_source_url"],
        "canonical_apply_url": st.session_state["prospect_canonical_url"],
        "job_id": st.session_state["prospect_job_id"],
        "company": st.session_state["prospect_company"],
        "job_title": st.session_state["prospect_role"],
        "location": st.session_state["prospect_location"],
        "salary_range": st.session_state["prospect_salary"],
        "posting_date": st.session_state["prospect_posting_date"],
        "source": st.session_state["prospect_source"],
        "priority": st.session_state["prospect_priority"],
        "status": st.session_state["prospect_status"],
        "work_arrangement": st.session_state["prospect_work_arrangement"],
        "job_description": st.session_state["prospect_description"],
        "notes": st.session_state["prospect_notes"],
        "next_action": st.session_state["prospect_next_action"],
    }
    match_report = None
    if any(
        values.get(key)
        for key in ("company", "job_title", "job_description", "official_url")
    ):
        intelligence = detect_prospect_intelligence(values)
        match_report = intelligence.get("match_report")
        _render_intelligence_preview(st, intelligence)
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
    save_column, generate_column = st.columns(2)
    save_clicked = save_column.button(
        "Save Prospect", use_container_width=True, disabled=not complete_for_save
    )
    generate_clicked = generate_column.button(
        "Save Prospect + Generate Package", use_container_width=True, type="primary",
        disabled=not complete_for_save or bool(match_report and match_report.get("match_score") is None),
    )
    if not (save_clicked or generate_clicked):
        return

    try:
        with st.spinner("Saving prospect…"):
            intake = create_prospect(build_prospect_payload(values), PROJECT_ROOT)
            if generate_clicked:
                package = generate_package(intake["tracker_id"], PROJECT_ROOT)
                st.session_state["package_preview_prospect_id"] = intake["tracker_id"]
                st.session_state["last_package_outputs"] = package["outputs"]
                st.session_state["last_package_result"] = package
                focus_dashboard_role(st.session_state, intake["tracker_id"])
                st.session_state["dashboard_materials_role_id"] = intake["tracker_id"]
            else:
                dashboard = generate_dashboard(PROJECT_ROOT)
                st.session_state["last_package_outputs"] = {
                    "job_file": intake["job_file_path"],
                    "dashboard": dashboard["output_path"],
                }
    except (ProspectIntakeError, PackageGenerationError, TrackerValidationError) as error:
        st.error(str(error))
        return

    st.success(
        f"Saved {intake['tracker_id']}"
        + (" and generated the full package." if generate_clicked else ".")
    )
    if generate_clicked:
        _render_package_summary(st, package)
    _show_output_paths(st, st.session_state["last_package_outputs"], "intake_output")


def _load_applications(st: Any) -> list[Dict[str, Any]]:
    try:
        return load_application_tracker(PROJECT_ROOT)
    except TrackerValidationError as error:
        st.error(str(error))
        return []


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
    resolved = resolve_job_reference(tracker_id, project_root)
    parsed_job = parse_job_description(resolved["job_path"])
    intelligence = get_effective_voice_profile(
        company_name=str(parsed_job.get("company") or ""),
        job_title=str(parsed_job.get("job_title") or ""),
        job_description=str(parsed_job.get("raw_text") or ""),
        source_url=str(parsed_job.get("source_url") or ""),
    )
    intelligence["profile_label"] = _humanize_taxonomy(
        intelligence["profile_name"]
    )
    intelligence["role_family_label"] = _humanize_taxonomy(
        intelligence.get("role_family_label") or intelligence["role_family"]
    )
    intelligence["freshness"] = detect_job_freshness(str(parsed_job.get("raw_text") or ""))
    intelligence["match_report"] = score_job_match(resolved["job_path"], project_root)
    return intelligence


def _render_generate_package(st: Any) -> None:
    st.markdown(
        '<h2 class="cc-section-heading">Generate Application Package</h2>',
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
    try:
        voice_context = detected_application_voice(tracker_id, PROJECT_ROOT)
    except Exception as error:
        st.caption(f"Company voice detection unavailable: {error}")
    else:
        _render_intelligence_preview(st, voice_context)
    application = by_id[tracker_id]
    generate_followups_too = st.checkbox(
        "Generate follow-up materials after package generation",
        value=get_record_status(application) == "Applied",
        key=f"package_followups_{tracker_id}",
    )
    freshness = voice_context.get("freshness", {}) if "voice_context" in locals() else {}
    override_closed = False
    if freshness.get("is_closed"):
        override_closed = st.checkbox(
            "I verified this role is open; generate despite the closed-posting signal",
            value=False,
            key=f"package_closed_override_{tracker_id}",
        )
    if st.button("Generate Package", type="primary"):
        try:
            with st.spinner("Generating resumes, messages, strategy pack, and dashboard…"):
                result = generate_package(
                    tracker_id,
                    PROJECT_ROOT,
                    generate_followups_too=generate_followups_too,
                    override_closed=override_closed,
                )
        except PackageGenerationError as error:
            st.error(str(error))
            if error.checklist:
                _render_package_summary(
                    st, {"package_checklist": error.checklist}
                )
        else:
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


def _render_followups(st: Any) -> None:
    st.markdown(
        '<h2 class="cc-section-heading">Follow-Up</h2>',
        unsafe_allow_html=True,
    )
    bulk_column, folder_column = st.columns((3, 1))
    if bulk_column.button(
        "Generate missing follow-ups for all Applied roles",
        type="primary",
        use_container_width=True,
    ):
        with st.spinner("Generating missing follow-up packages…"):
            summary = generate_missing_followups(PROJECT_ROOT)
        st.success(
            f"Generated {summary['generated_count']}; skipped existing "
            f"{summary['skipped_existing_count']}; failed {summary['failed_count']}."
        )
        for tracker_id, error in summary["failed"].items():
            st.warning(f"{tracker_id}: {error}")

    followup_directory = PROJECT_ROOT / "exports" / "followups"
    if folder_column.button("Open follow-up folder", use_container_width=True):
        if not followup_directory.exists():
            followup_directory.mkdir(parents=True, exist_ok=True)
        opened, message = open_local_path(followup_directory)
        (st.success if opened else st.warning)(message)

    applications = networking_applications(_load_applications(st))
    if not applications:
        st.info("No roles are ready for follow-up or pre-application networking.")
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
        "Post-application follow-up"
        if get_record_status(application) in {"Applied", "Follow-up", "Interviewing"}
        else "Pre-application networking"
    )
    mode_column.markdown(f"**Outreach mode:** {mode}")
    try:
        _render_intelligence_preview(
            st, detected_application_voice(tracker_id, PROJECT_ROOT)
        )
    except Exception as error:
        st.caption(f"Role intelligence unavailable: {error}")

    button_label = (
        "Regenerate Follow-Ups"
        if _followup_strategy_path(application).is_file()
        else "Generate Follow-Ups"
    )
    if st.button(button_label, type="primary"):
        try:
            with st.spinner("Preparing role-specific follow-up messages and strategy…"):
                result = generate_followups(tracker_id, PROJECT_ROOT)
        except FollowupGenerationError as error:
            st.error(str(error))
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
    try:
        packages = _package_map(PROJECT_ROOT)
    except Exception as error:
        st.error(f"Could not load application packages: {error}")
        packages = {}

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

    _render_summary_metrics(st, applications)

    st.markdown(
        '<h2 class="cc-section-heading">Dashboard Work Mode</h2>',
        unsafe_allow_html=True,
    )
    mode = st.selectbox(
        "Mode",
        DASHBOARD_MODES,
        format_func=lambda value: value.replace(" Mode", ""),
        key="dashboard_mode",
    )
    search = st.text_input(
        "Search company, title, category, role family, source, or location",
        key="dashboard_search",
    )
    filter_columns = st.columns(3)
    match_tier = filter_columns[0].selectbox(
        "Match Tier", MATCH_TIER_FILTERS, key="dashboard_match_tier"
    )
    recommended_action = filter_columns[1].selectbox(
        "Recommended Action", ACTION_FILTERS, key="dashboard_action"
    )
    application_status = filter_columns[2].selectbox(
        "Application Status", STATUS_FILTERS, key="dashboard_status"
    )
    follow_up_status = "All"
    with st.expander("Advanced filters", expanded=False):
        source_columns = st.columns(3)
        source_type = source_columns[0].selectbox("Source Type", SOURCE_TYPE_FILTERS, key="dashboard_source_type")
        verification_status = source_columns[1].selectbox("Verification Status", VERIFICATION_STATUS_FILTERS, key="dashboard_verification_status")
        trust_label = source_columns[2].selectbox("Trust Label", TRUST_LABEL_FILTERS, key="dashboard_trust_label")
    sort_by = st.selectbox("Sort by", SORT_OPTIONS, key="dashboard_sort")

    all_records = prepare_dashboard_records(applications, packages)
    records = list(all_records)
    if not (mode == "All Mode" and application_status in HIDDEN_STATUSES):
        records = select_dashboard_mode(records, mode)
    records = filter_dashboard_records(
        records,
        match_tier=match_tier,
        recommended_action=recommended_action,
        application_status=application_status,
        follow_up_status=follow_up_status,
        search=search,
        source_type=source_type,
        verification_status=verification_status,
        trust_label=trust_label,
    )
    records = sort_dashboard_records(records, sort_by)
    st.session_state.setdefault("dashboard_compact_mode", True)
    st.session_state.setdefault("dashboard_next_steps_collapsed", False)
    has_focused_role = bool(
        str(st.session_state.get("dashboard_focused_role_id") or "").strip()
    )
    workspace_controls = st.columns(3)
    if workspace_controls[0].button(
        "Collapse All", key="dashboard_collapse_all", use_container_width=True
    ):
        collapse_dashboard_working_view(st.session_state)
        st.rerun()
    if workspace_controls[1].button(
        "Expand Focused",
        key="dashboard_expand_focused",
        use_container_width=True,
        disabled=not has_focused_role,
    ):
        expand_focused_dashboard_role(st.session_state)
        st.rerun()
    if workspace_controls[2].button(
        "Clear Focus",
        key="dashboard_clear_focus_control",
        use_container_width=True,
        disabled=not has_focused_role,
    ):
        clear_focused_dashboard_role(st.session_state)
        st.rerun()
    focused_id = _render_recommended_next_steps(
        st, records, mode, packages, focus_records=all_records
    )
    st.caption(f"{len(records)} roles match the current mode and filters.")
    tracker_records = [
        record for record in records if str(record.get("id") or "") != focused_id
    ]
    _render_application_tracker(st, tracker_records, packages, mode)


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
    dashboard_tab, add_tab, generate_tab, followup_tab, status_tab, outputs_tab = st.tabs(
        (
            "Dashboard",
            "Add Prospect",
            "Generate Package",
            "Follow-Up",
            "Advanced Status Update",
            "Outputs",
        )
    )
    with dashboard_tab:
        _render_dashboard(st)
    with add_tab:
        _render_add_prospect(st)
    with generate_tab:
        _render_generate_package(st)
    with followup_tab:
        _render_followups(st)
    with status_tab:
        _render_update_status(st)
    with outputs_tab:
        _render_recent_outputs(st)


if __name__ == "__main__":
    main()
