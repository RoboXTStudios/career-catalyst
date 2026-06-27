"""Parse local job description files with simple Sprint 2 logic."""

import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union


IMPORTANT_PHRASES = (
    "enterprise strategy",
    "cross-functional",
    "operational planning",
    "executive communication",
    "process improvement",
    "business operations",
    "strategic programs",
    "change management",
    "stakeholder alignment",
    "streaming entertainment",
    "global teams",
    "fandom",
)

STOP_WORDS = {
    "a",
    "about",
    "across",
    "all",
    "also",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "can",
    "for",
    "from",
    "has",
    "have",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "our",
    "that",
    "the",
    "their",
    "this",
    "to",
    "we",
    "with",
    "you",
    "your",
}

METADATA_LABELS = {
    "job_title": ("job title", "title", "role"),
    "company": ("company", "organization"),
    "location": ("location", "work location"),
    "salary_range": ("salary", "salary range", "compensation", "compensation range"),
    "employment_type": ("employment type", "job type", "type"),
    "source_url": ("source url", "source", "posting url", "job url"),
}

RESPONSIBILITY_HEADINGS = (
    "responsibilities",
    "key responsibilities",
    "what you'll do",
    "what you will do",
    "the role",
)

QUALIFICATION_HEADINGS = (
    "qualifications",
    "requirements",
    "what you bring",
    "you have",
    "preferred qualifications",
)

RESPONSIBILITY_TERMS = (
    "lead",
    "develop",
    "drive",
    "manage",
    "partner",
    "coordinate",
    "align",
    "improve",
    "support",
    "communicate",
    "translate",
    "oversee",
)

QUALIFICATION_TERMS = (
    "experience",
    "background",
    "ability",
    "knowledge",
    "familiarity",
    "proven",
    "years",
    "skills",
)

PathInput = Union[str, Path]


class JobParseError(Exception):
    """Base exception for job description parsing errors."""


class MissingJobDescriptionError(JobParseError):
    """Raised when the requested job description file does not exist."""

    def __init__(self, file_path: PathInput) -> None:
        super().__init__(f"Job description file not found: {file_path}")
        self.file_path = file_path


def load_job_description(file_path: PathInput) -> str:
    """Read a local Markdown or text job description file."""
    path = Path(file_path)

    if not path.is_file():
        raise MissingJobDescriptionError(file_path)

    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise JobParseError(f"Unable to read job description file {file_path}: {error}") from error


def _normalize_heading(line: str) -> str:
    heading = re.sub(r"^#+\s*", "", line.strip())
    return heading.strip().strip(":").lower()


def _clean_list_item(line: str) -> str:
    return re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()


def _non_empty_lines(text: str) -> List[str]:
    return [line.rstrip() for line in text.splitlines() if line.strip()]


def _inline_label_value(line: str, labels: Iterable[str]) -> Optional[str]:
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.match(rf"^\s*(?:#+\s*)?(?:{label_pattern})\s*:\s*(.+?)\s*$", line, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _heading_label_value(lines: List[str], index: int, labels: Iterable[str]) -> Optional[str]:
    normalized = _normalize_heading(lines[index])
    if normalized not in labels:
        return None

    for next_line in lines[index + 1 :]:
        stripped = next_line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return None
        return _clean_list_item(stripped)

    return None


def _extract_labeled_value(text: str, labels: Iterable[str]) -> Optional[str]:
    label_tuple = tuple(labels)
    lines = text.splitlines()

    for index, line in enumerate(lines):
        inline_value = _inline_label_value(line, label_tuple)
        if inline_value:
            return inline_value

        heading_value = _heading_label_value(lines, index, label_tuple)
        if heading_value:
            return heading_value

    return None


def _extract_salary(text: str) -> Optional[str]:
    labeled_salary = _extract_labeled_value(text, METADATA_LABELS["salary_range"])
    if labeled_salary:
        return labeled_salary

    match = re.search(
        r"\$[0-9][0-9,]*(?:\s*(?:-|–|to)\s*\$?[0-9][0-9,]*)?(?:\s*(?:per year|annually|/year|a year))?",
        text,
        flags=re.IGNORECASE,
    )
    if match:
        return match.group(0).strip()
    return None


def _extract_employment_type(text: str) -> Optional[str]:
    labeled_type = _extract_labeled_value(text, METADATA_LABELS["employment_type"])
    if labeled_type:
        return labeled_type

    match = re.search(r"\b(full-time|part-time|contract|temporary|internship)\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return None


def _extract_source_url(text: str) -> Optional[str]:
    labeled_source = _extract_labeled_value(text, METADATA_LABELS["source_url"])
    if labeled_source and re.match(r"https?://", labeled_source):
        return labeled_source

    match = re.search(r"https?://[^\s)]+", text)
    if match:
        return match.group(0)
    return None


def _extract_job_title(text: str) -> Optional[str]:
    labeled_title = _extract_labeled_value(text, METADATA_LABELS["job_title"])
    if labeled_title:
        return labeled_title

    for line in text.splitlines():
        match = re.match(r"^\s*#\s+(.+?)\s*$", line)
        if match:
            return match.group(1).strip()
    return None


def extract_metadata(text: str) -> Dict[str, Optional[str]]:
    """Extract basic job metadata when available."""
    metadata = {
        "job_title": _extract_job_title(text),
        "company": _extract_labeled_value(text, METADATA_LABELS["company"]),
        "location": _extract_labeled_value(text, METADATA_LABELS["location"]),
        "salary_range": _extract_salary(text),
        "employment_type": _extract_employment_type(text),
        "source_url": _extract_source_url(text),
    }
    return metadata


def _is_heading(line: str) -> bool:
    return bool(re.match(r"^\s*#{1,6}\s+\S", line))


def _section_matches(line: str, headings: Tuple[str, ...]) -> bool:
    normalized = _normalize_heading(line)
    return any(normalized == heading or heading in normalized for heading in headings)


def _extract_section_items(text: str, headings: Tuple[str, ...]) -> List[str]:
    items = []
    active = False

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        if _is_heading(stripped):
            active = _section_matches(stripped, headings)
            continue

        if not active:
            continue

        cleaned = _clean_list_item(stripped)
        if cleaned:
            items.append(cleaned)

    return items


def _extract_bullet_lines(text: str) -> List[str]:
    return [_clean_list_item(line) for line in text.splitlines() if re.match(r"^\s*(?:[-*]|\d+[.)])\s+", line)]


def _contains_any(text: str, terms: Tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def extract_responsibilities(text: str) -> List[str]:
    """Extract likely responsibilities from headings or responsibility-like bullets."""
    items = _extract_section_items(text, RESPONSIBILITY_HEADINGS)
    if items:
        return items

    return [line for line in _extract_bullet_lines(text) if _contains_any(line, RESPONSIBILITY_TERMS)]


def extract_qualifications(text: str) -> List[str]:
    """Extract likely qualifications from headings or qualification-like bullets."""
    items = _extract_section_items(text, QUALIFICATION_HEADINGS)
    if items:
        return items

    return [line for line in _extract_bullet_lines(text) if _contains_any(line, QUALIFICATION_TERMS)]


def extract_keywords(text: str, limit: int = 12) -> List[str]:
    """Extract important local keywords with phrase detection and simple word frequency."""
    lowered = text.lower()
    phrase_matches = [phrase for phrase in IMPORTANT_PHRASES if phrase in lowered]

    tokens = re.findall(r"[a-z][a-z0-9+-]*", lowered)
    counts = Counter(token for token in tokens if token not in STOP_WORDS and len(token) > 2)

    keywords = list(phrase_matches)
    for token, _count in counts.most_common():
        if token not in keywords:
            keywords.append(token)
        if len(keywords) >= limit:
            break

    return keywords[:limit]


def _summary(parsed: Dict[str, Any]) -> str:
    title = parsed.get("job_title") or "Unknown role"
    company = parsed.get("company") or "unknown company"
    keyword_count = len(parsed.get("keywords", []))
    responsibility_count = len(parsed.get("responsibilities", []))
    qualification_count = len(parsed.get("qualifications", []))
    return (
        f"{title} at {company}: {keyword_count} keywords, "
        f"{responsibility_count} responsibilities, {qualification_count} qualifications."
    )


def parse_job_description(file_path: PathInput) -> Dict[str, Any]:
    """Parse a local job description file into a structured dictionary."""
    text = load_job_description(file_path)
    metadata = extract_metadata(text)
    parsed = {
        "source_path": str(file_path),
        "raw_text": text,
        "job_title": metadata["job_title"],
        "company": metadata["company"],
        "location": metadata["location"],
        "salary_range": metadata["salary_range"],
        "employment_type": metadata["employment_type"],
        "source_url": metadata["source_url"],
        "keywords": extract_keywords(text),
        "responsibilities": extract_responsibilities(text),
        "qualifications": extract_qualifications(text),
    }
    parsed["summary"] = _summary(parsed)
    return parsed
