"""Candidate-facing resume platform policy shared by text and DOCX output."""

from __future__ import annotations

from typing import Any, Iterable


RESUME_EXCLUDED_PLATFORMS = frozenset({"notion", "substack"})


def filter_resume_platform_items(items: Iterable[Any]) -> list[str]:
    """Remove resume-prohibited platforms while preserving every other item."""
    return [
        str(item).strip()
        for item in items
        if str(item).strip().casefold() not in RESUME_EXCLUDED_PLATFORMS
    ]
