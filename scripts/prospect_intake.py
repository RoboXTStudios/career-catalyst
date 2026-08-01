"""Create job files and tracker entries from local UI or CLI intake."""

from __future__ import annotations

import errno
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

try:
    from .application_tracker import add_prospect, make_tracker_id
    from .dynamic_role_intelligence import get_effective_voice_profile
    from .filename_utils import canonical_employer_name, is_valid_role_title, safe_filename
    from .job_identity import infer_job_fields_from_url, preferred_role_title
    from .job_importer import (
        MINIMUM_DESCRIPTION_LENGTH,
        JobImportError,
        create_job_markdown,
        import_job_from_url,
        validate_official_url,
    )
    from .job_freshness import detect_job_freshness
    from .job_source_registry import normalize_job_source
    from .parse_job import JobParseError, extract_metadata, normalize_compensation, parse_job_description
    from .score_match import persisted_match_fields, score_job_match
except ImportError:
    from application_tracker import add_prospect, make_tracker_id
    from dynamic_role_intelligence import get_effective_voice_profile
    from filename_utils import canonical_employer_name, is_valid_role_title, safe_filename
    from job_identity import infer_job_fields_from_url, preferred_role_title
    from job_importer import (
        MINIMUM_DESCRIPTION_LENGTH,
        JobImportError,
        create_job_markdown,
        import_job_from_url,
        validate_official_url,
    )
    from job_freshness import detect_job_freshness
    from job_source_registry import normalize_job_source
    from parse_job import JobParseError, extract_metadata, normalize_compensation, parse_job_description
    from score_match import persisted_match_fields, score_job_match


PathInput = Union[str, Path]
VERIFY_FIRST_SOURCE_TYPES = {
    "Industry Job Board",
    "Gaming Industry Job Board",
    "Music Industry Job Board",
    "Entertainment Job Board",
    "Startup / Tech Job Board",
    "Generic Aggregator",
    "Remote Job Aggregator",
    "Compensation-Focused Aggregator",
    "Gated Source",
    "Unknown Source",
}
REVIEW_FIRST_SOURCE_TYPES = {
    "Generic Aggregator",
    "Remote Job Aggregator",
    "Compensation-Focused Aggregator",
    "Gated Source",
    "Unknown Source",
}
VERIFY_FIRST_MESSAGE = "Verify on employer site before generating package or applying."


class ProspectIntakeError(Exception):
    """Raised when prospect intake is missing required local data."""


def _project_relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _job_filename(role: str, company: str, job_id: Any = "") -> str:
    if not company or not is_valid_role_title(role):
        raise ProspectIntakeError("A company and role title are required to name the job file.")
    stem = "_".join(
        str(value).strip() for value in (company, role, job_id) if str(value or "").strip()
    )
    try:
        return safe_filename(stem, "md", lowercase=True)
    except ValueError as error:
        raise ProspectIntakeError(
            "Career Catalyst prevented an unsafe filename. Confirm the title and try again."
        ) from error


def _infer_pasted_identity(description: str) -> tuple[str, str]:
    """Infer common title/company layouts when a pasted posting has no labels."""
    metadata = extract_metadata(description)
    role = str(metadata.get("job_title") or "").strip()
    company = str(metadata.get("company") or "").strip()
    if role and company:
        return company, role

    lines = [
        re.sub(r"^[#*\-\s]+", "", line).strip()
        for line in description.splitlines()
        if line.strip()
    ]
    if lines:
        at_match = re.match(r"^(.{3,100}?)\s+at\s+(.{2,80})$", lines[0], re.I)
        if at_match:
            role = role or at_match.group(1).strip()
            company = company or at_match.group(2).strip()
    title_signals = (
        "director", "manager", "lead", "head", "president", "officer",
        "strategist", "operations", "producer", "executive",
    )
    if not role and lines and len(lines[0]) <= 100 and any(
        signal in lines[0].lower() for signal in title_signals
    ):
        role = lines[0]
    if not company and role and len(lines) > 1:
        candidate = lines[1]
        if len(candidate) <= 80 and not re.search(r"[.!?]$|\b(?:about|description|responsibilities)\b", candidate, re.I):
            company = re.sub(r"^(?:company|organization)\s*:\s*", "", candidate, flags=re.I)
    return company, role


def _clean_identity(company: Any, role: Any) -> tuple[str, str]:
    clean_company = re.sub(r"\s+", " ", str(company or "").strip())
    clean_role = re.sub(r"\s+", " ", str(role or "").strip())
    at_match = re.match(r"^(.{3,120}?)\s+at\s+(.{2,100})$", clean_role, re.I)
    if at_match:
        if not clean_company:
            clean_company = at_match.group(2).strip()
        if clean_company.lower() == at_match.group(2).strip().lower():
            clean_role = at_match.group(1).strip()
    if clean_company:
        clean_role = re.sub(
            rf"\s*(?:[-|–—]\s*)?(?:at\s+)?{re.escape(clean_company)}\s*$",
            "",
            clean_role,
            flags=re.I,
        ).strip()
    clean_company = re.sub(r"\s*(?:jobs?|careers?|job\s+opening|hiring)\s*$", "", clean_company, flags=re.I).strip()
    return clean_company, clean_role


def _work_arrangement(location: Any = "", description: Any = "") -> str:
    combined = f"{location or ''}\n{description or ''}"
    if re.search(r"\bhybrid\b", combined, re.I):
        return "Hybrid"
    if re.search(r"\bremote\b|telecommute|#li-remote", combined, re.I):
        return "Remote"
    if re.search(r"\bon[-\s]?site\b|\bin[-\s]?office\b|#li-onsite", combined, re.I):
        return "On-site"
    if re.search(r"\bflexible\b", combined, re.I):
        return "Flexible"
    return "Not specified"


def _source_needs_verify_first(verification: Dict[str, Any]) -> bool:
    return (
        str(verification.get("source_type") or "") in VERIFY_FIRST_SOURCE_TYPES
        or str(verification.get("verification_status") or "") in {"Industry Board", "Aggregator Only", "Gated / Limited Visibility", "Cannot Verify", "Not Verified"}
    ) and str(verification.get("verification_status") or "") != "Employer Source"


def _merge_next_action(current: Any, verification: Dict[str, Any]) -> str:
    current_text = str(current or "").strip()
    if verification.get("freshness_risk") == "High" or verification.get("verification_status") == "Stale / Closed Risk":
        return "Verify role is still active before generating package."
    if _source_needs_verify_first(verification):
        if not current_text or current_text == "Review fit and generate application package.":
            return VERIFY_FIRST_MESSAGE
        if VERIFY_FIRST_MESSAGE.lower() not in current_text.lower():
            return f"{current_text} {VERIFY_FIRST_MESSAGE}"
    return current_text or str(verification.get("recommended_next_step") or "Review fit before generating package.")


def _source_adjusted_match_report(report: Dict[str, Any], verification: Dict[str, Any]) -> Dict[str, Any]:
    adjusted = dict(report or {})
    source_type = str(verification.get("source_type") or "")
    canonical_url = str(verification.get("canonical_apply_url") or "").strip()
    if (
        adjusted.get("recommended_action") == "Generate Package"
        and source_type in REVIEW_FIRST_SOURCE_TYPES
        and not canonical_url
    ):
        adjusted["recommended_action"] = "Review First"
        gaps = list(adjusted.get("match_gaps") or [])
        gaps.append("Source requires employer-site verification before investing in a full package.")
        adjusted["match_gaps"] = list(dict.fromkeys(gaps))
    elif _source_needs_verify_first(verification):
        gaps = list(adjusted.get("match_gaps") or [])
        gaps.append("Verify the listing on the employer site before applying.")
        adjusted["match_gaps"] = list(dict.fromkeys(gaps))
    return adjusted


def _field_warnings(
    normalized: Dict[str, Any],
    verification: Dict[str, Any],
    intelligence: Optional[Dict[str, Any]] = None,
) -> list[str]:
    warnings = list(verification.get("source_warnings") or [])
    if not str(normalized.get("location") or "").strip() or str(normalized.get("location")).strip() == "Not specified":
        warnings.append("Location was not detected. Review before saving.")
    if not str(normalized.get("work_arrangement") or "").strip() or str(normalized.get("work_arrangement")).strip() == "Not specified":
        warnings.append("Work arrangement was not detected. Review before saving.")
    compensation = normalized.get("compensation") or {}
    state = str(compensation.get("disclosure_state") or "unknown_unverified")
    if state == "not_listed":
        warnings.append("Compensation not listed — verify before recruiter screen.")
    elif state == "unknown_unverified":
        warnings.append("Compensation unknown — verify posting or recruiter details.")
    elif compensation.get("needs_review"):
        warnings.append("Compensation was saved from a manual value. Review before applying.")
    if _source_needs_verify_first(verification):
        warnings.append(VERIFY_FIRST_MESSAGE)
    if intelligence and intelligence.get("source") == "dynamic_inference":
        warnings.append("Role family was inferred. Review if this is a strategic or product-ops role.")
    return list(dict.fromkeys(str(warning).strip() for warning in warnings if str(warning).strip()))


def create_prospect(
    job_data: Dict[str, Any],
    project_root: Optional[PathInput] = None,
    *,
    run_match_analysis: bool = True,
) -> Dict[str, Any]:
    """Create a clean job file and add or update its tracker entry."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    normalized_input = dict(job_data)
    company = str(normalized_input.get("company") or "").strip()
    supplied_company = company
    role = str(normalized_input.get("role") or normalized_input.get("job_title") or "").strip()
    description = str(normalized_input.get("job_description") or "").strip()
    raw_url = str(normalized_input.get("official_url") or "").strip()
    url_fallback = infer_job_fields_from_url(raw_url)
    if url_fallback:
        company = company or url_fallback.get("company", "")
        role = preferred_role_title(role, "", raw_url)
        for key in ("location", "job_id", "source"):
            if url_fallback.get(key) and not normalized_input.get(key):
                normalized_input[key] = url_fallback[key]
    if raw_url and (not company or not role or len(description) < MINIMUM_DESCRIPTION_LENGTH):
        try:
            imported = import_job_from_url(raw_url)
        except JobImportError as error:
            if len(description) < MINIMUM_DESCRIPTION_LENGTH:
                raise ProspectIntakeError(str(error)) from error
        else:
            for key, value in imported.items():
                if value and not normalized_input.get(key):
                    normalized_input[key] = value
            company = str(normalized_input.get("company") or "").strip()
            role = preferred_role_title(
                role,
                normalized_input.get("role") or normalized_input.get("job_title"),
                raw_url,
            )
            description = str(normalized_input.get("job_description") or "").strip()

    if description and (not company or not role):
        metadata = extract_metadata(description)
        inferred_company, inferred_role = _infer_pasted_identity(description)
        company = company or inferred_company
        role = preferred_role_title(role, inferred_role, raw_url)
        normalized_input.setdefault("posting_date", metadata.get("posting_date") or "")
        normalized_input.setdefault("location", metadata.get("location") or "")
        normalized_input.setdefault("work_arrangement", metadata.get("work_arrangement") or "")
        normalized_input.setdefault("salary_range", metadata.get("salary_range") or "")
    else:
        metadata = extract_metadata(description) if description else {}
    company, role = _clean_identity(company, role)
    company = canonical_employer_name(company)
    company_aliases = list(normalized_input.get("company_aliases") or [])
    if (
        supplied_company
        and supplied_company.casefold() != company.casefold()
        and supplied_company not in company_aliases
    ):
        company_aliases.append(supplied_company)
    role = preferred_role_title("", role, raw_url)
    location = (
        str(normalized_input.get("location") or metadata.get("location") or "").strip()
        or "Not specified"
    )
    work_arrangement = (
        str(normalized_input.get("work_arrangement") or metadata.get("work_arrangement") or "").strip()
        or _work_arrangement(location, description)
        or "Not specified"
    )
    salary_value = str(normalized_input.get("salary_range") or metadata.get("salary_range") or "").strip()
    compensation = normalize_compensation(
        normalized_input.get("compensation") or salary_value,
        source="manual" if normalized_input.get("compensation_manual_override") else "description",
        manual_override=bool(normalized_input.get("compensation_manual_override")),
        disclosure_state=(
            normalized_input.get("compensation_disclosure_state")
            or metadata.get("compensation_disclosure_state")
        ),
    )
    salary_range = str(
        compensation.get("display")
        or compensation.get("status_message")
        or salary_value
        or "Compensation unknown — verify posting or recruiter details."
    ).strip()
    try:
        official_url = validate_official_url(raw_url) if raw_url else ""
    except JobImportError as error:
        raise ProspectIntakeError(str(error)) from error
    if not company or not role:
        raise ProspectIntakeError("Company and role title are required.")
    if not is_valid_role_title(role):
        raise ProspectIntakeError("Please confirm the role title before saving.")
    if len(description) < MINIMUM_DESCRIPTION_LENGTH:
        raise ProspectIntakeError(
            "Paste the job description text before saving (at least 80 characters)."
        )

    tracker_id = str(normalized_input.get("tracker_id") or make_tracker_id(company, role))
    normalized = dict(normalized_input)
    normalized.update(
        {
            "tracker_id": tracker_id,
            "company": company,
            "company_aliases": company_aliases,
            "job_title": role,
            "location": location,
            "work_arrangement": work_arrangement,
            "salary_range": salary_range,
            "compensation": compensation,
            "compensation_disclosure_state": compensation["disclosure_state"],
            "job_description": description,
            "official_url": official_url,
            "source_url": official_url,
            "original_source_url": official_url,
            "job_id": str(normalized_input.get("job_id") or "").strip(),
        }
    )
    verification = normalize_job_source(normalized)
    normalized.update(verification)
    try:
        markdown = create_job_markdown(normalized)
    except Exception as error:
        raise ProspectIntakeError(str(error)) from error

    job_directory = root / "jobs"
    job_directory.mkdir(parents=True, exist_ok=True)
    job_path = job_directory / _job_filename(
        role, company, normalized_input.get("job_id")
    )
    try:
        job_path.write_text(markdown, encoding="utf-8")
    except OSError as error:
        if error.errno == errno.ENAMETOOLONG:
            raise ProspectIntakeError(
                "Career Catalyst could not save this prospect because the generated filename "
                "was too long. It will use a shorter safe filename after you confirm the role title."
            ) from error
        raise ProspectIntakeError(
            f"Career Catalyst could not save this prospect. Confirm the title and try again: {error}"
        ) from error

    intelligence = get_effective_voice_profile(
        company_name=company,
        job_title=role,
        job_description=description,
        source_url=official_url,
    )
    freshness = detect_job_freshness(markdown)
    match_report = (
        _source_adjusted_match_report(score_job_match(job_path, root), verification)
        if run_match_analysis
        else {}
    )
    field_warnings = _field_warnings(normalized, verification, intelligence)
    next_action = _merge_next_action(job_data.get("next_action"), verification)

    tracker_result = add_prospect(
        {
            "id": tracker_id,
            "company": company,
            "company_aliases": company_aliases,
            "role": role,
            "status": str(job_data.get("status") or "Prospect"),
            "priority": str(job_data.get("priority") or "Medium"),
            "source": verification["source_name"],
            "official_url": official_url,
            "source_url": official_url,
            "job_id": str(normalized.get("job_id") or ""),
            "location": location,
            "salary_range": salary_range,
            "compensation_minimum": compensation.get("minimum"),
            "compensation_maximum": compensation.get("maximum"),
            "compensation_currency": compensation.get("currency"),
            "compensation_period": compensation.get("period"),
            "compensation_raw": compensation.get("raw"),
            "compensation_source": compensation.get("source"),
            "compensation_manual_override": compensation.get("manual_override", False),
            "compensation_disclosure_state": compensation["disclosure_state"],
            "work_arrangement": work_arrangement,
            "notes": str(job_data.get("notes") or "").strip(),
            "next_action": next_action,
            **{
                key: str(job_data[key])
                for key in (
                    "reopened_from_archive_id",
                    "reopened_from_manifest",
                    "reopen_request_id",
                )
                if job_data.get(key)
            },
            "field_warnings": field_warnings,
            "show_on_dashboard": bool(job_data.get("show_on_dashboard", True)),
            "job_file": _project_relative(job_path, root),
            "company_category": intelligence["company_category"],
            "role_family": intelligence["role_family"],
            "company_voice_profile": intelligence["profile_name"],
            "company_voice_source": intelligence["source"],
            "company_voice_label": intelligence.get("company_voice_label", intelligence["profile_name"]),
            "company_inference_confidence": intelligence.get("confidence_label", "Medium"),
            "posting_date": freshness.get("posting_date") or "",
            "posting_age_days": freshness.get("age_days"),
            "freshness": freshness["category"],
            "freshness_label": freshness["label"],
            "posting_status": freshness["posting_status"],
            **persisted_match_fields(match_report),
            **verification,
        },
        root,
    )
    return {
        "tracker_id": tracker_id,
        "job_file_path": str(job_path),
        "relative_job_file_path": _project_relative(job_path, root),
        "tracker_created": tracker_result["created"],
        "application": tracker_result["application"],
    }


def add_prospect_from_job_file(
    job_file_path: PathInput,
    project_root: Optional[PathInput] = None,
) -> Dict[str, Any]:
    """Register an existing local job file without duplicating its tracker record."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    path = Path(job_file_path)
    resolved = path if path.is_absolute() else root / path
    try:
        parsed = parse_job_description(resolved)
    except JobParseError as error:
        raise ProspectIntakeError(str(error)) from error

    company, role = _clean_identity(parsed.get("company"), parsed.get("job_title"))
    if not company or not role:
        raise ProspectIntakeError(
            "The job file needs a # role heading and a Company: metadata line."
        )
    raw_text = str(parsed.get("raw_text") or "")
    tracker_match = re.search(
        r"^\s*Tracker ID\s*:\s*(.+?)\s*$", raw_text, flags=re.I | re.M
    )
    source_match = re.search(
        r"^\s*(?:Official source|Source)\s*:\s*(.+?)\s*$", raw_text, flags=re.I | re.M
    )
    tracker_id = tracker_match.group(1).strip() if tracker_match else make_tracker_id(company, role)
    intelligence = get_effective_voice_profile(
        company_name=company,
        job_title=role,
        job_description=raw_text,
        source_url=str(parsed.get("source_url") or ""),
    )
    freshness = detect_job_freshness(raw_text)
    verification = normalize_job_source(
        {
            "official_url": str(parsed.get("source_url") or ""),
            "source": source_match.group(1).strip() if source_match else "",
            "posting_date": parsed.get("posting_date"),
            "raw_text": raw_text,
        }
    )
    match_report = _source_adjusted_match_report(score_job_match(resolved, root), verification)
    location = str(parsed.get("location") or "").strip() or "Not specified"
    work_arrangement = str(parsed.get("work_arrangement") or "").strip() or _work_arrangement(location, raw_text)
    normalized_for_warnings = {
        "location": location,
        "work_arrangement": work_arrangement,
        "salary_range": str(parsed.get("salary_range") or "Not disclosed"),
        "compensation": parsed.get("compensation"),
    }
    field_warnings = _field_warnings(normalized_for_warnings, verification, intelligence)
    next_action = _merge_next_action(verification.get("recommended_next_step"), verification)
    compensation = parsed.get("compensation") or normalize_compensation(
        parsed.get("salary_range"),
        disclosure_state=parsed.get("compensation_disclosure_state"),
    )
    salary_display = str(
        parsed.get("salary_range")
        or compensation.get("status_message")
        or "Compensation unknown — verify posting or recruiter details."
    )
    tracker_result = add_prospect(
        {
            "id": tracker_id,
            "company": company,
            "role": role,
            "status": "Prospect",
            "priority": "Medium",
            "source": verification["source_name"],
            "official_url": str(parsed.get("source_url") or ""),
            "location": location,
            "salary_range": salary_display,
            "compensation_disclosure_state": compensation["disclosure_state"],
            "compensation_minimum": compensation.get("minimum"),
            "compensation_maximum": compensation.get("maximum"),
            "compensation_currency": compensation.get("currency"),
            "compensation_period": compensation.get("period"),
            "compensation_raw": compensation.get("raw"),
            "compensation_source": compensation.get("source"),
            "work_arrangement": work_arrangement,
            "job_file": _project_relative(resolved, root),
            "next_action": next_action,
            "field_warnings": field_warnings,
            "show_on_dashboard": True,
            "company_category": intelligence["company_category"],
            "role_family": intelligence["role_family"],
            "company_voice_profile": intelligence["profile_name"],
            "company_voice_source": intelligence["source"],
            "company_voice_label": intelligence.get("company_voice_label", intelligence["profile_name"]),
            "company_inference_confidence": intelligence.get("confidence_label", "Medium"),
            "posting_date": freshness.get("posting_date") or "",
            "posting_age_days": freshness.get("age_days"),
            "freshness": freshness["category"],
            "freshness_label": freshness["label"],
            "posting_status": freshness["posting_status"],
            **persisted_match_fields(match_report),
            **verification,
        },
        root,
    )
    return {
        "tracker_id": tracker_id,
        "job_file_path": str(resolved),
        "relative_job_file_path": _project_relative(resolved, root),
        "tracker_created": tracker_result["created"],
        "application": tracker_result["application"],
    }
