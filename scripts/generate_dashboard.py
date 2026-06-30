"""Generate a static local dashboard from Career Catalyst project files."""

import html
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
from urllib.parse import quote

if __package__:
    from .application_tracker import (
        ACTIVE_STATUSES,
        DRAFT_STATUSES,
        HIDDEN_STATUSES,
        TrackerValidationError,
        normalize_tracker_value,
        tracker_company_keys,
        tracker_role_keys,
        validate_application_tracker,
    )
    from .dynamic_role_intelligence import get_effective_voice_profile
    from .job_freshness import detect_job_freshness
    from .filename_utils import short_company_name, short_role_name
    from .parse_job import JobParseError, parse_job_description
else:
    from application_tracker import (
        ACTIVE_STATUSES,
        DRAFT_STATUSES,
        HIDDEN_STATUSES,
        TrackerValidationError,
        normalize_tracker_value,
        tracker_company_keys,
        tracker_role_keys,
        validate_application_tracker,
    )
    from dynamic_role_intelligence import get_effective_voice_profile
    from job_freshness import detect_job_freshness
    from filename_utils import short_company_name, short_role_name
    from parse_job import JobParseError, parse_job_description


PathInput = Union[str, Path]
ASSET_DIRECTORIES = (
    "exports/markdown",
    "exports/docx",
    "exports/messages",
    "exports/strategy_packs",
    "exports/followups",
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
)


class DashboardGenerationError(Exception):
    """Raised when a dashboard cannot be generated from local project files."""


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _display_taxonomy(value: Any) -> str:
    label = str(value or "").replace("_", " ").title()
    return label.replace("Ai ", "AI ").replace("Gtm ", "GTM ")


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
    return None


def _package_for_asset(
    path: Path, packages: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    file_key = _slug(path.stem)
    candidates = [
        package
        for package in packages
        if any(
            key in file_key
            for key in (
                _slug(package["company"]),
                _slug(short_company_name(package["company"])),
            )
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
                _slug(package["role"]),
                _slug(short_role_name(package["role"])),
            )
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
    unassigned: List[Tuple[str, Path]] = []
    for relative_directory in ASSET_DIRECTORIES:
        for path in _scan_files(root, relative_directory, (".md", ".docx")):
            label = _asset_label(path)
            if label is None:
                continue
            package = _package_for_asset(path, packages)
            if package is None:
                unassigned.append((label, path))
                continue
            existing_path = package["files"].get(label)
            if existing_path is None or (
                path.name.startswith("TrishaLynch_")
                and not existing_path.name.startswith("TrishaLynch_")
            ):
                package["files"][label] = path
    return unassigned


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
        "paused",
        "rejected",
        "reviewed",
    }
    normalized = _slug(status)
    return normalized if normalized in known_statuses else "default"


def _render_badges(tracker: Dict[str, Any]) -> str:
    badges = []
    status = str(tracker.get("status") or "").strip()
    priority = str(tracker.get("priority") or "").strip()
    if status:
        badges.append(
            f'<span class="badge status-{_status_class(status)}">{html.escape(status)}</span>'
        )
    if priority:
        badges.append(f'<span class="badge priority">{html.escape(priority)} priority</span>')
    return "".join(badges)


def _render_metadata(package: Dict[str, Any]) -> str:
    tracker = package.get("tracker", {})
    values = (
        ("Location", package.get("location")),
        ("Salary", tracker.get("salary_range") or package.get("salary_range")),
        ("Freshness", tracker.get("freshness_label") or tracker.get("freshness") or package.get("freshness", {}).get("label")),
        ("Opportunity score", f"{tracker.get('opportunity_score')}/100" if tracker.get("opportunity_score") is not None else None),
        ("Recommendation", tracker.get("apply_recommendation")),
        ("Source", tracker.get("source")),
        ("Submitted", tracker.get("submitted_date")),
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
    items = [
        f'<div class="meta-item"><dt>{label}</dt><dd>{html.escape(str(value))}</dd></div>'
        for label, value in values
        if value
    ]
    if not items:
        return ""
    return f'<dl class="metadata">{"".join(items)}</dl>'


def _render_match_score(tracker: Dict[str, Any]) -> str:
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
        '<div class="match-details">'
        f'{render_list("Top strengths", strengths)}'
        f'{render_list("Gaps / cautions", gaps)}'
        '</div></section>'
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
        f"{_render_match_score(tracker)}"
        f"{_render_metadata(package)}"
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
        "draft": [],
        "hidden": [],
    }
    for package in packages:
        tracker = package.get("tracker", {})
        status = str(tracker.get("status") or "Drafted")
        if tracker and (
            tracker.get("show_on_dashboard") is False or status in HIDDEN_STATUSES
        ):
            groups["hidden"].append(package)
        elif status in ACTIVE_STATUSES:
            groups["active"].append(package)
        elif status in DRAFT_STATUSES or not tracker:
            groups["draft"].append(package)
        else:
            groups["hidden"].append(package)
    return groups


def _summary_counts(
    root: Path,
    groups: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, int]:
    applied_count = sum(
        1
        for package in groups["active"]
        if package.get("tracker", {}).get("status") == "Applied"
    )
    return {
        "Total job files": len(
            [
                path
                for path in _scan_files(root, "jobs", (".md", ".txt"))
                if path.name.lower() != "readme.md"
            ]
        ),
        "Active applications": len(groups["active"]),
        "Applied applications": applied_count,
        "Draft or paused roles": len(groups["draft"]),
        "Hidden/invalid roles": len(groups["hidden"]),
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
        "Active / Applied",
        "active-applied",
        groups["active"],
        dashboard_directory,
    )
    draft_group = _render_group(
        "Draft / Paused",
        "draft-paused",
        groups["draft"],
        dashboard_directory,
    )
    hidden_group = _render_hidden_group(groups["hidden"], dashboard_directory)
    visible_count = len(groups["active"]) + len(groups["draft"])

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
      grid-template-columns: repeat(5, minmax(0, 1fr));
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
    .status-applied, .status-follow_up {{ background: var(--blue-soft); color: var(--blue); }}
    .status-interviewing {{ background: var(--accent-soft); color: var(--accent); }}
    .status-rejected {{ background: var(--red-soft); color: var(--red); }}
    .status-paused {{ background: #eef1f3; color: #4c5963; }}
    .status-invalid {{ background: var(--red-soft); color: var(--red); }}
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
    <section class="packages" aria-labelledby="packages-heading">
      <div class="section-heading">
        <h2 id="packages-heading">Application Packages</h2>
        <span class="section-count">{visible_count} visible roles</span>
      </div>
      {active_group}
      {draft_group}
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
