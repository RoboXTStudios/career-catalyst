"""Command line helpers for Career Catalyst."""

import argparse
import sys
from pathlib import Path
from typing import Any, List, Optional

if __package__:
    from .export_docx import (
        ATS_MODE,
        STYLED_MODE,
        SUPPORTED_MODES,
        DocxExportError,
        export_ats_docx,
        export_styled_docx,
    )
    from .load_data import (
        DataLoadError,
        REQUIRED_YAML_FILES,
        load_all_yaml,
        load_yaml_file,
    )
    from .parse_job import JobParseError, parse_job_description
    from .score_match import score_job_match
    from .tailor_resume import ResumeTailoringError, tailor_resume
else:
    from export_docx import (
        ATS_MODE,
        STYLED_MODE,
        SUPPORTED_MODES,
        DocxExportError,
        export_ats_docx,
        export_styled_docx,
    )
    from load_data import (
        DataLoadError,
        REQUIRED_YAML_FILES,
        load_all_yaml,
        load_yaml_file,
    )
    from parse_job import JobParseError, parse_job_description
    from score_match import score_job_match
    from tailor_resume import ResumeTailoringError, tailor_resume


PROJECT_ROOT = Path.cwd()


def _print_list(title: str, values: List[str]) -> None:
    print(f"{title}:")
    for value in values:
        print(f"- {value}")


def validate_data() -> int:
    try:
        load_all_yaml(PROJECT_ROOT)
    except DataLoadError as error:
        print(f"Data validation failed: {error}", file=sys.stderr)
        return 1

    print("Data validation succeeded.")
    _print_list("Loaded files", list(REQUIRED_YAML_FILES))
    return 0


def _candidate_name(profile: dict[str, Any]) -> str:
    candidate = profile.get("candidate", {})
    if isinstance(candidate, dict):
        return str(candidate.get("name", "Unknown"))
    return "Unknown"


def _positioning(profile: dict[str, Any]) -> str:
    candidate = profile.get("candidate", {})
    if isinstance(candidate, dict) and candidate.get("headline"):
        return str(candidate["headline"])
    return "Not available"


def _target_industries(profile: dict[str, Any]) -> List[str]:
    industries = profile.get("target_industries", [])
    if not isinstance(industries, list):
        return []
    return [str(industry) for industry in industries]


def _target_roles(profile: dict[str, Any], roles_config: dict[str, Any]) -> List[str]:
    profile_roles = profile.get("target_roles")
    if isinstance(profile_roles, list):
        return [str(role) for role in profile_roles]

    role_profiles = roles_config.get("role_profiles", [])
    if not isinstance(role_profiles, list):
        return []

    roles = []
    for role_profile in role_profiles:
        if isinstance(role_profile, dict) and role_profile.get("title"):
            roles.append(str(role_profile["title"]))
    return roles


def show_profile() -> int:
    try:
        profile = load_yaml_file("data/personal_brand.yml", PROJECT_ROOT)
        roles_config = load_yaml_file("config/role_profiles.yml", PROJECT_ROOT)
    except DataLoadError as error:
        print(f"Could not show profile: {error}", file=sys.stderr)
        return 1

    print(f"Candidate: {_candidate_name(profile)}")
    print(f"Positioning: {_positioning(profile)}")

    industries = _target_industries(profile)
    if industries:
        _print_list("Target industries", industries)
    else:
        print("Target industries: Not available")

    roles = _target_roles(profile, roles_config)
    if roles:
        _print_list("Target roles", roles)
    else:
        print("Target roles: Not available")

    return 0


def parse_job(file_path: str) -> int:
    try:
        parsed = parse_job_description(PROJECT_ROOT / file_path)
    except JobParseError as error:
        print(f"Could not parse job description: {error}", file=sys.stderr)
        return 1

    print(f"Job title: {parsed.get('job_title') or 'Not found'}")
    print(f"Company: {parsed.get('company') or 'Not found'}")
    print(f"Location: {parsed.get('location') or 'Not found'}")
    print(f"Salary range: {parsed.get('salary_range') or 'Not found'}")
    print(f"Employment type: {parsed.get('employment_type') or 'Not found'}")

    keywords = parsed.get("keywords", [])
    if keywords:
        _print_list("Top keywords", keywords)
    else:
        print("Top keywords: None found")

    print(f"Responsibilities count: {len(parsed.get('responsibilities', []))}")
    print(f"Qualifications count: {len(parsed.get('qualifications', []))}")
    print(f"Summary: {parsed.get('summary')}")
    return 0


def score_job(file_path: str) -> int:
    try:
        report = score_job_match(file_path, PROJECT_ROOT)
    except (DataLoadError, JobParseError) as error:
        print(f"Could not score job description: {error}", file=sys.stderr)
        return 1

    print(f"Job title: {report.get('job_title') or 'Not found'}")
    print(f"Company: {report.get('company') or 'Not found'}")
    print(f"Location: {report.get('location') or 'Not found'}")
    print(f"Salary range: {report.get('salary_range') or 'Not found'}")
    print(f"Match score: {report.get('match_score')}")
    print(f"Match band: {report.get('match_band')}")
    print(f"Recommended resume profile: {report.get('recommended_resume_profile')}")

    top_skills = report.get("top_matching_skills", [])
    if top_skills:
        _print_list("Top matching skills", top_skills)
    else:
        print("Top matching skills: None found")

    top_projects = report.get("top_matching_projects", [])
    if top_projects:
        print("Top matching projects:")
        for project in top_projects:
            matched_keywords = ", ".join(project.get("matched_keywords", []))
            print(f"- {project.get('name')} ({matched_keywords})")
    else:
        print("Top matching projects: None found")

    missing_keywords = report.get("missing_keywords", [])
    if missing_keywords:
        _print_list("Missing keywords", missing_keywords)
    else:
        print("Missing keywords: None found")

    tailoring_notes = report.get("tailoring_notes", [])
    if tailoring_notes:
        _print_list("Tailoring notes", tailoring_notes)
    else:
        print("Tailoring notes: None")

    return 0


def tailor_resume_command(resume_profile: str, file_path: str) -> int:
    try:
        result = tailor_resume(resume_profile, file_path, PROJECT_ROOT)
    except (DataLoadError, JobParseError, ResumeTailoringError, OSError) as error:
        print(f"Could not tailor resume: {error}", file=sys.stderr)
        return 1

    print(f"Job title: {result.get('job_title') or 'Not found'}")
    print(f"Company: {result.get('company') or 'Not found'}")
    print(f"Recommended resume profile: {result.get('recommended_resume_profile')}")
    print(f"Match score: {result.get('match_score')}")
    print(f"Output path: {result.get('output_path')}")

    notes = result.get("tailoring_notes", [])
    if notes:
        _print_list("Top tailoring notes", notes[:3])
    else:
        print("Top tailoring notes: None")

    return 0


def export_docx_command(mode_or_file: str, file_path: Optional[str] = None) -> int:
    if file_path is None:
        mode = STYLED_MODE
        markdown_path = mode_or_file
    else:
        mode = mode_or_file.lower()
        markdown_path = file_path

    if mode not in SUPPORTED_MODES:
        print(
            f"Could not export DOCX: export mode must be '{STYLED_MODE}' or '{ATS_MODE}'.",
            file=sys.stderr,
        )
        return 2

    try:
        exporter = export_styled_docx if mode == STYLED_MODE else export_ats_docx
        result = exporter(markdown_path, PROJECT_ROOT)
    except (DocxExportError, OSError) as error:
        print(f"Could not export DOCX: {error}", file=sys.stderr)
        return 1

    print(f"Export mode: {mode}")
    print(f"Source Markdown path: {result.get('source_path')}")
    print(f"Output DOCX path: {result.get('output_path')}")
    print("DOCX export succeeded.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Career Catalyst CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate-data", help="Validate required YAML files")
    subparsers.add_parser("show-profile", help="Show candidate profile summary")
    parse_job_parser = subparsers.add_parser("parse-job", help="Parse a local job description file")
    parse_job_parser.add_argument("file_path", help="Path to a local Markdown or text job description")
    score_parser = subparsers.add_parser("score", help="Score a local job description against career data")
    score_parser.add_argument("file_path", help="Path to a local Markdown or text job description")
    tailor_parser = subparsers.add_parser("tailor", help="Generate a tailored Markdown resume")
    tailor_parser.add_argument("resume_profile", help="Resume profile to use")
    tailor_parser.add_argument("file_path", help="Path to a local Markdown or text job description")
    export_docx_parser = subparsers.add_parser("export-docx", help="Export a Markdown resume to DOCX")
    export_docx_parser.add_argument(
        "mode_or_file",
        help="Export mode (styled or ats), or a Markdown path for the default styled mode",
    )
    export_docx_parser.add_argument(
        "file_path",
        nargs="?",
        help="Path to a tailored Markdown resume when an export mode is provided",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "validate-data":
        return validate_data()
    if args.command == "show-profile":
        return show_profile()
    if args.command == "parse-job":
        return parse_job(args.file_path)
    if args.command == "score":
        return score_job(args.file_path)
    if args.command == "tailor":
        return tailor_resume_command(args.resume_profile, args.file_path)
    if args.command == "export-docx":
        return export_docx_command(args.mode_or_file, args.file_path)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
