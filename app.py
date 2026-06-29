"""Local Streamlit cockpit for Career Catalyst.

Run with: streamlit run app.py
"""

from __future__ import annotations

import html
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
    update_status,
)
from scripts.generate_dashboard import generate_dashboard, load_application_packages
from scripts.job_importer import JobImportError, import_job_from_url
from scripts.package_generator import PackageGenerationError, generate_package
from scripts.prospect_intake import ProspectIntakeError, create_prospect


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
  .cc-status-applied, .cc-status-follow-up { background: var(--cc-blue-soft); color: var(--cc-blue); }
  .cc-status-interviewing { background: var(--cc-accent-soft); color: var(--cc-accent); }
  .cc-status-rejected, .cc-status-invalid { background: var(--cc-red-soft); color: var(--cc-red); }
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
  .cc-tracker-row { display: grid; grid-template-columns: 92px minmax(0, 1fr); gap: 12px; margin-top: 10px; font-size: 14px; }
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
    for values in grouped.values():
        values.sort(
            key=lambda item: (
                str(item.get("company") or "").lower(),
                str(item.get("role") or "").lower(),
            )
        )
    return grouped


def build_prospect_payload(values: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize widget values without importing or executing Streamlit."""
    return {
        "official_url": str(values.get("official_url") or "").strip(),
        "company": str(values.get("company") or "").strip(),
        "job_title": str(values.get("job_title") or "").strip(),
        "location": str(values.get("location") or "").strip(),
        "salary_range": str(values.get("salary_range") or "").strip(),
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
    status_class = status.lower().replace(" ", "-")
    badges = [
        f'<span class="cc-badge cc-status-{html.escape(status_class)}">'
        f"{html.escape(status)}</span>"
    ]
    if priority:
        badges.append(
            '<span class="cc-badge cc-priority">'
            f"{html.escape(priority)} priority</span>"
        )
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
    metadata = (
        ("Location", application.get("location") or package.get("location")),
        ("Salary", application.get("salary_range") or package.get("salary_range")),
        ("Submitted", application.get("submitted_date")),
    )
    items = "".join(
        '<span class="cc-meta-item">'
        f'<span class="cc-meta-label">{html.escape(label)}</span>'
        f"{html.escape(str(value))}</span>"
        for label, value in metadata
        if value
    )
    return f'<div class="cc-metadata">{items}</div>' if items else ""


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
        st.markdown(
            '<p class="cc-materials-label">Application materials</p>',
            unsafe_allow_html=True,
        )
        _material_button_rows(st, tracker_id, package.get("files", {}))


def _render_application_tracker(
    st: Any,
    applications: list[Dict[str, Any]],
    packages: Dict[str, Dict[str, Any]],
) -> None:
    st.markdown(
        '<h2 class="cc-section-heading">Application Tracker</h2>',
        unsafe_allow_html=True,
    )
    grouped = group_applications_by_status(applications)
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


def _initialize_intake_state(st: Any) -> None:
    defaults = {
        "prospect_url": "",
        "prospect_company": "",
        "prospect_role": "",
        "prospect_location": "",
        "prospect_salary": "",
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


def _render_add_prospect(st: Any) -> None:
    st.markdown(
        '<h2 class="cc-section-heading">Add Prospect</h2>',
        unsafe_allow_html=True,
    )
    st.caption(
        "Paste the official URL and job description for the reliable path, or try a lightweight import first."
    )
    _initialize_intake_state(st)

    st.text_input("Official career page URL", key="prospect_url")

    def try_import() -> None:
        try:
            imported = import_job_from_url(st.session_state.get("prospect_url", ""))
        except JobImportError as error:
            st.session_state["prospect_import_result"] = ("error", str(error))
            return
        st.session_state["prospect_company"] = imported.get("company", "")
        st.session_state["prospect_role"] = imported.get("job_title", "")
        st.session_state["prospect_location"] = imported.get("location", "")
        st.session_state["prospect_salary"] = imported.get("salary_range", "")
        st.session_state["prospect_source"] = imported.get("source", "Official career page")
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
        "source": st.session_state["prospect_source"],
        "priority": st.session_state["prospect_priority"],
        "status": st.session_state["prospect_status"],
        "work_arrangement": st.session_state["prospect_work_arrangement"],
        "job_description": st.session_state["prospect_description"],
        "notes": st.session_state["prospect_notes"],
        "next_action": st.session_state["prospect_next_action"],
    }
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
    _show_output_paths(st, st.session_state["last_package_outputs"], "intake_output")


def _load_applications(st: Any) -> list[Dict[str, Any]]:
    try:
        return load_application_tracker(PROJECT_ROOT)
    except TrackerValidationError as error:
        st.error(str(error))
        return []


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
    if st.button("Generate Package", type="primary"):
        try:
            with st.spinner("Generating resumes, messages, strategy pack, and dashboard…"):
                result = generate_package(tracker_id, PROJECT_ROOT)
        except PackageGenerationError as error:
            st.error(str(error))
        else:
            st.success(
                f"Generated {result['job_title']} at {result['company']} — status: {result['status']}."
            )
            st.metric("Match score", result.get("match_score") or "—")
            st.session_state["last_package_outputs"] = result["outputs"]
    outputs = st.session_state.get("last_package_outputs")
    if outputs:
        _show_output_paths(st, outputs, "generated_output")


def _render_update_status(st: Any) -> None:
    st.markdown(
        '<h2 class="cc-section-heading">Update Status</h2>',
        unsafe_allow_html=True,
    )
    applications = _load_applications(st)
    if not applications:
        return
    by_id = {str(item["id"]): item for item in applications}
    tracker_id = st.selectbox(
        "Tracker entry",
        tuple(by_id),
        format_func=lambda value: _application_label(by_id[value]),
        key="status_tracker_id",
    )
    application = by_id[tracker_id]
    widget_prefix = f"status_{tracker_id}"
    status = st.selectbox(
        "Application status",
        VALID_STATUSES,
        index=VALID_STATUSES.index(str(application.get("status") or "Drafted")),
        key=f"{widget_prefix}_value",
    )
    priority_options = ("High", "Medium", "Low", "Do Not Pursue")
    current_priority = str(application.get("priority") or "Medium")
    priority = st.selectbox(
        "Priority",
        priority_options,
        index=priority_options.index(current_priority) if current_priority in priority_options else 1,
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
    _render_application_tracker(st, applications, packages)


def _render_recent_outputs(st: Any) -> None:
    st.markdown(
        '<h2 class="cc-section-heading">Recent Outputs</h2>',
        unsafe_allow_html=True,
    )
    dashboard_path = PROJECT_ROOT / "exports" / "dashboard" / "index.html"
    with st.container(border=True):
        st.markdown("**Quick access**")
        dashboard_column, docx_column, messages_column, strategy_column = st.columns(4)
        quick_links = (
            (dashboard_column, "Dashboard", dashboard_path),
            (docx_column, "DOCX resumes", PROJECT_ROOT / "exports" / "docx"),
            (messages_column, "Messages", PROJECT_ROOT / "exports" / "messages"),
            (
                strategy_column,
                "Strategy packs",
                PROJECT_ROOT / "exports" / "strategy_packs",
            ),
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
    dashboard_tab, add_tab, generate_tab, status_tab, outputs_tab = st.tabs(
        (
            "Dashboard",
            "Add Prospect",
            "Generate Package",
            "Update Status",
            "Outputs",
        )
    )
    with dashboard_tab:
        _render_dashboard(st)
    with add_tab:
        _render_add_prospect(st)
    with generate_tab:
        _render_generate_package(st)
    with status_tab:
        _render_update_status(st)
    with outputs_tab:
        _render_recent_outputs(st)


if __name__ == "__main__":
    main()
