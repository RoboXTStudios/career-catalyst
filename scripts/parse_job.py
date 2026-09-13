"""Parse local job description files with simple Sprint 2 logic."""

import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

try:
    from .filename_utils import canonical_employer_name, is_valid_role_title
except ImportError:
    from filename_utils import canonical_employer_name, is_valid_role_title


IMPORTANT_PHRASES = (
    "agency operations", "delivery outcomes", "team leads", "operating standards",
    "quality standards", "capacity visibility", "people leadership", "leadership development",

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
    "work_arrangement": ("work arrangement", "work model", "work style"),
    "salary_range": ("salary", "salary range", "compensation", "compensation range"),
    "compensation_disclosure_state": ("compensation status", "salary disclosure status"),
    "employment_type": ("employment type", "job type", "type"),
    "source_url": ("source url", "source", "posting url", "job url"),
    "posting_date": ("posting date", "date posted", "posted on", "dateposted", "published"),
}

COMPENSATION_DISCLOSURE_STATES = (
    "provided",
    "not_listed",
    "unknown_unverified",
)

COMPENSATION_STATE_LABELS = {
    "provided": "Provided",
    "not_listed": "Not listed",
    "unknown_unverified": "Unknown / unverified",
}

COMPENSATION_STATE_MESSAGES = {
    "not_listed": "Compensation not listed — verify before recruiter screen.",
    "unknown_unverified": "Compensation unknown — verify posting or recruiter details.",
}

RESPONSIBILITY_HEADINGS = (
    "responsibilities",
    "key responsibilities",
    "what you'll do",
    "what you will do",
    "what you'll own",
    "the role",
)

QUALIFICATION_HEADINGS = (
    "qualifications",
    "requirements",
    "required qualifications",
    "what you bring",
    "you have",
)

PREFERRED_QUALIFICATION_HEADINGS = (
    "preferred qualifications",
    "nice to have",
    "bonus points",
    "a strong plus",
)

BOILERPLATE_HEADINGS = (
    "about us",
    "how we work",
    "growth & opportunity",
    "what we offer",
    "company overview",
    "benefits",
    "equal employment opportunity",
    "eeo",
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

NON_SALARY_MONEY_TERMS = (
    "budget", "media spend", "ad spend", "managed spend", "spend", "revenue",
    "pipeline", "billings", "investment", "portfolio", "p&l", "profit", "loss",
    "sales target", "quota", "equity value", "equity valued", "stock grant",
    "bonus", "commission", "job id",
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


def _analysis_text(text: str) -> str:
    """Strip stored ATS markup before parsing without rewriting the source file."""
    if not re.search(
        r"</?[a-z][^>]*>|&(?:amp;)*(?:lt|gt);",
        str(text or ""),
        flags=re.IGNORECASE,
    ):
        return text
    # Imported lazily because job_importer also uses extract_metadata from this
    # module. At analysis time both modules are fully initialized.
    try:
        from .job_importer import _plain_html_text
    except ImportError:
        from job_importer import _plain_html_text
    description_heading = re.search(
        r"^##\s+Job Description\s*$", text, flags=re.IGNORECASE | re.MULTILINE
    )
    if description_heading:
        prefix = text[: description_heading.end()].rstrip()
        description = text[description_heading.end() :]
        return prefix + "\n\n" + _plain_html_text(description) + "\n"
    return _plain_html_text(text)


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


_COMP_AMOUNT = r"(?P<{name}_currency>(?:USD\s*)?\$|USD\s*)?\s*(?P<{name}_number>\d{{1,3}}(?:,\d{{3}})*(?:\.\d+)?)\s*(?P<{name}_suffix>[kK]?)"
_COMP_LABEL = r"(?:base\s+salary|annual\s+salary|salary\s+range|salary|base\s+pay|compensation(?:\s+range)?|pay\s+range)"
_COMP_PERIOD = r"(?:per\s+(?:year|annum|hour)|annually|yearly|hourly|/\s*(?:year|yr|hour|hr)|an\s+hour)"


def _comp_amount(match: re.Match[str], name: str) -> Optional[float]:
    raw = match.group(f"{name}_number")
    if not raw:
        return None
    value = float(raw.replace(",", ""))
    if match.group(f"{name}_suffix"):
        value *= 1000
    return value


def _comp_display_amount(value: Optional[float], period: str) -> str:
    if value is None:
        return ""
    if period == "hour":
        return f"${value:,.2f}"
    return f"${value:,.0f}"


def normalize_compensation_disclosure_state(
    value: Any, *, detected: bool = False
) -> str:
    """Normalize saved labels without guessing that a blank means Not listed."""
    if detected:
        return "provided"
    normalized = re.sub(r"[^a-z]+", "_", str(value or "").strip().lower()).strip("_")
    aliases = {
        "provided": "provided",
        "not_listed": "not_listed",
        "not_disclosed": "not_listed",
        "unknown": "unknown_unverified",
        "unverified": "unknown_unverified",
        "unknown_unverified": "unknown_unverified",
    }
    return aliases.get(normalized, "unknown_unverified")


def compensation_status_message(value: Any) -> str:
    state = (
        value.get("disclosure_state")
        if isinstance(value, dict)
        else value
    )
    normalized = normalize_compensation_disclosure_state(state)
    return COMPENSATION_STATE_MESSAGES.get(normalized, "")


def empty_compensation(
    raw: Any = "",
    source: str = "description",
    manual_override: bool = False,
    disclosure_state: Any = None,
) -> Dict[str, Any]:
    """Return the stable empty compensation shape used throughout intake and scoring."""
    state = normalize_compensation_disclosure_state(disclosure_state)
    if state == "provided":
        state = "unknown_unverified"
    return {
        "minimum": None,
        "maximum": None,
        "currency": "USD" if "$" in str(raw or "") else None,
        "period": None,
        "raw": str(raw or "").strip(),
        "display": str(raw or "").strip() if manual_override else "",
        "source": source,
        "manual_override": bool(manual_override),
        "detected": bool(str(raw or "").strip()) if manual_override else False,
        "needs_review": bool(str(raw or "").strip()) if manual_override else False,
        "disclosure_state": state,
        "disclosure_label": COMPENSATION_STATE_LABELS[state],
        "status_message": COMPENSATION_STATE_MESSAGES.get(state, ""),
    }


def normalize_compensation(
    value: Any,
    *,
    source: str = "description",
    manual_override: bool = False,
    disclosure_state: Any = None,
) -> Dict[str, Any]:
    """Parse one deterministic compensation result without AI or network work."""
    if isinstance(value, dict):
        raw_value = value.get("raw") or value.get("display") or ""
        source = str(value.get("source") or source)
        manual_override = bool(value.get("manual_override", manual_override))
        if disclosure_state is None:
            disclosure_state = value.get("disclosure_state")
        if value.get("detected") and (value.get("minimum") is not None or value.get("maximum") is not None):
            result = empty_compensation(
                raw_value, source, manual_override, disclosure_state="provided"
            )
            result.update(value)
            result["disclosure_state"] = "provided"
            result["disclosure_label"] = COMPENSATION_STATE_LABELS["provided"]
            result["status_message"] = ""
            return result
        value = raw_value

    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if not text:
        return empty_compensation(
            "", source, manual_override, disclosure_state=disclosure_state
        )

    amount = _COMP_AMOUNT
    range_pattern = re.compile(
        rf"(?:(?P<label>{_COMP_LABEL})\s*[:\-]?\s*)?"
        rf"{amount.format(name='min')}\s*(?:-|–|—|−|to)\s*"
        rf"{amount.format(name='max')}(?:\s*(?P<period>{_COMP_PERIOD}|USD))?",
        re.I,
    )
    bound_pattern = re.compile(
        rf"(?P<bound>minimum|min(?:imum)?|starting(?:\s+salary)?|starts?\s+at|from|at\s+least|"
        rf"maximum|max(?:imum)?|up\s+to|no\s+more\s+than)"
        rf"(?:\s+(?:base\s+)?(?:salary|pay|compensation))?\s*(?:is|of)?\s*[:\-]?\s*"
        rf"{amount.format(name='value')}(?:\s*(?P<period>{_COMP_PERIOD}))?",
        re.I,
    )
    labeled_single_pattern = re.compile(
        rf"(?P<label>{_COMP_LABEL})\s*[:\-]?\s*{amount.format(name='value')}"
        rf"(?:\s*(?P<period>{_COMP_PERIOD}|USD))?",
        re.I,
    )
    period_single_pattern = re.compile(
        rf"{amount.format(name='value')}\s*(?P<period>{_COMP_PERIOD})",
        re.I,
    )

    match: Optional[re.Match[str]] = None
    kind = ""
    for candidate_kind, pattern in (
        ("range", range_pattern),
        ("bound", bound_pattern),
        ("single", labeled_single_pattern),
        ("single", period_single_pattern),
    ):
        for candidate in pattern.finditer(text):
            context = text[max(0, candidate.start() - 55) : min(len(text), candidate.end() + 55)]
            has_salary_label = bool(re.search(_COMP_LABEL, context, re.I))
            if salary_parsing_warning(context) and not has_salary_label:
                continue
            match, kind = candidate, candidate_kind
            break
        if match:
            break

    if not match:
        return empty_compensation(
            text,
            "manual" if manual_override else source,
            manual_override,
            disclosure_state=disclosure_state,
        )

    if kind == "range":
        minimum = _comp_amount(match, "min")
        maximum = _comp_amount(match, "max")
    else:
        number = _comp_amount(match, "value")
        bound = str(match.groupdict().get("bound") or "").lower()
        minimum = None if bound.startswith(("max", "up to", "no more")) else number
        maximum = number if bound.startswith(("max", "up to", "no more")) else None

    period_text = str(match.groupdict().get("period") or "").lower()
    period = "hour" if re.search(r"hour|hr", period_text) else "year"
    values = [number for number in (minimum, maximum) if number is not None]
    valid = bool(values) and all(
        (10 <= number <= 1000) if period == "hour" else (20000 <= number <= 2_000_000)
        for number in values
    )
    if not valid:
        return empty_compensation(
            text,
            "manual" if manual_override else source,
            manual_override,
            disclosure_state=disclosure_state,
        )

    if minimum is not None and maximum is not None:
        display = f"{_comp_display_amount(minimum, period)} – {_comp_display_amount(maximum, period)}"
    elif minimum is not None:
        display = f"From {_comp_display_amount(minimum, period)}"
    else:
        display = f"Up to {_comp_display_amount(maximum, period)}"
    display += " per hour" if period == "hour" else " per year"
    raw = match.group(0).strip()
    return {
        "minimum": minimum,
        "maximum": maximum,
        "currency": "USD",
        "period": period,
        "raw": raw,
        "display": text if manual_override else display,
        "source": "manual" if manual_override else source,
        "manual_override": bool(manual_override),
        "detected": True,
        "needs_review": bool(manual_override and text != display),
        "disclosure_state": "provided",
        "disclosure_label": COMPENSATION_STATE_LABELS["provided"],
        "status_message": "",
    }


def _extract_compensation(text: str) -> Dict[str, Any]:
    labeled_salary = _extract_labeled_value(text, METADATA_LABELS["salary_range"])
    if labeled_salary:
        labeled = normalize_compensation(labeled_salary, source="labeled_description")
        if labeled["detected"]:
            return labeled
    return normalize_compensation(text, source="description")


def _extract_salary(text: str) -> Optional[str]:
    compensation = _extract_compensation(text)
    return str(compensation.get("raw") or "") or None if compensation.get("detected") else None


def salary_parsing_warning(text: Any) -> bool:
    """Return whether money text looks like a budget/business metric, not pay."""
    lowered = re.sub(r"\s+", " ", str(text or "").lower())
    has_money = bool(
        re.search(r"\$\s*\d", lowered)
        or re.search(r"\b\d+(?:\.\d+)?\s+million\s+dollars?\b", lowered)
    )
    return has_money and any(term in lowered for term in NON_SALARY_MONEY_TERMS)


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


def _extract_work_arrangement(text: str) -> Optional[str]:
    labeled = _extract_labeled_value(text, METADATA_LABELS["work_arrangement"])
    if labeled:
        return labeled
    lowered = text.lower()
    if re.search(r"\bhybrid\b", lowered):
        return "Hybrid"
    if re.search(r"\bremote\b|#li-remote", lowered):
        return "Remote"
    if re.search(r"\bon[-\s]?site\b|\bin[-\s]?office\b|#li-onsite", lowered):
        return "On-site"
    if re.search(r"\bflexible\b", lowered):
        return "Flexible"
    return None


def _extract_location(text: str) -> Optional[str]:
    labeled = _extract_labeled_value(text, METADATA_LABELS["location"])
    if labeled:
        return labeled

    city_state = re.search(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3},\s*(?:CA|NY|WA|OR|TX|IL|GA|FL|MA|PA|NJ|DC|TN|CO|AZ|NV))\b",
        text,
    )
    if city_state:
        return city_state.group(1).strip()

    compact = re.sub(r"\s+", " ", text)
    for pattern, value in (
        (r"\bRemote\b", "Remote"),
        (r"\bHybrid\b", "Hybrid"),
        (r"\bUnited States\b", "United States"),
        (r"\bCalifornia\b", "California"),
        (r"\bUS\b|\bU\.S\.\b|\bUSA\b", "US"),
    ):
        if re.search(pattern, compact, flags=re.I):
            return value
    return None


def _extract_job_title(text: str) -> Optional[str]:
    labeled_title = _extract_labeled_value(text, METADATA_LABELS["job_title"])
    if labeled_title and is_valid_role_title(labeled_title):
        return labeled_title

    for line in text.splitlines():
        match = re.match(r"^\s*#\s+(.+?)\s*$", line)
        if match:
            title = match.group(1).strip()
            return title if is_valid_role_title(title) else None
    return None


def extract_metadata(text: str) -> Dict[str, Any]:
    """Extract basic job metadata when available."""
    explicit_compensation_state = _extract_labeled_value(
        text, METADATA_LABELS["compensation_disclosure_state"]
    )
    compensation = normalize_compensation(
        _extract_compensation(text),
        disclosure_state=explicit_compensation_state,
    )
    metadata = {
        "job_title": _extract_job_title(text),
        "company": _extract_labeled_value(text, METADATA_LABELS["company"]),
        "location": _extract_location(text),
        "work_arrangement": _extract_work_arrangement(text),
        "salary_range": (compensation.get("raw") or None) if compensation.get("detected") else None,
        "compensation": compensation,
        "compensation_disclosure_state": compensation["disclosure_state"],
        "employment_type": _extract_employment_type(text),
        "source_url": _extract_source_url(text),
        "posting_date": _extract_labeled_value(text, METADATA_LABELS["posting_date"]),
    }
    return metadata


def _is_heading(line: str) -> bool:
    return bool(re.match(r"^\s*#{1,6}\s+\S", line))


def _section_matches(line: str, headings: Tuple[str, ...]) -> bool:
    normalized = _normalize_heading(line)
    return any(normalized == heading or heading in normalized for heading in headings)


def _extract_section_items(text: str, headings: Tuple[str, ...], stop_headings: Tuple[str, ...] = ()) -> List[str]:
    items = []
    active = False

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        plain_heading = _normalize_heading(stripped) in (
            RESPONSIBILITY_HEADINGS + QUALIFICATION_HEADINGS
            + PREFERRED_QUALIFICATION_HEADINGS + BOILERPLATE_HEADINGS
        )
        if _is_heading(stripped) or plain_heading:
            if stop_headings and _section_matches(stripped, stop_headings):
                active = False
            else:
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
    """Extract likely required qualifications without merging preferred-only sections."""
    items = _extract_section_items(text, QUALIFICATION_HEADINGS, PREFERRED_QUALIFICATION_HEADINGS)
    if items:
        return items

    return [line for line in _extract_bullet_lines(text) if _contains_any(line, QUALIFICATION_TERMS)]


def extract_preferred_qualifications(text: str) -> List[str]:
    """Extract preferred qualifications separately from requirements."""
    return _extract_section_items(text, PREFERRED_QUALIFICATION_HEADINGS)


def extract_boilerplate(text: str) -> List[str]:
    """Retain company/benefits/EEO text for inspection while excluding it from scoring requirements."""
    return _extract_section_items(text, BOILERPLATE_HEADINGS)


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
    return parse_job_text(load_job_description(file_path), source_path=str(file_path))


def parse_job_text(text: str, *, source_path: str = "") -> Dict[str, Any]:
    """Parse persisted or unsaved posting text without a temporary file."""
    text = _analysis_text(text)
    metadata = extract_metadata(text)
    parsed = {
        "source_path": source_path,
        "raw_text": text,
        "job_title": metadata["job_title"],
        "company": (
            canonical_employer_name(metadata["company"])
            if metadata["company"]
            else None
        ),
        "location": metadata["location"],
        "salary_range": metadata["salary_range"],
        "compensation": metadata["compensation"],
        "compensation_disclosure_state": metadata["compensation_disclosure_state"],
        "employment_type": metadata["employment_type"],
        "source_url": metadata["source_url"],
        "posting_date": metadata["posting_date"],
        "work_arrangement": metadata["work_arrangement"],
        "keywords": extract_keywords(text),
        "responsibilities": extract_responsibilities(text),
        "qualifications": extract_qualifications(text),
        "preferred_qualifications": extract_preferred_qualifications(text),
        "boilerplate_sections": extract_boilerplate(text),
    }
    parsed["summary"] = _summary(parsed)
    return parsed
