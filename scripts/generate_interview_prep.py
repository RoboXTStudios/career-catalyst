"""Backward-compatible entry point for role-specific Career Intelligence."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Union

try:
    from .career_intelligence import generate_career_intelligence
except ImportError:
    from career_intelligence import generate_career_intelligence


PathInput = Union[str, Path]


def generate_interview_prep(
    job_path: PathInput,
    project_root: Optional[PathInput] = None,
    role_intent: Optional[Dict[str, Any]] = None,
    *,
    additional_context: str = "",
    associated_evidence_projects: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Delegate to the single structured Career Intelligence engine."""
    return generate_career_intelligence(
        job_path,
        project_root,
        role_intent,
        additional_context=additional_context,
        associated_evidence_projects=associated_evidence_projects,
    )
