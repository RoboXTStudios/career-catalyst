"""Classify imported job sources and derive lightweight verification signals."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Dict, Iterable, Optional
from urllib.parse import parse_qs, urlparse

try:
    from .job_freshness import detect_job_freshness
except ImportError:
    from job_freshness import detect_job_freshness


SOURCE_TYPES = (
    "Direct Employer",
    "Employer ATS",
    "Direct Company Discovery",
    "Industry Job Board",
    "Gaming Industry Job Board",
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
    _source(
        "paramount",
        "Paramount Careers",
        ("careers.paramount.com", "paramount.com"),
        "Direct Employer",
        1,
        "Direct Employer",
        False,
        notes="Official Paramount employer careers source.",
    ),
    _source(
        "aeg_worldwide",
        "AEG Worldwide Careers",
        ("aegworldwide.com",),
        "Direct Employer",
        1,
        "Direct Employer",
        False,
        notes="Official AEG Worldwide employer careers source.",
    ),
    _source(
        "axs",
        "AEG/AXS Careers",
        ("axs.com",),
        "Direct Employer",
        1,
        "Direct Employer",
        False,
        notes="Official AEG/AXS employer source.",
    ),
    _source("workday", "Workday", ("myworkdayjobs.com", "workday.com", "workdayjobs.com"), "Employer ATS", 1, "Verified Company Source", False),
    _source("greenhouse", "Greenhouse", ("greenhouse.io",), "Employer ATS", 1, "Verified Company Source", False),
    _source("lever", "Lever", ("lever.co",), "Employer ATS", 1, "Verified Company Source", False),
    _source("ashby", "Ashby", ("ashbyhq.com",), "Employer ATS", 1, "Verified Company Source", False),
    _source("smartrecruiters", "SmartRecruiters", ("smartrecruiters.com",), "Employer ATS", 1, "Verified Company Source", False),
    _source("icims", "iCIMS", ("icims.com",), "Employer ATS", 1, "Verified Company Source", False),
    _source("oracle_taleo", "Oracle Cloud / Taleo", ("oraclecloud.com", "taleo.net"), "Employer ATS", 1, "Verified Company Source", False),
    _source(
        "digitalhire", "DigitalHire", ("digitalhire.com",), "Employer ATS", 2,
        "Verified Company Source", True,
        notes="DigitalHire employer ATS / hosted career platform. Verify freshness and employer identity before package generation if posting age is old or missing.",
    ),
    _source("careerhound", "CareerHound.io", ("careerhound.io",), "Direct Company Discovery", 2, "Verified Company Source", False),
    _source("getwork", "Getwork", ("getwork.com",), "Direct Company Discovery", 2, "Verified Company Source", False),
    _source("entertainment_careers", "EntertainmentCareers.net", ("entertainmentcareers.net", "entertainmentcareers.com"), "Entertainment Job Board", 2, "Industry Job Board", False),
    _source("showbizjobs", "ShowbizJobs", ("showbizjobs.com",), "Entertainment Job Board", 2, "Industry Job Board", False),
    _source("mbw_jobs", "Music Business Worldwide Jobs", ("musicbusinessworldwide.com",), "Music Industry Job Board", 2, "Industry Job Board", False),
    _source("musiccareers", "MusicCareers.co", ("musiccareers.co",), "Music Industry Job Board", 2, "Industry Job Board", False),
    _source("jobs_by_rostr", "Jobs by ROSTR", ("jobsbyrostr.com", "rostr.cc"), "Music Industry Job Board", 2, "Industry Job Board", False),
    _source("doors_open", "Doors Open", ("doorsopen.co",), "Music Industry Job Board", 2, "Industry Job Board", False),
    _source(
        "gamejobs",
        "GameJobs.co",
        ("gamejobs.co",),
        "Gaming Industry Job Board",
        2,
        "Industry Job Board",
        True,
        notes=(
            "GameJobs.co is an industry job board. Verify the role on the employer "
            "site before generating a package or applying."
        ),
    ),
    _source("hollylist", "Hollylist", ("hollylist.com",), "Entertainment Job Board", 3, "Industry Job Board", True, True, "Some listing details may require an account."),
    _source("mediabistro", "Mediabistro", ("mediabistro.com",), "Entertainment Job Board", 2, "Industry Job Board", False),
    _source("built_in", "Built In", ("builtin.com",), "Startup / Tech Job Board", 2, "Industry Job Board", False),
    _source("wellfound", "Wellfound", ("wellfound.com", "angel.co"), "Startup / Tech Job Board", 2, "Industry Job Board", False),
    _source("yc_jobs", "Y Combinator Jobs", ("ycombinator.com", "workatastartup.com"), "Startup / Tech Job Board", 2, "Industry Job Board", False),
    _source("jobgether", "Jobgether", ("jobgether.com",), "Remote Job Aggregator", 4, "Aggregator - Verify First", True),
    _source("jobtogether", "Jobtogether", ("jobtogether.com",), "Remote Job Aggregator", 4, "Aggregator - Verify First", True),
    _source("ziprecruiter", "ZipRecruiter", ("ziprecruiter.com",), "Generic Aggregator", 4, "Aggregator - Verify First", True),
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
    "Gaming Industry Job Board",
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
    "this job is no longer available",
    "posting is expired",
    "posting is inactive",
    "posting was removed",
    "posting is unavailable",
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


def _looks_like_employer_career_label(label: Any, company: Any = "") -> bool:
    clean_label = re.sub(r"\s+", " ", str(label or "").strip())
    if not clean_label:
        return False
    if re.fullmatch(r"(?:official|company)\s+careers?(?:\s+(?:page|site))?", clean_label, re.I):
        return True
    if re.fullmatch(r"official\s+.+?\s+(?:careers?|jobs?|career\s+site)", clean_label, re.I):
        return True
    if re.fullmatch(
        r"(?:google|paramount|sony|disney|warner\s+music\s+group|wmg|aeg|axs)\s+"
        r"(?:careers?|jobs?|career\s+site)",
        clean_label,
        re.I,
    ):
        return True
    company_words = {
        word for word in re.findall(r"[a-z0-9]+", str(company or "").lower())
        if len(word) >= 3 and word not in {"company", "corporate", "worldwide", "entertainment", "interactive"}
    }
    label_words = set(re.findall(r"[a-z0-9]+", clean_label.lower()))
    return bool(
        company_words.intersection(label_words)
        and re.search(r"\b(?:careers?|jobs?|career\s+site)\s*$", clean_label, re.I)
    )


def _company_named_career_label(label: Any, company: Any = "") -> bool:
    """Return true only when the label names the employer, not a generic page."""
    clean_label = re.sub(r"\s+", " ", str(label or "").strip())
    company_words = {
        word for word in re.findall(r"[a-z0-9]+", str(company or "").lower())
        if len(word) >= 3 and word not in {"company", "corporate", "worldwide", "entertainment", "interactive"}
    }
    label_words = set(re.findall(r"[a-z0-9]+", clean_label.lower()))
    return bool(
        company_words
        and company_words.intersection(label_words)
        and re.search(r"\b(?:careers?|jobs?|career\s+site)\b", clean_label, re.I)
    )


def _domain_matches_company(host: str, company: Any) -> bool:
    """Conservative employer-domain heuristic for non-ATS direct career pages."""
    compact_host = re.sub(r"[^a-z0-9]+", "", host.lower())
    if not compact_host:
        return False
    stop_words = {
        "the", "and", "inc", "llc", "ltd", "corp", "corporation", "company",
        "co", "group", "holdings", "worldwide", "interactive", "entertainment",
    }
    company_tokens = [
        token
        for token in re.findall(r"[a-z0-9]+", str(company or "").lower())
        if len(token) >= 3 and token not in stop_words
    ]
    if not company_tokens:
        return False
    compact_company = "".join(company_tokens)
    return compact_company in compact_host or any(token in compact_host for token in company_tokens[:2])


def _display_from_domain(url: str) -> str:
    host = source_domain(url)
    return host or "Unknown"


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
    if not host and (
        re.search(r"\b(?:official|company)\s+(?:career|careers|job|jobs)(?:\s+page)?\b", label, re.I)
        or re.fullmatch(r"official\s+.+?\s+(?:careers?|jobs?|career\s+site)", label, re.I)
    ):
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


def freshness_risk(
    posting_date: Any, today: Optional[date] = None, content: Any = ""
) -> Dict[str, Any]:
    """Classify posting-age risk without failing on missing or malformed dates."""
    reference_date = today or date.today()
    freshness = detect_job_freshness(
        f"Posting date: {posting_date or ''}\n{content or ''}", reference_date
    )
    age = freshness.get("age_days")
    if age is None:
        return {"freshness_risk": "Unknown", "posting_age_days": None}
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
    source_labels = (
        values.get("source_name"),
        values.get("source"),
        values.get("source_label"),
        values.get("apply_source"),
        values.get("application_source"),
    )
    supplied_source = next(
        (
            str(value).strip()
            for value in source_labels
            if str(value or "").strip() and str(value).strip().lower() != "unknown"
        ),
        "",
    )
    apply_url = str(values.get("apply_url") or values.get("application_url") or "").strip()
    classification_url = original_url or apply_url
    registry = classify_source(classification_url, "" if original_url else supplied_source)
    label_inferred_employer = _looks_like_employer_career_label(
        supplied_source, values.get("company")
    )
    if registry["source_type"] == "Unknown Source" and original_url:
        original_host = source_domain(original_url)
        if _domain_matches_company(original_host, values.get("company")) or _company_named_career_label(
            supplied_source, values.get("company")
        ):
            registry = _source(
                "company_careers", "Company career page", (), "Direct Employer", 1,
                "Direct Employer", False,
                notes="Source identity inferred from an employer-owned domain or company-named careers label.",
            )
    if label_inferred_employer and registry["source_type"] == "Unknown Source" and not original_url:
        registry = _source(
            "company_careers", "Company career page", (), "Direct Employer", 1,
            "Direct Employer", False,
            notes="Source identity inferred from a legacy employer-careers label.",
        )
    inferred_employer = bool(
        not original_url
        and (registry["source_type"] in EMPLOYER_TYPES or label_inferred_employer)
    )
    content = "\n".join(
        str(values.get(key) or "")
        for key in ("job_description", "description", "raw_text", "posting_status")
    )
    lowered = content.lower()
    freshness_signal = detect_job_freshness(
        f"Posting date: {values.get('posting_date') or ''}\n{content}", today
    )
    closed_reason = freshness_signal.get("closed_reason") or next(
        (phrase for phrase in CLOSED_PHRASES if phrase in lowered), None
    )
    if not closed_reason and str(values.get("posting_status") or "").strip().lower() in {
        "closed", "expired", "unavailable", "possibly closed"
    }:
        closed_reason = str(values.get("posting_status")).strip().lower()
    freshness = freshness_risk(values.get("posting_date"), today, content)
    age_days = freshness["posting_age_days"]
    stale_age = bool(age_days is not None and age_days >= 90)
    aged_posting = bool(age_days is not None and age_days >= 31)

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
    if inferred_employer:
        verification_status = "Employer Source"
    elif not original_url:
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
    if inferred_employer:
        notes.append(
            "Source label indicates an employer careers page, but the original source URL "
            "was not stored. Verify manually if needed."
        )
        warnings.append("Original source URL missing; verify manually if needed")
    elif not original_url:
        notes.append("source URL is missing")
        warnings.append("Source URL missing")
    elif source_type == "Unknown Source":
        notes.append("source domain is not in the registry; verify manually")
        warnings.append("Unknown source domain")
    if age_days is None:
        notes.append("posting date missing; verify manually")
        warnings.append("Posting date missing or malformed")
    if registry.get("notes") and registry["source_key"] != "unknown" and not inferred_employer:
        notes.append(str(registry["notes"]))

    if closed_reason or stale_age:
        verification_status = "Stale / Closed Risk"
        if registry["source_key"] != "digitalhire":
            trust_label = "Stale Risk"
        if closed_reason:
            notes.append(f"closed or expired language detected: {closed_reason}")
        if stale_age:
            notes.append(f"posting age indicates stale risk: {age_days} days old")
        warnings.append("Role may be stale, closed, or expired")
        next_step = "Verify manually before generating package."
    elif aged_posting:
        notes.append(f"posting is {age_days} days old; verify that it is still active")
        warnings.append("Posting appears older than 30 days")
        next_step = "Verify manually before generating package."
    elif registry["gated"] and not canonical_url:
        next_step = "Verify manually before investing time."
        warnings.append("Canonical employer application is not visible")
    elif source_type in AGGREGATOR_TYPES and not canonical_url:
        next_step = "Verify on employer site before generating package or applying."
        warnings.append("No canonical employer apply URL found")
    elif source_type == "Unknown Source" or (not original_url and not inferred_employer):
        next_step = "Verify the source and role manually before applying."
    elif inferred_employer:
        next_step = "Verify manually if needed, then use the employer career site."
    elif verification_status == "Industry Board" and not canonical_url:
        next_step = "Verify on employer site before generating package or applying."
        warnings.append("Industry job board source requires employer-site verification")
    elif source_type in EMPLOYER_TYPES and age_days is None:
        next_step = "Official employer source detected; verify posting freshness if date is missing."
    else:
        next_step = "Proceed using the canonical employer application."

    source_name = registry["display_name"] if original_url or apply_url else supplied_source if inferred_employer else "Unknown"
    if original_url and registry["source_type"] == "Unknown Source":
        source_name = _display_from_domain(original_url)

    greenhouse_job_id = ""
    if original_url:
        greenhouse_job_id = str(
            (parse_qs(urlparse(original_url).query).get("gh_jid") or [""])[0]
        ).strip()

    return {
        "original_source_url": original_url,
        "source_domain": source_domain(classification_url),
        "source_name": source_name,
        "source_type": source_type if original_url or inferred_employer else "Unknown Source",
        "source_trust_label": trust_label if original_url or inferred_employer else "Unknown Source",
        "verification_status": verification_status,
        "canonical_apply_url": canonical_url,
        "canonical_apply_domain": source_domain(canonical_url),
        "verification_notes": "; ".join(dict.fromkeys(notes)) or "No verification cautions detected.",
        "source_confidence": (
            "High" if original_url and source_type != "Unknown Source"
            else "Medium" if inferred_employer
            else "Low"
        ),
        "requires_verification": bool(registry["requires_verification"]),
        "source_warnings": list(dict.fromkeys(warnings)),
        "freshness_risk": freshness["freshness_risk"],
        "freshness": freshness_signal["category"],
        "freshness_label": freshness_signal["label"],
        "posting_status": freshness_signal["posting_status"],
        "posting_age_days": age_days,
        "canonical_employer": (
            str(values.get("company") or "").strip()
            if source_type in EMPLOYER_TYPES
            else ""
        ),
        "recommended_next_step": next_step,
        "greenhouse_job_id": greenhouse_job_id,
        "greenhouse_backed_hint": bool(greenhouse_job_id),
    }
