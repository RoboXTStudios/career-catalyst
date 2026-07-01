"""Lightweight official career-page import with a manual-paste fallback."""

from __future__ import annotations

import json
import re
from html import unescape
from html.parser import HTMLParser
from typing import Any, Dict, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

try:
    from .job_source_registry import classify_source, normalize_job_source
    from .parse_job import extract_metadata
except ImportError:
    from job_source_registry import classify_source, normalize_job_source
    from parse_job import extract_metadata


BLOCKED_PRIMARY_HOSTS = (
    "indeed.com",
    "linkedin.com",
    "entertainmentcareers.net",
    "entertainmentcareers.com",
)
MINIMUM_DESCRIPTION_LENGTH = 80


class JobImportError(Exception):
    """Raised when a career page cannot produce a safe, useful import."""


class _VisibleTextParser(HTMLParser):
    """Collect useful visible text and basic page metadata without dependencies."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hidden_depth = 0
        self.current_heading: Optional[str] = None
        self.title_parts: list[str] = []
        self.h1_parts: list[str] = []
        self.text_parts: list[str] = []
        self.site_name = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript", "svg"}:
            self.hidden_depth += 1
        if lowered in {"title", "h1"}:
            self.current_heading = lowered
        if lowered == "meta":
            attributes = {key.lower(): value or "" for key, value in attrs}
            if attributes.get("property", "").lower() == "og:site_name":
                self.site_name = attributes.get("content", "").strip()

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript", "svg"} and self.hidden_depth:
            self.hidden_depth -= 1
        if lowered == self.current_heading:
            self.current_heading = None

    def handle_data(self, data: str) -> None:
        if self.hidden_depth:
            return
        cleaned = " ".join(data.split())
        if not cleaned:
            return
        self.text_parts.append(cleaned)
        if self.current_heading == "title":
            self.title_parts.append(cleaned)
        elif self.current_heading == "h1":
            self.h1_parts.append(cleaned)


def _manual_fallback(message: str) -> JobImportError:
    return JobImportError(
        f"{message} Keep the official URL and paste the job description text manually."
    )


def _validated_url(url: str) -> str:
    clean_url = str(url or "").strip()
    parsed = urlparse(clean_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise _manual_fallback("Enter a complete http:// or https:// career-page URL.")
    return clean_url


def validate_official_url(url: str) -> str:
    """Validate an official-page URL without fetching it."""
    return _validated_url(url)


def fetch_job_page(url: str, timeout: int = 12) -> str:
    """Fetch one official career page with a small timeout and no browser automation."""
    clean_url = _validated_url(url)
    hostname = (urlparse(clean_url).hostname or "").lower()
    if any(hostname == host or hostname.endswith(f".{host}") for host in BLOCKED_PRIMARY_HOSTS):
        raise _manual_fallback(
            "Automated import supports official company career pages; this board is supported "
            "for source classification but not automated page import."
        )
    request = Request(
        clean_url,
        headers={
            "User-Agent": "CareerCatalyst/0.0.20 (local personal career-page importer)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # nosec: user supplies an official URL
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "application/xhtml+xml"}:
                raise _manual_fallback(
                    f"The URL returned {content_type or 'non-HTML content'} instead of a career page."
                )
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except JobImportError:
        raise
    except HTTPError as error:
        raise _manual_fallback(
            f"The career page returned HTTP {error.code} and could not be imported."
        ) from error
    except (URLError, TimeoutError, OSError) as error:
        raise _manual_fallback(f"The career page could not be reached ({error}).") from error


def _walk_json(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk_json(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_json(nested)


def _job_posting(html: str) -> Optional[Dict[str, Any]]:
    scripts = re.findall(
        r"<script\b[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for script in scripts:
        try:
            loaded = json.loads(unescape(script).strip())
        except (json.JSONDecodeError, TypeError):
            continue
        for item in _walk_json(loaded):
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if any(str(value).lower() == "jobposting" for value in types):
                return item
    return None


def _plain_html_text(value: Any) -> str:
    parser = _VisibleTextParser()
    parser.feed(str(value or ""))
    return "\n".join(parser.text_parts).strip()


def _structured_location(posting: Dict[str, Any]) -> str:
    locations = posting.get("jobLocation") or []
    if isinstance(locations, dict):
        locations = [locations]
    values = []
    for location in locations if isinstance(locations, list) else []:
        if not isinstance(location, dict):
            continue
        address = location.get("address", location)
        if not isinstance(address, dict):
            continue
        parts = [
            address.get("addressLocality"),
            address.get("addressRegion"),
            address.get("addressCountry"),
        ]
        clean = ", ".join(str(part).strip() for part in parts if part)
        if clean and clean not in values:
            values.append(clean)
    if not values and str(posting.get("jobLocationType") or "").upper() == "TELECOMMUTE":
        return "Remote"
    return "; ".join(values)


def _structured_salary(posting: Dict[str, Any]) -> str:
    salary = posting.get("baseSalary")
    if not isinstance(salary, dict):
        return ""
    currency = str(salary.get("currency") or "").strip()
    value = salary.get("value", salary)
    if not isinstance(value, dict):
        return str(value or "").strip()
    minimum = value.get("minValue")
    maximum = value.get("maxValue")
    unit = str(value.get("unitText") or "").strip().lower()
    if minimum is None and maximum is None:
        return ""
    prefix = "$" if currency.upper() == "USD" else f"{currency} " if currency else ""
    amount = (
        f"{prefix}{minimum:,}-{prefix}{maximum:,}"
        if isinstance(minimum, (int, float)) and isinstance(maximum, (int, float))
        else f"{prefix}{minimum or maximum}"
    )
    return f"{amount}{f' per {unit}' if unit else ''}".strip()


def _work_arrangement(location: Any = "", description: Any = "") -> str:
    combined = f"{location or ''}\n{description or ''}"
    if re.search(r"\bhybrid\b", combined, flags=re.I):
        return "Hybrid"
    if re.search(r"\bremote\b|telecommute", combined, flags=re.I):
        return "Remote"
    if re.search(r"\bon[-\s]?site\b|\bin[-\s]?office\b", combined, flags=re.I):
        return "On-site"
    return "Not specified"


def _clean_identity(title: Any, company: Any = "") -> tuple[str, str]:
    """Normalize title/company without flattening intentional brand casing."""
    clean_title = re.sub(r"\s+", " ", str(title or "").strip())
    clean_company = re.sub(r"\s+", " ", str(company or "").strip())
    at_match = re.match(r"^(.{3,120}?)\s+at\s+(.{2,100})$", clean_title, re.I)
    if at_match:
        if not clean_company:
            clean_company = at_match.group(2).strip()
        if clean_company and clean_company.lower() == at_match.group(2).strip().lower():
            clean_title = at_match.group(1).strip()
    if clean_company:
        clean_title = re.sub(
            rf"\s*(?:[-|–—]\s*)?(?:at\s+)?{re.escape(clean_company)}\s*$",
            "",
            clean_title,
            flags=re.I,
        ).strip()
    clean_company = re.sub(r"\s*(?:jobs?|careers?|job\s+opening|hiring)\s*$", "", clean_company, flags=re.I).strip()
    return clean_title, clean_company


def _source_name(url: str) -> str:
    classified = classify_source(url)
    if classified["source_type"] != "Unknown Source":
        return str(classified["display_name"])
    return "Official career page"


def create_job_markdown(job_data: Dict[str, Any]) -> str:
    """Render normalized job data into Career Catalyst's Markdown format."""
    title, company = _clean_identity(
        job_data.get("job_title") or job_data.get("role") or "",
        job_data.get("company") or "",
    )
    description = str(job_data.get("job_description") or job_data.get("description") or "").strip()
    if not title or not company or len(description) < MINIMUM_DESCRIPTION_LENGTH:
        raise _manual_fallback(
            "The page did not provide a complete title, company, and job description."
        )
    location = str(job_data.get("location") or "").strip() or "Not specified"
    work_arrangement = (
        str(job_data.get("work_arrangement") or "").strip()
        or _work_arrangement(location, description)
        or "Not specified"
    )

    lines = [f"# {title}", "", f"Company: {company}"]
    optional_fields = (
        ("Tracker ID", job_data.get("tracker_id")),
        ("Location", location),
        ("Work arrangement", work_arrangement),
        ("Salary range", job_data.get("salary_range")),
        ("Posting date", job_data.get("posting_date")),
        ("Official source", job_data.get("source")),
        ("Official URL", job_data.get("official_url") or job_data.get("source_url")),
        ("Canonical apply URL", job_data.get("canonical_apply_url")),
        ("Source type", job_data.get("source_type")),
        ("Trust label", job_data.get("source_trust_label")),
        ("Verification status", job_data.get("verification_status")),
    )
    lines.extend(f"{label}: {str(value).strip()}" for label, value in optional_fields if value)
    lines.extend(["", "## Job Description", "", description, ""])
    return "\n".join(lines)


def extract_job_text(html: str, url: str) -> str:
    """Extract a useful canonical job document from JSON-LD or plain HTML."""
    _validated_url(url)
    if not str(html or "").strip():
        raise _manual_fallback("The career page returned no HTML.")

    posting = _job_posting(html)
    if posting:
        organization = posting.get("hiringOrganization") or {}
        company = organization.get("name") if isinstance(organization, dict) else organization
        description = _plain_html_text(posting.get("description"))
        location = _structured_location(posting)
        return create_job_markdown(
            {
                "job_title": posting.get("title"),
                "company": company,
                "location": location,
                "work_arrangement": _work_arrangement(location, description),
                "salary_range": _structured_salary(posting),
                "posting_date": posting.get("datePosted"),
                "source": _source_name(url),
                "official_url": url,
                "job_description": description,
            }
        )

    parser = _VisibleTextParser()
    parser.feed(html)
    page_title = " ".join(parser.title_parts).strip()
    title = " ".join(parser.h1_parts).strip() or page_title
    company = parser.site_name
    match = re.match(r"Job Application for (.+?) at (.+?)(?:\s*[|\-].*)?$", title, re.I)
    if match:
        title, company = match.group(1).strip(), match.group(2).strip()
    elif " @ " in title:
        title, company = (part.strip() for part in title.split(" @ ", 1))
    title = re.sub(r"\s*[|\-]\s*(?:careers?|jobs?).*$", "", title, flags=re.I).strip()
    title, company = _clean_identity(title, company)
    visible_text = "\n".join(parser.text_parts)
    metadata = extract_metadata(visible_text)
    location = metadata.get("location") or "Not specified"
    return create_job_markdown(
        {
            "job_title": metadata.get("job_title") or title,
            "company": metadata.get("company") or company,
            "location": location,
            "work_arrangement": metadata.get("work_arrangement") or _work_arrangement(location, visible_text),
            "salary_range": metadata.get("salary_range"),
            "posting_date": metadata.get("posting_date"),
            "source": _source_name(url),
            "official_url": url,
            "job_description": visible_text,
        }
    )


def parse_imported_job(raw_text: str, url: str) -> Dict[str, Any]:
    """Parse canonical imported text into fields suitable for the intake form."""
    metadata = extract_metadata(raw_text)
    description_match = re.search(
        r"^##\s+Job Description\s*$\n(.*)", raw_text, flags=re.I | re.M | re.S
    )
    description = (description_match.group(1) if description_match else raw_text).strip()
    title, company = _clean_identity(metadata.get("job_title"), metadata.get("company"))
    location = metadata.get("location") or "Not specified"
    work_arrangement = metadata.get("work_arrangement") or _work_arrangement(location, description)
    parsed: Dict[str, Any] = {
        "job_title": title,
        "company": company,
        "location": location,
        "work_arrangement": work_arrangement or "Not specified",
        "salary_range": metadata.get("salary_range") or "",
        "posting_date": metadata.get("posting_date") or "",
        "source": _source_name(url),
        "official_url": url,
        "job_description": description,
    }
    parsed.update(normalize_job_source(parsed))
    # Validate the minimum useful payload before a UI can treat import as successful.
    create_job_markdown(parsed)
    return parsed


def import_job_from_url(url: str) -> Dict[str, Any]:
    """Fetch, extract, and parse an official job page in one UI-friendly call."""
    html = fetch_job_page(url)
    raw_text = extract_job_text(html, url)
    return parse_imported_job(raw_text, url)
