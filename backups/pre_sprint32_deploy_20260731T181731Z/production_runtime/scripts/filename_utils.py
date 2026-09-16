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
    "beast industries": "Beast Industries",
}

# Exact employer identities shared by import, tracker, package, and filename flows.
# ATS board tokens are aliases, not employer names, so keep their normalization here
# instead of adding role-specific exceptions to scoring or generation.
CANONICAL_EMPLOYER_NAMES: Dict[str, str] = {
    "beast industries": "Beast Industries",
    "mrbeast": "Beast Industries",
    "mr beast": "Beast Industries",
    "mrbeastyoutube": "Beast Industries",
    "mr beast youtube": "Beast Industries",
}

ROLE_SHORT_NAMES: Dict[str, str] = {
    "head of global creative and product development operations": "HeadGlobalCreativeOps",
    "director enterprise strategy initiatives": "DirectorEnterpriseStrategy",
    "strategy and operations lead youtube auction brand": "StrategyOpsLeadYouTube",
    "operations lead ai creator platform": "OpsLeadAICreatorPlatform",
}

MATERIAL_TYPE_NAMES: Dict[str, str] = {
    "ats resume": "ats_resume",
    "ats": "ats_resume",
    "styled resume": "styled_resume",
    "styled": "styled_resume",
    "cover letter": "cover_letter",
    "cover letter docx": "cover_letter",
    "cover letter text": "cover_letter",
    "application note": "application_note",
    "hiring manager message": "hiring_manager_message",
    "hiring manager": "hiring_manager_message",
    "recruiter message": "recruiter_message",
    "recruiter": "recruiter_message",
    "followup strategy": "followup_strategy",
    "follow up strategy": "followup_strategy",
    "recruiter followup": "recruiter_followup",
    "recruiter follow up": "recruiter_followup",
    "hiring manager followup": "hiring_manager_followup",
    "hiring manager follow up": "hiring_manager_followup",
    "referral ask": "referral_ask",
    "warm contact message": "warm_contact_message",
    "interview prep": "interview_prep",
    "interview preparation": "interview_prep",
    "package summary": "package_summary",
    "strategy pack": "strategy_pack",
}

ALLOWED_MATERIAL_TYPES = set(MATERIAL_TYPE_NAMES.values())

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


def canonical_employer_name(company: Any) -> str:
    """Normalize exact employer aliases without changing unrelated brand names."""
    raw = re.sub(r"\s+", " ", str(company or "").strip())
    key = _key(raw)
    if not raw:
        return ""
    return CANONICAL_EMPLOYER_NAMES.get(key, raw)


def company_display_name(company: Any) -> str:
    """Return the familiar public company name for human-facing materials."""
    original = re.sub(r"\s+", " ", str(company or "").strip())
    raw = canonical_employer_name(original)
    key = _key(raw)
    if not raw:
        return "Company"
    if raw != original:
        return raw
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


def company_filename_component(company: Any, *, max_words: int = 4) -> str:
    """Return a concise lowercase snake_case company component."""
    short = COMPANY_SHORT_NAMES.get(_key(str(company or "")))
    source = short if short else company_display_name(company)
    tokens = [token.lower() for token in _tokens(source) if token.lower() not in COMPANY_SUFFIXES]
    return re.sub(r"_+", "_", "_".join(tokens[:max_words])).strip("_") or "company"


def role_filename_component(role_title: Any, *, max_words: int = 6) -> str:
    """Return a concise lowercase snake_case role component without profile labels."""
    words = []
    for token in _tokens(str(role_title or "")):
        lowered = token.lower()
        if lowered in ROLE_STOP_WORDS:
            continue
        words.append(lowered)
        if len(words) == max_words:
            break
    return re.sub(r"_+", "_", "_".join(words)).strip("_") or "role"


def filename_component(value: Any, *, max_words: int) -> str:
    """Return a lowercase snake_case filename component."""
    tokens = _tokens(str(value or ""))[:max_words]
    return re.sub(r"_+", "_", "_".join(token.lower() for token in tokens)).strip("_")


def normalize_material_type(export_type: str) -> str:
    """Normalize material labels to the allowed lowercase snake_case values."""
    key = _key(str(export_type or ""))
    if key in MATERIAL_TYPE_NAMES:
        return MATERIAL_TYPE_NAMES[key]
    snake = filename_component(export_type, max_words=5)
    if snake in ALLOWED_MATERIAL_TYPES:
        return snake
    return snake or "material"


def short_export_type(export_type: str) -> str:
    """Normalize an export label to an allowed filename material type."""
    return normalize_material_type(export_type)


def build_upload_filename(
    candidate_name: str,
    role_title: str,
    company: str,
    export_type: str,
    extension: str,
) -> str:
    """Build a clean generated-material filename.

    Standard: [company]_[role]_[candidate]_[material_type].[file_type]
    """
    if not is_valid_role_title(role_title):
        raise ValueError("Please confirm the role title before generating filenames.")
    components = (
        company_filename_component(company),
        role_filename_component(role_title),
        filename_component(candidate_name, max_words=4),
        normalize_material_type(export_type),
    )
    return safe_filename("_".join(part for part in components if part), extension, lowercase=True)
