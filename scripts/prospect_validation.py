"""Current-state prospect validation and health summaries."""

from __future__ import annotations

from typing import Any, Dict

try:
    from .filename_utils import is_valid_role_title
    from .job_importer import is_usable_job_description
    from .job_source_registry import normalize_job_source
except ImportError:
    from filename_utils import is_valid_role_title
    from job_importer import is_usable_job_description
    from job_source_registry import normalize_job_source


PROSPECT_HEALTH_STATES = (
    "Excellent",
    "Ready to Apply",
    "Needs Review",
    "Incomplete",
    "Blocked",
)


def _analysis_item(label: str, complete: bool) -> Dict[str, Any]:
    return {"label": label, "status": "complete" if complete else "pending"}


def compute_prospect_validation_state(
    values: Dict[str, Any], intelligence: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """Reconcile analysis, verification, and health from only the current prospect data."""
    current = dict(values or {})
    intelligence = dict(intelligence or {})
    source_url = str(
        current.get("original_source_url")
        or current.get("official_url")
        or current.get("source_url")
        or current.get("posting_url")
        or ""
    ).strip()
    company = str(current.get("company") or "").strip()
    role = str(current.get("job_title") or current.get("role") or "").strip()
    description = current.get("job_description") or current.get("description") or ""
    description_ready = is_usable_job_description(description)
    company_ready = bool(company)
    role_ready = is_valid_role_title(role)
    match_report = current.get("match_report") or intelligence.get("match_report") or {}
    match_ready = isinstance(match_report, dict) and match_report.get("match_score") is not None
    role_classified = bool(intelligence.get("role_family")) and role_ready
    package_ready = bool(description_ready and company_ready and role_ready and match_ready)
    verification = (
        intelligence.get("source_verification")
        if isinstance(intelligence.get("source_verification"), dict)
        else normalize_job_source(current)
    )

    analysis = [
        _analysis_item("URL saved", bool(source_url)),
        _analysis_item("Job description parsed", description_ready),
        _analysis_item("Company detected", company_ready),
        _analysis_item("Role classified", role_classified),
        _analysis_item("Match score generated", match_ready),
        _analysis_item("Package ready", package_ready),
    ]

    observations = []
    source_name = str(verification.get("source_name") or "").strip()
    source_known = verification.get("source_recognition") == "Known source"
    if source_known:
        observations.append(
            {
                "label": f"{source_name or 'Posting source'} recognized.",
                "level": "info",
            }
        )
    elif source_url:
        observations.append(
            {"label": "Source metadata unavailable.", "level": "caution"}
        )
    if verification.get("posting_age_days") is None:
        observations.append(
            {"label": "Posting date unavailable.", "level": "info"}
        )
    if not str(current.get("salary_range") or "").strip() or str(
        current.get("salary_range")
    ).strip() in {"Not disclosed", "Not specified"}:
        observations.append(
            {"label": "Salary information unavailable.", "level": "info"}
        )
    if str(current.get("description_source") or "").lower() == "manual":
        observations.append(
            {"label": "Description manually supplied by user.", "level": "info"}
        )
    if source_url and (
        verification.get("requires_verification")
        or verification.get("verification_status")
        in {"Aggregator Only", "Industry Board", "Gated / Limited Visibility"}
    ):
        observations.append(
            {
                "label": "Original posting should be confirmed before submitting.",
                "level": "caution",
            }
        )
    if not source_url:
        observations.append(
            {"label": "Original posting URL unavailable.", "level": "info"}
        )
    stale_or_closed = verification.get("verification_status") == "Stale / Closed Risk"
    if stale_or_closed:
        observations.append(
            {"label": "Posting may be stale or closed.", "level": "caution"}
        )

    if stale_or_closed:
        health = "Blocked"
    elif not (description_ready and company_ready and role_ready):
        health = "Incomplete"
    elif not match_ready or (source_url and not source_known):
        health = "Needs Review"
    elif (
        verification.get("posting_age_days") is not None
        and str(current.get("salary_range") or "").strip()
        and not verification.get("requires_verification")
    ):
        health = "Excellent"
    else:
        health = "Ready to Apply"

    return {
        "health": health,
        "content_analysis": analysis,
        "posting_verification": observations,
        "package_ready": package_ready,
        "original_posting_url": source_url,
        "source_verification": verification,
    }
