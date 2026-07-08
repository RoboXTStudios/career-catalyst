"""Build concise, upload-friendly filenames for generated career materials."""

import hashlib
import re
from typing import Any, Dict, Iterable, List, Optional


COMPANY_SHORT_NAMES: Dict[str, str] = {
    "sony interactive entertainment playstation": "PlayStation",
    "crunchyroll": "Crunchyroll",
    "google": "Google",
    "netflix": "Netflix",
    "tencent": "Tencent",
    "universal music group": "UMG",
    "600 umg recordings": "UMG",
    "600 umg recordings inc": "UMG",
    "paramount": "Paramount",
    "paramount streaming": "Paramount",
    "aeg worldwide axs": "AEGAXS",
    "warner music group": "WMG",
    "warner chappell music": "WMG",
    "warner chappell music inc": "WMG",
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
MAX_FILENAME_STEM_LENGTH = 120
MAX_ROLE_TITLE_LENGTH = 120
TITLE_SENTENCE_MARKERS = (
    "you will",
    "this role",
    "responsible for",
    "reports to",
    "as director",
    "as senior",
    "the role",
    "will own",
)


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


def role_title_issue(value: Any) -> Optional[str]:
    """Return why a value looks like description prose rather than a role title."""
    title = re.sub(r"\s+", " ", str(value or "").strip())
    lowered = title.lower()
    if not title:
        return "missing"
    if len(title) > MAX_ROLE_TITLE_LENGTH:
        return "too long"
    if any(marker in lowered for marker in TITLE_SENTENCE_MARKERS):
        return "contains job-description language"
    sentence_text = re.sub(r"\b(?:Sr|Jr|St)\.", "", title, flags=re.I)
    if (
        re.search(r"[.!?]\s*$", sentence_text)
        or re.search(r"[.!?]\s+[A-Z]", sentence_text)
        or len(re.findall(r"[.!?]", sentence_text)) > 1
    ):
        return "looks like a sentence"
    if len(title.split()) > 18:
        return "contains too many words"
    if title.count(",") >= 4 and re.search(
        r"\b(?:own|lead|manage|build|drive|support|develop|deliver)\b", lowered
    ):
        return "looks like job-description copy"
    return None


def is_valid_role_title(value: Any) -> bool:
    return role_title_issue(value) is None


def safe_filename(
    stem: Any,
    extension: str,
    *,
    lowercase: bool = False,
    max_stem_length: int = MAX_FILENAME_STEM_LENGTH,
) -> str:
    """Return a filesystem-safe, length-capped filename with stable collision hash."""
    safe_extension = "".join(re.findall(r"[A-Za-z0-9]+", str(extension or ""))).lower()
    if not safe_extension:
        raise ValueError("A filename extension is required.")
    raw_stem = re.sub(r"\s+", " ", str(stem or "").strip()).replace("&", " and ")
    clean_stem = re.sub(r"[^A-Za-z0-9]+", "_", raw_stem).strip("_")
    clean_stem = re.sub(r"_+", "_", clean_stem)
    if lowercase:
        clean_stem = clean_stem.lower()
    if not clean_stem:
        raise ValueError("A non-empty filename stem is required.")
    if len(clean_stem) > max_stem_length:
        digest = hashlib.sha256(clean_stem.encode("utf-8")).hexdigest()[:8]
        prefix_length = max(1, max_stem_length - len(digest) - 1)
        clean_stem = f"{clean_stem[:prefix_length].rstrip('_')}_{digest}"
    return f"{clean_stem}.{safe_extension}"


def compact_candidate_name(candidate_name: str) -> str:
    """Convert a candidate name to compact PascalCase."""
    return _pascal_case(_tokens(candidate_name)) or "Candidate"


def company_display_name(company: Any) -> str:
    """Return the familiar public company name for human-facing materials."""
    raw = re.sub(r"\s+", " ", str(company or "").strip())
    key = _key(raw)
    if not raw:
        return "Company"
    if "umg recordings" in key or "universal music group" in key:
        return "Universal Music Group"
    if "paramount" in key:
        return "Paramount"
    if "aeg" in key and ("axs" in key or "worldwide" in key):
        return "AEG/AXS"
    if "warner chappell" in key or "warner music group" in key:
        return "WMG"
    return re.sub(
        r"\s+(?:incorporated|inc\.?|llc|ltd\.?|limited|corporation|corp\.?)$",
        "",
        raw,
        flags=re.I,
    ).strip().rstrip(" ,.")


def short_company_name(company: str) -> str:
    """Return a concise company label, preferring known public-facing names."""
    display_name = company_display_name(company)
    known_name = COMPANY_SHORT_NAMES.get(_key(company)) or COMPANY_SHORT_NAMES.get(
        _key(display_name)
    )
    if known_name:
        return known_name

    tokens = [
        token
        for token in _tokens(display_name)
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
    if not is_valid_role_title(role_title):
        raise ValueError("Please confirm the role title before generating filenames.")
    components = (
        compact_candidate_name(candidate_name),
        short_role_name(role_title),
        short_company_name(company),
        short_export_type(export_type),
    )
    return safe_filename("_".join(components), extension)
