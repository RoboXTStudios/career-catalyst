"""Lightweight official career-page import with a manual-paste fallback."""

from __future__ import annotations

import json
import re
from html import unescape
from html.parser import HTMLParser
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse, urlunparse
from urllib.request import Request, urlopen

try:
    from .filename_utils import canonical_employer_name, company_display_name, is_valid_role_title
    from .job_identity import infer_job_fields_from_url, preferred_role_title
    from .job_source_registry import classify_source, normalize_job_source
    from .parse_job import extract_metadata
except ImportError:
    from filename_utils import canonical_employer_name, company_display_name, is_valid_role_title
    from job_identity import infer_job_fields_from_url, preferred_role_title
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
        if lowered in {"script", "style", "noscript", "svg", "nav", "footer", "aside", "form"}:
            self.hidden_depth += 1
        if lowered in {"title", "h1"}:
            self.current_heading = lowered
        if lowered == "meta":
            attributes = {key.lower(): value or "" for key, value in attrs}
            if attributes.get("property", "").lower() == "og:site_name":
                self.site_name = attributes.get("content", "").strip()

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript", "svg", "nav", "footer", "aside", "form"} and self.hidden_depth:
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



def _greenhouse_identity(url: str) -> Dict[str, str]:
    """Return stable Greenhouse board/job identity for supported posting URLs."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    segments = [segment for segment in parsed.path.split("/") if segment]
    if host not in {"job-boards.greenhouse.io", "boards.greenhouse.io"} or len(segments) < 3:
        return {}
    if segments[1].lower() != "jobs" or not segments[2].isdigit():
        return {}
    canonical = urlunparse((parsed.scheme, parsed.netloc, f"/{segments[0]}/jobs/{segments[2]}", "", "", ""))
    return {"board_token": segments[0], "job_id": segments[2], "canonical_url": canonical}


def _greenhouse_board_job_api_url(url: str) -> str:
    """Return the Greenhouse Boards API URL for supported job posting URLs."""
    identity = _greenhouse_identity(url)
    if not identity:
        return ""
    board_token = quote(identity["board_token"], safe="")
    job_id = quote(identity["job_id"], safe="")
    return f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}"


def _fetch_json(url: str, timeout: int = 12) -> Dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": "CareerCatalyst/0.0.20 (local personal career-page importer)",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:  # nosec: derived from supported ATS URL
            content_type = response.headers.get_content_type()
            if content_type not in {"application/json", "text/json", "text/plain"}:
                raise _manual_fallback(
                    f"The job API returned {content_type or 'non-JSON content'} instead of job details."
                )
            charset = response.headers.get_content_charset() or "utf-8"
            return json.loads(response.read().decode(charset, errors="replace"))
    except JobImportError:
        raise
    except HTTPError as error:
        raise _manual_fallback(
            f"The job API returned HTTP {error.code} and could not be imported."
        ) from error
    except (json.JSONDecodeError, URLError, TimeoutError, OSError) as error:
        raise _manual_fallback(f"The job API could not be reached or parsed ({error}).") from error


def _greenhouse_company_from_url(url: str) -> str:
    identity = _greenhouse_identity(url)
    token = identity.get("board_token", "")
    if not token:
        return ""
    board_label = re.sub(r"[-_]+", " ", token).strip().title()
    return canonical_employer_name(board_label)


def _greenhouse_location(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("name") or "").strip()
    return str(value or "").strip()


def _extract_greenhouse_job(url: str, timeout: int = 12) -> Optional[Dict[str, Any]]:
    api_url = _greenhouse_board_job_api_url(url)
    if not api_url:
        return None
    identity = _greenhouse_identity(url)
    payload = _fetch_json(api_url, timeout)
    description = _plain_html_text(payload.get("content"))
    metadata = extract_metadata(description)
    company = _greenhouse_company_from_url(url)
    canonical_url = str(payload.get("absolute_url") or identity.get("canonical_url") or url).strip()
    parsed = {
        "job_title": payload.get("title") or "",
        "company": company,
        "location": _greenhouse_location(payload.get("location")) or "Not specified",
        "work_arrangement": _work_arrangement(_greenhouse_location(payload.get("location")), description),
        "job_id": str(payload.get("id") or "").strip(),
        "external_job_id": str(payload.get("id") or "").strip(),
        "source_platform": "Greenhouse",
        "description_status": "Verified",
        "source": _source_name(url),
        "source_url": identity.get("canonical_url") or url,
        "official_url": identity.get("canonical_url") or url,
        "original_source_url": url,
        "posting_url": identity.get("canonical_url") or url,
        "application_url": canonical_url,
        "canonical_apply_url": canonical_url,
        "job_description": description,
        "salary_range": metadata.get("salary_range") or "",
        "compensation": metadata.get("compensation"),
        "posting_date": metadata.get("posting_date") or "",
    }
    _validate_greenhouse_payload(parsed, identity)
    parsed.update(normalize_job_source(parsed))
    parsed["source_url"] = identity.get("canonical_url") or url
    parsed["official_url"] = identity.get("canonical_url") or url
    parsed["original_source_url"] = url
    parsed["posting_url"] = identity.get("canonical_url") or url
    parsed["application_url"] = canonical_url or parsed.get("application_url") or url
    parsed["canonical_apply_url"] = canonical_url or parsed.get("canonical_apply_url") or url
    create_job_markdown(parsed)
    return parsed


def _validate_greenhouse_payload(parsed: Dict[str, Any], identity: Dict[str, str]) -> None:
    """Block Greenhouse imports whose structured record does not match the requested job."""
    requested_id = str(identity.get("job_id") or "").strip()
    payload_id = str(parsed.get("job_id") or "").strip()
    description = str(parsed.get("job_description") or "").strip()
    title = str(parsed.get("job_title") or "").strip()
    if requested_id and payload_id and requested_id != payload_id:
        raise _manual_fallback("Career Catalyst could not verify the Greenhouse job id for this URL.")
    if not title or len(description) < MINIMUM_DESCRIPTION_LENGTH:
        raise _manual_fallback("Career Catalyst could not verify the complete job description from this URL.")
    lowered = description.lower()
    nav_terms = sum(1 for term in ("view all jobs", "job openings", "department", "apply for this job") if term in lowered)
    role_terms = sum(1 for term in _terms_for_integrity(title) if term in lowered)
    if nav_terms >= 2 and role_terms == 0:
        raise _manual_fallback("Career Catalyst could not verify role-specific Greenhouse content from this URL.")


def _terms_for_integrity(value: str) -> list[str]:
    return [term for term in re.findall(r"[a-z0-9]+", value.lower()) if len(term) > 3]

def _manual_fallback(message: str) -> JobImportError:
    return JobImportError(
        f"{message} Keep the official URL and paste the job description text manually."
    )


def _validated_url(url: str) -> str:
    clean_url = str(url or "").strip()
    parsed = urlparse(clean_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise _manual_fallback("Enter a complete http:// or https:// career-page URL.")
    return urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", "", parsed.query, ""))


def _clean_visible_text(value: Any) -> str:
    """Decode nested HTML and remove common page chrome without inventing text."""
    text = _plain_html_text(value)
    blocked_lines = (
        "accept cookies", "cookie preferences", "privacy choices", "skip to content",
        "recommended jobs", "similar jobs", "view all jobs", "sign up for job alerts",
    )
    lines = []
    for raw_line in text.splitlines():
        line = " ".join(raw_line.split()).strip()
        if not line or any(term in line.lower() for term in blocked_lines):
            continue
        if not lines or lines[-1] != line:
            lines.append(line)
    return "\n".join(lines).strip()


def _merge_fields(*sources: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Merge successful extraction layers without erasing earlier values."""
    merged: Dict[str, Any] = {}
    warnings: list[str] = []
    for source in sources:
        if not source:
            continue
        warnings.extend(str(item) for item in source.get("import_warnings", []) if item)
        for key, value in source.items():
            if key == "import_warnings" or value in (None, "", [], {}):
                continue
            if merged.get(key) in (None, "", [], {}):
                merged[key] = value
    if warnings:
        merged["import_warnings"] = list(dict.fromkeys(warnings))
    return merged


def _organization_name(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("name")
    return company_display_name(canonical_employer_name(value))


def _posting_date(value: Any) -> str:
    """Keep the public posting date while removing time/offset noise."""
    text = str(value or "").strip()
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else text


def _structured_job_fields(posting: Dict[str, Any], url: str, platform: str = "") -> Dict[str, Any]:
    """Normalize JSON-LD-shaped job data into editable intake fields."""
    description = _clean_visible_text(
        posting.get("description") or posting.get("descriptionPlain")
        or posting.get("content") or posting.get("jobDescription")
    )
    description_metadata = extract_metadata(description) if description else {}
    organization = posting.get("hiringOrganization") or posting.get("company") or posting.get("organization")
    company = _organization_name(organization)
    location = _structured_location(posting) or _greenhouse_location(posting.get("location"))
    salary = _structured_salary(posting)
    if not salary:
        salary = str(posting.get("salaryRange") or posting.get("salary") or "").strip()
    if not salary:
        salary = str(description_metadata.get("salary_range") or "").strip()
    application_url = str(
        posting.get("applicationUrl") or posting.get("applyUrl") or posting.get("absolute_url")
        or posting.get("url") or url
    ).strip()
    job_id = str(
        posting.get("job_id") or posting.get("jobId") or posting.get("id")
        or posting.get("identifier") or ""
    ).strip()
    if isinstance(posting.get("identifier"), dict):
        job_id = str(posting["identifier"].get("value") or job_id).strip()
    return {
        "job_title": posting.get("title") or posting.get("text") or posting.get("name") or "",
        "company": company,
        "location": location or "Not specified",
        "work_arrangement": _work_arrangement(location, description),
        "job_id": job_id,
        "external_job_id": job_id,
        "source_platform": platform or _source_name(url),
        "source": platform or _source_name(url),
        "source_url": url,
        "posting_url": url,
        "official_url": url,
        "original_source_url": url,
        "application_url": application_url,
        "canonical_apply_url": application_url,
        "job_description": description,
        "salary_range": salary,
        "compensation": description_metadata.get("compensation"),
        "posting_date": _posting_date(
            posting.get("datePosted") or posting.get("postedAt") or posting.get("createdAt")
        ),
    }


def _path_segments(url: str) -> list[str]:
    return [segment for segment in urlparse(url).path.split("/") if segment]


def _lever_fields(url: str, timeout: int) -> Optional[Dict[str, Any]]:
    parsed = urlparse(url)
    segments = _path_segments(url)
    if not (parsed.hostname or "").endswith("lever.co") or len(segments) < 2:
        return None
    payload = _fetch_json(
        f"https://api.lever.co/v0/postings/{quote(segments[0], safe='')}/{quote(segments[-1], safe='')}",
        timeout,
    )
    description_parts = [payload.get("descriptionPlain") or payload.get("description") or ""]
    for item in payload.get("lists") or []:
        if isinstance(item, dict):
            description_parts.extend((item.get("text") or "", item.get("content") or ""))
    fields = _structured_job_fields(
        {
            **payload,
            "description": "\n".join(str(part) for part in description_parts if part),
            "applicationUrl": payload.get("applyUrl"),
            "location": (payload.get("categories") or {}).get("location"),
            "id": payload.get("id") or segments[-1],
        },
        url,
        "Lever",
    )
    fields["company"] = canonical_employer_name(segments[0].replace("-", " ").title())
    return fields


def _ashby_fields(url: str, timeout: int) -> Optional[Dict[str, Any]]:
    parsed = urlparse(url)
    segments = _path_segments(url)
    if not (parsed.hostname or "").endswith("ashbyhq.com") or len(segments) < 2:
        return None
    payload = _fetch_json(
        f"https://api.ashbyhq.com/posting-api/job-board/{quote(segments[0], safe='')}?includeCompensation=true",
        timeout,
    )
    jobs = payload.get("jobs") or []
    target = next(
        (
            job for job in jobs if isinstance(job, dict) and segments[-1] in {
                str(job.get("id") or ""), str(job.get("jobPostingId") or ""),
                str(job.get("jobUrl") or "").rstrip("/").split("/")[-1],
            }
        ),
        None,
    )
    if target is None:
        raise _manual_fallback("Ashby returned a job board, but not the requested posting.")
    fields = _structured_job_fields(target, url, "Ashby")
    fields["company"] = canonical_employer_name(
        target.get("companyName") or segments[0].replace("-", " ").title()
    )
    return fields


def _smartrecruiters_fields(url: str, timeout: int) -> Optional[Dict[str, Any]]:
    parsed = urlparse(url)
    segments = _path_segments(url)
    if not (parsed.hostname or "").endswith("smartrecruiters.com") or len(segments) < 2:
        return None
    company = segments[-2]
    job_id = segments[-1].split("-", 1)[0]
    payload = _fetch_json(
        f"https://api.smartrecruiters.com/v1/companies/{quote(company, safe='')}/postings/{quote(job_id, safe='')}",
        timeout,
    )
    sections = payload.get("jobAd") or {}
    description = "\n".join(
        str(value) for value in sections.values() if isinstance(value, str)
    )
    fields = _structured_job_fields({**payload, "description": description}, url, "SmartRecruiters")
    fields["company"] = canonical_employer_name(company.replace("-", " ").title())
    return fields


@dataclass(frozen=True)
class PlatformAdapter:
    """Deterministic public adapter; unsupported details fall through safely."""

    name: str
    hosts: tuple[str, ...]
    extractor: Optional[Callable[[str, int], Optional[Dict[str, Any]]]] = None

    def matches(self, url: str) -> bool:
        host = (urlparse(url).hostname or "").lower()
        return any(host == candidate or host.endswith(f".{candidate}") for candidate in self.hosts)

    def extract(self, url: str, timeout: int) -> Optional[Dict[str, Any]]:
        return self.extractor(url, timeout) if self.extractor else None


PLATFORM_ADAPTERS = (
    PlatformAdapter("Greenhouse", ("greenhouse.io",), lambda url, timeout: _extract_greenhouse_job(url, timeout)),
    PlatformAdapter("Lever", ("lever.co",), _lever_fields),
    PlatformAdapter("Ashby", ("ashbyhq.com",), _ashby_fields),
    PlatformAdapter("SmartRecruiters", ("smartrecruiters.com",), _smartrecruiters_fields),
    PlatformAdapter("Workday", ("myworkdayjobs.com", "workdayjobs.com")),
    PlatformAdapter("Jobvite", ("jobvite.com",)),
    PlatformAdapter("iCIMS", ("icims.com",)),
    PlatformAdapter("LinkedIn", ("linkedin.com",)),
)


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
        loaded = None
        for candidate in (script, unescape(script)):
            try:
                loaded = json.loads(candidate.strip())
                break
            except (json.JSONDecodeError, TypeError):
                continue
        if loaded is None:
            continue
        for item in _walk_json(loaded):
            item_type = item.get("@type")
            types = item_type if isinstance(item_type, list) else [item_type]
            if any(str(value).lower() == "jobposting" for value in types):
                return item
    return None


def _embedded_job_posting(html: str) -> Optional[Dict[str, Any]]:
    """Find useful job-shaped data in ordinary embedded JSON page state."""
    scripts = re.findall(
        r"<script\b[^>]*(?:type=[\"']application/json[\"']|id=[\"']__NEXT_DATA__[\"'])[^>]*>(.*?)</script>",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    candidates: list[tuple[int, Dict[str, Any]]] = []
    for script in scripts:
        try:
            loaded = json.loads(unescape(script).strip())
        except (json.JSONDecodeError, TypeError):
            continue
        for item in _walk_json(loaded):
            keys = {str(key).lower() for key in item}
            score = sum(
                bool(keys & group)
                for group in (
                    {"title", "jobtitle", "name"},
                    {"description", "jobdescription", "content"},
                    {"company", "hiringorganization", "organization"},
                    {"location", "joblocation", "locations"},
                )
            )
            if score >= 2:
                candidates.append((score, item))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


def _plain_html_text(value: Any) -> str:
    text = str(value or "")
    # Greenhouse sometimes returns HTML whose tags are themselves entity-escaped.
    # Decode before parsing and repeat a bounded number of times so neither raw tags
    # nor &lt;...&gt; fragments enter scoring, role analysis, or saved job files.
    for _ in range(3):
        decoded = unescape(text)
        parser = _VisibleTextParser()
        parser.feed(decoded)
        cleaned = "\n".join(parser.text_parts).strip()
        text = cleaned
        if not re.search(r"&(?:lt|gt|amp|quot|#\d+|#x[0-9a-f]+);|</?[a-z][^>]*>", text, re.I):
            break
    return text


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
        clean = ", ".join(
            str(part).strip() for part in parts
            if part and str(part).strip().lower() not in {"unavailable", "not specified", "n/a"}
        )
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
    if minimum in (None, 0, 0.0) and maximum in (None, 0, 0.0):
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
    if clean_title and not is_valid_role_title(clean_title):
        clean_title = ""
    return clean_title, clean_company


def _source_name(url: str) -> str:
    classified = classify_source(url)
    if classified.get("source_key") == "greenhouse":
        return "Official Greenhouse"
    if classified["source_type"] != "Unknown Source":
        return str(classified["display_name"])
    return "Official career page"


def create_job_markdown(job_data: Dict[str, Any]) -> str:
    """Render normalized job data into Career Catalyst's Markdown format."""
    source_url = job_data.get("official_url") or job_data.get("source_url") or ""
    fallback = infer_job_fields_from_url(source_url)
    title, company = _clean_identity(
        job_data.get("job_title") or job_data.get("role") or "",
        job_data.get("company") or "",
    )
    title = preferred_role_title("", title, source_url)
    company = company or fallback.get("company", "")
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
        ("Job ID", job_data.get("job_id") or fallback.get("job_id")),
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


def extract_job_fields(html: str, url: str) -> Dict[str, Any]:
    """Layer JSON-LD, embedded state, and semantic visible HTML without total loss."""
    clean_url = _validated_url(url)
    if not str(html or "").strip():
        return {
            "source_url": clean_url,
            "posting_url": clean_url,
            "official_url": clean_url,
            "original_source_url": clean_url,
            "import_warnings": ["The career page returned no readable content."],
        }
    structured = _job_posting(html)
    embedded = _embedded_job_posting(html)
    layers: list[Dict[str, Any]] = []
    if structured:
        layers.append(_structured_job_fields(structured, clean_url))
    if embedded and embedded is not structured:
        layers.append(_structured_job_fields(embedded, clean_url))

    parser = _VisibleTextParser()
    parser.feed(unescape(html))
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
    visible_text = _clean_visible_text(html)
    metadata = extract_metadata(visible_text)
    html_layer = {
        "job_title": preferred_role_title("", metadata.get("job_title") or title, clean_url),
        "company": canonical_employer_name(metadata.get("company") or company),
        "location": metadata.get("location") or "Not specified",
        "work_arrangement": metadata.get("work_arrangement") or _work_arrangement(metadata.get("location"), visible_text),
        "salary_range": metadata.get("salary_range") or "",
        "compensation": metadata.get("compensation"),
        "posting_date": metadata.get("posting_date") or "",
        "source": _source_name(clean_url),
        "source_platform": _source_name(clean_url),
        "source_url": clean_url,
        "posting_url": clean_url,
        "official_url": clean_url,
        "original_source_url": clean_url,
        "application_url": clean_url,
        "canonical_apply_url": clean_url,
        "job_description": visible_text,
    }
    layers.append(html_layer)
    merged = _merge_fields(*layers)
    if "icims" in html.lower():
        merged["source_platform"] = "iCIMS"
        merged["source"] = "iCIMS"
    fallback = infer_job_fields_from_url(clean_url)
    merged["company"] = canonical_employer_name(merged.get("company") or fallback.get("company"))
    merged["job_title"] = preferred_role_title("", merged.get("job_title"), clean_url)
    for key in ("job_id", "location"):
        if not merged.get(key) and fallback.get(key):
            merged[key] = fallback[key]
    return merged


def parse_imported_job(raw_text: str, url: str) -> Dict[str, Any]:
    """Parse canonical imported text into fields suitable for the intake form."""
    metadata = extract_metadata(raw_text)
    description_match = re.search(
        r"^##\s+Job Description\s*$\n(.*)", raw_text, flags=re.I | re.M | re.S
    )
    description = (description_match.group(1) if description_match else raw_text).strip()
    fallback = infer_job_fields_from_url(url)
    title, company = _clean_identity(metadata.get("job_title"), metadata.get("company"))
    title = preferred_role_title("", title, url)
    company = company or fallback.get("company", "")
    location = metadata.get("location") or fallback.get("location") or "Not specified"
    work_arrangement = metadata.get("work_arrangement") or _work_arrangement(location, description)
    parsed: Dict[str, Any] = {
        "job_title": title,
        "company": company,
        "location": location,
        "work_arrangement": work_arrangement or "Not specified",
        "salary_range": metadata.get("salary_range") or "",
        "compensation": metadata.get("compensation"),
        "posting_date": metadata.get("posting_date") or "",
        "job_id": fallback.get("job_id") or "",
        "source": _source_name(url),
        "source_url": url,
        "official_url": url,
        "original_source_url": url,
        "canonical_apply_url": url,
        "job_description": description,
    }
    parsed.update(normalize_job_source(parsed))
    parsed["source_url"] = url
    parsed["official_url"] = url
    parsed["original_source_url"] = url
    parsed["canonical_apply_url"] = parsed.get("canonical_apply_url") or url
    # Validate the minimum useful payload before a UI can treat import as successful.
    create_job_markdown(parsed)
    return parsed


def import_job_from_url(url: str, timeout: int = 12) -> Dict[str, Any]:
    """Layer public platform adapters and page parsing into an editable result."""
    clean_url = _validated_url(url)
    adapter = next((candidate for candidate in PLATFORM_ADAPTERS if candidate.matches(clean_url)), None)
    adapted: Optional[Dict[str, Any]] = None
    adapter_warning = ""
    if adapter and adapter.extractor:
        try:
            adapted = adapter.extract(clean_url, timeout)
        except JobImportError as error:
            adapter_warning = str(error)
    if adapted and all(
        (
            adapted.get("company"),
            adapted.get("job_title"),
            len(str(adapted.get("job_description") or "").strip()) >= MINIMUM_DESCRIPTION_LENGTH,
        )
    ):
        adapted.update(normalize_job_source(adapted))
        adapted["import_status"] = "success"
        adapted["missing_fields"] = []
        return adapted

    page_fields: Dict[str, Any] = {}
    page_warning = ""
    try:
        html = fetch_job_page(clean_url, timeout)
        page_fields = extract_job_fields(html, clean_url)
    except JobImportError as error:
        page_warning = str(error)
    merged = _merge_fields(adapted, page_fields)
    merged.setdefault("source_url", clean_url)
    merged.setdefault("posting_url", clean_url)
    merged.setdefault("official_url", clean_url)
    merged.setdefault("original_source_url", clean_url)
    if adapter:
        merged.setdefault("source_platform", adapter.name)
        merged.setdefault("source", adapter.name)
    merged.update(normalize_job_source(merged))
    missing = []
    for key, label in (
        ("company", "employer"),
        ("job_title", "role title"),
        ("job_description", "job description"),
    ):
        value = str(merged.get(key) or "").strip()
        if not value or (key == "job_description" and len(value) < MINIMUM_DESCRIPTION_LENGTH):
            missing.append(label)
    warnings = list(merged.get("import_warnings") or [])
    warnings.extend(value for value in (adapter_warning, page_warning) if value)
    if missing:
        warnings.append("Manual review is needed for: " + ", ".join(missing) + ".")
    merged["import_warnings"] = list(dict.fromkeys(warnings))
    merged["missing_fields"] = missing
    merged["import_status"] = "partial" if merged and missing else "success"
    if not merged.get("company") and not merged.get("job_title") and not merged.get("job_description"):
        raise _manual_fallback(
            page_warning or adapter_warning or "The source blocked or did not expose public job details."
        )
    return merged
