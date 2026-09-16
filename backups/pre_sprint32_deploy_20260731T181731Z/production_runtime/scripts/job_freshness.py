"""Detect job posting freshness and closed-role language from local text."""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, Optional


CLOSED_PHRASES = (
    "applications closed",
    "applications are closed",
    "no longer available",
    "job expired",
    "this role has been filled",
    "role has been filled",
    "position closed",
    "position has been filled",
    "this job is no longer available",
    "job is no longer available",
    "posting has expired",
    "job has expired",
    "posting was removed",
    "job was removed",
    "this job has been removed",
    "job is inactive",
    "role is inactive",
    "position is inactive",
    "job is unavailable",
    "role is unavailable",
)
POSSIBLY_CLOSED_PHRASES = (
    "may no longer be available",
    "not currently accepting applications",
    "no longer accepting applications",
)
CURRENT_PHRASES = (
    "currently accepting applications",
    "applications are open",
    "posting is active",
    "role is active",
    "status: open",
    "status - open",
)
DATE_PATTERNS = (
    r'["\']?datePosted["\']?\s*:\s*["\']?(?P<date>\d{4}-\d{2}-\d{2})',
    r"(?:date posted|dateposted|posted(?: on)?|posting date|published)\s*[:\-]?\s*"
    r"(?P<date>\d{4}-\d{2}-\d{2})",
    r"(?:date posted|dateposted|posted(?: on)?|posting date|published)\s*[:\-]?\s*"
    r"(?P<date>\d{1,2}/\d{1,2}/\d{4})",
    r"(?:date posted|dateposted|posted(?: on)?|posting date|published)\s*[:\-]?\s*"
    r"(?P<date>(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2},?\s+\d{4})",
)


def _parse_date(value: str) -> Optional[date]:
    clean = re.sub(r"\s+", " ", str(value or "").strip())
    for pattern in (
        "%Y-%m-%d",
        "%m/%d/%Y",
        "%B %d, %Y",
        "%B %d %Y",
        "%b %d, %Y",
        "%b %d %Y",
    ):
        try:
            return datetime.strptime(clean, pattern).date()
        except ValueError:
            continue
    return None


def explicit_posting_age_days(text: str) -> Optional[int]:
    """Return age stated in relative posting language, including stale variants."""
    raw_text = str(text or "")
    months = re.search(
        r"\b(?:posted\s+)?(?:about\s+|at\s+least\s+)?(\d+)\s+months?\s+(?:ago|old)\b",
        raw_text,
        re.I,
    )
    if months:
        return int(months.group(1)) * 30
    older_than = re.search(r"\bolder\s+than\s+(\d+)\s+days?\b", raw_text, re.I)
    if older_than:
        return int(older_than.group(1)) + 1
    days = re.search(
        r"\b(?:posted\s+)?(?:(more\s+than|over|older\s+than|at\s+least)\s+)?"
        r"(\d+)\s*(\+)?\s+days?\s+(?:ago|old)\b",
        raw_text,
        re.I,
    )
    if days:
        age = int(days.group(2))
        if days.group(1) and days.group(1).lower() in {"more than", "over", "older than"}:
            age += 1
        return age
    return None


def _posting_date(text: str, today: date) -> Optional[date]:
    explicit_age = explicit_posting_age_days(text)
    if explicit_age is not None:
        return today - timedelta(days=explicit_age)
    if re.search(r"\bposted\s+today\b", text, re.I):
        return today
    if re.search(r"\bposted\s+yesterday\b", text, re.I):
        return today - timedelta(days=1)
    for pattern in DATE_PATTERNS:
        match = re.search(pattern, text, re.I)
        if match:
            parsed = _parse_date(match.group("date"))
            if parsed:
                return parsed
    return None


def detect_job_freshness(text: str, today: Optional[date] = None) -> Dict[str, Any]:
    """Return normalized freshness, priority, and closed-role status."""
    reference_date = today or date.today()
    raw_text = str(text or "")
    lowered = raw_text.lower()
    closed_match = next((phrase for phrase in CLOSED_PHRASES if phrase in lowered), None)
    possible_match = next(
        (phrase for phrase in POSSIBLY_CLOSED_PHRASES if phrase in lowered), None
    )
    standalone_status = re.search(
        r"(?im)^\s*(?:status\s*[:\-]\s*)?(closed|expired|inactive|removed|unavailable)\s*[.!]?\s*$",
        raw_text,
    )
    if not closed_match and standalone_status:
        closed_match = standalone_status.group(1).lower()
    posting_date = _posting_date(raw_text, reference_date)
    age_days = max(0, (reference_date - posting_date).days) if posting_date else None

    if age_days is None:
        category = "Unknown freshness"
        priority = "Verify manually"
        score = 50
    elif age_days <= 7:
        category, priority, score = "Fresh", "High priority", 100
    elif age_days <= 20:
        category, priority, score = "Active", "Good priority", 82
    elif age_days <= 30:
        category, priority, score = "Aging", "Apply if strong fit", 58
    else:
        category, priority, score = "Stale", "Verify manually", 25

    has_current_signal = any(phrase in lowered for phrase in CURRENT_PHRASES)
    if closed_match:
        posting_status = "Closed"
    elif possible_match:
        posting_status = "Possibly Closed"
    elif age_days is not None and age_days >= 90 and not has_current_signal:
        posting_status = "Stale / Closed Risk"
    elif age_days is not None and age_days >= 31 and not has_current_signal:
        posting_status = "Possibly stale"
    elif age_days is None and not has_current_signal:
        posting_status = "Verify manually"
    else:
        posting_status = "Open"
    is_closed = posting_status in {"Closed", "Possibly Closed"}
    is_stale = bool(age_days is not None and age_days >= 31 and not has_current_signal)
    if is_closed:
        score = 0

    return {
        "category": category,
        "label": f"{category} / {priority}",
        "priority": priority,
        "posting_status": posting_status,
        "is_closed": is_closed,
        "is_stale": is_stale,
        "closed_reason": closed_match or possible_match,
        "posting_date": posting_date.isoformat() if posting_date else None,
        "posting_date_label": posting_date.isoformat() if posting_date else "Posting date unknown",
        "age_days": age_days,
        "score": score,
    }
