"""Build concise, upload-friendly filenames for generated career materials."""

import re
from typing import Dict, Iterable, List


COMPANY_SHORT_NAMES: Dict[str, str] = {
    "sony interactive entertainment playstation": "PlayStation",
    "crunchyroll": "Crunchyroll",
    "google": "Google",
    "netflix": "Netflix",
    "tencent": "Tencent",
}

ROLE_SHORT_NAMES: Dict[str, str] = {
    "head of global creative and product development operations": "HeadGlobalCreativeOps",
    "director enterprise strategy initiatives": "DirectorEnterpriseStrategy",
    "strategy and operations lead youtube auction brand": "StrategyOpsLeadYouTube",
    "operations lead ai creator platform": "OpsLeadAICreatorPlatform",
}

EXPORT_TYPE_NAMES: Dict[str, str] = {
    "styled": "Styled",
    "ats": "ATS",
    "cover letter": "CoverLetter",
    "recruiter message": "RecruiterMessage",
    "hiring manager message": "HiringManagerMessage",
    "application note": "ApplicationNote",
    "strategy pack": "StrategyPack",
}

ROLE_STOP_WORDS = {"a", "an", "and", "for", "of", "the"}
ROLE_ABBREVIATIONS = {
    "artificial": "AI",
    "operations": "Ops",
    "operational": "Ops",
}
COMPANY_SUFFIXES = {"inc", "incorporated", "llc", "ltd", "limited", "corporation", "corp"}
ACRONYMS = {"ai": "AI", "ats": "ATS", "qa": "QA", "dss": "DSS"}


def _key(value: str) -> str:
    return " ".join(re.findall(r"[A-Za-z0-9]+", value)).lower()


def _tokens(value: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9]+", value)


def _pascal_case(tokens: Iterable[str]) -> str:
    parts = []
    for token in tokens:
        lowered = token.lower()
        parts.append(ACRONYMS.get(lowered, lowered.capitalize()))
    return "".join(parts)


def compact_candidate_name(candidate_name: str) -> str:
    """Convert a candidate name to compact PascalCase."""
    return _pascal_case(_tokens(candidate_name)) or "Candidate"


def short_company_name(company: str) -> str:
    """Return a concise company label, preferring known public-facing names."""
    known_name = COMPANY_SHORT_NAMES.get(_key(company))
    if known_name:
        return known_name

    tokens = [
        token
        for token in _tokens(company)
        if token.lower() not in COMPANY_SUFFIXES
    ]
    return _pascal_case(tokens[:4]) or "Company"


def short_role_name(role_title: str) -> str:
    """Return a concise role label, preferring approved explicit mappings."""
    known_name = ROLE_SHORT_NAMES.get(_key(role_title))
    if known_name:
        return known_name

    shortened = []
    for token in _tokens(role_title):
        lowered = token.lower()
        if lowered in ROLE_STOP_WORDS:
            continue
        shortened.append(ROLE_ABBREVIATIONS.get(lowered, token))
        if len(shortened) == 6:
            break
    return _pascal_case(shortened) or "Role"


def short_export_type(export_type: str) -> str:
    """Normalize an export label to a compact filename component."""
    known_name = EXPORT_TYPE_NAMES.get(_key(export_type))
    if known_name:
        return known_name
    return _pascal_case(_tokens(export_type)) or "Export"


def build_upload_filename(
    candidate_name: str,
    role_title: str,
    company: str,
    export_type: str,
    extension: str,
) -> str:
    """Build a safe filename from candidate, role, company, and export type."""
    safe_extension = "".join(re.findall(r"[A-Za-z0-9]+", extension)).lower()
    if not safe_extension:
        raise ValueError("A filename extension is required.")

    components = (
        compact_candidate_name(candidate_name),
        short_role_name(role_title),
        short_company_name(company),
        short_export_type(export_type),
    )
    return "_".join(components) + f".{safe_extension}"
