"""Shared role-family detection and claim safeguards."""

from typing import Any, Dict, List


GOOGLE_YOUTUBE_SIGNALS = (
    "youtube",
    "google ads",
    "brand auction",
)

GOOGLE_IMPLICATION_PHRASES = (
    "worked at google",
    "inside google",
    "employed by google",
    "google employee",
    "my employment at google",
    "owned google products",
    "owned google advertising products",
    "partnered directly with google executives",
    "internal google relationship",
    "internal referral",
    "has an internal referral",
    "i know the team",
    "knows the team",
    "family connection",
    "family relationship",
    "family at google",
    "family member at google",
    "relative at google",
    "my cousin at google",
    "my sibling at google",
    "my spouse at google",
)


def is_google_youtube_role(parsed_job: Dict[str, Any]) -> bool:
    """Identify Google/YouTube activation roles from local parsed job details."""
    company = str(parsed_job.get("company") or "").strip().lower()
    text = " ".join(
        str(value)
        for value in (
            parsed_job.get("job_title", ""),
            parsed_job.get("raw_text", ""),
            *parsed_job.get("keywords", []),
        )
    ).lower()
    return company == "google" or any(
        signal in text for signal in GOOGLE_YOUTUBE_SIGNALS
    )


def google_claim_violations(text: str) -> List[str]:
    """Return phrases that imply unsupported Google access, employment, or family ties."""
    lowered = text.lower()
    return [phrase for phrase in GOOGLE_IMPLICATION_PHRASES if phrase in lowered]
