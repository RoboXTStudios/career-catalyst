"""Generate a static local dashboard from Career Catalyst project files."""

import html
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union
from urllib.parse import quote

if __package__:
    from .filename_utils import short_company_name, short_role_name
    from .load_data import DataLoadError, load_yaml_file
    from .parse_job import JobParseError, parse_job_description
else:
    from filename_utils import short_company_name, short_role_name
    from load_data import DataLoadError, load_yaml_file
    from parse_job import JobParseError, parse_job_description


PathInput = Union[str, Path]
TRACKER_PATH = "data/application_tracker.yml"
ASSET_DIRECTORIES = (
    "exports/markdown",
    "exports/docx",
    "exports/messages",
    "exports/strategy_packs",
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
)


class DashboardGenerationError(Exception):
    """Raised when a dashboard cannot be generated from local project files."""


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


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

        packages.append(
            {
                "company": str(company or "Company not listed"),
                "role": str(role or "Role not listed"),
                "location": parsed.get("location"),
                "salary_range": parsed.get("salary_range"),
                "job_path": path,
                "tracker": {},
                "files": {"Job Description": path},
            }
        )
    return packages


def _load_tracker(root: Path) -> List[Dict[str, Any]]:
    tracker_file = root / TRACKER_PATH
    if not tracker_file.is_file():
        return []

    loaded = load_yaml_file(TRACKER_PATH, root)
    applications = loaded.get("applications", [])
    if not isinstance(applications, list):
        raise DashboardGenerationError(
            f"Tracker file must contain an applications list: {TRACKER_PATH}"
        )
    return [item for item in applications if isinstance(item, dict)]


def _matching_package(
    packages: List[Dict[str, Any]], company: str, role: str
) -> Optional[Dict[str, Any]]:
    company_key = _slug(company)
    role_key = _slug(role)
    for package in packages:
        if _slug(package["company"]) == company_key and _slug(package["role"]) == role_key:
            return package
    return None


def _merge_tracker(packages: List[Dict[str, Any]], tracker: List[Dict[str, Any]]) -> None:
    for application in tracker:
        company = str(application.get("company") or "Company not listed")
        role = str(application.get("role") or "Role not listed")
        package = _matching_package(packages, company, role)
        if package is None:
            package = {
                "company": company,
                "role": role,
                "location": application.get("location"),
                "salary_range": application.get("salary_range"),
                "job_path": None,
                "tracker": {},
                "files": {},
            }
            packages.append(package)
        package["tracker"] = application


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
        "drafted",
        "follow_up",
        "interviewing",
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
    values = (
        ("Location", package.get("location")),
        ("Salary", package.get("salary_range")),
        ("Source", package.get("tracker", {}).get("source")),
    )
    items = [
        f'<div class="meta-item"><dt>{label}</dt><dd>{html.escape(str(value))}</dd></div>'
        for label, value in values
        if value
    ]
    if not items:
        return ""
    return f'<dl class="metadata">{"".join(items)}</dl>'


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


def _summary_counts(root: Path) -> Dict[str, int]:
    return {
        "Total job files": len(
            [
                path
                for path in _scan_files(root, "jobs", (".md", ".txt"))
                if path.name.lower() != "readme.md"
            ]
        ),
        "Total resumes generated": len(
            _scan_files(root, "exports/markdown", (".md",))
        ),
        "Total DOCX files": len(_scan_files(root, "exports/docx", (".docx",))),
        "Total messages generated": len(
            _scan_files(root, "exports/messages", (".md",))
        ),
        "Total strategy packs generated": len(
            _scan_files(root, "exports/strategy_packs", (".md",))
        ),
    }


def _render_html(
    packages: List[Dict[str, Any]],
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
    package_cards = "".join(
        _render_package(package, dashboard_directory) for package in packages
    )
    if not package_cards:
        package_cards = '<p class="empty-state">No application packages found.</p>'

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
    .priority {{ border: 1px solid #e1c891; background: #ffffff; color: var(--gold); }}
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
        <span class="section-count">{len(packages)} tracked roles</span>
      </div>
      <div class="application-list">{package_cards}</div>
    </section>
    {_render_unassigned(unassigned, dashboard_directory)}
  </main>
</body>
</html>
"""


def generate_dashboard(project_root: PathInput = Path.cwd()) -> Dict[str, Any]:
    """Build the local static dashboard and return generation details."""
    root = Path(project_root).resolve()
    dashboard_directory = root / "exports" / "dashboard"
    output_path = dashboard_directory / "index.html"

    try:
        packages = _load_jobs(root)
        tracker = _load_tracker(root)
        _merge_tracker(packages, tracker)
        unassigned = _attach_assets(root, packages)
        counts = _summary_counts(root)
        packages.sort(
            key=lambda item: (
                0 if item.get("tracker") else 1,
                _slug(item["company"]),
                _slug(item["role"]),
            )
        )
        dashboard_directory.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            _render_html(packages, counts, unassigned, dashboard_directory),
            encoding="utf-8",
        )
    except (DataLoadError, JobParseError, OSError) as error:
        raise DashboardGenerationError(f"Could not generate dashboard: {error}") from error

    return {
        "output_path": str(output_path),
        "relative_output_path": output_path.relative_to(root).as_posix(),
        "application_count": len(packages),
        "summary": counts,
    }
