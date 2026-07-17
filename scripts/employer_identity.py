"""Applicant-facing employer identity without rewriting historical source data."""

from __future__ import annotations

import re
from typing import Any


OMG23_DISPLAY_NAME = "OMG23 / Omnicom Media Group"
OMG23_SHORTHAND = "OMG23"
OMG23_SOURCE_ALIASES = (
    "OMG23 / OMD Entertainment, Omnicom Media Group",
    "OMG23 / OMD Entertainment",
    "OMD Entertainment, Omnicom Media Group",
    "OMD Entertainment",
)


def canonical_employer_name(value: Any) -> str:
    """Map historical OMG23 aliases to one applicant-facing display name."""
    text = str(value or "").strip()
    normalized = " ".join(re.findall(r"[a-z0-9]+", text.lower()))
    if normalized in {
        "omg23",
        "omd entertainment",
        "omnicom media group",
        "omg23 omd entertainment",
        "omg23 omd entertainment omnicom media group",
        "omd entertainment omnicom media group",
        "omg23 omnicom media group",
    }:
        return OMG23_DISPLAY_NAME
    return text


def normalize_applicant_employer_names(text: Any) -> str:
    """Normalize long-form aliases and use OMG23 after the first full reference."""
    result = str(text or "")
    aliases = sorted(
        (*OMG23_SOURCE_ALIASES, OMG23_DISPLAY_NAME), key=len, reverse=True
    )
    pattern = re.compile(
        "|".join(re.escape(alias) for alias in aliases), flags=re.IGNORECASE
    )
    occurrences = 0

    def replace(_match: re.Match[str]) -> str:
        nonlocal occurrences
        occurrences += 1
        return OMG23_DISPLAY_NAME if occurrences == 1 else OMG23_SHORTHAND

    return pattern.sub(replace, result)


def employer_name_violations(text: Any) -> list[dict[str, Any]]:
    """Return structured applicant-facing employer naming violations."""
    value = str(text or "")
    violations: list[dict[str, Any]] = []
    for alias in OMG23_SOURCE_ALIASES:
        if re.search(re.escape(alias), value, flags=re.IGNORECASE):
            violations.append(
                {
                    "code": "historical_employer_alias",
                    "detail": alias,
                    "correctable": True,
                }
            )
    full_count = len(
        re.findall(re.escape(OMG23_DISPLAY_NAME), value, flags=re.IGNORECASE)
    )
    if full_count > 1:
        violations.append(
            {
                "code": "repeated_full_employer_name",
                "detail": full_count,
                "correctable": True,
            }
        )
    paragraph_starts = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", value)
        if paragraph.strip()
    ]
    for previous, current in zip(paragraph_starts, paragraph_starts[1:]):
        if previous.startswith(f"At {OMG23_DISPLAY_NAME}") and current.startswith(
            f"At {OMG23_DISPLAY_NAME}"
        ):
            violations.append(
                {
                    "code": "repeated_employer_paragraph_opening",
                    "detail": OMG23_DISPLAY_NAME,
                    "correctable": True,
                }
            )
            break
    return violations
