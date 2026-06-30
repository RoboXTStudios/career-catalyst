"""Command line helpers for Career Catalyst."""

import argparse
import sys
from pathlib import Path
from typing import Any, List, Optional

if __package__:
    from .application_tracker import (
        TrackerValidationError,
        TrackerUpdateError,
        hide_role,
        update_status,
        validate_application_tracker,
    )
    from .generate_dashboard import DashboardGenerationError, generate_dashboard
    from .generate_application_note import generate_application_note
    from .generate_cover_letter import ApplicationMaterialError, generate_cover_letter
    from .dynamic_role_intelligence import get_effective_voice_profile
    from .generate_followups import (
        FollowupGenerationError,
        generate_followups,
        generate_missing_followups,
    )
    from .generate_messages import generate_message
    from .generate_strategy_pack import StrategyPackError, generate_strategy_pack
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
    from .package_generator import (
        PackageGenerationError,
        generate_package,
        resolve_job_reference,
    )
    from .prospect_intake import ProspectIntakeError, add_prospect_from_job_file
    from .score_match import score_job_match
    from .tailor_resume import ResumeTailoringError, tailor_resume
else:
    from application_tracker import (
        TrackerUpdateError,
        TrackerValidationError,
        hide_role,
        update_status,
        validate_application_tracker,
    )
    from generate_dashboard import DashboardGenerationError, generate_dashboard
    from generate_application_note import generate_application_note
    from generate_cover_letter import ApplicationMaterialError, generate_cover_letter
    from dynamic_role_intelligence import get_effective_voice_profile
    from generate_followups import (
        FollowupGenerationError,
        generate_followups,
        generate_missing_followups,
    )
    from generate_messages import generate_message
    from generate_strategy_pack import StrategyPackError, generate_strategy_pack
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
    from package_generator import (
        PackageGenerationError,
        generate_package,
        resolve_job_reference,
    )
    from prospect_intake import ProspectIntakeError, add_prospect_from_job_file
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


def _print_material_result(result: dict[str, Any], success_message: str) -> None:
    print(f"Job title: {result.get('job_title') or 'Not found'}")
    print(f"Company: {result.get('company') or 'Not found'}")
    print(f"Match score: {result.get('match_score')}")
    print(f"Output file path: {result.get('output_path')}")
    if result.get("txt_output_path"):
        print(f"Plain text output path: {result.get('txt_output_path')}")
    print(success_message)


def cover_letter_command(file_path: str) -> int:
    try:
        result = generate_cover_letter(file_path, PROJECT_ROOT)
    except (DataLoadError, JobParseError, ApplicationMaterialError, OSError) as error:
        print(f"Could not generate cover letter: {error}", file=sys.stderr)
        return 1

    _print_material_result(result, "Cover letter generated successfully.")
    return 0


def message_command(message_type: str, file_path: str) -> int:
    try:
        result = generate_message(message_type, file_path, PROJECT_ROOT)
    except (DataLoadError, JobParseError, ApplicationMaterialError, OSError) as error:
        print(f"Could not generate message: {error}", file=sys.stderr)
        return 1

    label = "Recruiter" if message_type == "recruiter" else "Hiring manager"
    _print_material_result(result, f"{label} message generated successfully.")
    return 0


def application_note_command(file_path: str) -> int:
    try:
        result = generate_application_note(file_path, PROJECT_ROOT)
    except (DataLoadError, JobParseError, ApplicationMaterialError, OSError) as error:
        print(f"Could not generate application note: {error}", file=sys.stderr)
        return 1

    _print_material_result(result, "Application note generated successfully.")
    return 0


def strategy_pack_command(file_path: str) -> int:
    try:
        result = generate_strategy_pack(file_path, PROJECT_ROOT)
    except (DataLoadError, JobParseError, StrategyPackError, OSError) as error:
        print(f"Could not generate strategy pack: {error}", file=sys.stderr)
        return 1

    print(f"Job title: {result.get('job_title') or 'Not found'}")
    print(f"Company: {result.get('company') or 'Not found'}")
    print(f"Match score: {result.get('match_score')}")
    print(f"Match band: {result.get('match_band')}")
    print(f"Output file path: {result.get('output_path')}")
    print("Strategy pack generated successfully.")
    return 0


def dashboard_command() -> int:
    try:
        result = generate_dashboard(PROJECT_ROOT)
    except DashboardGenerationError as error:
        print(f"Could not create dashboard: {error}", file=sys.stderr)
        return 1

    print("Dashboard created")
    print(f"Output path: {result.get('output_path')}")
    print(f"Open: open {result.get('relative_output_path')}")
    return 0


def validate_tracker_command() -> int:
    try:
        report = validate_application_tracker(PROJECT_ROOT)
    except TrackerValidationError as error:
        print(f"Tracker validation failed: {error}", file=sys.stderr)
        return 1

    print("Application tracker validation succeeded.")
    print(f"Applications: {len(report['applications'])}")
    print("Status counts:")
    for status, count in report["status_counts"].items():
        print(f"- {status}: {count}")
    for warning in report["warnings"]:
        print(f"Warning: {warning}")
    return 0


def add_prospect_command(file_path: str) -> int:
    try:
        result = add_prospect_from_job_file(file_path, PROJECT_ROOT)
        generate_dashboard(PROJECT_ROOT)
    except (ProspectIntakeError, TrackerValidationError, DashboardGenerationError) as error:
        print(f"Could not add prospect: {error}", file=sys.stderr)
        return 1

    action = "created" if result["tracker_created"] else "updated"
    print(f"Prospect {action}: {result['tracker_id']}")
    print(f"Job file: {result['job_file_path']}")
    return 0


def generate_package_command(
    job_file_or_tracker_id: str,
    generate_followups_too: Optional[bool] = None,
    override_closed: bool = False,
) -> int:
    try:
        result = generate_package(
            job_file_or_tracker_id,
            PROJECT_ROOT,
            generate_followups_too=generate_followups_too,
            override_closed=override_closed,
        )
    except PackageGenerationError as error:
        print(str(error), file=sys.stderr)
        return 1

    print(f"Package generated: {result['tracker_id']}")
    print(f"Status: {result['status']}")
    print(f"Match score: {result.get('match_score')}")
    print(f"Opportunity score: {result['opportunity']['overall_score']}")
    print(f"Recommendation: {result['opportunity']['apply_recommendation']}")
    print(f"Freshness: {result['freshness']['label']}")
    quality = result["package_quality"]
    print(
        "Package quality: "
        f"resume {quality['resume_tailoring_score']}, cover letter {quality['cover_letter_score']}, "
        f"ATS {quality['ats_keyword_match']}, voice {quality['voice_match']}, "
        f"confidence {quality['confidence_level']}"
    )
    for label, path in result["outputs"].items():
        print(f"{label}: {path}")
    return 0


def detect_role_command(job_file_or_tracker_id: str) -> int:
    try:
        candidate = Path(job_file_or_tracker_id)
        resolved_path = candidate if candidate.is_absolute() else PROJECT_ROOT / candidate
        if resolved_path.is_file():
            job_path = resolved_path
        else:
            resolved = resolve_job_reference(job_file_or_tracker_id, PROJECT_ROOT)
            job_path = Path(resolved["job_path"])
        parsed = parse_job_description(job_path)
        intelligence = get_effective_voice_profile(
            company_name=str(parsed.get("company") or ""),
            job_title=str(parsed.get("job_title") or ""),
            job_description=str(parsed.get("raw_text") or ""),
            source_url=str(parsed.get("source_url") or ""),
        )
    except (JobParseError, PackageGenerationError, DataLoadError) as error:
        print(f"Could not detect role: {error}", file=sys.stderr)
        return 1

    print(f"Company: {parsed.get('company') or 'Not found'}")
    print(f"Role: {parsed.get('job_title') or 'Not found'}")
    print(f"Company category: {intelligence['company_category']}")
    print(f"Role family: {intelligence['role_family']}")
    print(f"Voice profile: {intelligence['profile_name']}")
    print(f"Source: {intelligence['source']}")
    print(f"Confidence: {intelligence['confidence']}")
    print(f"Reasoning summary: {intelligence['reasoning_summary']}")
    return 0


def followups_command(tracker_id: str) -> int:
    try:
        result = generate_followups(tracker_id, PROJECT_ROOT)
    except FollowupGenerationError as error:
        print(f"Could not generate follow-ups: {error}", file=sys.stderr)
        return 1

    print(f"Company: {result['company']}")
    print(f"Role: {result['role']}")
    print(f"Status: {result['status']}")
    print("Generated follow-up files:")
    for label, path in result["outputs"].items():
        print(f"- {label}: {path}")
    print("Follow-up materials generated successfully.")
    return 0


def followups_all_command(force: bool = False) -> int:
    result = generate_missing_followups(PROJECT_ROOT, force=force)
    print(f"Generated: {result['generated_count']}")
    print(f"Skipped existing: {result['skipped_existing_count']}")
    print(f"Failed: {result['failed_count']}")
    for tracker_id, error in result["failed"].items():
        print(f"- {tracker_id}: {error}", file=sys.stderr)
    return 1 if result["failed_count"] else 0


def update_status_command(tracker_id: str, status: str) -> int:
    try:
        application = update_status(tracker_id, status, PROJECT_ROOT)
        generate_dashboard(PROJECT_ROOT)
    except (TrackerUpdateError, TrackerValidationError, DashboardGenerationError) as error:
        print(f"Could not update status: {error}", file=sys.stderr)
        return 1

    print(f"Updated {tracker_id} to {application['status']}.")
    if application.get("submitted_date"):
        print(f"Submitted date: {application['submitted_date']}")
    return 0


def hide_role_command(tracker_id: str, reason: str) -> int:
    try:
        application = hide_role(tracker_id, reason, PROJECT_ROOT)
        generate_dashboard(PROJECT_ROOT)
    except (TrackerUpdateError, TrackerValidationError, DashboardGenerationError) as error:
        print(f"Could not hide role: {error}", file=sys.stderr)
        return 1

    print(f"Hidden {tracker_id} with status {application['status']}.")
    return 0


def launcher_info_command() -> int:
    launcher_path = PROJECT_ROOT / "launchers" / "Open_Career_Catalyst.command"
    print("Career Catalyst macOS launcher")
    print(f"Launcher path: {launcher_path}")
    print("First time only: chmod +x launchers/Open_Career_Catalyst.command")
    print("Launch: Double-click Open_Career_Catalyst.command in Finder.")
    print("Stop: Close the Terminal window or press Control+C.")
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
    cover_letter_parser = subparsers.add_parser(
        "cover-letter",
        help="Generate a grounded cover letter",
    )
    cover_letter_parser.add_argument("file_path", help="Path to a local job description")
    message_parser = subparsers.add_parser(
        "message",
        help="Generate a recruiter or hiring manager message",
    )
    message_parser.add_argument("message_type", choices=("recruiter", "hiring-manager"))
    message_parser.add_argument("file_path", help="Path to a local job description")
    application_note_parser = subparsers.add_parser(
        "application-note",
        help="Generate a short application portal note",
    )
    application_note_parser.add_argument("file_path", help="Path to a local job description")
    strategy_pack_parser = subparsers.add_parser(
        "strategy-pack",
        help="Generate a grounded Standout Strategy Pack",
    )
    strategy_pack_parser.add_argument("file_path", help="Path to a local job description")
    subparsers.add_parser("dashboard", help="Generate the local static dashboard")
    subparsers.add_parser("validate-tracker", help="Validate application tracker data")
    add_prospect_parser = subparsers.add_parser(
        "add-prospect", help="Add or update a tracker entry from a local job file"
    )
    add_prospect_parser.add_argument("job_file_path", help="Path to a local job description")
    package_parser = subparsers.add_parser(
        "generate-package", help="Generate every application material for a job"
    )
    package_parser.add_argument("job_file_or_tracker_id")
    package_parser.add_argument(
        "--followups",
        action="store_true",
        default=None,
        help="Generate follow-up materials after the package",
    )
    package_parser.add_argument(
        "--override-closed",
        action="store_true",
        help="Generate only after manually verifying a closed-signal posting is still open",
    )
    detect_parser = subparsers.add_parser(
        "detect-role", help="Detect company category, role family, and voice guidance"
    )
    detect_parser.add_argument("job_file_or_tracker_id")
    followups_parser = subparsers.add_parser(
        "followups", help="Generate follow-up materials for a submitted application"
    )
    followups_parser.add_argument("tracker_id")
    followups_all_parser = subparsers.add_parser(
        "followups-all", help="Generate missing follow-ups for all visible Applied roles"
    )
    followups_all_parser.add_argument("--force", action="store_true")
    status_parser = subparsers.add_parser(
        "update-status", help="Update a tracker entry and refresh the dashboard"
    )
    status_parser.add_argument("tracker_id")
    status_parser.add_argument("status")
    hide_parser = subparsers.add_parser(
        "hide-role", help="Mark a tracker entry Invalid and hide it from the active dashboard"
    )
    hide_parser.add_argument("tracker_id")
    hide_parser.add_argument("reason", nargs="+")
    subparsers.add_parser(
        "launcher-info", help="Show how to open Career Catalyst with the macOS launcher"
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
    if args.command == "cover-letter":
        return cover_letter_command(args.file_path)
    if args.command == "message":
        return message_command(args.message_type, args.file_path)
    if args.command == "application-note":
        return application_note_command(args.file_path)
    if args.command == "strategy-pack":
        return strategy_pack_command(args.file_path)
    if args.command == "dashboard":
        return dashboard_command()
    if args.command == "validate-tracker":
        return validate_tracker_command()
    if args.command == "add-prospect":
        return add_prospect_command(args.job_file_path)
    if args.command == "generate-package":
        return generate_package_command(
            args.job_file_or_tracker_id, args.followups, args.override_closed
        )
    if args.command == "detect-role":
        return detect_role_command(args.job_file_or_tracker_id)
    if args.command == "followups":
        return followups_command(args.tracker_id)
    if args.command == "followups-all":
        return followups_all_command(args.force)
    if args.command == "update-status":
        return update_status_command(args.tracker_id, args.status)
    if args.command == "hide-role":
        return hide_role_command(args.tracker_id, " ".join(args.reason))
    if args.command == "launcher-info":
        return launcher_info_command()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
