"""Score a parsed job description against Career Catalyst data."""

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

try:
    from .capability_graph import (
        alignment_score as capability_alignment_score,
        build_alignment_matrix,
        load_capability_graph,
    )
    from .evidence_profile import (
        evidence_gap_analysis,
        evidence_text,
        load_evidence_profile,
        select_profile_evidence,
    )
    from .load_data import DataLoadError, load_all_yaml
    from .job_freshness import detect_job_freshness
    from .parse_job import (
        extract_keywords,
        extract_qualifications,
        extract_responsibilities,
        parse_job_description,
    )
    from .role_lens import build_requirement_map, classify_role_lens
    from .role_interpreter import (
        INTERPRETATION_SCORE_FIELDS,
        interpret_role,
        substantive_interpretation_text,
    )
    from .role_evidence_selection import build_role_evidence_selection
except ImportError:
    from capability_graph import (
        alignment_score as capability_alignment_score,
        build_alignment_matrix,
        load_capability_graph,
    )
    from evidence_profile import (
        evidence_gap_analysis,
        evidence_text,
        load_evidence_profile,
        select_profile_evidence,
    )
    from load_data import DataLoadError, load_all_yaml
    from job_freshness import detect_job_freshness
    from parse_job import (
        extract_keywords,
        extract_qualifications,
        extract_responsibilities,
        parse_job_description,
    )
    from role_lens import build_requirement_map, classify_role_lens
    from role_interpreter import (
        INTERPRETATION_SCORE_FIELDS,
        interpret_role,
        substantive_interpretation_text,
    )
    from role_evidence_selection import build_role_evidence_selection


GENERIC_TERMS = {
    "ability",
    "across",
    "company",
    "experience",
    "job",
    "management",
    "responsible",
    "role",
    "strong",
    "support",
    "team",
    "teams",
    "work",
    "working",
}

RESUME_PROFILE_KEYWORDS = {
    "executive_operations": (
        "strategy",
        "operations",
        "enterprise",
        "initiatives",
        "business operations",
    ),
    "entertainment_marketing": (
        "marketing",
        "campaign",
        "audience",
        "brand",
        "creative",
    ),
    "music_industry": (
        "artist",
        "label",
        "music",
        "touring",
        "fan engagement",
    ),
    "product_ai": (
        "product",
        "ai",
        "automation",
        "systems",
        "platform",
        "workflow",
    ),
}

PathInput = Union[str, Path]

MATCH_PERSISTENCE_FIELDS = (
    "match_score",
    "match_tier",
    "match_summary",
    "match_strengths",
    "match_gaps",
    "recommended_action",
    "confidence",
    "data_confidence",
    "match_verification_notes",
    "functional_evidence",
    "material_fit_gaps",
    "diligence_cautions",
    "score_breakdown",
    "role_interpretation",
    "interpretation_assessment",
    "evidence_profile",
    "capability_graph",
    "evidence_gap_analysis",
    "role_evidence_selection",
)

FUNCTIONAL_SIGNAL_GROUPS = (
    ("technical client solutions", ("technical solutions", "client solutions", "technical consultation", "technical escalations", "technical troubleshooting")),
    ("implementation and onboarding", ("implementation", "onboarding", "deployment", "go live", "integration project")),
    ("product operations", ("product operations", "launch readiness", "product feedback", "product governance", "launch enablement")),
    ("product management", ("product management", "product roadmap", "product requirements", "product decisions")),
    ("revenue operations", ("revenue operations", "sales operations", "sales forecasting", "pipeline management", "territory planning")),
    ("people operations", ("people operations", "employee lifecycle", "employee relations", "workforce planning", "hris")),
    ("executive operations", ("chief of staff", "executive priorities", "decision support", "leadership cadence")),
    ("ad/media operations", ("ad operations", "media operations", "trafficking", "media execution")),
    ("programmatic", ("programmatic", "ad tech", "adtech", "dsp", "ad server")),
    ("campaign operations", ("campaign operations", "marketing operations", "campaign management", "campaign execution")),
    ("marketing technology and measurement", ("marketing technology", "martech", "measurement", "vendor operations", "vendor management")),
    ("workflow and process automation", ("workflow", "automation", "process improvement", "operational excellence", "scalable process")),
    ("strategic operations", ("strategic operations", "business operations", "operating model", "transformation", "operational strategy", "strategy and operations")),
)

FUNCTIONAL_ADJACENCY_GROUPS = (
    (
        "programmatic and ad technology operations",
        ("ad tech", "ads signals", "campaign delivery", "advertiser initiatives"),
        ("programmatic", "ad operations", "dv360", "cm360", "google marketing platform"),
    ),
    (
        "measurement and signal readiness",
        ("measurement products", "pixels", "conversions api", "ad signals"),
        ("measurement readiness", "measurement", "analytics", "marketing science"),
    ),
    (
        "technical platform activation",
        ("technical execution", "ads products", "gtm readiness", "product feedback loops"),
        ("platform activation", "platform capabilities", "google and youtube", "product activation"),
    ),
    (
        "workflow design and automation",
        ("optimize workflows", "processes and tooling", "scale support models", "ai tools"),
        ("workflow", "automation", "process improvement", "operational systems"),
    ),
    (
        "cross-functional technical leadership",
        ("cross-functional", "sales, product, and engineering", "technical initiatives"),
        ("cross-functional leadership", "technology, analytics", "marketing, technology", "engineering"),
    ),
    (
        "governance, quality, and scalable operations",
        ("system reliability", "service level", "operational readiness", "scale support"),
        ("governance", "qa", "scalable execution", "execution standards"),
    ),
)

DIRECT_FUNCTION_SIGNALS = (
    "technical solutions",
    "technical support",
    "pixel implementation",
    "conversions api",
    "technical troubleshooting",
    "debugging",
)

DECISION_WEIGHTS = {
    "evidence_base": 0.20,
    "functional_alignment": 0.18,
    "functional_evidence": 0.12,
    "capability_alignment": 0.15,
    "seniority_scope": 0.15,
    "industry_domain": 0.08,
    "compensation": 0.07,
    "work_arrangement": 0.05,
}

TARGET_INDUSTRY_SIGNALS = (
    "music",
    "entertainment",
    "streaming",
    "media",
    "creator economy",
    "creators",
    "advertising technology",
    "marketing technology",
    "martech",
    "brand marketing",
    "creative technology",
)

OBVIOUS_NON_FIT_SIGNALS = (
    "active medical license",
    "registered nurse",
    "licensed clinical",
    "admitted to the bar",
    "active bar membership",
    "certified public accountant required",
    "security clearance required",
    "software engineering degree required",
)

MINIMUM_MEANINGFUL_DESCRIPTION_LENGTH = 80


def incomplete_match_report(job_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a safe no-score gate when required import fields are incomplete."""
    company = str(job_data.get("company") or "").strip()
    title = str(job_data.get("job_title") or job_data.get("role") or "").strip()
    description = str(
        job_data.get("job_description") or job_data.get("description") or ""
    ).strip()
    missing = []
    if not company:
        missing.append("company")
    if not title:
        missing.append("role title")
    if len(description) < MINIMUM_MEANINGFUL_DESCRIPTION_LENGTH:
        missing.append("job description")
    if not missing:
        return None
    return {
        "job_title": title or None,
        "company": company or None,
        "match_score": None,
        "match_band": "Not scored",
        "match_tier": "Not scored",
        "match_summary": "Import is incomplete, so Career Catalyst has not scored this role.",
        "match_strengths": [],
        "match_gaps": ["Missing " + ", ".join(missing) + "."],
        "recommended_action": "Complete Import / Paste Job Description",
        "next_action": "Paste the job description and re-score before generating package.",
        "confidence": "Low",
        "top_matching_skills": [],
        "top_matching_projects": [],
        "top_matching_experience": [],
        "missing_keywords": [],
        "recommended_resume_profile": None,
        "tailoring_notes": [],
        "incomplete_import": True,
        "missing_required_fields": missing,
    }


def _flatten_strings(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        strings = []
        for nested in value.values():
            strings.extend(_flatten_strings(nested))
        return strings
    if isinstance(value, list):
        strings = []
        for nested in value:
            strings.extend(_flatten_strings(nested))
        return strings
    return [str(value)]


def _normalize_text(text: str) -> str:
    text = text.lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9+]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _stem_token(token: str) -> str:
    if token == "strategic":
        return "strategy"
    if token in {"operational", "operations"}:
        return "operation"
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith("s"):
        return token[:-1]
    return token


def _terms(text: str) -> List[str]:
    normalized = _normalize_text(text)
    return [
        _stem_token(token)
        for token in normalized.split()
        if token and token not in GENERIC_TERMS and len(token) > 2
    ]


def _term_set(text: str) -> Set[str]:
    return set(_terms(text))


def _keyword_matches_text(keyword: str, text: str, allow_partial: bool = False) -> bool:
    normalized_keyword = _normalize_text(keyword)
    normalized_text = _normalize_text(text)

    if not normalized_keyword:
        return False
    if normalized_keyword in normalized_text:
        return True

    keyword_terms = _terms(keyword)
    if not keyword_terms:
        return False

    text_terms = _term_set(text)
    matches = sum(1 for term in keyword_terms if term in text_terms)
    if allow_partial:
        required_matches = max(1, len(keyword_terms) - 1)
    elif len(keyword_terms) <= 2:
        required_matches = len(keyword_terms)
    else:
        required_matches = len(keyword_terms) - 1
    return matches >= required_matches


def _dedupe(values: Iterable[str]) -> List[str]:
    seen = set()
    deduped = []
    for value in values:
        normalized = _normalize_text(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(value)
    return deduped


def _job_terms(parsed_job: Dict[str, Any]) -> List[str]:
    values = []
    values.extend(parsed_job.get("keywords", []))
    values.extend(_flatten_strings(parsed_job.get("responsibilities", [])))
    values.extend(_flatten_strings(parsed_job.get("qualifications", [])))
    return _dedupe([value for value in values if isinstance(value, str)])


def _important_keywords(parsed_job: Dict[str, Any]) -> List[str]:
    keywords = parsed_job.get("keywords", [])
    return [keyword for keyword in keywords if keyword and _terms(str(keyword))]


def _skills_from_data(career_data: Dict[str, Any]) -> List[str]:
    skill_groups = career_data["data"]["skills"].get("skill_groups", {})
    return _dedupe(_flatten_strings(skill_groups))


def _candidate_text(career_data: Dict[str, Any]) -> str:
    sections = [
        career_data["data"].get("skills", {}),
        career_data["data"].get("achievements", {}),
        career_data["data"].get("positions", {}),
        career_data["data"].get("projects", {}),
        career_data["data"].get("personal_brand", {}),
        career_data["config"].get("role_profiles", {}),
    ]
    return "\n".join(_flatten_strings(sections))


def _matched_keywords_for_text(keywords: Sequence[str], text: str, allow_partial: bool = False) -> List[str]:
    return [keyword for keyword in keywords if _keyword_matches_text(str(keyword), text, allow_partial)]


def _score_from_count(matched_count: int, target_count: int) -> float:
    if target_count <= 0:
        return 0.0
    return min(100.0, (matched_count / float(target_count)) * 100.0)


def _top_matching_skills(career_data: Dict[str, Any], parsed_job: Dict[str, Any]) -> List[str]:
    job_text = "\n".join(_job_terms(parsed_job))
    matches = []
    for skill in _skills_from_data(career_data):
        if _keyword_matches_text(skill, job_text, allow_partial=True):
            matches.append(skill)
            continue

        skill_terms = set(_terms(skill))
        job_terms = _term_set(job_text)
        if skill_terms and len(skill_terms.intersection(job_terms)) >= max(1, len(skill_terms) - 1):
            matches.append(skill)

    return matches[:10]


def _top_matching_projects(career_data: Dict[str, Any], keywords: Sequence[str]) -> List[Dict[str, Any]]:
    projects = career_data["data"]["projects"].get("projects", [])
    matches = []

    for project in projects:
        text = "\n".join(_flatten_strings(project))
        matched_keywords = _matched_keywords_for_text(keywords, text)
        if not matched_keywords:
            continue
        matches.append(
            {
                "name": project.get("name", "Unnamed project"),
                "matched_keywords": matched_keywords[:5],
            }
        )

    return sorted(matches, key=lambda item: len(item["matched_keywords"]), reverse=True)[:3]


def _top_matching_experience(career_data: Dict[str, Any], keywords: Sequence[str]) -> List[Dict[str, Any]]:
    experience_items = []

    for achievement in career_data["data"]["achievements"].get("achievements", []):
        text = "\n".join(_flatten_strings(achievement))
        matched_keywords = _matched_keywords_for_text(keywords, text)
        if matched_keywords:
            experience_items.append(
                {
                    "source": "achievement",
                    "title": achievement.get("theme", achievement.get("id", "Achievement")),
                    "matched_keywords": matched_keywords[:5],
                }
            )

    for position in career_data["data"]["positions"].get("positions", []):
        text = "\n".join(_flatten_strings(position))
        matched_keywords = _matched_keywords_for_text(keywords, text)
        if matched_keywords:
            experience_items.append(
                {
                    "source": "position",
                    "title": position.get("company", "Position"),
                    "matched_keywords": matched_keywords[:5],
                }
            )

    return sorted(experience_items, key=lambda item: len(item["matched_keywords"]), reverse=True)[:5]


def _target_company_score(career_data: Dict[str, Any], parsed_job: Dict[str, Any]) -> float:
    company = parsed_job.get("company")
    if not company:
        return 0.0

    for target_company in career_data["config"]["target_companies"].get("target_companies", []):
        if _normalize_text(target_company.get("name", "")) == _normalize_text(str(company)):
            return 40.0
    return 0.0


def _target_role_score(career_data: Dict[str, Any], parsed_job: Dict[str, Any]) -> float:
    title = parsed_job.get("job_title") or ""
    title_terms = _term_set(str(title))
    if not title_terms:
        return 0.0

    best_score = 0.0
    for role_profile in career_data["config"]["role_profiles"].get("role_profiles", []):
        role_text = "\n".join(_flatten_strings(role_profile))
        role_terms = _term_set(role_text)
        if not role_terms:
            continue
        overlap = len(title_terms.intersection(role_terms))
        best_score = max(best_score, min(35.0, overlap / float(len(title_terms)) * 35.0))

    return best_score


def _industry_alignment_score(career_data: Dict[str, Any], parsed_job: Dict[str, Any]) -> float:
    candidate_industries = career_data["data"]["personal_brand"].get("target_industries", [])
    target_company_industries = []
    company = parsed_job.get("company")

    for target_company in career_data["config"]["target_companies"].get("target_companies", []):
        if company and _normalize_text(target_company.get("name", "")) == _normalize_text(str(company)):
            target_company_industries.extend(target_company.get("industries", []))

    candidate_terms = _term_set(" ".join(_flatten_strings(candidate_industries)))
    job_terms = _term_set(" ".join(_job_terms(parsed_job) + _flatten_strings(target_company_industries)))
    if not candidate_terms:
        return 0.0

    overlap = len(candidate_terms.intersection(job_terms))
    return min(25.0, overlap / float(max(1, min(len(candidate_terms), 4))) * 25.0)


def _alignment_score(career_data: Dict[str, Any], parsed_job: Dict[str, Any]) -> float:
    return min(
        100.0,
        _target_company_score(career_data, parsed_job)
        + _target_role_score(career_data, parsed_job)
        + _industry_alignment_score(career_data, parsed_job),
    )


def _match_band(score: float) -> str:
    if score >= 90:
        return "Excellent fit"
    if score >= 75:
        return "Strong fit"
    if score >= 60:
        return "Possible fit"
    if score >= 40:
        return "Weak fit"
    return "Poor fit"


def _recommended_resume_profile(parsed_job: Dict[str, Any]) -> str:
    text = " ".join(
        _flatten_strings(
            [
                parsed_job.get("job_title"),
                parsed_job.get("keywords", []),
                parsed_job.get("responsibilities", []),
                parsed_job.get("qualifications", []),
            ]
        )
    )

    best_profile = "executive_operations"
    best_count = -1
    for profile, keywords in RESUME_PROFILE_KEYWORDS.items():
        count = sum(1 for keyword in keywords if _keyword_matches_text(keyword, text, allow_partial=True))
        if count > best_count:
            best_profile = profile
            best_count = count

    return best_profile


def _missing_keywords(keywords: Sequence[str], candidate_text: str) -> List[str]:
    missing = []
    for keyword in keywords:
        if not _keyword_matches_text(str(keyword), candidate_text):
            missing.append(str(keyword))
    return missing[:8]


def _tailoring_notes(
    report: Dict[str, Any],
    top_skills: Sequence[str],
    top_projects: Sequence[Dict[str, Any]],
    top_experience: Sequence[Dict[str, Any]],
) -> List[str]:
    notes = []

    if top_skills:
        notes.append("Emphasize " + ", ".join(top_skills[:3]) + " as the opening skills cluster.")

    if report["missing_keywords"]:
        notes.append("Add or validate language for " + ", ".join(report["missing_keywords"][:3]) + " where it is accurate.")

    if top_projects:
        notes.append("Elevate " + str(top_projects[0]["name"]) + " as the strongest project proof point.")

    if top_experience:
        notes.append("Lead experience bullets with " + str(top_experience[0]["title"]) + " because it carries the strongest overlap.")

    if report["match_score"] >= 75:
        notes.append("This role is worth applying to based on the current structured data match.")
    else:
        notes.append("Apply selectively unless the missing keywords can be supported with accurate examples.")

    return notes[:6]


def persisted_match_fields(report: Dict[str, Any]) -> Dict[str, Any]:
    """Return only the Sprint 13 fields stored on a tracker record."""
    return {
        field: report[field]
        for field in MATCH_PERSISTENCE_FIELDS
        if field in report and report[field] is not None
    }


def _empty_career_data() -> Dict[str, Any]:
    """Allow isolated intake fixtures to score safely without a full profile tree."""
    return {
        "data": {
            "skills": {"skill_groups": {}},
            "achievements": {"achievements": []},
            "positions": {"positions": []},
            "projects": {"projects": []},
            "personal_brand": {"target_industries": []},
        },
        "config": {
            "role_profiles": {"role_profiles": []},
            "target_companies": {"target_companies": []},
        },
    }


def _signal_groups(text: str) -> List[str]:
    lowered = text.lower()
    return [
        label
        for label, signals in FUNCTIONAL_SIGNAL_GROUPS
        if any(signal in lowered for signal in signals)
    ]


def _functional_fit(text: str) -> Tuple[int, List[str]]:
    matched = _signal_groups(text)
    if not matched:
        return 20, matched
    return min(100, 30 + (25 * len(matched))), matched


def _functional_evidence_alignment(role_text: str, candidate_text: str) -> Dict[str, Any]:
    """Distinguish direct evidence, sustained adjacency, and weak transferability."""
    role = role_text.lower()
    candidate = candidate_text.lower()
    direct = [
        signal
        for signal in DIRECT_FUNCTION_SIGNALS
        if signal in role and signal in candidate
    ]
    adjacent = [
        label
        for label, role_signals, candidate_signals in FUNCTIONAL_ADJACENCY_GROUPS
        if any(signal in role for signal in role_signals)
        and any(signal in candidate for signal in candidate_signals)
    ]
    if len(direct) >= 2:
        level, score = "Direct match", 100
    elif len(adjacent) >= 3:
        level, score = "Strong functional adjacency", 90
    else:
        level, score = "Weak transferability", 40
    return {
        "level": level,
        "score": score,
        "direct_capabilities": direct,
        "adjacent_capabilities": adjacent,
    }


def _seniority_fit(title: Any, role_text: Any = "") -> Tuple[int, str, Optional[str]]:
    lowered = str(title or "").lower()
    combined = f"{lowered}\n{str(role_text or '').lower()}"
    executive_scope = bool(
        (
            lowered.startswith("chief ")
            and "chief of staff" not in lowered
        )
        or any(signal in lowered for signal in ("executive vice president", "senior vice president"))
        or (
            any(signal in lowered for signal in ("vice president", "vp "))
            and any(
                signal in combined
                for signal in (
                    "enterprise-wide executive ownership",
                    "company-wide executive ownership",
                    "c-suite accountability",
                    "board accountability",
                )
            )
        )
    )
    if executive_scope:
        return (
            35,
            "",
            "The role requires enterprise executive scope beyond the evidence profile's Group Director ownership.",
        )
    if any(signal in lowered for signal in ("vice president", "vp ", "head of", "group director", "director")):
        return 100, "The seniority is aligned with Trisha's director/head-of target level.", None
    if any(signal in lowered for signal in ("senior manager", "sr. manager", "sr manager", "principal", "lead")):
        return 90, "The seniority is aligned with Trisha's senior manager/lead target range.", None
    if "manager" in lowered or "senior" in lowered:
        demonstrated_scope = any(
            signal in combined
            for signal in (
                "lead a high-impact team",
                "lead the team",
                "supervise",
                "mentor",
                "people management",
                "team ownership",
                "strategic direction",
            )
        )
        return (
            100 if demonstrated_scope else 85,
            (
                "The responsibilities demonstrate team and operational ownership compatible with Trisha's Group Director experience."
                if demonstrated_scope
                else "The Manager title is treated as neutral; confirm responsibilities and decision scope."
            ),
            None,
        )
    if any(signal in lowered for signal in ("coordinator", "assistant", "junior", "entry level", "associate")):
        return 20, "", "The role is materially below Trisha's established scope and target seniority."
    return 70, "The title is neutral; responsibilities and decision scope should determine level fit.", None


def _industry_fit(text: str, company: Any = "") -> Tuple[int, Optional[str], bool]:
    lowered = text.lower()
    matches = [signal for signal in TARGET_INDUSTRY_SIGNALS if signal in lowered]
    company_lowered = str(company or "").lower()
    pure_agency = "agency" in company_lowered and not any(
        signal in lowered for signal in ("client-side", "in-house", "brand role", "brand team")
    )
    if matches:
        score = min(100, 75 + (8 * min(len(matches), 4)))
        if pure_agency:
            score = min(score, 60)
        return score, matches[0], pure_agency
    if pure_agency:
        return 35, None, True
    return 55, None, False


def _salary_amounts(salary_value: Any, raw_text: str) -> List[int]:
    salary_text = str(salary_value or "")
    candidates = [salary_text]
    amounts: List[int] = []
    for candidate in candidates:
        for raw_number, suffix in re.findall(
            r"(?<!\d)\$?\s*(\d{2,6}(?:,\d{3})*(?:\.\d+)?)\s*([kK]?)(?!\w)",
            candidate,
        ):
            number = float(raw_number.replace(",", ""))
            if suffix or number < 1000:
                number *= 1000
            if 30000 <= number <= 1000000:
                amounts.append(int(number))
    return sorted(set(amounts))


def _salary_fit(salary_value: Any, raw_text: str) -> Tuple[int, str, Optional[str]]:
    disclosed = bool(
        str(salary_value or "").strip()
        and str(salary_value or "").strip().lower() not in {"not disclosed", "unknown", "n/a"}
    )
    amounts = _salary_amounts(salary_value, raw_text) if disclosed else []
    if not amounts:
        # Missing compensation is a posting-completeness issue, not a candidate-fit gap.
        return 100, "Not disclosed", None
    minimum, maximum = min(amounts), max(amounts)
    display = str(salary_value).strip()
    if minimum >= 150000:
        return 100, display, None
    if maximum >= 150000:
        return 90, display, None
    if minimum >= 120000:
        return 78, display, None
    if maximum >= 120000:
        return 68, display, "The lower end of the range is below Trisha's $120k caution threshold."
    if maximum >= 85000:
        return (
            45,
            display,
            "Compensation is below the $120k caution threshold; pursue only if the role is a strategic doorway.",
        )
    return 25, display, "Compensation is materially below Trisha's target range."


def _work_arrangement(parsed_job: Dict[str, Any]) -> Tuple[int, str, Optional[str]]:
    raw_text = str(parsed_job.get("raw_text") or "")
    labeled = re.search(
        r"^\s*Work arrangement\s*:\s*(.+?)\s*$", raw_text, flags=re.I | re.M
    )
    arrangement = str(parsed_job.get("work_arrangement") or "").strip()
    if not arrangement and labeled:
        arrangement = labeled.group(1).strip()
    # A reviewed arrangement is authoritative even when the original description
    # contains stale or conflicting importer text.
    combined = (
        arrangement
        if arrangement and arrangement.lower() != "not specified"
        else f"{parsed_job.get('location') or ''} {raw_text}"
    ).lower()
    heavy_onsite = bool(
        re.search(r"(?:minimum of\s+)?[4-5]\s+days?\s+per week\s+in (?:the )?office", combined)
        or "#li-onsite" in combined
    )
    if heavy_onsite:
        return 25, arrangement or "Heavy on-site", "The heavy on-site requirement is a practical constraint, especially at lower pay."
    if "remote" in combined:
        return 100, arrangement or "Remote", None
    if "hybrid" in combined:
        return 88, arrangement or "Hybrid", None
    if any(signal in combined for signal in ("on-site", "onsite", "in office", "in-office")):
        return 45, arrangement or "On-site", "The on-site requirement should be weighed against commute and compensation."
    if "flexible" in combined:
        return 82, arrangement or "Flexible", None
    # An unavailable arrangement is neutral until an actual incompatibility is known.
    return 100, arrangement or "Not specified", None


def _confidence(parsed_job: Dict[str, Any], salary_display: str, work_label: str, freshness: Dict[str, Any]) -> str:
    missing = sum(
        (
            not bool(parsed_job.get("job_title")),
            not bool(parsed_job.get("company")),
            not bool(parsed_job.get("location")),
            salary_display == "Not disclosed",
            work_label == "Not specified",
            freshness.get("age_days") is None,
            not bool(parsed_job.get("source_url")),
            str(parsed_job.get("salary_source") or "").lower() == "manual",
        )
    )
    if missing <= 1:
        confidence = "High"
    elif missing <= 3:
        confidence = "Medium"
    else:
        confidence = "Low"
    if salary_display == "Not disclosed" and confidence == "High":
        return "Medium"
    return confidence


def _match_tier(score: int) -> str:
    if score >= 82:
        return "Strong Match"
    if score >= 68:
        return "Good Match"
    if score >= 55:
        return "Stretch Match"
    if score >= 35:
        return "Weak Match"
    return "Pass"


def _interpretation_assessment(
    interpretation: Dict[str, Any],
    candidate_text: str,
    functional_evidence: Dict[str, Any],
    alignment_matrix: Optional[List[Dict[str, Any]]] = None,
    gap_analysis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Make the interpreter-to-score handoff explicit and auditable."""
    assessed_requirements = []
    for requirement in interpretation.get("true_must_haves") or []:
        supported = _keyword_matches_text(str(requirement), candidate_text, allow_partial=True)
        assessed_requirements.append(
            {
                "requirement": str(requirement),
                "assessment": "Supported by profile language" if supported else "Needs verification",
            }
        )
    checks = []
    technical = str(interpretation.get("technical_depth") or "Unclear")
    if technical in {"High", "Moderate", "Unclear"}:
        checks.append(
            {
                "field": "technical_depth",
                "interpreted_value": technical,
                "assessment": functional_evidence.get("level", "Needs verification"),
                "question": "Confirm implementation, troubleshooting, API/integration, and coding depth.",
            }
        )
    for field, question in (
        ("people_management_expectation", "Confirm formal people-management scope and team composition."),
        ("client_facing_expectation", "Confirm direct client interaction and escalation ownership."),
        ("strategic_vs_execution_balance", "Confirm the expected balance of strategy and detailed execution."),
    ):
        checks.append(
            {
                "field": field,
                "interpreted_value": interpretation.get(field),
                "assessment": "Explicitly considered in fit review",
                "question": question,
            }
        )
    direct = [str(value) for value in functional_evidence.get("direct_capabilities") or []]
    adjacent = [str(value) for value in functional_evidence.get("adjacent_capabilities") or []]
    return {
        "interpretation_source": "user_reviewed" if interpretation.get("user_reviewed") else "automatic",
        "fields_passed_into_scoring": list(INTERPRETATION_SCORE_FIELDS),
        "primary_archetype_assessed": interpretation.get("primary_archetype"),
        "assessed_requirements": assessed_requirements,
        "dimension_checks": checks,
        "directly_relevant_evidence": direct,
        "adjacent_relevance": adjacent,
        "capability_alignment_matrix": list(alignment_matrix or []),
        "evidence_gap_analysis": dict(gap_analysis or {}),
        "verification_needed": [
            item["requirement"]
            for item in assessed_requirements
            if item["assessment"] == "Needs verification"
        ] + list(interpretation.get("major_fit_questions") or []),
        "consistent": True,
    }


def _decision_match_report(
    parsed_job: Dict[str, Any],
    legacy_report: Dict[str, Any],
    role_interpretation: Dict[str, Any],
    candidate_text: str,
    capability_alignment_matrix: Optional[List[Dict[str, Any]]] = None,
    gap_analysis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    raw_text = str(parsed_job.get("raw_text") or "")
    title = str(parsed_job.get("job_title") or "")
    combined = f"{title}\n{parsed_job.get('company') or ''}\n{raw_text}"
    substantive_role = substantive_interpretation_text(role_interpretation)
    functional_score, functional_matches = _functional_fit(substantive_role)
    functional_evidence = dict(legacy_report.get("functional_evidence") or {})
    interpretation_assessment = _interpretation_assessment(
        role_interpretation,
        candidate_text,
        functional_evidence,
        capability_alignment_matrix,
        gap_analysis,
    )
    adjacency_score = int(functional_evidence.get("score") or 40)
    capability_rows = list(capability_alignment_matrix or [])
    recognized_capability_rows = [
        row for row in capability_rows if row.get("underlying_capabilities")
    ]
    capability_score = (
        capability_alignment_score(capability_rows)
        if recognized_capability_rows
        else 60
        if capability_rows
        else 0
    )
    seniority_score, seniority_strength, seniority_material_gap = _seniority_fit(
        title, combined
    )
    industry_score, industry_signal, pure_agency = _industry_fit(
        combined, parsed_job.get("company")
    )
    salary_score, salary_display, salary_gap = _salary_fit(parsed_job.get("salary_range"), raw_text)
    work_score, work_label, work_gap = _work_arrangement(parsed_job)
    freshness = detect_job_freshness(raw_text)
    non_fit_signals = [signal for signal in OBVIOUS_NON_FIT_SIGNALS if signal in combined.lower()]
    dimension_scores = {
        "evidence_base": int(legacy_report["match_score"]),
        "functional_alignment": functional_score,
        "functional_evidence": adjacency_score,
        "capability_alignment": capability_score,
        "seniority_scope": seniority_score,
        "industry_domain": industry_score,
        "compensation": salary_score,
        "work_arrangement": work_score,
    }
    dimensions = {
        key: {
            "score": value,
            "weight": DECISION_WEIGHTS[key],
            "points": round(value * DECISION_WEIGHTS[key], 2),
        }
        for key, value in dimension_scores.items()
    }
    penalties = []
    if seniority_material_gap:
        penalties.append(
            {"reason": seniority_material_gap, "points": -10}
        )
    if non_fit_signals:
        penalties.append(
            {
                "reason": f"Likely hard non-fit requirement: {non_fit_signals[0]}",
                "points": -15,
            }
        )
    technical_gap = bool(
        role_interpretation.get("technical_depth") == "High"
        and functional_evidence.get("level") == "Weak transferability"
    )
    if technical_gap:
        penalties.append(
            {
                "reason": "The interpreted role requires high hands-on technical depth that is not directly established in the evidence profile.",
                "points": -8,
            }
        )
    pre_penalty_score = sum(item["points"] for item in dimensions.values())
    raw_score = pre_penalty_score + sum(item["points"] for item in penalties)
    score = round(raw_score)
    score = int(max(0, min(100, score)))
    tier = _match_tier(score)
    initial_tier = tier

    strengths: List[str] = []
    if functional_matches:
        strengths.append("Functional alignment includes " + ", ".join(functional_matches[:3]) + ".")
    if functional_evidence.get("level") == "Direct match":
        strengths.append("Career evidence shows direct ownership of closely matching technical and operational capabilities.")
    elif functional_evidence.get("level") == "Strong functional adjacency":
        adjacent = functional_evidence.get("adjacent_capabilities") or []
        strengths.append(
            "Sustained career evidence establishes strong functional adjacency"
            + (" across " + ", ".join(str(value) for value in adjacent[:3]) if adjacent else "")
            + "."
        )
    if seniority_strength:
        strengths.append(seniority_strength)
    if industry_signal and not pure_agency:
        strengths.append(f"The {industry_signal} context is adjacent to Trisha's target industries.")
    if salary_display != "Not disclosed" and salary_score >= 78:
        strengths.append("The disclosed compensation is aligned with or near Trisha's target.")
    if work_score >= 82:
        strengths.append(f"The {work_label.lower()} arrangement supports practical fit.")
    if legacy_report.get("top_matching_skills"):
        strengths.append(
            "Career evidence overlaps in "
            + ", ".join(str(value) for value in legacy_report["top_matching_skills"][:3])
            + "."
        )
    fallback_strengths = (
        "The role has enough detail for a pre-package fit review.",
        "The role title and employer are clearly identified.",
        "The listing can be evaluated before spending package-generation time.",
    )
    for strength in fallback_strengths:
        if len(strengths) >= 3:
            break
        strengths.append(strength)

    gaps: List[str] = []
    material_fit_gaps: List[str] = []
    diligence_cautions: List[str] = []
    if salary_gap:
        gaps.append(salary_gap)
        if salary_score <= 45:
            material_fit_gaps.append(salary_gap)
    if work_gap:
        gaps.append(work_gap)
        if work_score <= 45:
            material_fit_gaps.append(work_gap)
    if seniority_material_gap:
        gaps.append(seniority_material_gap)
        material_fit_gaps.append(seniority_material_gap)
    if pure_agency:
        caution = "This appears to be an agency role; confirm that the scope is strategic and client-side adjacent."
        gaps.append(caution)
        diligence_cautions.append(caution)
    if non_fit_signals:
        gap = f"The listing includes a likely hard non-fit requirement: {non_fit_signals[0]}."
        gaps.append(gap)
        material_fit_gaps.append(gap)
    if technical_gap:
        gap = "High hands-on technical depth is material to this role and is not directly established in the current evidence profile."
        gaps.append(gap)
        material_fit_gaps.append(gap)
    if not functional_matches:
        gap = "The listing shows limited alignment with Trisha's core operations background."
        gaps.append(gap)
        material_fit_gaps.append(gap)
    elif functional_evidence.get("level") == "Weak transferability":
        gap = "The role's required function has limited support in the current evidence profile."
        gaps.append(gap)
        material_fit_gaps.append(gap)
    if not gaps:
        caution = "Confirm the reporting line and decision authority before generating the package."
        gaps.append(caution)
        diligence_cautions.append(caution)

    if freshness.get("is_closed"):
        action = "Review First"
    elif tier in {"Strong Match", "Good Match"}:
        action = "Generate Package"
    elif tier == "Stretch Match":
        action = "Review First"
    elif tier == "Weak Match" and industry_score >= 75 and functional_score >= 55:
        action = "Review First"
    else:
        action = "Pass"
    if freshness.get("is_stale") and action == "Generate Package":
        action = "Review First"
    if diligence_cautions and functional_evidence.get("level") == "Strong functional adjacency":
        action = "Review First"

    verification_notes: List[str] = []
    if not str(parsed_job.get("location") or "").strip():
        verification_notes.append("Location unavailable.")
    if work_label == "Not specified":
        verification_notes.append("Work arrangement unavailable.")
    if salary_display == "Not disclosed":
        verification_notes.append("Salary information unavailable.")
    elif str(parsed_job.get("salary_source") or "").lower() == "manual":
        verification_notes.append("Salary entered manually; confirm against the original posting.")
    if freshness.get("is_closed"):
        verification_notes.append("The posting appears closed; confirm its status before generating a package.")
    elif freshness.get("age_days") is None:
        verification_notes.append("Posting date unavailable.")
    elif freshness.get("category") in {"Aging", "Stale"}:
        verification_notes.append(
            f"Posting is {freshness['category'].lower()} at {freshness['age_days']} days old."
        )

    lead = {
        "Strong Match": "Strong alignment across Trisha's core experience, target level, and practical priorities.",
        "Good Match": "Good overall alignment, with a few cautions to weigh before investing further.",
        "Stretch Match": "There is credible alignment, but the tradeoffs deserve review before package generation.",
        "Weak Match": "The role has some overlap but falls short on important fit factors.",
        "Pass": "The current listing is not a sensible package-generation priority.",
    }[tier]
    if salary_score <= 45 and industry_score >= 75 and tier in {"Good Match", "Stretch Match"}:
        lead = "This could be a strategic doorway into a target industry, but the compensation gap is material."

    data_confidence = _confidence(parsed_job, salary_display, work_label, freshness)
    score_breakdown = {
        "base_score": int(legacy_report["match_score"]),
        "base_components": dict(legacy_report.get("evidence_base_breakdown") or {}),
        "dimensions": dimensions,
        "pre_penalty_score": round(pre_penalty_score, 2),
        "penalties": penalties,
        "raw_score": round(raw_score, 2),
        "rounding": "nearest integer",
        "floor": 0,
        "cap": 100,
        "final_score": score,
        "classification_thresholds": {
            "Strong Match": 82,
            "Good Match": 68,
            "Stretch Match": 55,
            "Weak Match": 35,
        },
        "initial_classification": initial_tier,
        "final_classification": tier,
        "consistency_adjustment": None,
        "interpretation_inputs": {
            field: role_interpretation.get(field)
            for field in INTERPRETATION_SCORE_FIELDS
        },
        "capability_alignment": {
            "score": capability_score,
            "matrix": list(capability_alignment_matrix or []),
            "weights": {
                "Direct": 1.0,
                "Strong Adjacent": 0.82,
                "Transferable": 0.58,
                "Weak": 0.25,
                "Unsupported": 0.0,
            },
        },
    }
    legacy_report.update(
        {
            "salary_range": salary_display,
            "match_score": score,
            "match_band": _match_band(score),
            "match_tier": tier,
            "match_summary": lead,
            "match_strengths": _dedupe(strengths)[:5],
            "match_gaps": _dedupe(gaps)[:5],
            "recommended_action": action,
            "confidence": data_confidence,
            "data_confidence": data_confidence,
            "verification_notes": _dedupe(verification_notes),
            "match_verification_notes": _dedupe(verification_notes),
            "material_fit_gaps": _dedupe(material_fit_gaps),
            "diligence_cautions": _dedupe(diligence_cautions),
            "score_breakdown": score_breakdown,
            "role_interpretation": role_interpretation,
            "interpretation_assessment": interpretation_assessment,
        }
    )
    return legacy_report


def _enforce_classification_consistency(report: Dict[str, Any]) -> Dict[str, Any]:
    """Require a concrete material gap before a role can remain Stretch."""
    material_gaps = [
        str(value).strip()
        for value in (report.get("material_fit_gaps") or [])
        if str(value).strip()
    ]
    initial_tier = str(report.get("match_tier") or "")
    adjustment = None
    if initial_tier == "Stretch Match" and not material_gaps:
        report["match_tier"] = "Good Match"
        report["match_summary"] = (
            "Substantial direct or strongly adjacent alignment, with only diligence items to confirm."
        )
        report["recommended_action"] = "Review First"
        adjustment = "Stretch classification removed because no material fit gap was identified."

    report["classification_consistency"] = {
        "initial_classification": initial_tier,
        "final_classification": report.get("match_tier"),
        "material_gap_required_for_stretch": True,
        "material_fit_gaps": material_gaps,
        "adjustment": adjustment,
        "consistent": not (
            report.get("match_tier") == "Stretch Match" and not material_gaps
        ),
    }
    breakdown = report.get("score_breakdown")
    if isinstance(breakdown, dict):
        breakdown["final_classification"] = report.get("match_tier")
        breakdown["consistency_adjustment"] = adjustment
    return report


def _score_parsed_job(
    parsed_job: Dict[str, Any],
    root: Path,
    role_interpretation: Optional[Dict[str, Any]] = None,
    evidence_selection_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    try:
        career_data = load_all_yaml(root)
    except DataLoadError:
        career_data = _empty_career_data()
    keywords = _important_keywords(parsed_job)
    resume_candidate_text = _candidate_text(career_data)
    evidence_profile = load_evidence_profile(root)
    profile_text = evidence_text(evidence_profile, "match_scoring")
    candidate_text = "\n".join(
        value for value in (resume_candidate_text, profile_text) if value.strip()
    )

    top_skills = _top_matching_skills(career_data, parsed_job)
    top_projects = _top_matching_projects(career_data, keywords)
    top_experience = _top_matching_experience(career_data, keywords)
    missing_keywords = _missing_keywords(keywords, candidate_text)

    skill_score = _score_from_count(len(top_skills), 6)
    experience_matched_keywords = set()
    for item in top_experience:
        experience_matched_keywords.update(item["matched_keywords"])
    experience_score = _score_from_count(len(experience_matched_keywords), 8)
    project_score = _score_from_count(len(top_projects), 2)
    alignment_score = _alignment_score(career_data, parsed_job)
    supplied = dict(role_interpretation or {})
    overrides = dict(supplied.get("user_overrides") or {})
    if supplied.get("user_reviewed"):
        overrides["user_reviewed"] = True
        for field in (
            "primary_archetype", "secondary_archetype", "plain_english_summary",
            "technical_depth",
            "people_management_expectation", "client_facing_expectation",
            "strategic_vs_execution_balance",
        ):
            if supplied.get(field) not in (None, ""):
                overrides[field] = supplied[field]
    interpreted = interpret_role(parsed_job, overrides or None)
    interpreted.setdefault("diagnostics", {})["evidence_profile_consulted"] = True
    interpreted["evidence_profile_context"] = {
        "verified_evidence_count": len(
            [
                item for item in evidence_profile.get("evidence") or []
                if item.get("verification_status") in {"Verified", "User Confirmed"}
            ]
        ),
        "rule": "Candidate experience conclusions must consult verified and user-confirmed evidence, not resume text alone.",
    }
    functional_evidence = _functional_evidence_alignment(
        substantive_interpretation_text(interpreted), candidate_text
    )
    capability_graph = load_capability_graph(root, evidence_profile)
    alignment_requirements = [
        str(value)
        for value in [
            *(interpreted.get("true_must_haves") or []),
            *(interpreted.get("top_responsibilities") or []),
        ]
        if str(value).strip() and len(str(value)) <= 700
    ][:10]
    capability_alignment_matrix = build_alignment_matrix(
        alignment_requirements, capability_graph, evidence_profile
    )
    gap_analysis = evidence_gap_analysis(
        alignment_requirements, evidence_profile, resume_candidate_text
    )
    selected_profile_evidence = select_profile_evidence(
        {**parsed_job, "primary_archetype": interpreted.get("primary_archetype")},
        evidence_profile,
        usage="match_scoring",
        max_items=8,
    )
    interpreted["evidence_profile_context"]["selected_evidence_ids"] = [
        item["id"] for item in selected_profile_evidence
    ]
    interpreted["evidence_profile_context"]["experience_language_rule"] = (
        "Use missing-from-resume language when verified profile evidence exists; reserve "
        "no-experience conclusions for truly absent or explicitly unsupported evidence."
    )
    role_evidence_selection = build_role_evidence_selection(
        {**parsed_job, "primary_archetype": interpreted.get("primary_archetype")},
        evidence_profile,
        capability_alignment_matrix,
        gap_analysis,
        evidence_selection_overrides,
        usage="match_scoring",
    )
    # From this point onward scoring and decision language use the exact saved final set,
    # rather than every verified fact in the global profile.
    final_selected_ids = set(role_evidence_selection.get("selected_evidence_ids") or [])
    selected_profile_evidence = [
        item for item in evidence_profile.get("evidence") or []
        if str(item.get("id")) in final_selected_ids
    ]
    selected_profile_text = evidence_text(
        {"evidence": selected_profile_evidence}, "match_scoring"
    )
    candidate_text = "\n".join(
        value for value in (resume_candidate_text, selected_profile_text) if value.strip()
    )
    missing_keywords = _missing_keywords(keywords, candidate_text)
    functional_evidence = _functional_evidence_alignment(
        substantive_interpretation_text(interpreted), candidate_text
    )

    match_score = round(
        (skill_score * 0.35)
        + (experience_score * 0.30)
        + (project_score * 0.20)
        + (alignment_score * 0.15)
    )

    report = {
        "job_title": parsed_job.get("job_title"),
        "company": parsed_job.get("company"),
        "location": parsed_job.get("location"),
        "salary_range": parsed_job.get("salary_range"),
        "match_score": int(max(0, min(100, match_score))),
        "match_band": _match_band(match_score),
        "top_matching_skills": top_skills,
        "top_matching_projects": top_projects,
        "top_matching_experience": top_experience,
        "missing_keywords": missing_keywords,
        "recommended_resume_profile": _recommended_resume_profile(parsed_job),
        "tailoring_notes": [],
        "functional_evidence": functional_evidence,
        "evidence_profile": {
            "source_of_truth": True,
            "selected_evidence_ids": [item["id"] for item in selected_profile_evidence],
            "selected_evidence": selected_profile_evidence,
            "verified_evidence_count": interpreted["evidence_profile_context"]["verified_evidence_count"],
        },
        "capability_graph": {
            "capability_count": len(capability_graph.get("capabilities") or []),
            "alignment_matrix": capability_alignment_matrix,
            "alignment_score": capability_alignment_score(capability_alignment_matrix),
        },
        "evidence_gap_analysis": gap_analysis,
        "role_evidence_selection": role_evidence_selection,
        "evidence_base_breakdown": {
            "skills": {"score": round(skill_score, 2), "weight": 0.35},
            "experience": {"score": round(experience_score, 2), "weight": 0.30},
            "projects": {"score": round(project_score, 2), "weight": 0.20},
            "target_alignment": {"score": round(alignment_score, 2), "weight": 0.15},
            "final": int(max(0, min(100, match_score))),
        },
    }
    report = _decision_match_report(
        parsed_job,
        report,
        interpreted,
        candidate_text,
        capability_alignment_matrix,
        gap_analysis,
    )
    role_lens = classify_role_lens(parsed_job)
    requirement_map = build_requirement_map(parsed_job, role_lens)
    report["role_lens"] = role_lens
    report["requirement_map"] = requirement_map
    if role_lens["primary"] == "people_operations":
        unsupported = _dedupe(
            str(item.get("normalized_concept") or "")
            for item in requirement_map
            if item.get("strength") == "Unsupported"
        )
        if unsupported:
            penalty = min(12, 2 * len(unsupported))
            report["match_score"] = max(0, int(report["match_score"]) - penalty)
            report["match_band"] = _match_band(report["match_score"])
            report["match_tier"] = _match_tier(report["match_score"])
            report["match_gaps"] = _dedupe(
                [
                    *report.get("match_gaps", []),
                    "Direct evidence is not established for: "
                    + ", ".join(unsupported[:5])
                    + ".",
                ]
            )[:5]
            report["material_fit_gaps"] = _dedupe(
                [
                    *report.get("material_fit_gaps", []),
                    "Direct evidence is not established for: "
                    + ", ".join(unsupported[:5])
                    + ".",
                ]
            )
            breakdown = report.get("score_breakdown")
            if isinstance(breakdown, dict):
                breakdown.setdefault("penalties", []).append(
                    {
                        "reason": "Unsupported role-lens requirements",
                        "points": -penalty,
                    }
                )
                breakdown["raw_score"] = round(
                    float(breakdown.get("raw_score") or 0) - penalty, 2
                )
                breakdown["final_score"] = report["match_score"]
                breakdown["initial_classification"] = report["match_tier"]
            if report.get("recommended_action") == "Generate Package":
                report["recommended_action"] = "Review First"
    report = _enforce_classification_consistency(report)
    report["tailoring_notes"] = _tailoring_notes(
        report, top_skills, top_projects, top_experience
    )
    return report


def score_job_data(job_data: Dict[str, Any], project_root: Optional[PathInput] = None) -> Dict[str, Any]:
    """Score unsaved intake data so the UI can show the gate before generation."""
    incomplete = incomplete_match_report(job_data)
    if incomplete:
        return incomplete
    root = Path(project_root) if project_root is not None else Path.cwd()
    raw_text = str(job_data.get("raw_text") or job_data.get("job_description") or "")
    metadata_lines = "\n".join(
        line
        for line in (
            f"# {job_data.get('job_title') or job_data.get('role') or ''}",
            f"Company: {job_data.get('company') or ''}",
            f"Location: {job_data.get('location') or ''}",
            f"Work arrangement: {job_data.get('work_arrangement') or ''}",
            f"Salary range: {job_data.get('salary_range') or ''}",
            f"Posting date: {job_data.get('posting_date') or ''}",
        )
        if not line.endswith(": ") and line != "# "
    )
    canonical_text = f"{metadata_lines}\n\n{raw_text}".strip()
    parsed_job = {
        "raw_text": canonical_text,
        "job_title": job_data.get("job_title") or job_data.get("role"),
        "company": job_data.get("company"),
        "location": job_data.get("location"),
        "salary_range": job_data.get("salary_range"),
        "posting_date": job_data.get("posting_date"),
        "work_arrangement": job_data.get("work_arrangement"),
        "salary_source": job_data.get("salary_source"),
        "source_url": job_data.get("source_url") or job_data.get("official_url"),
        "keywords": extract_keywords(canonical_text),
        "responsibilities": extract_responsibilities(canonical_text),
        "qualifications": extract_qualifications(canonical_text),
    }
    return _score_parsed_job(
        parsed_job,
        root,
        job_data.get("role_interpretation")
        if isinstance(job_data.get("role_interpretation"), dict)
        else None,
        job_data.get("evidence_selection_overrides")
        if isinstance(job_data.get("evidence_selection_overrides"), dict)
        else None,
    )


def score_job_match(
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
    role_interpretation: Optional[Dict[str, Any]] = None,
    evidence_selection_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return the legacy tailoring report plus the Sprint 13 decision gate."""
    root = Path(project_root) if project_root is not None else Path.cwd()
    parsed_job = parse_job_description(root / job_path)
    raw_text = str(parsed_job.get("raw_text") or "")
    description_match = re.search(
        r"^##\s+Job Description\s*$\n(.*)", raw_text, flags=re.I | re.M | re.S
    )
    incomplete = incomplete_match_report(
        {
            **parsed_job,
            "job_description": (
                description_match.group(1).strip() if description_match else raw_text
            ),
        }
    )
    if incomplete:
        return incomplete
    return _score_parsed_job(
        parsed_job, root, role_interpretation, evidence_selection_overrides
    )
