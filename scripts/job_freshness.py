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
)
POSSIBLY_CLOSED_PHRASES = (
    "may no longer be available",
    "not currently accepting applications",
    "no longer accepting applications",
)
DATE_PATTERNS = (
    r"(?:date posted|dateposted|posted(?: on)?|posting date|published)\s*[:\-]?\s*"
    r"(?P<date>\d{4}-\d{2}-\d{2})",
    r"(?:date posted|dateposted|posted(?: on)?|posting date|published)\s*[:\-]?\s*"
    r"(?P<date>(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\s+\d{1,2},?\s+\d{4})",
)


def _parse_date(value: str) -> Optional[date]:
    clean = re.sub(r"\s+", " ", str(value or "").strip())
    for pattern in ("%Y-%m-%d", "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
        try:
            return datetime.strptime(clean, pattern).date()
        except ValueError:
            continue
    return None


def _posting_date(text: str, today: date) -> Optional[date]:
    relative = re.search(r"\bposted\s+(?:about\s+)?(\d+)\s+days?\s+ago\b", text, re.I)
    if relative:
        return today - timedelta(days=int(relative.group(1)))
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
        category, priority, score = "Stale", "Lower priority", 25

    posting_status = "Closed" if closed_match else "Possibly Closed" if possible_match else "Open"
    is_closed = posting_status in {"Closed", "Possibly Closed"}
    if is_closed:
        score = 0

    return {
        "category": category,
        "label": f"{category} / {priority}",
        "priority": priority,
        "posting_status": posting_status,
        "is_closed": is_closed,
        "closed_reason": closed_match or possible_match,
        "posting_date": posting_date.isoformat() if posting_date else None,
        "age_days": age_days,
        "score": score,
    }

