"""Classify imported job sources and derive lightweight verification signals."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, Optional
from urllib.parse import urlparse


SOURCE_TYPES = (
    "Direct Employer",
    "Employer ATS",
    "Direct Company Discovery",
    "Industry Job Board",
    "Music Industry Job Board",
    "Entertainment Job Board",
    "Startup / Tech Job Board",
    "Remote Job Aggregator",
    "Compensation-Focused Aggregator",
    "Gated Source",
    "Generic Aggregator",
    "Unknown Source",
)
TRUST_LABELS = (
    "Direct Employer",
    "Verified Company Source",
    "Industry Job Board",
    "Aggregator - Verify First",
    "Gated Source",
    "Stale Risk",
    "Cannot Verify",
    "Unknown Source",
)
VERIFICATION_STATUSES = (
    "Verified Active",
    "Possibly Active",
    "Employer Source",
    "Aggregator Only",
    "Industry Board",
    "Gated / Limited Visibility",
    "Stale / Closed Risk",
    "Cannot Verify",
    "Not Verified",
)


def _source(
    source_key: str,
    display_name: str,
    domains: Iterable[str],
    source_type: str,
    trust_tier: int,
    default_trust_label: str,
    requires_verification: bool,
    gated: bool = False,
    notes: str = "",
    canonical_apply_patterns: Iterable[str] = (),
) -> Dict[str, Any]:
    return {
        "source_key": source_key,
        "display_name": display_name,
        "domains": tuple(domains),
        "source_type": source_type,
        "trust_tier": trust_tier,
        "default_trust_label": default_trust_label,
        "requires_verification": requires_verification,
        "gated": gated,
        "notes": notes,
        "canonical_apply_patterns": tuple(canonical_apply_patterns),
    }


SOURCE_REGISTRY = (
    _source("workday", "Workday", ("myworkdayjobs.com", "workday.com"), "Employer ATS", 1, "Verified Company Source", False),
    _source("greenhouse", "Greenhouse", ("greenhouse.io",), "Employer ATS", 1, "Verified Company Source", False),
    _source("lever", "Lever", ("lever.co",), "Employer ATS", 1, "Verified Company Source", False),
    _source("ashby", "Ashby", ("ashbyhq.com",), "Employer ATS", 1, "Verified Company Source", False),
    _source("smartrecruiters", "SmartRecruiters", ("smartrecruiters.com",), "Employer ATS", 1, "Verified Company Source", False),
    _source("icims", "iCIMS", ("icims.com",), "Employer ATS", 1, "Verified Company Source", False),
    _source("oracle_taleo", "Oracle Cloud / Taleo", ("oraclecloud.com", "taleo.net"), "Employer ATS", 1, "Verified Company Source", False),
    _source("careerhound", "CareerHound.io", ("careerhound.io",), "Direct Company Discovery", 2, "Verified Company Source", False),
    _source("getwork", "Getwork", ("getwork.com",), "Direct Company Discovery", 2, "Verified Company Source", False),
    _source("entertainment_careers", "EntertainmentCareers.net", ("entertainmentcareers.net", "entertainmentcareers.com"), "Entertainment Job Board", 2, "Industry Job Board", False),
    _source("showbizjobs", "ShowbizJobs", ("showbizjobs.com",), "Entertainment Job Board", 2, "Industry Job Board", False),
    _source("mbw_jobs", "Music Business Worldwide Jobs", ("musicbusinessworldwide.com",), "Music Industry Job Board", 2, "Industry Job Board", False),
    _source("musiccareers", "MusicCareers.co", ("musiccareers.co",), "Music Industry Job Board", 2, "Industry Job Board", False),
    _source("jobs_by_rostr", "Jobs by ROSTR", ("jobsbyrostr.com", "rostr.cc"), "Music Industry Job Board", 2, "Industry Job Board", False),
    _source("doors_open", "Doors Open", ("doorsopen.co",), "Music Industry Job Board", 2, "Industry Job Board", False),
    _source("hollylist", "Hollylist", ("hollylist.com",), "Entertainment Job Board", 3, "Industry Job Board", True, True, "Some listing details may require an account."),
    _source("mediabistro", "Mediabistro", ("mediabistro.com",), "Entertainment Job Board", 2, "Industry Job Board", False),
    _source("built_in", "Built In", ("builtin.com",), "Startup / Tech Job Board", 2, "Industry Job Board", False),
    _source("wellfound", "Wellfound", ("wellfound.com", "angel.co"), "Startup / Tech Job Board", 2, "Industry Job Board", False),
    _source("yc_jobs", "Y Combinator Jobs", ("ycombinator.com", "workatastartup.com"), "Startup / Tech Job Board", 2, "Industry Job Board", False),
    _source("jobgether", "Jobgether", ("jobgether.com",), "Remote Job Aggregator", 4, "Aggregator - Verify First", True),
    _source("jobtogether", "Jobtogether", ("jobtogether.com",), "Remote Job Aggregator", 4, "Aggregator - Verify First", True),
    _source("flexjobs", "FlexJobs", ("flexjobs.com",), "Gated Source", 4, "Gated Source", True, True, "Canonical apply details may be hidden behind a subscription."),
    _source("ladders", "Ladders", ("theladders.com", "ladders.com"), "Compensation-Focused Aggregator", 4, "Aggregator - Verify First", True),
)

UNKNOWN_SOURCE = _source(
    "unknown", "Unknown", (), "Unknown Source", 5, "Unknown Source", True,
    notes="No registry match was found.",
)

AGGREGATOR_TYPES = {
    "Remote Job Aggregator",
    "Compensation-Focused Aggregator",
    "Generic Aggregator",
}
INDUSTRY_BOARD_TYPES = {
    "Industry Job Board",
    "Music Industry Job Board",
    "Entertainment Job Board",
    "Startup / Tech Job Board",
}
EMPLOYER_TYPES = {"Direct Employer", "Employer ATS"}
CLOSED_PHRASES = (
    "applications closed",
    "applications are closed",
    "no longer available",
    "job expired",
    "role has been filled",
    "position has been filled",
    "position closed",
    "no longer accepting applications",
    "not currently accepting applications",
    "job is unavailable",
)
URL_PATTERN = re.compile(r"https?://[^\s<>\"']+", re.I)


def source_domain(url: Any) -> str:
    """Return a normalized hostname without a leading www prefix."""
    host = (urlparse(str(url or "").strip()).hostname or "").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def _domain_matches(host: str, registered_domain: str) -> bool:
    return host == registered_domain or host.endswith(f".{registered_domain}")


def _label_matches(label: str, entry: Dict[str, Any]) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "", label.lower())
    names = (entry["source_key"], entry["display_name"], *entry["domains"])
    return any(
        re.sub(r"[^a-z0-9]+", "", str(name).lower()) in normalized
        for name in names
        if len(re.sub(r"[^a-z0-9]+", "", str(name).lower())) >= 5
    )


def classify_source(url: Any = "", source_label: Any = "") -> Dict[str, Any]:
    """Find a registry entry by URL domain, then by a supplied source label."""
    host = source_domain(url)
    for entry in SOURCE_REGISTRY:
        if host and any(_domain_matches(host, domain) for domain in entry["domains"]):
            return dict(entry)
    label = str(source_label or "").strip()
    for entry in SOURCE_REGISTRY:
        if label and _label_matches(label, entry):
            return dict(entry)
    if re.search(r"\b(?:official|company)\s+(?:career|careers|job|jobs)(?:\s+page)?\b", label, re.I):
        return _source(
            "company_careers", "Company career page", (), "Direct Employer", 1,
            "Direct Employer", False, notes="Identified from the supplied source label.",
        )
    return dict(UNKNOWN_SOURCE)


def _parse_posting_date(value: Any) -> Optional[date]:
    clean = re.sub(r"\s+", " ", str(value or "").strip())
    for pattern in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            return datetime.strptime(clean, pattern).date()
        except ValueError:
            continue
    return None


def freshness_risk(posting_date: Any, today: Optional[date] = None) -> Dict[str, Any]:
    """Classify posting-age risk without failing on missing or malformed dates."""
    parsed = _parse_posting_date(posting_date)
    if parsed is None:
        return {"freshness_risk": "Unknown", "posting_age_days": None}
    age = max(0, ((today or date.today()) - parsed).days)
    risk = "Low" if age <= 14 else "Medium" if age <= 30 else "High"
    return {"freshness_risk": risk, "posting_age_days": age}


def _candidate_urls(record: Dict[str, Any], content: str) -> list[tuple[str, bool]]:
    candidates = []
    for key in ("canonical_apply_url", "employer_apply_url", "apply_url", "application_url"):
        value = str(record.get(key) or "").strip().rstrip(".,);]")
        if value.startswith(("http://", "https://")):
            candidates.append((value, True))
    candidates.extend((match.group(0).rstrip(".,);]"), False) for match in URL_PATTERN.finditer(content))
    return candidates


def _looks_canonical(url: str) -> bool:
    classified = classify_source(url)
    if classified["source_type"] in EMPLOYER_TYPES:
        return True
    parsed = urlparse(url)
    return bool(re.search(r"/(?:careers?|jobs?|positions?|opportunities)(?:/|\b)", parsed.path, re.I))


def normalize_job_source(record: Dict[str, Any], today: Optional[date] = None) -> Dict[str, Any]:
    """Return normalized source, canonical apply, freshness, and guidance fields."""
    values = dict(record or {})
    original_url = str(
        values.get("original_source_url")
        or values.get("official_url")
        or values.get("source_url")
        or values.get("listing_url")
        or values.get("url")
        or ""
    ).strip()
    supplied_source = values.get("source_name") or values.get("source") or ""
    registry = classify_source(original_url, supplied_source)
    content = "\n".join(
        str(values.get(key) or "")
        for key in ("job_description", "description", "raw_text", "posting_status")
    )
    lowered = content.lower()
    closed_reason = next((phrase for phrase in CLOSED_PHRASES if phrase in lowered), None)
    if not closed_reason and str(values.get("posting_status") or "").strip().lower() in {
        "closed", "expired", "unavailable", "possibly closed"
    }:
        closed_reason = str(values.get("posting_status")).strip().lower()
    freshness = freshness_risk(values.get("posting_date"), today)

    canonical_url = ""
    canonical_is_explicit = False
    if original_url and registry["source_type"] in EMPLOYER_TYPES:
        canonical_url = original_url
        canonical_is_explicit = True
    elif original_url and registry["source_type"] == "Direct Company Discovery":
        canonical_url = ""
    else:
        original_host = source_domain(original_url)
        for candidate, explicit in _candidate_urls(values, content):
            if candidate == original_url or source_domain(candidate) == original_host:
                continue
            if _looks_canonical(candidate):
                canonical_url = candidate
                canonical_is_explicit = explicit
                break

    source_type = registry["source_type"]
    trust_label = registry["default_trust_label"]
    if registry["gated"]:
        trust_label = "Gated Source"
    if not original_url:
        verification_status = "Not Verified"
    elif source_type in EMPLOYER_TYPES:
        verification_status = "Employer Source"
    elif source_type == "Direct Company Discovery":
        verification_status = "Possibly Active"
    elif registry["gated"]:
        verification_status = "Gated / Limited Visibility"
    elif source_type in AGGREGATOR_TYPES:
        verification_status = "Verified Active" if canonical_url and canonical_is_explicit else "Possibly Active" if canonical_url else "Aggregator Only"
    elif source_type in INDUSTRY_BOARD_TYPES:
        verification_status = "Industry Board"
    else:
        verification_status = "Not Verified"

    notes = []
    warnings = []
    if not original_url:
        notes.append("source URL is missing")
        warnings.append("Source URL missing")
    elif source_type == "Unknown Source":
        notes.append("source domain is not in the registry; verify manually")
        warnings.append("Unknown source domain")
    if not values.get("posting_date") or freshness["posting_age_days"] is None:
        notes.append("posting date missing; verify manually")
        warnings.append("Posting date missing or malformed")
    if registry.get("notes"):
        notes.append(str(registry["notes"]))

    if closed_reason:
        verification_status = "Stale / Closed Risk"
        trust_label = "Stale Risk"
        notes.append(f"closed or expired language detected: {closed_reason}")
        warnings.append("Role may be closed or expired")
        next_step = "Pass unless the employer confirms the role is active."
    elif registry["gated"] and not canonical_url:
        next_step = "Verify manually before investing time."
        warnings.append("Canonical employer application is not visible")
    elif source_type in AGGREGATOR_TYPES and not canonical_url:
        next_step = "Verify on employer site before generating package or applying."
        warnings.append("No canonical employer apply URL found")
    elif source_type == "Unknown Source" or not original_url:
        next_step = "Verify the source and role manually before applying."
    elif verification_status == "Industry Board" and not canonical_url:
        next_step = "Confirm the role on the employer site before applying."
    else:
        next_step = "Proceed using the canonical employer application."

    return {
        "original_source_url": original_url,
        "source_domain": source_domain(original_url),
        "source_name": registry["display_name"] if original_url else "Unknown",
        "source_type": source_type if original_url else "Unknown Source",
        "source_trust_label": trust_label if original_url else "Unknown Source",
        "verification_status": verification_status,
        "canonical_apply_url": canonical_url,
        "canonical_apply_domain": source_domain(canonical_url),
        "verification_notes": "; ".join(dict.fromkeys(notes)) or "No verification cautions detected.",
        "source_confidence": "High" if original_url and source_type != "Unknown Source" else "Low",
        "source_warnings": list(dict.fromkeys(warnings)),
        "freshness_risk": freshness["freshness_risk"],
        "recommended_next_step": next_step,
    }
