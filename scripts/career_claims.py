"""Shared, canonical public career claims for generated candidate materials."""

from __future__ import annotations

import re
from typing import Any


PUBLIC_OMG23_NAME = "OMG23 (Omnicom Media Group)"
HISTORICAL_OMG23_ALIASES = (
    "OMD Entertainment",
    "OMG23 / OMD Entertainment",
    "Omnicom Media Group",
)
STALE_PUBLIC_CLAIMS = (
    "OMG23 / OMD Entertainment",
    "cross-functional teams of 60+",
    "teams of 60+",
    "more than 60 people",
    "led a team of 64",
)
DEFAULT_LEADERSHIP_CLAIM = (
    "led 10 direct reports and provided strategic and operational leadership across "
    "an integrated 64-person organization"
)


class PublicCareerClaimError(ValueError):
    """Raised when generated material uses a superseded public career claim."""


def omg23_position(career_data: dict[str, Any]) -> dict[str, Any]:
    positions = career_data.get("data", {}).get("positions", {}).get("positions", [])
    return next(
        (
            position
            for position in positions
            if "omg23" in str(position.get("company") or "").lower()
            or any(
                "omg23" in str(alias).lower()
                for alias in position.get("internal_aliases", [])
            )
        ),
        {},
    )


def public_omg23_name(career_data: dict[str, Any]) -> str:
    return str(omg23_position(career_data).get("company") or PUBLIC_OMG23_NAME)


def leadership_claim(career_data: dict[str, Any]) -> str:
    achievements = career_data.get("data", {}).get("achievements", {}).get(
        "achievements", []
    )
    claim = next(
        (
            str(item.get("statement") or "")
            for item in achievements
            if item.get("id") == "cross_functional_leadership"
        ),
        "",
    )
    if not claim:
        return DEFAULT_LEADERSHIP_CLAIM
    if "10 direct reports" not in claim or "64-person organization" not in claim:
        raise PublicCareerClaimError(
            "Canonical leadership evidence must distinguish 10 direct reports from the "
            "integrated 64-person organization."
        )
    claim = claim.rstrip(".")
    return claim[:1].lower() + claim[1:]


def historical_omg23_aliases(career_data: dict[str, Any]) -> tuple[str, ...]:
    configured = omg23_position(career_data).get("internal_aliases", [])
    return tuple(dict.fromkeys([*HISTORICAL_OMG23_ALIASES, *map(str, configured)]))


def is_ai_transformation_role(parsed_job: dict[str, Any]) -> bool:
    text = " ".join(
        str(value or "")
        for value in (
            parsed_job.get("job_title"),
            parsed_job.get("raw_text"),
            parsed_job.get("job_description"),
        )
    ).lower()
    return (
        any(
            phrase in text
            for phrase in (
                "ai transformation",
                "artificial intelligence transformation",
                "marketing transformation",
                "martech transformation",
            )
        )
        or ("ai" in text and "change management" in text and "adoption" in text)
    )


def public_claim_violations(text: str) -> list[str]:
    return [
        phrase
        for phrase in STALE_PUBLIC_CLAIMS
        if re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, flags=re.I)
    ]


def validate_public_career_claims(text: str) -> None:
    violations = public_claim_violations(str(text or ""))
    if violations:
        raise PublicCareerClaimError(
            "Generated material uses superseded public career language: "
            + ", ".join(violations)
        )
