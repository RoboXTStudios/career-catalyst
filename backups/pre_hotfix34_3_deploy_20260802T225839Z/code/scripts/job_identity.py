"""Validate imported role identity and infer conservative fields from job URLs."""

from __future__ import annotations

import re
from typing import Any, Dict
from urllib.parse import unquote, urlparse

try:
    from .filename_utils import is_valid_role_title
except ImportError:
    from filename_utils import is_valid_role_title


def infer_job_fields_from_url(url: Any) -> Dict[str, str]:
    """Infer only fields encoded plainly in a supported official job URL."""
    clean_url = str(url or "").strip()
    parsed = urlparse(clean_url)
    host = (parsed.hostname or "").lower()
    segments = [unquote(value).strip() for value in parsed.path.split("/") if value.strip()]
    inferred: Dict[str, str] = {}

    if host == "careers.paramount.com" or host.endswith(".careers.paramount.com"):
        inferred["company"] = "Paramount"
        inferred["source"] = "Paramount Careers"
        if segments and segments[-1].isdigit():
            inferred["job_id"] = segments[-1]
        slug = next((segment for segment in segments if "-" in segment and not segment.isdigit()), "")
        tokens = [token.strip() for token in slug.split("-") if token.strip()]
        if len(tokens) >= 4:
            state_index = next(
                (
                    index
                    for index in range(len(tokens) - 1, 0, -1)
                    if re.fullmatch(r"[A-Z]{2}", tokens[index])
                    and index + 1 < len(tokens)
                    and re.fullmatch(r"\d{5}", tokens[index + 1])
                ),
                None,
            )
            if state_index and state_index > 1:
                city = tokens[0]
                title = " ".join(tokens[1:state_index])
                title = re.sub(r"\s+,", ",", title)
                title = re.sub(r"\s+", " ", title).strip(" ,-_")
                if is_valid_role_title(title):
                    inferred["job_title"] = title
                if re.fullmatch(r"[A-Za-z][A-Za-z .']+", city):
                    inferred["location"] = f"{city}, {tokens[state_index]}"
    return inferred


def preferred_role_title(existing: Any, imported: Any, url: Any = "") -> str:
    """Protect a valid user title, then accept valid import or URL fallback."""
    current = re.sub(r"\s+", " ", str(existing or "").strip())
    candidate = re.sub(r"\s+", " ", str(imported or "").strip())
    if is_valid_role_title(current):
        return current
    if is_valid_role_title(candidate):
        return candidate
    fallback = infer_job_fields_from_url(url).get("job_title", "")
    return fallback if is_valid_role_title(fallback) else ""
