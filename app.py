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
    load_application_tracker,
    update_prospect,
    update_status,
)
from scripts.dynamic_role_intelligence import get_effective_voice_profile
from scripts.filename_utils import build_upload_filename
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
    recommended_next_steps,
    select_dashboard_mode,
    source_verification_caution,
    sort_dashboard_records,
)
from scripts.generate_followups import (
    FOLLOWUP_ELIGIBLE_STATUSES,
    FollowupGenerationError,
    generate_followups,
    generate_missing_followups,
)
from scripts.job_importer import MINIMUM_DESCRIPTION_LENGTH, JobImportError, import_job_from_url
from scripts.job_freshness import detect_job_freshness
from scripts.job_source_registry import normalize_job_source
from scripts.package_generator import (
    PackageGenerationError,
    generate_package,
    resolve_job_reference,
)
from scripts.parse_job import parse_job_description, salary_parsing_warning
from scripts.prospect_intake import ProspectIntakeError, create_prospect
from scripts.score_match import score_job_data, score_job_match


PROJECT_ROOT = Path(__file__).resolve().parent
UI_DESCRIPTION = (
    "Add prospects, generate tailored application packages, track statuses, and manage "
    "job search materials from one local workspace."
)
TRACKER_GROUPS = (
    "Active / Applied",
    "Draft / Reviewed / Paused",
    "Hidden / Invalid",
)
PRIORITY_OPTIONS = ("High", "Medium", "Low", "Do Not Pursue")
FOLLOW_UP_EDIT_OPTIONS = (
    "Auto",
    "Not due yet",
    "Due soon",
    "Due now",
    "Overdue",
    "Follow-up sent",
    "Not applicable",
    "Not verified",
)
OUTPUT_LABELS = {
    "job_file": "Job description",
    "resume_markdown": "Tailored resume",
    "styled_docx": "Styled resume",
    "ats_docx": "ATS resume",
    "cover_letter": "Cover letter",
    "cover_letter_text": "Cover letter text",
    "recruiter_message": "Recruiter message",
    "hiring_manager_message": "Hiring manager message",
    "application_note": "Application note",
    "strategy_pack": "Strategy pack",
    "interview_prep": "Interview prep",
    "package_summary": "Package quality summary",
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
    grid-template-columns: repeat(5, minmax(0, 1fr));
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
    """Return the five cockpit metrics without mutating tracker data."""
    return {
        "Total applications": len(applications),
        "Applied": sum(item.get("status") == "Applied" for item in applications),
        "Reviewed": sum(item.get("status") == "Reviewed" for item in applications),
        "Paused": sum(item.get("status") == "Paused" for item in applications),
        "Invalid/Hidden": sum(
            item.get("status") in HIDDEN_STATUSES
            or item.get("show_on_dashboard") is False
            for item in applications
        ),
    }


def group_applications_by_status(
    applications: list[Dict[str, Any]],
    preserve_order: bool = False,
) -> Dict[str, list[Dict[str, Any]]]:
    """Group tracker records for the interactive dashboard without changing order on disk."""
    grouped = {label: [] for label in TRACKER_GROUPS}
    for application in applications:
        status = str(application.get("status") or "Drafted")
        if application.get("show_on_dashboard") is False or status in HIDDEN_STATUSES:
            label = "Hidden / Invalid"
        elif status in ACTIVE_STATUSES:
            label = "Active / Applied"
        else:
            label = "Draft / Reviewed / Paused"
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
    current = str(current_status or "Drafted")
    return VALID_STATUSES if current in VALID_STATUSES else (current,) + VALID_STATUSES


def resolve_selected_tracker_id(
    tracker_ids: list[str], selected_tracker_id: Any = None
) -> str:
    """Keep a stable tracker selection when labels or record order change."""
    selected = str(selected_tracker_id or "")
    if selected in tracker_ids:
        return selected
    return tracker_ids[0] if tracker_ids else ""


def update_dashboard_role(
    tracker_id: str,
    values: Dict[str, Any],
    project_root: Path = PROJECT_ROOT,
) -> Dict[str, Any]:
    """Persist dashboard card fields against one durable tracker id."""
    clean_id = str(tracker_id or "").strip()
    if not clean_id:
        raise TrackerValidationError("A stable tracker id is required for dashboard updates.")
    status = str(values.get("status") or "Drafted")
    updates: Dict[str, Any] = {}
    for field in ("priority", "notes", "next_action", "suggested_follow_up_date"):
        if field in values:
            updates[field] = str(values.get(field) or "")
    if "show_on_dashboard" in values:
        updates["show_on_dashboard"] = bool(values["show_on_dashboard"])
    if "follow_up_status" in values:
        follow_up_status = str(values.get("follow_up_status") or "").strip()
        updates["follow_up_status"] = (
            "" if follow_up_status == "Auto" else follow_up_status
        )
    if status in HIDDEN_STATUSES:
        updates["show_on_dashboard"] = False
    if status in VALID_STATUSES:
        return update_status(clean_id, status, project_root, **updates)
    # Unknown legacy statuses remain readable and notes can still be edited safely.
    return update_prospect(clean_id, updates, project_root)


def build_prospect_payload(values: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize widget values without importing or executing Streamlit."""
    return {
        "official_url": str(values.get("official_url") or "").strip(),
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
    status = str(application.get("status") or "Drafted")
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


def _match_score_html(report: Dict[str, Any]) -> str:
    score = report.get("match_score")
    if score is None:
        return (
            '<section class="cc-match-gate cc-match-unscored">'
            '<span class="cc-match-label">Match Score</span><strong>Not scored yet</strong>'
            '<p class="cc-match-summary">Re-import or update this role to calculate the pre-package recommendation.</p>'
            '</section>'
        )

    def render_list(label: str, key: str) -> str:
        values = report.get(key) or []
        if not isinstance(values, list) or not values:
            return ""
        items = "".join(f"<li>{html.escape(str(value))}</li>" for value in values)
        return f'<div><strong>{label}</strong><ul>{items}</ul></div>'

    return (
        '<section class="cc-match-gate">'
        '<div class="cc-match-heading"><div>'
        '<span class="cc-match-label">Match Score</span>'
        f'<span class="cc-match-number">{html.escape(str(score))}<small>/100</small></span>'
        '</div>'
        f'<span class="cc-match-tier">{html.escape(str(report.get("match_tier") or "Not scored yet"))}</span></div>'
        '<div class="cc-match-action"><span>Recommended action</span>'
        f'<strong>{html.escape(str(report.get("recommended_action") or "Review First"))}</strong>'
        f'<span>Confidence: {html.escape(str(report.get("confidence") or "Low"))}</span></div>'
        f'<p class="cc-match-summary">{html.escape(str(report.get("match_summary") or "Review the fit before generating a package."))}</p>'
        '<div class="cc-match-details">'
        f'{render_list("Top strengths", "match_strengths")}'
        f'{render_list("Gaps / cautions", "match_gaps")}'
        '</div></section>'
    )


def _material_button_rows(
    st: Any,
    tracker_id: str,
    files: Dict[str, Path],
) -> None:
    materials = [
        (display_label, Path(files[source_label]))
        for source_label, display_label in PACKAGE_MATERIAL_LABELS.items()
        if source_label in files and Path(files[source_label]).exists()
    ]
    if not materials:
        st.caption("No generated application materials yet.")
        return
    for row_start in range(0, len(materials), 4):
        row = materials[row_start : row_start + 4]
        columns = st.columns(4)
        for index, (label, path) in enumerate(row):
            if columns[index].button(
                label,
                key=f"material_{tracker_id}_{row_start}_{index}",
                use_container_width=True,
                help=str(path),
            ):
                opened, message = open_local_path(path)
                (st.success if opened else st.warning)(message)


def _render_role_card(
    st: Any,
    application: Dict[str, Any],
    package: Dict[str, Any],
) -> None:
    tracker_id = str(application.get("id") or "application")
    with st.container(border=True):
        flash_key = f"dashboard_flash_{tracker_id}"
        if flash_key in st.session_state:
            st.success(st.session_state.pop(flash_key))
        persisted_widget_values = {
            f"dashboard_status_{tracker_id}": str(application.get("status") or "Drafted"),
            f"dashboard_priority_{tracker_id}": str(application.get("priority") or "Medium"),
            f"dashboard_notes_{tracker_id}": str(application.get("notes") or ""),
            f"dashboard_next_action_{tracker_id}": str(application.get("next_action") or "Review fit"),
            f"dashboard_follow_up_{tracker_id}": str(application.get("follow_up_status") or "Auto"),
            f"dashboard_follow_up_date_{tracker_id}": str(application.get("suggested_follow_up_date") or ""),
            f"dashboard_visibility_{tracker_id}": bool(application.get("show_on_dashboard", True)),
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
            f"{html.escape(str(application.get('company') or 'Company not listed'))}</p>"
            '<p class="cc-card-role">'
            f"{html.escape(str(application.get('role') or 'Role not listed'))}</p>",
            unsafe_allow_html=True,
        )
        badge_column.markdown(_status_badges(application), unsafe_allow_html=True)
        metadata = _metadata_html(application, package)
        if metadata:
            st.markdown(metadata, unsafe_allow_html=True)
        st.markdown(_match_score_html(application), unsafe_allow_html=True)
        notes = str(application.get("notes") or "").strip()
        if notes:
            st.markdown(
                '<div class="cc-tracker-row"><span class="cc-tracker-label">Notes</span>'
                f"<span>{html.escape(notes)}</span></div>",
                unsafe_allow_html=True,
            )
        next_action = str(application.get("next_action") or "").strip()
        if next_action:
            st.markdown(
                '<div class="cc-tracker-row"><span class="cc-tracker-label">Next action</span>'
                f"<span>{html.escape(next_action)}</span></div>",
                unsafe_allow_html=True,
            )
        verification_notes = str(application.get("verification_notes") or "Verify manually")
        st.markdown(
            '<div class="cc-tracker-row"><span class="cc-tracker-label">Verification notes</span>'
            f'<span>{html.escape(verification_notes)}</span></div>',
            unsafe_allow_html=True,
        )
        caution = source_verification_caution(application)
        if caution:
            st.markdown(
                f'<p class="cc-source-caution">{html.escape(caution)}</p>',
                unsafe_allow_html=True,
            )
        field_warnings = []
        for warning_key in ("field_warnings", "source_warnings"):
            warning_values = application.get(warning_key)
            if isinstance(warning_values, list):
                field_warnings.extend(str(value) for value in warning_values if value)
            elif warning_values:
                field_warnings.append(str(warning_values))
        field_warnings = list(dict.fromkeys(field_warnings))
        if field_warnings:
            items = "".join(f"<li>{html.escape(warning)}</li>" for warning in field_warnings)
            st.markdown(
                '<div class="cc-tracker-row"><span class="cc-tracker-label">Field warnings</span>'
                f"<ul>{items}</ul></div>",
                unsafe_allow_html=True,
            )
        st.markdown(
            '<p class="cc-materials-label">Application materials</p>',
            unsafe_allow_html=True,
        )
        materials_label = str(
            application.get("_materials_availability_label")
            or "Materials not verified"
        )
        st.caption(materials_label)
        _material_button_rows(st, tracker_id, package.get("files", {}))

        with st.expander("Quick actions", expanded=False):
            action_columns = st.columns(5)
            quick_statuses = (
                ("Mark Applied", "Applied"),
                ("Mark Reviewed", "Reviewed"),
                ("Pause", "Paused"),
                ("Pass", "Pass"),
                ("Hide / Invalid", "Invalid/Hidden"),
            )
            for column, (label, target_status) in zip(action_columns, quick_statuses):
                if column.button(
                    label,
                    key=f"dashboard_quick_{tracker_id}_{target_status}",
                    use_container_width=True,
                ):
                    try:
                        update_dashboard_role(
                            tracker_id,
                            {
                                "status": target_status,
                                "show_on_dashboard": target_status not in HIDDEN_STATUSES,
                            },
                            PROJECT_ROOT,
                        )
                    except (TrackerValidationError, OSError) as error:
                        st.error(str(error))
                    else:
                        st.session_state[flash_key] = f"Updated status to {target_status}."
                        st.rerun()

            cleanup_columns = st.columns(2)
            if cleanup_columns[0].button(
                "Keep Active",
                key=f"dashboard_keep_active_{tracker_id}",
                use_container_width=True,
            ):
                try:
                    update_dashboard_role(
                        tracker_id,
                        {"status": "Active", "show_on_dashboard": True},
                        PROJECT_ROOT,
                    )
                except (TrackerValidationError, OSError) as error:
                    st.error(str(error))
                else:
                    st.session_state[flash_key] = "Role kept active."
                    st.rerun()
            if cleanup_columns[1].button(
                "Verify manually",
                key=f"dashboard_verify_manually_{tracker_id}",
                use_container_width=True,
            ):
                try:
                    update_dashboard_role(
                        tracker_id,
                        {
                            "status": str(application.get("status") or "Drafted"),
                            "next_action": "Verify the current employer posting and apply path manually.",
                        },
                        PROJECT_ROOT,
                    )
                except (TrackerValidationError, OSError) as error:
                    st.error(str(error))
                else:
                    st.session_state[flash_key] = "Manual verification added as the next action."
                    st.rerun()

            generation_columns = st.columns(3)
            status_value = str(application.get("status") or "Drafted")
            generation_disabled = status_value in HIDDEN_STATUSES
            if generation_columns[0].button(
                "Generate Package",
                key=f"dashboard_generate_package_{tracker_id}",
                disabled=generation_disabled,
                use_container_width=True,
            ):
                try:
                    with st.spinner("Generating application package…"):
                        generate_package(tracker_id, PROJECT_ROOT)
                except PackageGenerationError as error:
                    st.error(str(error))
                else:
                    st.session_state[flash_key] = "Application package generated."
                    st.rerun()
            follow_up_disabled = (
                generation_disabled or status_value not in FOLLOWUP_ELIGIBLE_STATUSES
            )
            if generation_columns[1].button(
                "Generate Follow-Up Materials",
                key=f"dashboard_generate_followup_{tracker_id}",
                disabled=follow_up_disabled,
                use_container_width=True,
            ):
                try:
                    with st.spinner("Generating follow-up / outreach materials…"):
                        generate_followups(tracker_id, PROJECT_ROOT)
                except FollowupGenerationError as error:
                    st.error(str(error))
                else:
                    st.session_state[flash_key] = "Follow-up / outreach materials generated."
                    st.rerun()
            if generation_columns[2].button(
                "Refresh / Re-score",
                key=f"dashboard_rescore_{tracker_id}",
                disabled=generation_disabled,
                use_container_width=True,
            ):
                try:
                    resolved = resolve_job_reference(tracker_id, PROJECT_ROOT)
                    report = score_job_match(resolved["job_path"], PROJECT_ROOT)
                    update_prospect(
                        tracker_id,
                        {
                            key: report[key]
                            for key in (
                                "match_score",
                                "match_tier",
                                "recommended_action",
                                "confidence",
                                "match_summary",
                                "match_strengths",
                                "match_gaps",
                            )
                            if key in report
                        },
                        PROJECT_ROOT,
                    )
                except Exception as error:
                    st.error(f"Could not refresh score: {error}")
                else:
                    st.session_state[flash_key] = "Match score refreshed."
                    st.rerun()

            if status_value == "Paused" and application.get("_follow_up_materials_status") != "Available":
                st.info(
                    "Follow-up generation is usually intended for applied roles. "
                    "Change status to Applied or use package materials."
                )

        with st.expander("Edit role", expanded=False):
            current_status = str(application.get("status") or "Drafted")
            choices = status_options(current_status)
            current_priority = str(application.get("priority") or "Medium")
            priority_choices = (
                PRIORITY_OPTIONS
                if current_priority in PRIORITY_OPTIONS
                else (current_priority,) + PRIORITY_OPTIONS
            )
            current_follow_up = str(application.get("follow_up_status") or "Auto")
            follow_up_choices = (
                FOLLOW_UP_EDIT_OPTIONS
                if current_follow_up in FOLLOW_UP_EDIT_OPTIONS
                else (current_follow_up,) + FOLLOW_UP_EDIT_OPTIONS
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
                follow_up_columns = st.columns(2)
                edited_follow_up = follow_up_columns[0].selectbox(
                    "Follow-up status",
                    follow_up_choices,
                    index=follow_up_choices.index(current_follow_up),
                    key=f"dashboard_follow_up_{tracker_id}",
                )
                edited_follow_up_date = follow_up_columns[1].text_input(
                    "Suggested follow-up date",
                    value=str(application.get("suggested_follow_up_date") or ""),
                    key=f"dashboard_follow_up_date_{tracker_id}",
                )
                edited_visibility = st.checkbox(
                    "Show on dashboard",
                    value=bool(application.get("show_on_dashboard", True)),
                    key=f"dashboard_visibility_{tracker_id}",
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
                            "follow_up_status": edited_follow_up,
                            "suggested_follow_up_date": edited_follow_up_date,
                            "show_on_dashboard": edited_visibility,
                        },
                        PROJECT_ROOT,
                    )
                except (TrackerValidationError, OSError) as error:
                    st.error(str(error))
                else:
                    st.session_state[flash_key] = "Role updates saved."
                    st.rerun()


def _render_application_tracker(
    st: Any,
    applications: list[Dict[str, Any]],
    packages: Dict[str, Dict[str, Any]],
) -> None:
    st.markdown(
        '<h2 class="cc-section-heading">Application Tracker</h2>',
        unsafe_allow_html=True,
    )
    grouped = group_applications_by_status(applications, preserve_order=True)
    for label in TRACKER_GROUPS:
        group = grouped[label]
        count_label = "role" if len(group) == 1 else "roles"
        heading = (
            '<div class="cc-group-heading">'
            f'<span class="cc-group-title">{html.escape(label)}</span>'
            f'<span class="cc-group-count">{len(group)} {count_label}</span>'
            "</div>"
        )
        if label == "Hidden / Invalid":
            with st.expander(f"{label} ({len(group)})", expanded=False):
                for application in group:
                    _render_role_card(
                        st,
                        application,
                        packages.get(str(application.get("id")), {}),
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
            )


def _render_recommended_next_steps(
    st: Any, applications: list[Dict[str, Any]], mode: str
) -> None:
    steps = recommended_next_steps(applications, mode)
    with st.container(border=True):
        st.markdown("**Recommended Next Steps**")
        for index, step in enumerate(steps, start=1):
            st.markdown(f"{index}. {step}")


def _application_label(application: Dict[str, Any]) -> str:
    return (
        f"{application.get('company', 'Company')} — "
        f"{application.get('role', 'Role')} [{application.get('status', 'Drafted')}]"
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


def _initialize_intake_state(st: Any) -> None:
    defaults = {
        "prospect_url": "",
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

    st.text_input("Job listing URL", key="prospect_url")

    def try_import() -> None:
        try:
            imported = import_job_from_url(st.session_state.get("prospect_url", ""))
        except JobImportError as error:
            preview = import_failure_preview(st.session_state.get("prospect_url", ""), str(error))
            verification = preview["verification"]
            if verification.get("source_name") and verification.get("source_name") != "Unknown":
                st.session_state["prospect_source"] = verification["source_name"]
            st.session_state["prospect_import_result"] = ("error", preview["message"])
            return
        st.session_state["prospect_company"] = imported.get("company", "")
        st.session_state["prospect_role"] = imported.get("job_title", "")
        st.session_state["prospect_location"] = imported.get("location", "")
        st.session_state["prospect_salary"] = imported.get("salary_range", "")
        st.session_state["prospect_posting_date"] = imported.get("posting_date", "")
        st.session_state["prospect_source"] = imported.get(
            "source_name", imported.get("source", "Official career page")
        )
        st.session_state["prospect_description"] = imported.get("job_description", "")
        st.session_state["prospect_import_result"] = (
            "success",
            "Imported the role details. Review them before saving.",
        )

    st.button("Try Import From URL", on_click=try_import)
    import_result = st.session_state.get("prospect_import_result")
    if import_result:
        level, message = import_result
        (st.success if level == "success" else st.warning)(message)

    left, right = st.columns(2)
    with left:
        st.text_input("Company", key="prospect_company")
        st.text_input("Role title", key="prospect_role")
        st.text_input("Location", key="prospect_location")
        st.text_input("Salary range", key="prospect_salary")
        st.text_input("Source", key="prospect_source")
    with right:
        st.selectbox(
            "Priority",
            ("High", "Medium", "Low", "Do Not Pursue"),
            key="prospect_priority",
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
    )

    values = {
        "official_url": st.session_state["prospect_url"],
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
    if any(
        values.get(key)
        for key in ("company", "job_title", "job_description", "official_url")
    ):
        _render_intelligence_preview(st, detect_prospect_intelligence(values))
    save_column, generate_column = st.columns(2)
    save_clicked = save_column.button("Save Prospect", use_container_width=True)
    generate_clicked = generate_column.button(
        "Save Prospect + Generate Package", use_container_width=True, type="primary"
    )
    if not (save_clicked or generate_clicked):
        return

    try:
        with st.spinner("Saving prospect…"):
            intake = create_prospect(build_prospect_payload(values), PROJECT_ROOT)
            if generate_clicked:
                package = generate_package(intake["tracker_id"], PROJECT_ROOT)
                st.session_state["last_package_outputs"] = package["outputs"]
                st.session_state["last_package_result"] = package
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
        if application.get("status") in {"Applied", "Follow-up", "Interviewing"}
        and application.get("show_on_dashboard") is not False
    ]


def networking_applications(
    applications: list[Dict[str, Any]],
) -> list[Dict[str, Any]]:
    """Return visible roles eligible for follow-up or pre-application networking."""
    return [
        application
        for application in applications
        if application.get("status") in FOLLOWUP_ELIGIBLE_STATUSES
        and application.get("show_on_dashboard") is not False
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
    try:
        voice_context = detected_application_voice(tracker_id, PROJECT_ROOT)
    except Exception as error:
        st.caption(f"Company voice detection unavailable: {error}")
    else:
        _render_intelligence_preview(st, voice_context)
    application = by_id[tracker_id]
    generate_followups_too = st.checkbox(
        "Generate follow-up materials after package generation",
        value=application.get("status") == "Applied",
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
        else:
            st.success(
                f"Generated {result['job_title']} at {result['company']} — status: {result['status']}."
            )
            st.metric("Match score", result.get("match_score") or "—")
            st.session_state["last_package_outputs"] = result["outputs"]
            st.session_state["last_package_result"] = result
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
        if application.get("status") in {"Applied", "Follow-up", "Interviewing"}
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
    by_id = {str(item["id"]): item for item in applications}
    tracker_ids = list(by_id)
    selected_id = resolve_selected_tracker_id(
        tracker_ids, st.session_state.get("status_tracker_id")
    )
    if st.session_state.get("status_tracker_id") != selected_id:
        st.session_state["status_tracker_id"] = selected_id
    tracker_id = st.selectbox(
        "Tracker entry",
        tuple(tracker_ids),
        index=tracker_ids.index(selected_id),
        format_func=lambda value: _application_label(by_id[value]),
        key="status_tracker_id",
    )
    application = by_id[tracker_id]
    widget_prefix = f"status_{tracker_id}"
    choices = status_options(application.get("status"))
    current_status = str(application.get("status") or "Drafted")
    status = st.selectbox(
        "Application status",
        choices,
        index=choices.index(current_status),
        key=f"{widget_prefix}_value",
    )
    current_priority = str(application.get("priority") or "Medium")
    priority_options = (
        PRIORITY_OPTIONS
        if current_priority in PRIORITY_OPTIONS
        else (current_priority,) + PRIORITY_OPTIONS
    )
    priority = st.selectbox(
        "Priority",
        priority_options,
        index=priority_options.index(current_priority),
        key=f"{widget_prefix}_priority",
    )
    notes = st.text_area(
        "Notes", value=str(application.get("notes") or ""), key=f"{widget_prefix}_notes"
    )
    next_action = st.text_area(
        "Next action",
        value=str(application.get("next_action") or ""),
        key=f"{widget_prefix}_next_action",
    )
    show_on_dashboard = st.checkbox(
        "Show on dashboard",
        value=bool(application.get("show_on_dashboard", True)),
        key=f"{widget_prefix}_show",
    )
    if st.button("Save Status Update", type="primary"):
        try:
            updated = update_status(
                tracker_id,
                status,
                PROJECT_ROOT,
                notes=notes,
                next_action=next_action,
                priority=priority,
                show_on_dashboard=show_on_dashboard,
            )
            dashboard = generate_dashboard(PROJECT_ROOT)
        except (TrackerValidationError, OSError) as error:
            st.error(str(error))
        else:
            submitted = (
                f" Submitted {updated['submitted_date']}." if updated.get("submitted_date") else ""
            )
            st.success(f"Updated {tracker_id} to {updated['status']}.{submitted}")
            st.code(dashboard["output_path"], language=None)


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
        "Refresh dashboard", type="primary", use_container_width=True
    ):
        try:
            result = generate_dashboard(PROJECT_ROOT)
        except Exception as error:
            st.error(str(error))
        else:
            st.success(
                f"Dashboard refreshed with {result['application_count']} tracked roles."
            )
    if open_column.button("Open HTML dashboard", use_container_width=True):
        opened, message = open_local_path(dashboard_path)
        (st.success if opened else st.warning)(message)

    _render_summary_metrics(st, applications)

    st.markdown(
        '<h2 class="cc-section-heading">Dashboard Work Mode</h2>',
        unsafe_allow_html=True,
    )
    mode = st.selectbox("Mode", DASHBOARD_MODES, key="dashboard_mode")
    search = st.text_input(
        "Search company, title, category, role family, source, or location",
        key="dashboard_search",
    )
    filter_columns = st.columns(4)
    match_tier = filter_columns[0].selectbox(
        "Match Tier", MATCH_TIER_FILTERS, key="dashboard_match_tier"
    )
    recommended_action = filter_columns[1].selectbox(
        "Recommended Action", ACTION_FILTERS, key="dashboard_action"
    )
    application_status = filter_columns[2].selectbox(
        "Application Status", STATUS_FILTERS, key="dashboard_status"
    )
    follow_up_status = filter_columns[3].selectbox(
        "Follow-Up Status", FOLLOW_UP_FILTERS, key="dashboard_follow_up_status"
    )
    source_columns = st.columns(3)
    source_type = source_columns[0].selectbox(
        "Source Type", SOURCE_TYPE_FILTERS, key="dashboard_source_type"
    )
    verification_status = source_columns[1].selectbox(
        "Verification Status", VERIFICATION_STATUS_FILTERS, key="dashboard_verification_status"
    )
    trust_label = source_columns[2].selectbox(
        "Trust Label", TRUST_LABEL_FILTERS, key="dashboard_trust_label"
    )
    sort_by = st.selectbox("Sort by", SORT_OPTIONS, key="dashboard_sort")

    records = prepare_dashboard_records(applications, packages)
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
    _render_recommended_next_steps(st, records, mode)
    st.caption(f"{len(records)} roles match the current mode and filters.")
    _render_application_tracker(st, records, packages)


def _render_recent_outputs(st: Any) -> None:
    st.markdown(
        '<h2 class="cc-section-heading">Recent Outputs</h2>',
        unsafe_allow_html=True,
    )
    dashboard_path = PROJECT_ROOT / "exports" / "dashboard" / "index.html"
    with st.container(border=True):
        st.markdown("**Quick access**")
        dashboard_column, docx_column, messages_column, strategy_column, followup_column = st.columns(5)
        quick_links = (
            (dashboard_column, "Dashboard", dashboard_path),
            (docx_column, "DOCX resumes", PROJECT_ROOT / "exports" / "docx"),
            (messages_column, "Messages", PROJECT_ROOT / "exports" / "messages"),
            (
                strategy_column,
                "Strategy packs",
                PROJECT_ROOT / "exports" / "strategy_packs",
            ),
            (followup_column, "Follow-ups", PROJECT_ROOT / "exports" / "followups"),
        )
        for column, label, path in quick_links:
            if column.button(label, key=f"quick_{path.name}", use_container_width=True):
                opened, message = open_local_path(path)
                (st.success if opened else st.warning)(message)

    st.markdown("**Most recently generated**")
    files = recent_output_files()
    if not files:
        st.info("No generated files yet.")
        return
    for index, path in enumerate(files):
        relative = path.relative_to(PROJECT_ROOT)
        with st.container(border=True):
            left, right = st.columns((5, 1))
            left.code(str(relative), language=None)
            if right.button(
                "Open", key=f"recent_{index}_{path.name}", use_container_width=True
            ):
                opened, message = open_local_path(path)
                (st.success if opened else st.warning)(message)


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
