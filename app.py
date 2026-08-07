"""Local Streamlit cockpit for Career Catalyst.

Run with: streamlit run app.py
"""

from __future__ import annotations

import hashlib
import html
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

from scripts.application_tracker import (
    ARCHIVE_ELIGIBLE_STATUSES,
    VALID_STATUSES,
    TrackerValidationError,
    active_tracker_records,
    follow_up_action_state,
    get_record_status,
    find_existing_prospect,
    is_archive_eligible,
    load_application_tracker,
    normalize_status,
    update_prospect,
    update_status,
    workflow_status_bucket,
)
from scripts.career_intelligence import generate_career_intelligence
from scripts.dynamic_role_intelligence import get_effective_voice_profile
from scripts.evidence_engine import (
    EVIDENCE_PROJECT_STATUSES,
    EvidenceEngineError,
    archive_evidence_project,
    filter_evidence_projects,
    load_evidence_projects,
    normalize_evidence_project,
    normalize_multivalue,
    upsert_evidence_project,
)
from scripts.evidence_tailoring import package_preview_fingerprint, recommend_evidence_ids
from scripts.filename_utils import build_upload_filename, canonical_employer_name, company_display_name
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
from scripts.career_signals import next_action_signal, select_todays_focus, status_date
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
    merge_role_package_outputs,
    move_role_package,
)
from scripts.role_archive import (
    ARCHIVE_REASONS,
    archive_role,
    bulk_archive_roles,
    infer_archive_reason,
    list_archive_entries,
    open_archive_folder,
    reopen_as_new_prospect,
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
    job_reference_health,
    preflight_package_generation,
    resolve_job_reference,
)
from scripts.role_intent import (
    apply_role_intelligence_overrides,
    build_role_intent,
    normalize_role_intelligence_overrides,
    tailoring_plan,
)
from scripts.parse_job import (
    COMPENSATION_DISCLOSURE_STATES,
    COMPENSATION_STATE_LABELS,
    compensation_status_message,
    extract_metadata,
    normalize_compensation,
    normalize_compensation_disclosure_state,
    parse_job_description,
)
from scripts.prospect_intake import ProspectIntakeError, create_prospect
from scripts.resume_foundation import canonical_resume_foundation_info
from scripts.score_match import persisted_match_fields, score_job_data, score_job_match
from scripts.role_lifecycle import filter_live_records, lifecycle_counts
from scripts.role_state_resolver import resolve_selected_evidence, selected_evidence_ids
from scripts.storage_paths import canonical_archive_root, canonical_export_root


# The launcher executes code from a durable code root against a separate
# runtime root.  Runtime-owned tracker, jobs, Evidence, and config must win.
PROJECT_ROOT = Path(
    os.environ.get("CAREER_CATALYST_RUNTIME_ROOT") or Path(__file__).resolve().parent
).expanduser().resolve()
MISSING_POSTING_NOTICE = (
    "Posting file unavailable. Role data and saved Evidence remain accessible. "
    "Relink or restore the posting before generating new materials."
)
UI_DESCRIPTION = (
    "Add prospects, generate tailored application packages, track statuses, and manage "
    "job search materials from one local workspace."
)
TRACKER_GROUPS = VALID_STATUSES
CLEANUP_TRACKER_GROUPS = (
    "Needs decision",
    "Passed",
    "Hidden / Invalid",
    "Stale / Cannot Verify",
)
PRIORITY_OPTIONS = ("High", "Medium", "Low", "Do Not Pursue")
ARCHIVED_ONLY_STATUS_FILTERS = frozenset({"Withdrawn / Closed"})
ACTIVE_STATUS_FILTERS = tuple(
    status for status in VALID_STATUSES if status not in ARCHIVED_ONLY_STATUS_FILTERS
)
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
    "followup_strategy": "Follow-Up Plan",
    "dashboard": "Dashboard",
}


def _safe_job_reference_health(
    application: Dict[str, Any], project_root: Path = PROJECT_ROOT
) -> Dict[str, Any]:
    """Return posting readiness without allowing a malformed reference to break UI."""
    try:
        health = job_reference_health(application, project_root)
    except Exception:
        health = {}
    if str(health.get("status") or "") == "valid":
        return health
    return {
        **health,
        "status": str(health.get("status") or "missing"),
        "recoverable": bool(health.get("recoverable") or health.get("posting_url")),
        "message": MISSING_POSTING_NOTICE,
    }


def _render_missing_posting_notice(st: Any, health: Dict[str, Any]) -> None:
    """Show the stable repair state while keeping stored role data readable."""
    if str(health.get("status") or "") == "valid":
        return
    if hasattr(st, "warning"):
        st.warning(MISSING_POSTING_NOTICE)
    elif hasattr(st, "caption"):
        st.caption(MISSING_POSTING_NOTICE)
    posting_url = str(health.get("posting_url") or "").strip()
    if posting_url and hasattr(st, "link_button"):
        st.link_button(
            "Relink / open source posting",
            posting_url,
            use_container_width=False,
        )
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
    "Follow-Up Plan": "Follow-Up Plan",
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
  .cc-status-prospect, .cc-status-considered { background: var(--cc-gold-soft); color: var(--cc-gold); }
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
    """Return counts from the exact predicate used by dashboard filters."""
    counts = lifecycle_counts(applications, status_resolver=get_record_status)
    return {
        "Total": counts["All"],
        **{status: counts[status] for status in VALID_STATUSES if counts[status]},
    }


def application_summary_navigation(summary: Dict[str, int]) -> list[tuple[str, str, int]]:
    """Return user-facing summary labels and their canonical dashboard filters."""
    return [("Active", "All", summary["Total"])] + [
        (status, status, summary[status])
        for status in ACTIVE_STATUS_FILTERS
        if summary.get(status)
    ]


def active_application_status_options() -> tuple[str, ...]:
    """Return filters backed by the active tracker view, not the Archive tab."""
    return ("All",) + ACTIVE_STATUS_FILTERS


def archive_confirmation_message(final_status: Any) -> str:
    """Return the persistent confirmation shown after an archive transaction."""
    status = str(final_status or "Final status").strip()
    return f"Archived as {status}. Open the Archive tab to view this retained record."


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
            label = status if status in grouped else "Needs decision"
        grouped.setdefault(label, [])
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
    session_state: Any,
    prospect_id: str,
    evidence_project_ids: Any = None,
) -> bool:
    """Discard stale package preview state when prospect or Evidence changes."""
    selected = str(prospect_id or "").strip()
    previous = str(session_state.get("package_preview_prospect_id") or "").strip()
    fingerprint = (
        package_preview_fingerprint(selected, evidence_project_ids)
        if evidence_project_ids is not None
        else ""
    )
    previous_fingerprint = str(
        session_state.get("package_preview_selection_fingerprint") or ""
    )
    if previous == selected and (
        evidence_project_ids is None or previous_fingerprint == fingerprint
    ):
        return False
    for key in (
        "last_package_outputs",
        "last_package_result",
        "ats_resume_preview",
        "styled_resume_preview",
        "cover_letter_preview",
        "package_summary_preview",
        "package_evidence_usage",
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
    if evidence_project_ids is not None:
        session_state["package_preview_selection_fingerprint"] = fingerprint
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
    existing = find_dashboard_role(load_application_tracker(project_root), clean_id)
    if existing is None:
        raise TrackerValidationError(f"Tracker entry not found: {clean_id}")
    current_status = get_record_status(existing)
    status = normalize_status(values.get("status")) if "status" in values else current_status
    updates: Dict[str, Any] = {}
    for field in (
        "company",
        "role",
        "location",
        "work_arrangement",
        "job_file",
        "job_description",
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
        "salary_range",
        "compensation_disclosure_state",
        "compensation_currency",
        "compensation_period",
        "compensation_raw",
        "compensation_source",
        "match_tier",
        "match_summary",
        "recommended_action",
        "confidence",
        "company_category",
        "role_family",
        "company_voice_profile",
        "company_voice_source",
    ):
        if field in values:
            updates[field] = str(values.get(field) or "")
    if "evidence_project_ids" in values:
        updates["evidence_project_ids"] = [
            str(project_id)
            for project_id in values.get("evidence_project_ids", [])
            if str(project_id).strip()
        ]
    if "role_intelligence_overrides" in values:
        updates["role_intelligence_overrides"] = normalize_role_intelligence_overrides(
            values.get("role_intelligence_overrides")
        )
    if "show_on_dashboard" in values:
        updates["show_on_dashboard"] = bool(values["show_on_dashboard"])
    if "source_verified" in values:
        updates["source_verified"] = bool(values["source_verified"])
    for field in ("compensation_minimum", "compensation_maximum"):
        if field in values:
            updates[field] = values[field]
    if "match_score" in values:
        updates["match_score"] = values["match_score"]
    for field in ("match_strengths", "match_gaps"):
        if field in values:
            updates[field] = list(values.get(field) or [])
    for field in ("inferred_role_intelligence", "inferred_role_intent"):
        if field in values and isinstance(values[field], dict):
            updates[field] = dict(values[field])
    if "compensation_manual_override" in values:
        updates["compensation_manual_override"] = bool(
            values["compensation_manual_override"]
        )
    if "follow_up_status" in values:
        follow_up_status = str(values.get("follow_up_status") or "").strip()
        updates["follow_up_status"] = (
            "" if follow_up_status == "Auto" else follow_up_status
        )
    if "company" in updates:
        updates["company"] = canonical_employer_name(updates["company"])
    if "job_description" in updates and str(updates.get("job_description") or "").strip():
        job_reference = str(updates.get("job_file") or existing.get("job_file") or "").strip()
        job_path = Path(job_reference).expanduser()
        if not job_path.is_absolute():
            job_path = project_root / job_path
        resolved_job = job_path.resolve()
        if resolved_job.is_file() and (
            resolved_job == project_root.resolve() or project_root.resolve() in resolved_job.parents
        ):
            original_job = resolved_job.read_text(encoding="utf-8", errors="replace")
            header, separator, _body = original_job.partition("\n\n")
            if not separator:
                header = original_job.rstrip()
            resolved_job.write_text(
                header.rstrip() + "\n\n" + str(updates["job_description"]).strip() + "\n",
                encoding="utf-8",
            )
    # Archive state, not status, controls whether a role remains in live views.
    if "status" in values:
        updates["show_on_dashboard"] = True
    # Avoid stamping history or recalculating status when an edit leaves it
    # unchanged.  Score, Evidence IDs, history, and manual overrides are not
    # included in this edit path and therefore remain byte-for-byte intact.
    if status in VALID_STATUSES and status != current_status:
        return update_status(clean_id, status, project_root, **updates)
    # Unknown legacy statuses remain readable and notes can still be edited safely.
    return update_prospect(clean_id, updates, project_root)


def _job_description_body(value: Any) -> str:
    """Return editable posting text without duplicating the stored Markdown header."""
    text = str(value or "").strip()
    heading = re.search(r"^##\s+Job Description\s*$", text, flags=re.IGNORECASE | re.MULTILINE)
    if heading:
        return text[heading.end() :].strip()
    return text


def reparse_dashboard_role(
    tracker_id: str,
    refreshed_job_description: Any = "",
    project_root: Path = PROJECT_ROOT,
) -> Dict[str, Any]:
    """Reparse and rescore one existing role without changing its identity or workflow state."""
    clean_id = str(tracker_id or "").strip()
    if not clean_id:
        raise TrackerValidationError("A stable tracker id is required to re-parse a role.")
    existing = find_dashboard_role(load_application_tracker(project_root), clean_id)
    if existing is None:
        raise TrackerValidationError(f"Tracker entry not found: {clean_id}")
    resolved = resolve_job_reference(clean_id, project_root)
    job_path = Path(resolved["job_path"])
    current_parsed = parse_job_description(job_path)
    current_body = _job_description_body(current_parsed.get("raw_text"))
    requested_body = _job_description_body(refreshed_job_description)
    use_refresh = bool(requested_body and requested_body != current_body)

    parsed = current_parsed
    temporary_path: Path | None = None
    if use_refresh:
        original = job_path.read_text(encoding="utf-8", errors="replace")
        header = original.split("\n\n", 1)[0].rstrip()
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=job_path.suffix or ".md",
            prefix=f".{clean_id}.reparse-",
            dir=job_path.parent,
            delete=False,
        ) as temporary:
            temporary.write(header + "\n\n" + requested_body + "\n")
            temporary_path = Path(temporary.name)
        try:
            parsed = parse_job_description(temporary_path)
        finally:
            temporary_path.unlink(missing_ok=True)

    source_url = str(
        parsed.get("source_url")
        or existing.get("posting_url")
        or existing.get("official_url")
        or existing.get("source_url")
        or ""
    )
    raw_text = str(parsed.get("raw_text") or "")
    inferred_intelligence = get_effective_voice_profile(
        company_name=str(existing.get("company") or parsed.get("company") or ""),
        job_title=str(existing.get("role") or parsed.get("job_title") or ""),
        job_description=raw_text,
        source_url=source_url,
    )
    inferred_intent = build_role_intent(
        {
            **parsed,
            "company": existing.get("company") or parsed.get("company"),
            "job_title": existing.get("role") or parsed.get("job_title"),
            "role_family": inferred_intelligence.get("role_family"),
        },
        project_root,
    )
    effective_intelligence, _effective_intent = apply_role_intelligence_overrides(
        existing, inferred_intelligence, inferred_intent
    )
    selected_ids = {
        str(value)
        for value in selected_evidence_ids(existing)
        if str(value).strip()
    }
    try:
        selected_projects = [
            project
            for project in load_evidence_projects(project_root)
            if str(project.get("id") or "") in selected_ids
        ]
    except EvidenceEngineError:
        selected_projects = []
    match_report = score_job_data(
        {
            **existing,
            "company": existing.get("company") or parsed.get("company"),
            "job_title": existing.get("role") or parsed.get("job_title"),
            "job_description": raw_text,
        },
        project_root,
        selected_projects,
    )
    previous_inferred = existing.get("inferred_role_intelligence") or {}
    previous_family = (
        previous_inferred.get("role_family_label")
        or previous_inferred.get("role_family")
        or existing.get("role_family")
        or "Not recorded"
    )
    updates: Dict[str, Any] = {
        **persisted_match_fields(match_report),
        "company_category": effective_intelligence.get("company_category"),
        "role_family": effective_intelligence.get("role_family"),
        "company_voice_profile": effective_intelligence.get("profile_name"),
        "company_voice_source": effective_intelligence.get("source"),
        "inferred_role_intelligence": dict(inferred_intelligence),
        "inferred_role_intent": dict(inferred_intent),
    }
    if use_refresh:
        updates["job_description"] = requested_body
    refreshed = update_dashboard_role(clean_id, updates, project_root)
    return {
        "tracker_id": clean_id,
        "previous_score": existing.get("match_score"),
        "new_score": match_report.get("match_score"),
        "previous_role_family": previous_family,
        "new_role_family": (
            effective_intelligence.get("role_family_label")
            or effective_intelligence.get("role_family")
            or "Not available"
        ),
        "inferred_role_family": (
            inferred_intelligence.get("role_family_label")
            or inferred_intelligence.get("role_family")
            or "Not available"
        ),
        "used_refreshed_description": use_refresh,
        "application": refreshed,
    }


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


def _render_role_intelligence_editor(
    st: Any,
    application: Dict[str, Any],
    tracker_id: str,
) -> None:
    """Render the persisted, role-scoped intelligence override editor."""
    overrides = normalize_role_intelligence_overrides(
        application.get("role_intelligence_overrides")
    )
    focused = str(
        st.session_state.get("dashboard_edit_role_intelligence_id") or ""
    ) == tracker_id
    with st.expander("Edit Role Intelligence", expanded=focused):
        if not focused:
            if overrides:
                st.caption(
                    "Explicit role-intelligence overrides are active. Inferred source data remains preserved."
                )
            else:
                st.caption(
                    "Role intelligence is inferred from the posting. Open this section to add a targeted override."
                )
            if st.button(
                "Edit Role Intelligence",
                key=f"role_intelligence_edit_{tracker_id}",
                use_container_width=True,
            ):
                st.session_state["dashboard_edit_role_intelligence_id"] = tracker_id
                st.rerun()
            return

        inferred_intelligence: Dict[str, Any] = {}
        try:
            context = build_package_context(
                tracker_id, load_application_tracker(PROJECT_ROOT), PROJECT_ROOT
            )
            inferred_intelligence = dict(
                context.get("inferred_role_intelligence") or {}
            )
        except Exception as error:
            st.warning(f"Inferred intelligence is unavailable until the posting is restored: {error}")

        def inferred_label(*keys: str) -> str:
            for key in keys:
                value = str(inferred_intelligence.get(key) or "").strip()
                if value:
                    return value
            return "Not available"

        st.caption(
            "Blank fields fall back to inferred values. Saving overrides does not change match score, status, Evidence, or history."
        )
        with st.form(key=f"role_intelligence_form_{tracker_id}"):
            company_voice = st.text_input(
                "Company voice",
                value=str(overrides.get("company_voice") or ""),
                key=f"role_intelligence_company_voice_{tracker_id}",
            )
            category = st.text_input(
                "Category",
                value=str(overrides.get("category") or ""),
                key=f"role_intelligence_category_{tracker_id}",
            )
            role_family = st.text_input(
                "Role family",
                value=str(overrides.get("role_family") or ""),
                key=f"role_intelligence_role_family_{tracker_id}",
            )
            primary_need = st.text_area(
                "Primary hiring need",
                value=str(overrides.get("primary_hiring_need") or ""),
                key=f"role_intelligence_primary_need_{tracker_id}",
                height=90,
            )
            leading = st.text_area(
                "Leading themes",
                value="; ".join(overrides.get("leading_themes") or []),
                key=f"role_intelligence_leading_themes_{tracker_id}",
                height=90,
                help="Separate themes with semicolons.",
            )
            supporting = st.text_area(
                "Supporting themes",
                value="; ".join(overrides.get("supporting_themes") or []),
                key=f"role_intelligence_supporting_themes_{tracker_id}",
                height=90,
                help="Separate themes with semicolons.",
            )
            st.markdown(
                "**Inferred values**  \\nCompany voice: "
                + inferred_label("company_voice_label", "profile_name")
                + " · Category: "
                + inferred_label("company_category_label", "company_category")
                + " · Role family: "
                + inferred_label("role_family_label", "role_family")
            )
            controls = st.columns(3)
            save_clicked = controls[0].form_submit_button(
                "Save overrides", type="primary", use_container_width=True
            )
            cancel_clicked = controls[1].form_submit_button(
                "Cancel", use_container_width=True
            )
            clear_clicked = controls[2].form_submit_button(
                "Clear overrides", use_container_width=True
            )
        if cancel_clicked:
            st.session_state.pop("dashboard_edit_role_intelligence_id", None)
            st.rerun()
        if clear_clicked or save_clicked:
            next_values = (
                {}
                if clear_clicked
                else normalize_role_intelligence_overrides(
                    {
                        "company_voice": company_voice,
                        "category": category,
                        "role_family": role_family,
                        "primary_hiring_need": primary_need,
                        "leading_themes": leading,
                        "supporting_themes": supporting,
                    }
                )
            )
            try:
                update_dashboard_role(
                    tracker_id,
                    {"role_intelligence_overrides": next_values},
                    PROJECT_ROOT,
                )
            except (TrackerValidationError, OSError) as error:
                st.error(str(error))
            else:
                st.session_state.pop("dashboard_edit_role_intelligence_id", None)
                st.session_state["dashboard_notice"] = (
                    "Role intelligence overrides cleared."
                    if clear_clicked
                    else "Role intelligence overrides saved."
                )
                st.rerun()


def dashboard_status_actions(record: Dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """Return status-aware quick actions as label/action-key pairs."""
    status = get_record_status(record)
    actions = [
        ("Mark Applied", "applied"),
        ("Mark Considered", "considered"),
        ("Withdraw / Close", "withdrawn_closed"),
        ("New Prospect", "prospect"),
    ]
    if status in {"Applied", "Under Consideration", "Interviewing"}:
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
    status = get_record_status(record)
    if mode == "Cleanup Mode" and status in {"Prospect", "Considered"}:
        return (
            ("Withdraw / Close", "withdrawn_closed"),
            ("Keep Considered", "considered"),
        )
    if status in {"Rejected", "Withdrawn / Closed"}:
        return ()
    if status == "Considered":
        material_action = (
            ("Open materials", "open_materials")
            if has_materials
            else ("Generate package", "generate_package")
        )
        return (material_action, ("Mark Applied", "applied"), ("Withdraw / Close", "withdrawn_closed"))
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
        "considered": {"status": "Considered", "show_on_dashboard": True},
        "withdrawn_closed": {"status": "Withdrawn / Closed", "show_on_dashboard": True},
        "prospect": {"status": "Prospect", "show_on_dashboard": True},
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
    compensation = values.get("compensation") or normalize_compensation(
        values.get("salary_range"),
        source="manual" if values.get("compensation_manual_override") else "saved",
        manual_override=bool(values.get("compensation_manual_override")),
        disclosure_state=values.get("compensation_disclosure_state"),
    )
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
        "compensation": compensation,
        "compensation_disclosure_state": compensation["disclosure_state"],
        "compensation_manual_override": bool(values.get("compensation_manual_override")),
        "posting_date": str(values.get("posting_date") or "").strip(),
        "source": str(values.get("source") or "Official career page").strip(),
        "priority": str(values.get("priority") or "Medium"),
        "status": str(values.get("status") or "Prospect"),
        "work_arrangement": str(values.get("work_arrangement") or "").strip(),
        "job_description": str(values.get("job_description") or "").strip(),
        "notes": str(values.get("notes") or "").strip(),
        "next_action": str(values.get("next_action") or "").strip(),
        "show_on_dashboard": bool(values.get("show_on_dashboard", True)),
    }


def compensation_record_updates(
    disclosure_state: str, value: Any, *, manual_override: bool = True
) -> Dict[str, Any]:
    """Build one canonical tracker update without inventing missing numbers."""
    compensation = normalize_compensation(
        value,
        source="manual" if manual_override else "saved",
        manual_override=manual_override,
        disclosure_state=disclosure_state,
    )
    if disclosure_state == "provided" and not compensation.get("detected"):
        raise ValueError(
            "Provided compensation requires a verified range or value."
        )
    return {
        "salary_range": str(
            compensation.get("display")
            or compensation.get("status_message")
            or "Compensation unknown — verify posting or recruiter details."
        ),
        "compensation_disclosure_state": compensation["disclosure_state"],
        "compensation_minimum": compensation.get("minimum"),
        "compensation_maximum": compensation.get("maximum"),
        "compensation_currency": compensation.get("currency") or "",
        "compensation_period": compensation.get("period") or "",
        "compensation_raw": compensation.get("raw") or "",
        "compensation_source": compensation.get("source") or "",
        "compensation_manual_override": compensation.get("manual_override", False),
        "compensation": compensation,
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
        directory = (
            canonical_export_root(project_root) / relative_directory.removeprefix("exports/")
        )
        if directory.is_dir():
            candidates.extend(path for path in directory.iterdir() if path.is_file())
    return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[:limit]


def open_local_path(path: Path, project_root: Path = PROJECT_ROOT) -> tuple[bool, str]:
    """Open a safe project or canonical-library path through macOS."""
    resolved = path.resolve()
    root = project_root.resolve()
    library_root = canonical_export_root(project_root)
    allowed = any(
        resolved == allowed_root or allowed_root in resolved.parents
        for allowed_root in (root, library_root)
    )
    if not allowed:
        return False, "Career Catalyst only opens project files or canonical materials."
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
    st.markdown('<h2 class="cc-section-heading">Application Summary</h2>', unsafe_allow_html=True)
    summary = summarize_applications(applications)
    navigation = application_summary_navigation(summary)
    active_status = str(st.session_state.get("dashboard_status") or "All")
    for row_start in range(0, len(navigation), 4):
        columns = st.columns(4)
        for column, (label, status, count) in zip(columns, navigation[row_start : row_start + 4]):
            label = f"{label}\n{count}"
            if column.button(
                label,
                key=f"summary_{status.lower().replace(' ', '_').replace('/', '_')}",
                type="primary" if active_status == status else "secondary",
                use_container_width=True,
            ):
                apply_summary_navigation(st.session_state, status)
                st.rerun()


def _package_map(project_root: Path = PROJECT_ROOT) -> Dict[str, Dict[str, Any]]:
    package_data = load_application_packages(project_root)
    return {
        str(package.get("tracker_id")): package
        for package in package_data["packages"]
        if package.get("tracker_id")
    }


def _compensation_display(
    application: Dict[str, Any], package: Dict[str, Any] | None = None
) -> str:
    value = str(
        application.get("salary_range")
        or (package or {}).get("salary_range")
        or ""
    ).strip()
    if value and value.lower() not in {"not disclosed", "unknown", "n/a"}:
        return value
    state = normalize_compensation_disclosure_state(
        application.get("compensation_disclosure_state"),
        detected=bool(
            application.get("compensation_minimum") is not None
            or application.get("compensation_maximum") is not None
        ),
    )
    return compensation_status_message(state) or value


def _metadata_html(application: Dict[str, Any], package: Dict[str, Any]) -> str:
    humanize = lambda value: str(value).replace("_", " ").title()
    source_display = application.get("source_name")
    if not source_display or source_display == "Unknown":
        source_display = application.get("source") or "Unknown"
    metadata = (
        ("Location", application.get("location") or package.get("location")),
        ("Salary", _compensation_display(application, package)),
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
        if status in {"Applied", "Under Consideration", "Interviewing"}
        else None
    )
    status_fact = _status_date_fact(application, package)
    facts = [
        ("Location", application.get("location") or package.get("location")),
        ("Work arrangement", application.get("work_arrangement")),
        ("Salary", _compensation_display(application, package)),
        ("Source type", application.get("source_type") or "Unknown Source"),
        ("Verification", application.get("verification_status") or "Not Verified"),
        ("Posting date", application.get("posting_date") or "Posting date unknown"),
    ]
    if status_fact:
        facts.append(status_fact)
    facts.append(("Follow-up", relevant_follow_up))
    items = "".join(
        '<span class="cc-meta-item">'
        f'<span class="cc-meta-label">{html.escape(label)}</span>'
        f"{html.escape(str(value))}</span>"
        for label, value in facts
        if value
    )
    return f'<div class="cc-metadata">{items}</div>' if items else ""


def _status_date_fact(
    application: Dict[str, Any], package: Dict[str, Any] | None = None
) -> tuple[str, str] | None:
    """Return a truthful status-date label/value pair for a role card."""
    status = get_record_status(application)
    if status == "Prospect":
        return None
    if package and package.get("archived"):
        label = "Archived date"
    else:
        label = {
            "Applied": "Applied date",
            "Considered": "Status date",
            "Under Consideration": "Status date",
            "Interviewing": "Interviewing date",
            "Offer": "Offer date",
            "Rejected": "Rejected date",
            "Withdrawn / Closed": "Withdrawn date",
        }.get(status, "Status date")
    fields = (
        ("submitted_date", "applied_date", "application_date")
        if status == "Applied"
        else ("status_updated_at", "created_at")
    )
    value = next((str(application.get(field) or "").strip() for field in fields if str(application.get(field) or "").strip()), "")
    return (label, value[:10]) if value else None


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


def _stable_widget_key(
    context: str,
    owner_id: str,
    label: str,
    artifact: Path | str,
) -> str:
    """Build a deterministic, page-global key for one artifact action."""
    normalized_context = re.sub(r"[^a-z0-9]+", "_", str(context).lower()).strip("_")
    normalized_owner = re.sub(r"[^a-z0-9]+", "_", str(owner_id).lower()).strip("_")
    normalized_label = re.sub(r"[^a-z0-9]+", "_", str(label).lower()).strip("_")
    try:
        artifact_id = str(Path(artifact).expanduser().resolve())
    except (OSError, TypeError, ValueError):
        artifact_id = str(artifact)
    digest = hashlib.sha256(artifact_id.encode("utf-8")).hexdigest()[:12]
    return f"cc_{normalized_context}_{normalized_owner}_{normalized_label}_{digest}"


def _material_button_rows(
    st: Any,
    tracker_id: str,
    files: Dict[str, Path],
    *,
    context: str = "existing_material_open",
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
                    key=_stable_widget_key(context, tracker_id, source_label, path),
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
    saved_compensation_state = normalize_compensation_disclosure_state(
        application.get("compensation_disclosure_state"),
        detected=bool(
            application.get("compensation_minimum") is not None
            or application.get("compensation_maximum") is not None
        ),
    )
    compensation_state = st.selectbox(
        "Compensation status",
        COMPENSATION_DISCLOSURE_STATES,
        index=COMPENSATION_DISCLOSURE_STATES.index(saved_compensation_state),
        format_func=lambda value: COMPENSATION_STATE_LABELS[value],
        key=f"source_compensation_state_{tracker_id}",
    )
    compensation_value = ""
    if compensation_state != "not_listed":
        compensation_value = st.text_input(
            "Compensation range or value",
            value=str(application.get("compensation_raw") or (
                application.get("salary_range")
                if saved_compensation_state == "provided"
                else ""
            )),
            key=f"source_compensation_value_{tracker_id}",
        )
    compensation_message = compensation_status_message(compensation_state)
    if compensation_message:
        st.caption(compensation_message)
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
        try:
            compensation_updates = compensation_record_updates(
                compensation_state, compensation_value
            )
        except ValueError as error:
            st.warning(str(error))
            return
        selected_ids = {
            str(value) for value in selected_evidence_ids(application)
        }
        try:
            selected_projects = [
                project
                for project in load_evidence_projects(PROJECT_ROOT)
                if str(project.get("id") or "") in selected_ids
            ]
        except EvidenceEngineError:
            selected_projects = []
        health = _safe_job_reference_health(application, PROJECT_ROOT)
        if health.get("status") != "valid":
            _render_missing_posting_notice(st, health)
            st.caption("Source verification is paused until the local posting is repaired.")
            return
        try:
            resolved = resolve_job_reference(tracker_id, PROJECT_ROOT)
        except PackageGenerationError:
            _render_missing_posting_notice(st, _safe_job_reference_health(application, PROJECT_ROOT))
            return
        parsed = parse_job_description(resolved["job_path"])
        match_report = score_job_data(
            {
                **application,
                **compensation_updates,
                "job_title": application.get("role"),
                "job_description": parsed.get("raw_text") or "",
            },
            PROJECT_ROOT,
            selected_projects,
        )
        update_dashboard_role(
            tracker_id,
            {
                "status": get_record_status(application),
                "posting_date": posting_date,
                "verification_status": verified_status,
                "source_verified": source_verified,
                "freshness": freshness,
                "verification_notes": source_notes,
                **compensation_updates,
                **persisted_match_fields(match_report),
            },
            PROJECT_ROOT,
        )
        st.session_state["dashboard_notice"] = "Source verification updated."
        st.rerun()


def _project_option_labels(projects: list[Dict[str, Any]]) -> Dict[str, str]:
    """Return stable evidence project select labels keyed by project id."""
    labels: Dict[str, str] = {}
    for project in projects:
        context = project.get("employer") or project.get("client") or project.get("industry")
        suffix = f" · {context}" if context else ""
        labels[str(project.get("id"))] = f"{project.get('title', 'Untitled evidence')}{suffix}"
    return labels


def _render_relevant_evidence_panel(
    st: Any, application: Dict[str, Any], tracker_id: str
) -> None:
    """Attach evidence projects to a role without modifying the evidence records."""
    try:
        projects = load_evidence_projects(PROJECT_ROOT)
    except EvidenceEngineError as error:
        st.warning(f"Evidence projects could not be loaded: {error}")
        return
    active_projects = [project for project in projects if project.get("status") != "Archived"]
    if not active_projects:
        st.caption("No active evidence projects available yet.")
        return
    job_health = _safe_job_reference_health(application, PROJECT_ROOT)
    if job_health.get("status") != "valid":
        _render_missing_posting_notice(st, job_health)
    labels = _project_option_labels(active_projects)
    options = list(labels)
    evidence_resolution = resolve_selected_evidence(application, active_projects)
    if evidence_resolution["missing_ids"]:
        st.warning(
            "Saved Evidence could not be resolved for this role: "
            + ", ".join(evidence_resolution["missing_ids"])
            + ". Restore those records before generating materials."
        )
    current = [
        str(project_id)
        for project_id in evidence_resolution["selected_ids"]
        if str(project_id) in labels
    ]
    if job_health.get("status") == "valid":
        try:
            recommended = recommend_evidence_ids(
                parse_job_description(Path(str(job_health["path"]))), active_projects, limit=3
            )
        except (OSError, ValueError, TypeError):
            recommended = []
        if recommended:
            st.caption(
                "Role-aware suggestions: "
                + "; ".join(labels.get(project_id, project_id) for project_id in recommended)
                + ". Saved selections remain authoritative until you change them."
            )
    selected = st.multiselect(
        "Relevant Evidence",
        options=options,
        default=current,
        format_func=lambda value: labels.get(str(value), str(value)),
        key=f"relevant_evidence_{tracker_id}",
        help="Manual role association only. These projects are supplied to ATS resume and cover-letter generation for this role. Removing a project here does not delete it.",
    )
    included_titles = [labels.get(str(project_id), str(project_id)) for project_id in selected]
    if included_titles:
        st.caption("Evidence included in future generated materials: " + "; ".join(included_titles))
    else:
        st.caption("No Evidence projects will be supplied to future generated materials for this role.")
    if st.button(
        "Save Relevant Evidence",
        key=f"save_relevant_evidence_{tracker_id}",
        use_container_width=True,
        disabled=job_health.get("status") != "valid",
    ):
        selected_projects = [
            project for project in active_projects if str(project.get("id")) in selected
        ]
        try:
            resolved = resolve_job_reference(tracker_id, PROJECT_ROOT)
        except PackageGenerationError:
            _render_missing_posting_notice(st, _safe_job_reference_health(application, PROJECT_ROOT))
            return
        match_report = score_job_match(
            resolved["job_path"], PROJECT_ROOT, selected_projects
        )
        update_prospect(
            tracker_id,
            {
                "evidence_project_ids": list(selected),
                **persisted_match_fields(match_report),
            },
            PROJECT_ROOT,
        )
        reset_package_preview_for_selection(
            st.session_state, tracker_id, list(selected)
        )
        st.session_state["dashboard_notice"] = (
            "Relevant Evidence updated. Regenerate the package to apply the new tailoring."
        )
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
            title_column, badge_column = st.columns((4, 2))
            title_column.markdown(
                '<p class="cc-card-company">'
                f"{html.escape(company_display_name(application.get('company') or 'Company not listed'))}</p>"
                '<p class="cc-card-role">'
                f"{html.escape(str(application.get('role') or 'Role not listed'))}</p>",
                unsafe_allow_html=True,
            )
            badge_column.markdown(_status_badges(application), unsafe_allow_html=True)
            signal = next_action_signal(application)
            compact_facts = [
                f"Status: {get_record_status(application)}",
                f"Match: {application.get('match_score') if application.get('match_score') is not None else 'Not scored'}",
                f"Priority: {application.get('priority') or 'Medium'}",
                f"Date: {status_date(application) or 'Not recorded'}",
            ]
            st.caption(" · ".join(compact_facts))
            _render_missing_posting_notice(
                st, _safe_job_reference_health(application, PROJECT_ROOT)
            )
            st.markdown(f"**Next:** {html.escape(str(signal['action']))}")
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
            action_specs = [("view", "View Role", None), ("edit", "Edit Role", None)]
            if portal_url:
                action_specs.append(("portal", "Check Application Status", portal_url))
            if posting_url:
                action_specs.append(("posting", "Open Posting", posting_url))
            if first_material:
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
            if action_columns["edit"].button(
                "Edit Role",
                key=f"compact_edit_{tracker_id}",
                use_container_width=True,
            ):
                focus_dashboard_role(st.session_state, dashboard_role_reference(application))
                st.session_state["dashboard_edit_role_id"] = tracker_id
                st.rerun()
            if posting_url:
                action_columns["posting"].link_button("Open Posting", posting_url, use_container_width=True)
            if portal_url:
                action_columns["portal"].link_button("Check Application Status", portal_url, use_container_width=True)
            if first_material and action_columns["materials"].button(
                "Open Materials",
                key=f"compact_materials_{tracker_id}",
                use_container_width=True,
                help=str(first_material),
            ):
                focus_dashboard_role(st.session_state, dashboard_role_reference(application))
                st.session_state["dashboard_materials_role_id"] = tracker_id
                st.rerun()
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
        try:
            readiness = preflight_package_generation(tracker_id, [application], PROJECT_ROOT)
            readiness_label = {
                "ready": "Ready to Generate",
                "repairable": "Ready with Automatic Repairs",
                "blocked": "Needs Posting Repair",
                "conflict": "Blocked by Factual Conflict",
            }.get(str(readiness.get("status") or "blocked"), "Needs Evidence Review")
            st.caption(f"Application readiness: **{readiness_label}**")
        except Exception:
            st.caption("Application readiness: **Needs Review**")
        _render_missing_posting_notice(
            st, _safe_job_reference_health(application, PROJECT_ROOT)
        )
        metadata = _primary_facts_html(application, package)
        if metadata:
            st.markdown(metadata, unsafe_allow_html=True)
        st.markdown(
            _match_score_html(
                application, include_details=False, include_tier=False
            ),
            unsafe_allow_html=True,
        )
        signal = next_action_signal(application)
        st.markdown("#### Next Action")
        st.markdown(f"**{html.escape(str(signal['label']))}** — {html.escape(str(signal['reason']))}")
        st.write(signal["action"])
        if mode == "Cleanup Mode":
            st.info(recommended_next_steps([application], mode)[0])
        match_details = application.get("match_strengths") or application.get("match_gaps")
        if match_details:
            with st.expander("Match details", expanded=False):
                st.markdown(_match_score_html(application), unsafe_allow_html=True)
        with st.expander("Relevant Evidence", expanded=bool(selected_evidence_ids(application))):
            st.caption("Choose projects here to prioritize specific accomplishments in generated resumes and cover letters; Career Intelligence filters do not control materials.")
            _render_relevant_evidence_panel(st, application, tracker_id)

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
            _material_button_rows(
                st,
                tracker_id,
                files,
                context="dashboard_existing_material_open",
            )
            route = material_route(get_record_status(application))
            if route.get("archived") and material_count and not archived_materials:
                st.caption("Archive recommended")
            package_folder = exact_package.get("folder") or package.get("package_folder")
            if package_folder:
                library_actions = st.columns(2)
                if library_actions[0].button(
                    "Open Package Folder",
                    key=_stable_widget_key(
                        "dashboard_package_folder_open",
                        tracker_id,
                        "package_folder",
                        package_folder,
                    ),
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
        st.markdown("#### Application Links")
        link_columns = st.columns(2)
        if portal_url:
            link_columns[0].link_button("Check Application Status", portal_url, use_container_width=True)
        if posting_url:
            link_columns[1].link_button("Open Posting", posting_url, use_container_width=True)
            st.caption(f"Source URL: {posting_url}")
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
                apply_dashboard_status_action(tracker_id, "withdrawn_closed", PROJECT_ROOT)
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
            if get_record_status(application) == "Prospect" and more_columns[2].button(
                "Mark Considered",
                key=f"dashboard_more_reviewed_{tracker_id}",
                use_container_width=True,
            ):
                apply_dashboard_status_action(tracker_id, "considered", PROJECT_ROOT)
                st.session_state["dashboard_notice"] = "Role marked Considered."
                st.rerun()
            follow_up_action = follow_up_action_state(application)
            if follow_up_action["eligible"]:
                more_columns[3].caption("Use Follow-Up Plan in Generate Package.")
            else:
                more_columns[3].caption(
                    f"{follow_up_action['label']}: {follow_up_action['reason']}"
                )

        edit_focused = str(
            st.session_state.get("dashboard_edit_role_id") or ""
        ) == tracker_id
        with st.expander("Advanced edit role", expanded=edit_focused):
            st.caption("Edit Role — changes preserve status, score, Evidence, and application history.")
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
                edited_company = edit_columns[0].text_input(
                    "Company",
                    value=str(application.get("company") or ""),
                    key=f"dashboard_company_{tracker_id}",
                )
                edited_role = edit_columns[1].text_input(
                    "Role title",
                    value=str(application.get("role") or ""),
                    key=f"dashboard_role_{tracker_id}",
                )
                detail_columns = st.columns(2)
                edited_location = detail_columns[0].text_input(
                    "Location",
                    value=str(application.get("location") or ""),
                    key=f"dashboard_location_{tracker_id}",
                )
                edited_work_arrangement = detail_columns[1].text_input(
                    "Work arrangement",
                    value=str(application.get("work_arrangement") or ""),
                    key=f"dashboard_work_arrangement_{tracker_id}",
                )
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
                edited_job_file = st.text_input(
                    "Job description reference",
                    value=str(application.get("job_file") or ""),
                    key=f"dashboard_job_file_{tracker_id}",
                    help="Keep this pointed at the exact local posting used for package generation.",
                )
                job_description_value = str(application.get("job_description") or "")
                if not job_description_value:
                    job_reference_path = Path(str(application.get("job_file") or ""))
                    if not job_reference_path.is_absolute():
                        job_reference_path = PROJECT_ROOT / job_reference_path
                    if job_reference_path.is_file():
                        try:
                            job_description_value = str(
                                parse_job_description(job_reference_path).get("raw_text") or ""
                            )
                        except Exception:
                            job_description_value = ""
                edited_job_description = st.text_area(
                    "Job description (optional refresh)",
                    value=job_description_value,
                    key=f"dashboard_job_description_{tracker_id}",
                    height=180,
                )
                st.caption(
                    "Live roles remain visible until an eligible terminal role is explicitly archived."
                )
                save_clicked = st.form_submit_button(
                    "Save role updates", type="primary", use_container_width=True
                )
            reparse_clicked = st.button(
                "Re-parse details and re-score",
                key=f"dashboard_reparse_{tracker_id}",
                use_container_width=True,
                help="Rerun the current parser, Role Intelligence, and scoring pipeline for this existing role without generating materials.",
            )
            if reparse_clicked:
                try:
                    reparse_result = reparse_dashboard_role(
                        tracker_id,
                        st.session_state.get(f"dashboard_job_description_{tracker_id}", ""),
                        PROJECT_ROOT,
                    )
                except (TrackerValidationError, PackageGenerationError, OSError, ValueError) as error:
                    st.error(f"Role could not be reparsed: {error}")
                else:
                    previous_score = reparse_result.get("previous_score")
                    new_score = reparse_result.get("new_score")
                    st.session_state["dashboard_notice"] = (
                        "Role successfully reparsed and re-scored. "
                        f"Score: {previous_score if previous_score is not None else 'Not scored'} → "
                        f"{new_score if new_score is not None else 'Not scored'}; "
                        f"inferred role family: {reparse_result['previous_role_family']} → "
                        f"{reparse_result['new_role_family']}."
                    )
                    st.session_state.pop("dashboard_edit_role_id", None)
                    st.rerun()
            if save_clicked:
                try:
                    update_dashboard_role(
                        tracker_id,
                        {
                            "company": edited_company,
                            "role": edited_role,
                            "location": edited_location,
                            "work_arrangement": edited_work_arrangement,
                            "status": edited_status,
                            "priority": edited_priority,
                            "notes": edited_notes,
                            "next_action": edited_next_action,
                            "posting_url": edited_posting_url,
                            "application_portal_url": edited_portal_url,
                            "job_file": edited_job_file,
                            "job_description": edited_job_description,
                        },
                        PROJECT_ROOT,
                    )
                except (TrackerValidationError, OSError) as error:
                    st.error(str(error))
                else:
                    message = "Role updates saved."
                    st.session_state[flash_key] = message
                    st.session_state["dashboard_notice"] = message
                    st.session_state.pop("dashboard_edit_role_id", None)
                    st.rerun()

        _render_role_intelligence_editor(st, application, tracker_id)


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
            material_paths = dict(record.get("_material_paths") or {})
            first_material = next(
                (Path(path) for path in material_paths.values() if Path(path).exists()),
                None,
            )
            if first_material:
                action_specs.append(("materials", "Open Materials", None))
            action_columns = st.columns(len(action_specs))
            for column, (key, label, url) in zip(action_columns, action_specs):
                if url:
                    column.link_button(label, url, use_container_width=True)
                elif column.button(label, key=f"next_{key}_{role_reference}", use_container_width=True):
                    focus_dashboard_role(st.session_state, role_reference)
                    if key == "materials":
                        st.session_state["dashboard_materials_role_id"] = str(record.get("id") or "")
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
    seen_paths: set[Path] = set()
    for label, value in outputs.items():
        path = Path(value)
        display_label = OUTPUT_LABELS.get(label, label.replace("_", " ").title())
        st.markdown(f"**{display_label}**")
        st.code(str(path), language=None)
        if path.exists():
            resolved_path = path.expanduser().resolve()
            if resolved_path in seen_paths:
                st.caption("Same final artifact as another output entry.")
                continue
            seen_paths.add(resolved_path)
            _show_open_button(
                st,
                f"Open {display_label.lower()}",
                path,
                _stable_widget_key(key_prefix, "generated", label, path),
            )
        else:
            st.caption("Missing / not generated.")


def _render_persistent_package_controls(
    st: Any,
    tracker_id: str,
    application: Dict[str, Any],
    *,
    context: str = "package_existing_material_open",
) -> None:
    """Render durable material actions from the exact manifest, not session state."""
    package = find_exact_role_package(PROJECT_ROOT, application)
    files = {
        str(key): Path(value)
        for key, value in dict(package.get("files") or {}).items()
        if value
    }
    existing = {key: value for key, value in files.items() if value.is_file()}
    folder = package.get("folder")
    if not existing and not folder:
        return
    st.markdown("### Current package materials")
    if package.get("archived"):
        st.caption("An archived package is available; generating again will create the current role-scoped version.")
    _material_button_rows(
        st,
        tracker_id,
        existing,
        context=context,
    )
    if folder and Path(folder).is_dir():
        _show_open_button(
            st,
            "Open package folder",
            Path(folder),
            _stable_widget_key(
                f"{context}_folder",
                tracker_id,
                "package_folder",
                folder,
            ),
        )


def _persisted_package_result(
    project_root: Path, application: Dict[str, Any]
) -> Dict[str, Any] | None:
    """Rebuild the completed-results model from the role-owned manifest."""
    package = find_exact_role_package(project_root, application)
    manifest = package.get("manifest")
    folder = package.get("folder")
    if not isinstance(manifest, dict) or not folder:
        return None
    tracker_id = str(application.get("id") or "")
    if str(manifest.get("prospect_id") or "") != tracker_id:
        return None
    manifest_path = Path(folder) / "manifest.json"
    files = {
        str(key): Path(value)
        for key, value in dict(package.get("files") or {}).items()
        if value
    }
    materials = dict(manifest.get("materials") or {})

    def _find_material(*labels: str) -> Path | None:
        candidates = [materials.get(label) for label in labels]
        candidates.extend(files.get(label) for label in labels)
        for value in candidates:
            if value:
                path = Path(value)
                if path.is_file():
                    return path
        return None

    required = (
        ("ATS Resume DOCX", ("ATS Resume", "ATS DOCX", "ats_docx"), ".docx"),
        ("Styled Resume DOCX", ("Styled Resume", "Styled DOCX", "styled_docx"), ".docx"),
        ("Cover Letter DOCX", ("Cover Letter", "Cover Letter DOCX", "cover_letter_docx"), ".docx"),
        ("Package Summary", ("Package Summary", "package_summary_text", "package_summary"), ""),
        ("Canonical Manifest", ("Canonical Manifest", "manifest_path"), ".json"),
    )
    checklist = []
    for label, aliases, suffix in required:
        path = manifest_path if label == "Canonical Manifest" and manifest_path.is_file() else _find_material(*aliases)
        if path is not None and suffix and path.suffix.lower() != suffix:
            path = None
        checklist.append(
            {
                "material_type": label,
                "display_label": label,
                "exists": path is not None,
                "preferred_open_path": str(path) if path else None,
                "missing_reason": None if path else "Missing, empty, or invalid final artifact",
            }
        )
    if not all(item["exists"] for item in checklist):
        return None
    outputs = {key: str(path) for key, path in files.items() if path.is_file()}
    outputs["manifest_path"] = str(manifest_path)
    return {
        "tracker_id": tracker_id,
        "status": application.get("status"),
        "job_title": application.get("role"),
        "company": application.get("company"),
        "canonical_export_root": str(package.get("canonical_export_root") or manifest_path.parents[2]),
        "saved_package_location": str(Path(folder)),
        "match_score": application.get("match_score"),
        "match_band": application.get("match_band"),
        "match_tier": application.get("match_tier"),
        "match_summary": application.get("match_summary"),
        "match_strengths": application.get("match_strengths") or [],
        "match_gaps": application.get("match_gaps") or [],
        "recommended_action": application.get("recommended_action"),
        "confidence": application.get("confidence"),
        "freshness": {},
        "opportunity": {},
        "package_quality": manifest.get("package_quality") or {},
        "tailoring_metadata": manifest.get("tailoring_metadata") or {},
        "outputs": outputs,
        "package_checklist": checklist,
        "manifest": manifest,
        "package_complete": True,
    }


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
    tailoring = package_result.get("tailoring_metadata") or {}
    if tailoring:
        st.markdown("**Evidence use in generated materials**")
        st.caption(
            f"Selected: {tailoring.get('selected_count', 0)} · "
            f"Used anywhere: {tailoring.get('used_anywhere_count', 0)} · "
            f"Omitted from package: {tailoring.get('omitted_from_package_count', 0)}"
        )
        st.markdown(
            "**Used in Résumé:** "
            + (", ".join(tailoring.get("resume_projects_used") or []) or "None")
        )
        st.markdown(
            "**Used in Cover Letter:** "
            + (", ".join(tailoring.get("cover_letter_projects_used") or []) or "None")
        )
        not_used = tailoring.get("projects_not_used") or []
        st.markdown(
            "**Not Used and Why:** "
            + (
                "; ".join(
                    f"{item.get('title')}: {item.get('reason')}" for item in not_used
                )
                or "None"
            )
        )
        fallback = tailoring.get("unselected_fallback_used") or []
        st.markdown(
            "**Unselected fallback used:** "
            + (", ".join(str(item.get("title")) for item in fallback) or "None")
        )
        artifact_usage = tailoring.get("artifact_usage") or {}
        for selected_evidence in tailoring.get("selected_evidence") or []:
            evidence_id = str(selected_evidence.get("id") or "")
            title = str(selected_evidence.get("title") or "Untitled Evidence")
            details = []
            for artifact_key, label in (
                ("ats_resume", "ATS résumé"),
                ("styled_resume", "styled résumé"),
                ("cover_letter", "cover letter"),
            ):
                selection = artifact_usage.get(artifact_key) or {}
                used = any(
                    str(item.get("id") or "") == evidence_id
                    for item in selection.get("used") or []
                )
                omitted = next(
                    (
                        item
                        for item in selection.get("omitted") or []
                        if str(item.get("id") or "") == evidence_id
                    ),
                    None,
                )
                details.append(
                    f"{label}: Used"
                    if used
                    else f"{label}: Not used ({(omitted or {}).get('reason') or 'Better suited to another artifact.'})"
                )
            st.caption(f"{title} — " + "; ".join(details))
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
                _show_open_button(
                    row[1],
                    "Open",
                    path,
                    _stable_widget_key(
                        "generated_checklist_open",
                        str(package_result.get("tracker_id") or "package"),
                        label,
                        path,
                    ),
                )
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
        "prospect_application_url": "",
        "prospect_job_id": "",
        "prospect_company": "",
        "prospect_role": "",
        "prospect_location": "",
        "prospect_salary": "",
        "prospect_salary_auto_value": "",
        "prospect_salary_manual_override": False,
        "prospect_compensation_state": "unknown_unverified",
        "prospect_posting_date": "",
        "prospect_posting_date_auto_value": "",
        "prospect_posting_date_manual_override": False,
        "prospect_source": "Official career page",
        "prospect_priority": "Medium",
        "prospect_status": "Prospect",
        "prospect_work_arrangement": "Not specified",
        "prospect_description": "",
        "prospect_notes": "",
        "prospect_next_action": "Review fit and generate application package.",
        "prospect_intelligence_stale": False,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def apply_detected_intake_metadata(session_state: Any) -> Dict[str, Any]:
    """Locally parse editable description facts without network or AI work."""
    metadata = extract_metadata(str(session_state.get("prospect_description") or ""))
    if not session_state.get("prospect_salary_manual_override") and metadata.get("salary_range"):
        session_state["prospect_salary"] = metadata["salary_range"]
        session_state["prospect_salary_auto_value"] = metadata["salary_range"]
        session_state["prospect_compensation_state"] = "provided"
    if not session_state.get("prospect_posting_date_manual_override") and metadata.get("posting_date"):
        session_state["prospect_posting_date"] = metadata["posting_date"]
        session_state["prospect_posting_date_auto_value"] = metadata["posting_date"]
    mark_prospect_intelligence_stale(session_state)
    return metadata


def mark_compensation_manual_override(session_state: Any) -> None:
    """Remember that the editable compensation value now belongs to the user."""
    manual_value = str(session_state.get("prospect_salary") or "").strip()
    session_state["prospect_salary_manual_override"] = (
        manual_value
        != str(session_state.get("prospect_salary_auto_value") or "").strip()
    )
    if normalize_compensation(manual_value, manual_override=True).get("detected"):
        session_state["prospect_compensation_state"] = "provided"
    mark_prospect_intelligence_stale(session_state)


def mark_posting_date_manual_override(session_state: Any) -> None:
    """Remember a user-entered posting date across unrelated reruns and saves."""
    session_state["prospect_posting_date_manual_override"] = (
        str(session_state.get("prospect_posting_date") or "").strip()
        != str(session_state.get("prospect_posting_date_auto_value") or "").strip()
    )
    mark_prospect_intelligence_stale(session_state)


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
    intelligence["compensation"] = values.get("compensation") or normalize_compensation(
        values.get("salary_range") or values.get("job_description"),
        source="manual" if values.get("compensation_manual_override") else "description",
        manual_override=bool(values.get("compensation_manual_override")),
        disclosure_state=values.get("compensation_disclosure_state"),
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
    refreshed["compensation"] = metadata.get("compensation") or normalize_compensation(
        refreshed.get("salary_range"),
        source="description",
        disclosure_state=values.get("compensation_disclosure_state"),
    )
    refreshed["compensation_disclosure_state"] = refreshed["compensation"].get(
        "disclosure_state", "unknown_unverified"
    )
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
        session_state["prospect_salary_auto_value"] = ""
        session_state["prospect_salary_manual_override"] = False
        session_state["prospect_compensation_state"] = "unknown_unverified"
        session_state["prospect_posting_date_auto_value"] = ""
        session_state["prospect_posting_date_manual_override"] = False
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
        session_state["prospect_compensation_state"] = "unknown_unverified"
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
    if imported.get("salary_range"):
        session_state["prospect_salary_auto_value"] = imported["salary_range"]
        session_state["prospect_salary_manual_override"] = False
        session_state["prospect_compensation_state"] = "provided"
    elif imported.get("compensation_disclosure_state"):
        session_state["prospect_compensation_state"] = normalize_compensation_disclosure_state(
            imported.get("compensation_disclosure_state")
        )
    if imported.get("posting_date"):
        session_state["prospect_posting_date_auto_value"] = imported["posting_date"]
        session_state["prospect_posting_date_manual_override"] = False
    if imported.get("source_name") or imported.get("source"):
        session_state["prospect_source"] = imported.get("source_name") or imported.get("source")
    application_url = str(
        imported.get("application_url") or imported.get("canonical_apply_url") or ""
    ).strip()
    if application_url:
        session_state["prospect_application_url"] = application_url
        session_state["prospect_canonical_url"] = application_url
    incomplete = bool(
        not session_state.get("prospect_company")
        or not session_state.get("prospect_role")
        or len(str(session_state.get("prospect_description") or "").strip())
        < MINIMUM_DESCRIPTION_LENGTH
    )
    import_warnings = list(imported.get("import_warnings") or [])
    message = (
        "Imported title looked like job description text. Please confirm the role title before saving."
        if title_rejected
        else "Partial import saved the available fields. Review or complete the missing details."
        if incomplete
        else "Imported the role details. Review them before saving."
    )
    if import_warnings:
        message = f"{message} {import_warnings[0]}"
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
    compensation = intelligence.get("compensation") or {}
    if not compensation.get("detected") and re.search(r"\$\s*\d", description):
        messages.append(
            "Compensation could not be confirmed. Unrelated budget or spend figures were ignored; review the editable field."
        )
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
        if intelligence.get("location") or intelligence.get("work_arrangement"):
            st.markdown(
                f"Location: **{intelligence.get('location') or 'Not specified'}**  |  "
                f"Work arrangement: **{intelligence.get('work_arrangement') or 'Not specified'}**"
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


def _render_tailoring_plan(st: Any, role_intent: Dict[str, Any]) -> None:
    """Show the exact deterministic Role Intent decision used by generators."""
    plan = tailoring_plan(role_intent)
    with st.container(border=True):
        st.markdown("### Tailoring Plan")
        rows = (
            ("Detected role", plan["detected_role"]),
            ("Company voice", plan.get("company_voice") or "Inferred"),
            ("Category", plan.get("company_category") or "Inferred"),
            ("Role family", plan.get("role_family") or plan["detected_role"]),
            ("Primary hiring need", plan["primary_hiring_need"]),
            (
                "Selected Relevant Evidence",
                ", ".join(plan["selected_relevant_evidence"]) or "None selected",
            ),
            (
                "System-Recommended Supporting Projects",
                ", ".join(plan["system_recommended_projects"]) or "None",
            ),
            ("Leading with", ", ".join(plan["leading_with"]) or "Verified operating evidence"),
            ("Supporting with", ", ".join(plan["supporting_with"]) or "None"),
            ("De-emphasizing", ", ".join(plan["de_emphasizing"]) or "None"),
            ("Earlier career", plan["earlier_career"] or "Omitted to keep the résumé focused"),
            ("Target résumé length", plan["target_resume_length"]),
            ("Confidence", plan["confidence"]),
            ("Matched signals", ", ".join(plan["matched_signals"]) or "Conservative fallback"),
        )
        for label, value in rows:
            st.markdown(f"**{label}:** {value}")
        contribution = plan.get("evidence_score_contribution") or {}
        if contribution:
            st.markdown("**Selected Evidence Evaluated:** " + (
                ", ".join(plan["selected_relevant_evidence"]) or "None selected"
            ))
            st.markdown(
                "**Evidence-Supported Matches:** "
                + (", ".join(contribution.get("matched_requirements") or []) or "None")
            )
            st.markdown(f"**Evidence Contribution:** {int(contribution.get('delta') or 0):+d}")
            st.markdown(f"**Score Changed From:** {contribution.get('before', 0)}")
            st.markdown(f"**Current Evidence-Adjusted Match Score:** {contribution.get('after', 0)}")
            st.caption(str(contribution.get("explanation") or ""))
        if plan.get("resume_projects_used") or plan.get("cover_letter_projects_used") or plan.get("projects_not_used"):
            st.markdown(
                "**Used in Résumé:** "
                + (", ".join(plan.get("resume_projects_used") or []) or "None")
            )
            st.markdown(
                "**Used in Cover Letter:** "
                + (", ".join(plan.get("cover_letter_projects_used") or []) or "None")
            )
            not_used = plan.get("projects_not_used") or []
            st.markdown(
                "**Not Used and Why:** "
                + (
                    "; ".join(
                        f"{item.get('title')}: {item.get('reason')}" for item in not_used
                    )
                    or "None"
                )
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

    def mark_intelligence_stale() -> None:
        mark_prospect_intelligence_stale(st.session_state)

    def detect_description_facts() -> None:
        apply_detected_intake_metadata(st.session_state)

    def mark_salary_manual() -> None:
        mark_compensation_manual_override(st.session_state)

    def mark_posting_date_manual() -> None:
        mark_posting_date_manual_override(st.session_state)

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
        st.selectbox(
            "Compensation status",
            COMPENSATION_DISCLOSURE_STATES,
            key="prospect_compensation_state",
            format_func=lambda value: COMPENSATION_STATE_LABELS[value],
            on_change=mark_intelligence_stale,
        )
        if st.session_state["prospect_compensation_state"] != "not_listed":
            st.text_input(
                "Compensation",
                key="prospect_salary",
                on_change=mark_salary_manual,
                help="Enter a verified range or value. Leave blank when it is unknown.",
            )
        status_message = compensation_status_message(
            st.session_state["prospect_compensation_state"]
        )
        if status_message:
            st.caption(status_message)
        st.text_input(
            "Posting Date",
            key="prospect_posting_date",
            on_change=mark_posting_date_manual,
            placeholder="YYYY-MM-DD",
            help="Optional. Imported when the source provides a reliable date; otherwise enter it manually.",
        )
        st.text_input("Source", key="prospect_source")
    with right:
        st.selectbox(
            "Priority",
            ("High", "Medium", "Low", "Do Not Pursue"),
            key="prospect_priority",
        )
        st.text_input("Application/status portal URL", key="prospect_application_portal_url")
        st.text_input(
            "Application URL",
            key="prospect_application_url",
            help="The public apply destination is kept separate from the posting and status portal URLs.",
        )
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
        on_change=detect_description_facts,
    )

    def reparse_current_fields() -> None:
        refreshed = reparse_prospect_fields(
            {
                "official_url": st.session_state["prospect_url_value"],
                "company": st.session_state["prospect_company"],
                "job_title": st.session_state["prospect_role"],
                "location": st.session_state["prospect_location"],
                "salary_range": st.session_state["prospect_salary"],
                "compensation_disclosure_state": st.session_state[
                    "prospect_compensation_state"
                ],
                "posting_date": st.session_state["prospect_posting_date"],
                "work_arrangement": st.session_state["prospect_work_arrangement"],
                "job_description": st.session_state["prospect_description"],
            }
        )
        for state_key, value_key in (
            ("prospect_company", "company"),
            ("prospect_role", "job_title"),
            ("prospect_location", "location"),
            ("prospect_work_arrangement", "work_arrangement"),
        ):
            if refreshed.get(value_key):
                st.session_state[state_key] = refreshed[value_key]
        if refreshed.get("salary_range") and not st.session_state.get("prospect_salary_manual_override"):
            st.session_state["prospect_salary"] = refreshed["salary_range"]
            st.session_state["prospect_salary_auto_value"] = refreshed["salary_range"]
            st.session_state["prospect_compensation_state"] = "provided"
        if refreshed.get("posting_date") and not st.session_state.get("prospect_posting_date_manual_override"):
            st.session_state["prospect_posting_date"] = refreshed["posting_date"]
            st.session_state["prospect_posting_date_auto_value"] = refreshed["posting_date"]
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

    salary_input = (
        ""
        if st.session_state["prospect_compensation_state"] == "not_listed"
        else st.session_state["prospect_salary"]
    )
    compensation = normalize_compensation(
        salary_input,
        source="manual" if st.session_state.get("prospect_salary_manual_override") else "saved",
        manual_override=bool(st.session_state.get("prospect_salary_manual_override")),
        disclosure_state=st.session_state["prospect_compensation_state"],
    )
    values = {
        "posting_url": st.session_state["prospect_url_value"],
        "application_portal_url": st.session_state.get("prospect_application_portal_url", ""),
        "official_url": st.session_state["prospect_url_value"],
        "source_url": st.session_state["prospect_url_value"],
        "original_source_url": st.session_state["prospect_original_source_url"],
        "canonical_apply_url": (
            st.session_state.get("prospect_application_url")
            or st.session_state["prospect_canonical_url"]
        ),
        "application_url": st.session_state.get("prospect_application_url", ""),
        "job_id": st.session_state["prospect_job_id"],
        "company": st.session_state["prospect_company"],
        "job_title": st.session_state["prospect_role"],
        "location": st.session_state["prospect_location"],
        "salary_range": salary_input,
        "compensation": compensation,
        "compensation_disclosure_state": compensation["disclosure_state"],
        "compensation_manual_override": bool(st.session_state.get("prospect_salary_manual_override")),
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
        compensation = intelligence.get("compensation") or {}
        if compensation.get("detected"):
            with st.expander("Advanced Details", expanded=False):
                st.caption(
                    "Compensation source: "
                    f"{compensation.get('source') or 'unknown'} | "
                    f"Period: {compensation.get('period') or 'unknown'} | "
                    f"Raw match: {compensation.get('raw') or 'not available'}"
                )
    title_is_valid = is_valid_role_title(values["job_title"])
    if values["job_title"] and not title_is_valid:
        st.warning("Please confirm the role title before saving.")
    compensation_valid_for_save = not (
        st.session_state["prospect_compensation_state"] == "provided"
        and not compensation.get("detected")
    )
    if not compensation_valid_for_save:
        st.warning("Enter a verified compensation range or choose Not listed or Unknown / unverified.")
    if (
        values["company"]
        and title_is_valid
        and len(values["job_description"].strip()) < MINIMUM_DESCRIPTION_LENGTH
    ):
        st.warning("Paste the job description before adding this prospect.")
    complete_for_save = bool(
        values["company"]
        and title_is_valid
        and compensation_valid_for_save
        and len(values["job_description"].strip()) >= MINIMUM_DESCRIPTION_LENGTH
    )
    save_clicked = st.button(
        "Add Prospect",
        use_container_width=True,
        type="primary",
        disabled=not complete_for_save,
    )
    if not save_clicked:
        return

    # Intake is a write boundary. Resolve a stable existing opportunity first
    # so a re-import opens recovery actions instead of silently enriching or
    # appearing to create a second prospect.
    duplicate = find_existing_prospect(build_prospect_payload(values), PROJECT_ROOT)
    if duplicate is not None:
        duplicate_id = str(duplicate.get("id") or "")
        st.warning(
            "This opportunity already exists in Career Catalyst. "
            f"Existing role: {duplicate.get('role') or 'Unknown'} at "
            f"{company_display_name(duplicate.get('company'))}. No new prospect was created."
        )
        duplicate_columns = st.columns(3)
        if duplicate_columns[0].button(
            "Open existing role",
            key=f"duplicate_open_{duplicate_id}",
            use_container_width=True,
        ):
            focus_dashboard_role(st.session_state, duplicate_id)
            st.rerun()
        if duplicate_columns[1].button(
            "Edit existing role",
            key=f"duplicate_edit_{duplicate_id}",
            use_container_width=True,
        ):
            focus_dashboard_role(st.session_state, duplicate_id)
            st.session_state["dashboard_edit_role_id"] = duplicate_id
            st.rerun()
        if duplicate_columns[2].button(
            "Cancel",
            key=f"duplicate_cancel_{duplicate_id}",
            use_container_width=True,
        ):
            st.info("No changes were made.")
        return

    try:
        with st.spinner("Saving prospect…"):
            intake = create_prospect(
                build_prospect_payload(values),
                PROJECT_ROOT,
                run_match_analysis=False,
            )
    except (ProspectIntakeError, TrackerValidationError) as error:
        st.error(str(error))
        return

    if not intake.get("tracker_created", True):
        st.warning(
            "This opportunity already existed and was refreshed safely. "
            "Open the existing role to review its preserved history and materials."
        )
    else:
        st.success(f"Added {intake['tracker_id']} without generating materials.")
    st.info("Review the prospect on Dashboard. Use Generate Package only when you are ready to create materials.")


def _load_applications(
    st: Any, *, include_archived: bool = False
) -> list[Dict[str, Any]]:
    try:
        applications = load_application_tracker(PROJECT_ROOT)
        return applications if include_archived else active_tracker_records(applications)
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
        if get_record_status(application)
        in {"Applied", "Under Consideration", "Interviewing"}
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
    context = build_package_context(
        tracker_id, load_application_tracker(project_root), project_root
    )
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
    intelligence["location"] = str(context["parsed_job"].get("location") or "")
    intelligence["work_arrangement"] = str(
        context["parsed_job"].get("work_arrangement") or ""
    )
    return intelligence



def _package_recovery_key(tracker_id: str) -> str:
    return f"package_recovery_{tracker_id}"


def _package_recovery_action_key(tracker_id: str, action: str) -> str:
    return f"{_package_recovery_key(tracker_id)}_{action}"


def _render_package_recovery(
    st: Any,
    tracker_id: str,
    application: Dict[str, Any],
    *,
    override_closed: bool = False,
) -> None:
    recovery_key = _package_recovery_key(tracker_id)
    state = st.session_state.get(recovery_key)
    if not state:
        return
    conflicts = state.get("conflicts") or []
    conflict = conflicts[0] if conflicts else {}
    material_type = str(conflict.get("material_type") or "material")
    article = "an" if material_type[:1].lower() in "aeiou" else "a"
    current = (
        f"{application.get('role')} at "
        f"{company_display_name(application.get('company'))}"
    )
    other = ""
    if conflict.get("conflicting_role") or conflict.get("conflicting_company"):
        other = (
            f" Associated role: {conflict.get('conflicting_role') or 'unknown role'} "
            f"at {conflict.get('conflicting_company') or 'unknown company'}."
        )
    st.warning(
        f"Career Catalyst found {article} {material_type.lower()} associated with a different opportunity. "
        f"It was not reused or changed. Generate a clean draft for {current} "
        f"or review the conflicting material." + other
    )
    col1, col2, col3 = st.columns(3)
    if col1.button(
        "Generate a clean new draft",
        key=_package_recovery_action_key(tracker_id, "clean"),
    ):
        try:
            with st.spinner("Generating a clean role-scoped package…"):
                result = generate_package(
                    tracker_id,
                    PROJECT_ROOT,
                    generate_followups_too=st.session_state.get(
                        f"package_followups_{tracker_id}", False
                    ),
                    override_closed=override_closed,
                    force_clean_draft=True,
                )
        except PackageGenerationError as error:
            st.error(str(error))
        else:
            st.session_state.pop(recovery_key, None)
            st.session_state["last_package_outputs"] = result["outputs"]
            st.session_state["last_package_result"] = result
            st.session_state["package_preview_prospect_id"] = tracker_id
            st.success(
                f"Generated clean package for {result['job_title']} at {result['company']}."
            )
            _render_package_summary(st, result)
            refreshed = find_dashboard_role(load_application_tracker(PROJECT_ROOT), tracker_id)
            if refreshed is not None:
                _render_persistent_package_controls(
                    st,
                    tracker_id,
                    refreshed,
                    context="recovery_existing_material_open",
                )
    if col2.button(
        "View conflicting material",
        key=_package_recovery_action_key(tracker_id, "view"),
    ):
        path = conflict.get("path")
        if path:
            opened, message = open_local_path(Path(path))
            if opened:
                state["viewed_conflict_path"] = str(path)
                st.success(message)
            else:
                st.warning(message)
        else:
            st.info("No material path is available for this conflict.")
    viewed_path = state.get("viewed_conflict_path")
    if viewed_path:
        st.caption(str(viewed_path))
    if col3.button(
        "Cancel", key=_package_recovery_action_key(tracker_id, "cancel")
    ):
        st.session_state.pop(recovery_key, None)
        st.info("Generation cancelled. No materials were changed.")


FOLLOWUP_PACKAGE_LABELS = {
    "followup_strategy": "Follow-Up Plan",
    "recruiter_followup": "Recruiter Follow-Up",
    "hiring_manager_followup": "Hiring Manager Follow-Up",
    "warm_contact_message": "Warm Contact Message",
    "referral_ask": "Referral Ask",
}


def _render_followup_plan_result(st: Any, result: Dict[str, Any]) -> None:
    plan = dict(result.get("plan") or {})
    if not plan:
        return
    columns = st.columns(3)
    columns[0].markdown(f"**Timing**  \n{plan.get('timing_window', '')}")
    columns[1].markdown(
        f"**Recipient**  \n{plan.get('recommended_recipient_type', '')}"
    )
    columns[2].markdown(
        f"**Channel**  \n{plan.get('recommended_channel', '')}"
    )
    st.markdown(f"**Objective:** {plan.get('objective', '')}")
    st.markdown(f"**Why this route:** {plan.get('rationale', '')}")
    reinforce = plan.get("reinforce") or []
    if reinforce:
        st.markdown("**Reinforce from the original application**")
        for item in reinforce:
            st.markdown(f"- {item}")
    st.markdown(
        f"**Primary recommended message: {plan.get('primary_message_label', '')}**"
    )
    st.markdown(str(plan.get("primary_message") or ""))
    outputs = dict(result.get("outputs") or {})
    for key in plan.get("alternative_message_keys") or []:
        path = Path(str(outputs.get(key) or ""))
        if path.is_file():
            with st.expander(OUTPUT_LABELS.get(key, key.replace("_", " ").title())):
                st.markdown(path.read_text(encoding="utf-8"))
    avoid = plan.get("what_to_avoid") or []
    if avoid:
        with st.expander("What to avoid", expanded=False):
            for item in avoid:
                st.markdown(f"- {item}")


def _render_followup_plan_panel(
    st: Any, tracker_id: str, application: Dict[str, Any]
) -> None:
    st.markdown("### Follow-Up Plan")
    action = follow_up_action_state(application)
    if action["eligible"]:
        st.caption(str(action["reason"]))
        exact_package = find_exact_role_package(PROJECT_ROOT, application)
        package_available = bool(exact_package.get("folder"))
        if not package_available:
            st.info("Generate the base role package before adding its Follow-Up Plan.")
        if st.button(
            "Generate Follow-Up Plan",
            type="primary",
            disabled=not package_available,
            key=f"generate_followup_plan_{tracker_id}",
        ):
            try:
                with st.spinner("Preparing the recommended follow-up path…"):
                    generated = generate_followups(tracker_id, PROJECT_ROOT)
                    merged = merge_role_package_outputs(
                        PROJECT_ROOT,
                        application,
                        generated["outputs"],
                        material_labels=FOLLOWUP_PACKAGE_LABELS,
                    )
                    updated = update_prospect(
                        tracker_id,
                        {
                            "material_paths": merged["material_paths"],
                            "package_manifest": merged["manifest"],
                        },
                        PROJECT_ROOT,
                    )
                    generated["outputs"] = merged["outputs"]
                    generated["application"] = updated
            except (FollowupGenerationError, ValueError, OSError) as error:
                st.error(str(error))
            else:
                st.session_state[f"followup_plan_result_{tracker_id}"] = generated
                st.success("Follow-Up Plan was added to this exact role package.")
    elif action["key"] == "check_application_status" and action.get("portal_url"):
        st.info(str(action["reason"]))
        st.link_button("Check Application Status", str(action["portal_url"]))
    else:
        st.info(f"{action['label']} · {action['reason']}")

    result = st.session_state.get(f"followup_plan_result_{tracker_id}")
    if result:
        _render_followup_plan_result(st, result)

    activity = application.get("followup_activity")
    activity = activity if isinstance(activity, dict) else {}
    with st.expander("Follow-Up Activity", expanded=False):
        contact_columns = st.columns(3)
        contact_name = contact_columns[0].text_input(
            "Contact name",
            value=str(activity.get("contact_name") or ""),
            key=f"followup_contact_name_{tracker_id}",
        )
        contact_type = contact_columns[1].text_input(
            "Contact type",
            value=str(activity.get("contact_type") or ""),
            key=f"followup_contact_type_{tracker_id}",
        )
        channel = contact_columns[2].text_input(
            "Channel",
            value=str(activity.get("channel") or ""),
            key=f"followup_channel_{tracker_id}",
        )
        date_columns = st.columns(2)
        date_sent = date_columns[0].text_input(
            "Date sent (YYYY-MM-DD)",
            value=str(activity.get("date_sent") or ""),
            key=f"followup_date_sent_{tracker_id}",
        )
        next_date = date_columns[1].text_input(
            "Next follow-up date (YYYY-MM-DD)",
            value=str(activity.get("next_followup_date") or ""),
            key=f"followup_next_date_{tracker_id}",
        )
        response = st.text_area(
            "Response", value=str(activity.get("response") or ""), key=f"followup_response_{tracker_id}"
        )
        notes = st.text_area(
            "Notes", value=str(activity.get("notes") or ""), key=f"followup_activity_notes_{tracker_id}"
        )
        if st.button("Save Follow-Up Activity", key=f"save_followup_activity_{tracker_id}"):
            update_prospect(
                tracker_id,
                {
                    "followup_activity": {
                        "contact_name": contact_name.strip(),
                        "contact_type": contact_type.strip(),
                        "channel": channel.strip(),
                        "date_sent": date_sent.strip(),
                        "response": response.strip(),
                        "next_followup_date": next_date.strip(),
                        "notes": notes.strip(),
                    }
                },
                PROJECT_ROOT,
            )
            st.success("Follow-up activity saved. Application status was unchanged.")

def _render_generation_preflight(st: Any, preflight: Dict[str, Any]) -> None:
    """Show the shared readiness gate without exposing implementation errors."""
    status = str(preflight.get("status") or "ready")
    labels = {
        "ready": "Ready",
        "repairable": "Automatically repaired",
        "blocked": "Blocking factual issue",
        "conflict": "Blocking factual issue",
    }
    st.markdown(f"**Application preflight: {labels.get(status, status.title())}**")
    job_health = preflight.get("job_health") or {}
    if status == "blocked" and str(job_health.get("status") or "") != "valid":
        _render_missing_posting_notice(st, job_health)
    for item in preflight.get("ready") or []:
        st.caption("✓ " + str(item))
    for item in preflight.get("auto_repairs") or []:
        st.info("Automatic repair: " + str(item))
    for item in preflight.get("blocking_issues") or []:
        st.warning(str(item))
    selected_ids = list(preflight.get("selected_evidence_ids") or [])
    resolved_ids = list(preflight.get("resolved_evidence_ids") or [])
    missing_ids = list(preflight.get("missing_evidence_ids") or [])
    if selected_ids:
        st.caption(
            f"Tracker-selected Evidence: {len(resolved_ids)} of {len(selected_ids)} resolved."
        )
    if missing_ids:
        st.warning(
            "Selected Evidence could not be resolved: " + ", ".join(missing_ids)
        )
    limits = preflight.get("evidence_limits") or {}
    if limits:
        st.caption(
            "Selected Evidence limits: ATS résumé " + str(limits.get("ats_resume", 3))
            + ", styled résumé " + str(limits.get("styled_resume", 3))
            + ", cover letter " + str(limits.get("cover_letter", 2))
            + ". All selected records remain recorded in the Package Summary."
        )


def _render_generate_package(st: Any) -> None:
    st.markdown(
        '<h2 class="cc-section-heading">Generate Application Package</h2>',
        unsafe_allow_html=True,
    )
    st.caption(f"Canonical materials location: {canonical_export_root(PROJECT_ROOT)}")
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
    application = by_id[tracker_id]
    _render_persistent_package_controls(st, tracker_id, application)
    reset_package_preview_for_selection(
        st.session_state, tracker_id, selected_evidence_ids(application)
    )
    recovery_key = _package_recovery_key(tracker_id)
    if not st.session_state.get(recovery_key):
        preflight = preflight_package_generation(tracker_id, applications, PROJECT_ROOT)
        if preflight.get("status") == "conflict":
            st.session_state[recovery_key] = {
                "conflicts": preflight.get("conflicts") or []
            }
        else:
            _render_generation_preflight(st, preflight)
            if preflight.get("status") == "blocked":
                return
    if st.session_state.get(recovery_key):
        _render_package_recovery(st, tracker_id, application)
        return
    try:
        package_context = build_package_context(tracker_id, applications, PROJECT_ROOT)
    except Exception as error:
        st.caption(f"Tailoring Plan unavailable: {error}")
    else:
        voice_context = dict(package_context["role_intelligence"])
        voice_context["freshness"] = detect_job_freshness(
            str(package_context["parsed_job"].get("raw_text") or "")
        )
        voice_context["match_report"] = package_context["match_report"]
        voice_context["location"] = str(
            package_context["parsed_job"].get("location") or ""
        )
        voice_context["work_arrangement"] = str(
            package_context["parsed_job"].get("work_arrangement") or ""
        )
        _render_intelligence_preview(st, voice_context)
        _render_tailoring_plan(st, package_context["role_intent"])
    freshness = voice_context.get("freshness", {}) if "voice_context" in locals() else {}
    override_closed = False
    if freshness.get("is_closed"):
        override_closed = st.checkbox(
            "I verified this role is open; generate despite the closed-posting signal",
            value=False,
            key=f"package_closed_override_{tracker_id}",
        )
    if st.button(
        "Generate Package",
        type="primary",
        key=_package_recovery_action_key(tracker_id, "generate"),
    ):
        preflight = preflight_package_generation(tracker_id, applications, PROJECT_ROOT)
        if preflight.get("status") == "conflict":
            st.session_state[recovery_key] = {
                "conflicts": preflight.get("conflicts") or []
            }
            _render_package_recovery(
                st,
                tracker_id,
                application,
                override_closed=override_closed,
            )
            return
        if preflight.get("status") == "blocked":
            _render_generation_preflight(st, preflight)
            return
        try:
            with st.spinner("Generating resumes, messages, strategy pack, and dashboard…"):
                result = generate_package(
                    tracker_id,
                    PROJECT_ROOT,
                    generate_followups_too=False,
                    override_closed=override_closed,
                )
        except PackageGenerationError as error:
            if error.details and error.details.get("recovery"):
                st.session_state[recovery_key] = {
                    "conflicts": error.details.get("conflicts") or []
                }
                _render_package_recovery(
                    st,
                    tracker_id,
                    application,
                    override_closed=override_closed,
                )
                return
            st.error(str(error))
            if error.details:
                st.caption("Conflict details: " + ", ".join(str(v) for v in error.details.get("violations", [])))
            if error.checklist:
                _render_package_summary(
                    st, {"package_checklist": error.checklist}
                )
        else:
            if not result.get("package_complete"):
                st.error("Package generation did not complete. The prior package remains unchanged.")
                _render_package_summary(st, result)
                return
            st.success(
                f"Generated {result['job_title']} at {result['company']} — status: {result['status']}."
            )
            if result.get("saved_package_location"):
                st.info(f"Saved package: {result['saved_package_location']}")
            st.metric("Match score", result.get("match_score") or "—")
            st.session_state["last_package_outputs"] = result["outputs"]
            st.session_state["last_package_result"] = result
            st.session_state["package_preview_prospect_id"] = tracker_id
            st.session_state["package_preview_selection_fingerprint"] = (
                package_preview_fingerprint(
                    tracker_id, selected_evidence_ids(application)
                )
            )
            focus_dashboard_role(st.session_state, tracker_id)
            st.session_state["dashboard_materials_role_id"] = tracker_id
    persisted_result = _persisted_package_result(PROJECT_ROOT, application)
    if persisted_result:
        previous_result = st.session_state.get("last_package_result")
        if isinstance(previous_result, dict) and previous_result.get("tracker_id") == tracker_id:
            persisted_result = {**previous_result, **persisted_result}
        st.session_state["last_package_result"] = persisted_result
        st.session_state["last_package_outputs"] = persisted_result["outputs"]
        package_result = persisted_result
    else:
        package_result = st.session_state.get("last_package_result")
    if package_result and package_result.get("tracker_id") != tracker_id:
        package_result = None
    if package_result:
        _render_package_summary(st, package_result)
    outputs = st.session_state.get("last_package_outputs")
    if outputs:
        _show_output_paths(st, outputs, "generated_output")
    _render_followup_plan_panel(st, tracker_id, application)


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

    applications = _load_applications(st)
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
    posting_health = _safe_job_reference_health(application, PROJECT_ROOT)
    if posting_health.get("status") != "valid":
        _render_missing_posting_notice(st, posting_health)
    generate_clicked = False
    if follow_up_action["eligible"] and posting_health.get("status") == "valid":
        st.caption(str(follow_up_action["reason"]))
        generate_clicked = st.button(
            "Generate Follow-Up", type="primary", disabled=False
        )
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
    try:
        _render_intelligence_preview(
            st, detected_application_voice(tracker_id, PROJECT_ROOT)
        )
    except PackageGenerationError:
        _render_missing_posting_notice(st, posting_health)
    except Exception as error:
        st.caption(f"Role intelligence unavailable: {error}")

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


def _render_career_intelligence_result(st: Any, result: Dict[str, Any]) -> None:
    structured = dict(result.get("structured") or result)
    st.warning(str(structured.get("inference_notice") or ""))
    st.markdown("### What the hiring manager is likely hiring for")
    for item in structured.get("hiring_manager_intent") or []:
        st.markdown(f"- {item}")
    st.markdown("### Likely First-Screen Priorities")
    for item in structured.get("first_screen_priorities") or []:
        st.markdown(f"- {item}")
    st.markdown("### Likely Interview Questions")
    for group in structured.get("question_groups") or []:
        with st.expander(str(group.get("category") or "Interview questions")):
            for item in group.get("questions") or []:
                st.markdown(f"**{item.get('question', '')}**")
                st.markdown(f"- What they are testing: {item.get('testing', '')}")
                st.markdown(f"- Answer direction: {item.get('answer_direction', '')}")
                st.markdown(
                    "- Best verified evidence: "
                    + ", ".join(str(value) for value in item.get("evidence") or [])
                )
                st.markdown(f"- Caution: {item.get('caution', '')}")
    with st.expander("Best Evidence and STAR Stories", expanded=True):
        for item in structured.get("best_evidence") or []:
            st.markdown(f"**{item.get('label', '')}** · {item.get('description', '')}")
    with st.expander("Likely Concerns or Gaps", expanded=False):
        for item in structured.get("concerns_and_bridges") or []:
            st.markdown(
                f"**Concern:** {item.get('concern', '')}  \n**Bridge:** {item.get('bridge', '')}"
            )
    with st.expander("Questions Trisha Should Ask", expanded=False):
        for item in structured.get("questions_to_ask") or []:
            st.markdown(f"- {item}")
    st.markdown("### Tell Me About Yourself")
    st.markdown(str(structured.get("tell_me_about_yourself") or ""))
    st.markdown("### Why This Company / Why This Role")
    st.markdown(str(structured.get("why_company_role") or ""))
    st.markdown("### First 90-Day Themes")
    for item in structured.get("first_90_day_themes") or []:
        st.markdown(f"- {item}")
    if structured.get("user_supplied_context"):
        with st.expander("User-Supplied Context (not independently verified)"):
            st.markdown(str(structured["user_supplied_context"]))
    st.info(str(structured.get("voice_reminder") or ""))


def _render_career_intelligence(st: Any) -> None:
    st.markdown(
        '<h2 class="cc-section-heading">Career Intelligence</h2>',
        unsafe_allow_html=True,
    )
    applications = _load_applications(st)
    if not applications:
        st.info("No active roles are available.")
        return
    by_id = {str(item["id"]): item for item in applications}
    tracker_id = st.selectbox(
        "Role",
        tuple(by_id),
        format_func=lambda value: _application_label(by_id[value]),
        key="career_intelligence_tracker_id",
    )
    application = by_id[tracker_id]
    additional_context = st.text_area(
        "Additional context (user supplied; not independently verified)",
        value=str(application.get("career_intelligence_context") or ""),
        key=f"career_intelligence_context_{tracker_id}",
        help="Paste recruiter messages, interview logistics, research, or notes learned after applying.",
    )
    interview_notes = st.text_area(
        "Private interview notes",
        value=str(application.get("interview_notes") or ""),
        key=f"interview_notes_{tracker_id}",
    )
    if st.button("Save Context and Notes", key=f"save_career_context_{tracker_id}"):
        update_prospect(
            tracker_id,
            {
                "career_intelligence_context": additional_context,
                "interview_notes": interview_notes,
            },
            PROJECT_ROOT,
        )
        st.success("Career Intelligence context and private notes saved.")

    package = find_exact_role_package(PROJECT_ROOT, application)
    posting_health = _safe_job_reference_health(application, PROJECT_ROOT)
    if posting_health.get("status") != "valid":
        _render_missing_posting_notice(st, posting_health)
    if not package.get("folder"):
        st.info("Generate the base role package before attaching Career Intelligence.")
    button_label = (
        "Refresh Career Intelligence"
        if st.session_state.get(f"career_intelligence_result_{tracker_id}")
        else "Generate Career Intelligence"
    )
    if st.button(
        button_label,
        type="primary",
        disabled=not bool(package.get("folder"))
        or posting_health.get("status") != "valid",
        key=f"generate_career_intelligence_{tracker_id}",
    ):
        try:
            with st.spinner("Building posting-grounded interview intelligence…"):
                package_context = build_package_context(
                    tracker_id, applications, PROJECT_ROOT
                )
                result = generate_career_intelligence(
                    package_context["job_reference"],
                    PROJECT_ROOT,
                    package_context["role_intent"],
                    additional_context=additional_context,
                    associated_evidence_projects=package_context.get(
                        "associated_evidence_projects", []
                    ),
                )
                merged = merge_role_package_outputs(
                    PROJECT_ROOT,
                    application,
                    {"interview_prep": result["output_path"]},
                    material_labels={"interview_prep": "Interview Prep"},
                )
                update_prospect(
                    tracker_id,
                    {
                        "career_intelligence_context": additional_context,
                        "interview_notes": interview_notes,
                        "material_paths": merged["material_paths"],
                        "package_manifest": merged["manifest"],
                    },
                    PROJECT_ROOT,
                )
                result["output_path"] = merged["outputs"]["interview_prep"]
        except Exception as error:
            st.error(str(error))
        else:
            st.session_state[f"career_intelligence_result_{tracker_id}"] = result
            st.success("Career Intelligence was attached to this exact role package.")
    result = st.session_state.get(f"career_intelligence_result_{tracker_id}")
    if result:
        _render_career_intelligence_result(st, result)


def _render_archive(st: Any) -> None:
    st.markdown('<h2 class="cc-section-heading">Archive Log</h2>', unsafe_allow_html=True)
    archive_root = canonical_archive_root(PROJECT_ROOT)
    all_entries = list_archive_entries(archive_root)
    st.metric("Archived roles", len(all_entries))
    filters = st.columns(2)
    query = filters[0].text_input("Search company or role", key="archive_search")
    final_statuses = tuple(
        sorted({entry["final_status"] for entry in all_entries if entry["final_status"]})
    )
    final_status = filters[1].selectbox(
        "Final status", ("All",) + final_statuses, key="archive_final_status"
    )
    visible = list_archive_entries(
        archive_root, query=query, final_status=final_status
    )
    if not visible:
        st.caption("No archived roles match the current filters.")
    st.session_state.setdefault("archive_reopen_completed", [])
    completed = set(st.session_state["archive_reopen_completed"])
    for application in visible:
        archive_key = hashlib.sha256(
            str(application["manifest_path"]).encode("utf-8")
        ).hexdigest()[:12]
        with st.container(border=True):
            st.markdown(
                f"### {html.escape(application['company'])} — "
                f"{html.escape(application['role_title'])}"
            )
            st.caption(
                f"Final status: {application['final_status'] or 'Not recorded'} · "
                f"Archived: {application['archived_at'] or 'Not recorded'}"
            )
            actions = st.columns(2)
            if actions[0].button(
                "Open Folder", key=f"archive_open_{archive_key}"
            ):
                opened, message = open_archive_folder(
                    application["archive_folder"], archive_root
                )
                (st.success if opened else st.error)(message)
            archive_id = application["original_role_id"]
            if actions[1].button(
                "Reopen as New Prospect",
                key=f"archive_reopen_{archive_key}",
                disabled=archive_key in completed,
            ):
                request_id = f"streamlit:{archive_key}"
                try:
                    result = reopen_as_new_prospect(
                        application["manifest_path"],
                        PROJECT_ROOT,
                        archive_root=archive_root,
                        request_id=request_id,
                    )
                except (TrackerValidationError, ValueError, OSError) as error:
                    st.error(str(error))
                else:
                    completed.add(archive_key)
                    st.session_state["archive_reopen_completed"] = sorted(completed)
                    st.success(
                        "Created a fresh Prospect. Historical scores, package state, "
                        "follow-up plans, and generated materials were not restored."
                    )
                    st.rerun()

    applications = _load_applications(st)
    eligible = [item for item in applications if is_archive_eligible(item)]
    with st.expander(f"Bulk archive eligible roles ({len(eligible)})", expanded=False):
        labels = {str(item["id"]): _application_label(item) for item in eligible}
        for item in eligible:
            st.caption(f"{labels[str(item['id'])]} · Suggested reason: {infer_archive_reason(item)}")
        selected = st.multiselect(
            "Select roles to archive",
            tuple(labels),
            format_func=lambda value: labels[value],
            default=(),
            key="bulk_archive_selected",
        )
        reasons = {}
        for tracker_id in selected:
            entry = next(item for item in eligible if str(item["id"]) == tracker_id)
            inferred = infer_archive_reason(entry)
            reasons[tracker_id] = st.selectbox(
                f"Archive reason · {labels[tracker_id]}",
                ARCHIVE_REASONS,
                index=ARCHIVE_REASONS.index(inferred),
                key=f"bulk_archive_reason_{tracker_id}",
            )
        confirmed = st.checkbox(
            "I confirm only the selected roles should be archived",
            value=False,
            key="bulk_archive_confirm",
        )
        if st.button(
            "Archive Selected Roles",
            disabled=not selected or not confirmed,
            key="bulk_archive_apply",
        ):
            summary = bulk_archive_roles(selected, PROJECT_ROOT, reasons=reasons)
            st.success(
                f"Archived {len(summary['archived'])} · Skipped "
                f"{len(summary['skipped'])} · Failed {len(summary['failed'])}"
            )
            if not summary["failed"]:
                st.rerun()


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
        "Live roles remain visible until an eligible terminal role is explicitly archived."
    )
    if current_status in ARCHIVE_ELIGIBLE_STATUSES:
        st.warning(
            "Archiving removes this role from live Career Catalyst after preserving its "
            "posting, history, and existing materials in a local archive folder. Reopening "
            "later creates a new Prospect."
        )
        inferred_reason = infer_archive_reason(application)
        reason = st.selectbox(
            "Archive reason",
            ARCHIVE_REASONS,
            index=ARCHIVE_REASONS.index(inferred_reason),
            disabled=current_status == "Rejected",
            key=f"archive_reason_{tracker_id}",
        )
        if st.button("Archive Role", key=f"archive_role_{tracker_id}"):
            final_status = "Rejected" if current_status == "Rejected" else reason
            try:
                archive_role(
                    tracker_id,
                    final_status,
                    PROJECT_ROOT,
                )
            except (TrackerValidationError, ValueError, OSError) as error:
                st.error(str(error))
            else:
                st.session_state["status_update_notice"] = archive_confirmation_message(
                    final_status
                )
                st.rerun()
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
            if get_record_status(updated) in ARCHIVE_ELIGIBLE_STATUSES:
                st.session_state["status_update_notice"] += (
                    " Review the separate Archive Role action when ready."
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
    st.info(
        "Career Intelligence helps you explore patterns across experience, applications, strengths, and gaps. Career Intelligence is an explanatory view of current role, capability, Evidence, and application data—not a separate source of truth. "
        "Filters on this page only change what you see here; they do not control ATS resumes, cover letters, "
        "match scores, or generated application materials. To prioritize specific accomplishments for a role, "
        "associate projects through that role's Relevant Evidence section. "
        "Not represented in source résumé means stored Evidence records are not currently represented in the source résumé; "
        "they are not disqualified from future materials. One Evidence record may support multiple direct, inferred, or adjacent capabilities."
    )
    if "dashboard_notice" in st.session_state:
        st.success(st.session_state.pop("dashboard_notice"))

    st.session_state.setdefault("dashboard_status", "All")
    if st.session_state["dashboard_status"] not in active_application_status_options():
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
        "Application Status", active_application_status_options(), key="dashboard_status"
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
    archive_hint, archive_button = st.columns((5, 1))
    archive_hint.caption("Withdrawn / Closed roles are retained in the Archive tab.")
    if archive_button.button("View Archive", key="dashboard_view_archive"):
        st.info("Select the Archive tab above to view retained final-status records.")
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
    records = filter_dashboard_records(
        all_records,
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
    if not records:
        st.info("Try clearing filters to inspect application patterns, source quality, match strengths, gaps, and next actions.")
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
    for application in applications:
        package = find_exact_role_package(PROJECT_ROOT, application)
        if not package.get("folder") or package.get("archived"):
            continue
        active_packages.append((application, package))
    legacy_files = [
        path
        for relative in ("messages", "followups", "strategy_packs", "markdown")
        for path in (PROJECT_ROOT / "exports" / relative).glob("*")
        if path.is_file()
    ]
    metrics = st.columns(2)
    metrics[0].metric("Active packages", len(active_packages))
    metrics[1].metric("Needs cleanup / legacy", len(legacy_files))

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

    with st.expander("Needs Cleanup / Legacy Materials", expanded=False):
        st.caption(
            f"{len(legacy_files)} legacy files remain outside exact role package folders."
        )


def _render_evidence_library(st: Any) -> None:
    """Render the reusable project-based career evidence library."""
    st.markdown(
        '<h2 class="cc-section-heading">Evidence Projects</h2>',
        unsafe_allow_html=True,
    )
    foundation = canonical_resume_foundation_info(PROJECT_ROOT)
    st.caption(
        f"Résumé foundation: {foundation['name']} | "
        f"Last updated: {foundation['last_updated']} | "
        f"Last verified: {foundation['last_verified']}"
    )
    try:
        projects = load_evidence_projects(PROJECT_ROOT)
    except EvidenceEngineError as error:
        st.error(str(error))
        return
    st.caption(
        "Reusable career proof points that store projects, accomplishments, metrics, skills, technologies, and outcomes. "
        "Attach them from a role's Relevant Evidence section to prioritize them in future resumes and cover letters."
    )
    st.caption(
        "Add Evidence when a concrete project, accomplishment, result, or responsibility is missing or underrepresented "
        "in your résumé. Skills already supported by your résumé do not need duplicate Evidence records."
    )
    metrics = st.columns(3)
    for column, status in zip(metrics, EVIDENCE_PROJECT_STATUSES):
        column.metric(status, sum(1 for project in projects if project.get("status") == status))

    search_columns = st.columns((3, 1))
    query = search_columns[0].text_input(
        "Search title, employer, skill, technology, tag, or status",
        key="evidence_search",
    )
    status = search_columns[1].selectbox(
        "Status",
        ("All",) + EVIDENCE_PROJECT_STATUSES,
        key="evidence_status_filter",
    )
    filtered = filter_evidence_projects(projects, query=query, status=status)
    st.caption(f"{len(filtered)} evidence project(s) match.")

    with st.expander("Create or edit evidence project", expanded=False):
        labels = _project_option_labels(projects)
        edit_options = ["__new__"] + list(labels)
        selected_id = st.selectbox(
            "Project",
            edit_options,
            format_func=lambda value: "New project" if value == "__new__" else labels.get(value, value),
            key="evidence_edit_project",
        )
        existing = next((project for project in projects if project.get("id") == selected_id), {})
        title = st.text_input("Project title *", value=str(existing.get("title") or ""), key=f"evidence_title_{selected_id}")
        context_cols = st.columns(3)
        employer = context_cols[0].text_input("Employer or organization", value=str(existing.get("employer") or ""), key=f"evidence_employer_{selected_id}")
        client = context_cols[1].text_input("Client or business unit", value=str(existing.get("client") or existing.get("business_unit") or ""), key=f"evidence_client_{selected_id}")
        timeframe = context_cols[2].text_input("Start date/timeframe or duration", value=str(existing.get("timeframe") or existing.get("duration") or ""), key=f"evidence_timeframe_{selected_id}")
        taxonomy_cols = st.columns(4)
        industry = taxonomy_cols[0].text_input("Industry", value=str(existing.get("industry") or ""), key=f"evidence_industry_{selected_id}")
        function = taxonomy_cols[1].text_input("Function", value=str(existing.get("function") or ""), key=f"evidence_function_{selected_id}")
        project_type = taxonomy_cols[2].text_input("Project type", value=str(existing.get("project_type") or ""), key=f"evidence_type_{selected_id}")
        current_status = str(existing.get("status") or "Active")
        if current_status not in EVIDENCE_PROJECT_STATUSES:
            current_status = "Active"
        project_status = taxonomy_cols[3].selectbox(
            "Status",
            EVIDENCE_PROJECT_STATUSES,
            index=EVIDENCE_PROJECT_STATUSES.index(current_status),
            key=f"evidence_status_{selected_id}",
        )
        problem = st.text_area("Problem *", value=str(existing.get("problem") or ""), key=f"evidence_problem_{selected_id}", height=110)
        actions = st.text_area("Actions *", value=str(existing.get("actions") or ""), key=f"evidence_actions_{selected_id}", height=110)
        results = st.text_area("Results *", value=str(existing.get("results") or ""), key=f"evidence_results_{selected_id}", height=110)
        list_cols = st.columns(3)
        skills = list_cols[0].text_area("Skills (comma or newline separated)", value=", ".join(existing.get("skills", [])), key=f"evidence_skills_{selected_id}")
        technologies = list_cols[1].text_area("Technologies/platforms", value=", ".join(existing.get("technologies", [])), key=f"evidence_tech_{selected_id}")
        tags = list_cols[2].text_area("Tags", value=", ".join(existing.get("tags", [])), key=f"evidence_tags_{selected_id}")
        links = st.text_area("Supporting evidence or links", value="\\n".join(existing.get("links") or existing.get("supporting_evidence") or []), key=f"evidence_links_{selected_id}")
        notes = st.text_area("Notes", value=str(existing.get("notes") or ""), key=f"evidence_notes_{selected_id}")
        required_missing = not (title.strip() and problem.strip() and actions.strip() and results.strip())
        if st.button("Save evidence project", type="primary", disabled=required_missing, use_container_width=True):
            payload = normalize_evidence_project(
                {
                    **existing,
                    "title": title,
                    "employer": employer,
                    "client": client,
                    "business_unit": client,
                    "timeframe": timeframe,
                    "industry": industry,
                    "function": function,
                    "project_type": project_type,
                    "problem": problem,
                    "actions": actions,
                    "results": results,
                    "skills": normalize_multivalue(skills),
                    "technologies": normalize_multivalue(technologies),
                    "tags": normalize_multivalue(tags),
                    "links": normalize_multivalue(links),
                    "supporting_evidence": normalize_multivalue(links),
                    "notes": notes,
                    "status": project_status,
                }
            )
            try:
                upsert_evidence_project(payload, PROJECT_ROOT)
            except EvidenceEngineError as error:
                st.error(str(error))
            else:
                st.success("Evidence project saved.")
                st.rerun()
        if required_missing:
            st.caption("Required: Project title, Problem, Actions, and Results.")

    for project in filtered:
        with st.container(border=True):
            heading, action = st.columns((5, 1))
            heading.markdown(f"### {html.escape(str(project.get('title') or 'Untitled evidence'))}")
            action.markdown(f"**{project.get('status', 'Active')}**")
            context = " · ".join(
                str(project.get(field))
                for field in ("employer", "client", "industry", "function", "project_type")
                if project.get(field)
            )
            if context:
                st.caption(context)
            st.markdown(f"**Problem**  \n{html.escape(str(project.get('problem') or ''))}")
            st.markdown(f"**Actions**  \n{html.escape(str(project.get('actions') or ''))}")
            st.markdown(f"**Results**  \n{html.escape(str(project.get('results') or ''))}")
            for label, field in (("Skills", "skills"), ("Technologies", "technologies"), ("Tags", "tags"), ("Supporting links", "links")):
                values = project.get(field) or []
                if values:
                    st.caption(f"{label}: {', '.join(str(value) for value in values)}")
            if project.get("status") != "Archived" and st.button(
                "Archive project",
                key=f"archive_evidence_{project.get('id')}",
                use_container_width=True,
            ):
                archive_evidence_project(str(project.get("id")), PROJECT_ROOT)
                st.success("Evidence project archived.")
                st.rerun()


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
    (
        dashboard_tab,
        evidence_tab,
        add_tab,
        generate_tab,
        intelligence_tab,
        status_tab,
        outputs_tab,
        archive_tab,
    ) = st.tabs(
        (
            "Dashboard",
            "Evidence",
            "Add Prospect",
            "Generate Package",
            "Career Intelligence",
            "Advanced Status Update",
            "Outputs",
            "Archive",
        )
    )
    with dashboard_tab:
        _render_dashboard(st)
    with evidence_tab:
        _render_evidence_library(st)
    with add_tab:
        _render_add_prospect(st)
    with generate_tab:
        _render_generate_package(st)
    with intelligence_tab:
        _render_career_intelligence(st)
    with status_tab:
        _render_update_status(st)
    with outputs_tab:
        _render_recent_outputs(st)
    with archive_tab:
        _render_archive(st)


if __name__ == "__main__":
    main()
