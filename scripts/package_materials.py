"""Validate generated package files and choose safe, user-facing open paths."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable


MATERIAL_SPECS = (
    ("ATS Resume", "Resumes", ("ats_docx", "ats_resume_text"), ("docx", "txt", "md")),
    ("Styled Resume", "Resumes", ("styled_docx", "styled_pdf"), ("docx", "pdf", "txt", "md")),
    ("PDF Resume", "Resumes", ("styled_pdf",), ("pdf",)),
    ("Tailored Resume", "Resumes", ("tailored_resume_docx", "resume_text", "resume_markdown"), ("docx", "pdf", "txt", "md")),
    ("Cover Letter", "Letter/Application", ("cover_letter_docx", "cover_letter_text", "cover_letter"), ("docx", "pdf", "txt", "md")),
    ("Application Note", "Letter/Application", ("application_note_text", "application_note"), ("txt", "md")),
    ("Recruiter Message", "Outreach", ("recruiter_message_text", "recruiter_message"), ("txt", "md")),
    ("Hiring Manager Message", "Outreach", ("hiring_manager_message_text", "hiring_manager_message"), ("txt", "md")),
    ("Strategy Pack", "Strategy/Prep", ("strategy_pack_text", "strategy_pack"), ("txt", "md")),
    ("Interview Prep", "Strategy/Prep", ("interview_prep_text", "interview_prep"), ("txt", "md")),
    ("Package Summary", "Strategy/Prep", ("package_summary_text", "package_summary"), ("txt", "md")),
    ("Job Description", "Source", ("job_file",), ("txt", "md")),
)


def _existing_candidates(outputs: Dict[str, Any], keys: Iterable[str]) -> list[Path]:
    candidates = []
    for key in keys:
        value = outputs.get(key)
        if value and Path(str(value)).is_file():
            candidates.append(Path(str(value)))
    return candidates


def _preferred_path(candidates: list[Path], formats: tuple[str, ...]) -> Path | None:
    if not candidates:
        return None
    rank = {suffix: index for index, suffix in enumerate(formats)}
    return min(
        candidates,
        key=lambda path: (
            rank.get(path.suffix.lower().lstrip("."), len(rank)),
            -path.stat().st_mtime,
            path.name.lower(),
        ),
    )


def validate_package_outputs(
    outputs: Dict[str, Any], errors: Dict[str, str] | None = None
) -> list[Dict[str, Any]]:
    """Return a deterministic checklist with no active path for missing files."""
    checklist = []
    error_map = errors or {}
    for label, group, keys, formats in MATERIAL_SPECS:
        declared = [str(outputs[key]) for key in keys if outputs.get(key)]
        candidates = _existing_candidates(outputs, keys)
        preferred = _preferred_path(candidates, formats)
        missing_reason = None
        if preferred is None:
            missing_reason = next(
                (error_map[key] for key in keys if error_map.get(key)), None
            )
            if not missing_reason and label == "PDF Resume":
                missing_reason = "PDF not generated / unsupported"
            if not missing_reason:
                missing_reason = "Missing / not generated"
        checklist.append(
            {
                "material_type": label,
                "display_label": label,
                "group": group,
                "expected_paths": declared,
                "exists": preferred is not None,
                "preferred_open_path": str(preferred) if preferred else None,
                "file_format": preferred.suffix.lower().lstrip(".") if preferred else None,
                "missing_reason": missing_reason,
            }
        )
    return checklist


def preferred_material_paths(checklist: Iterable[Dict[str, Any]]) -> Dict[str, str]:
    """Flatten only verified checklist paths for tracker persistence and buttons."""
    return {
        str(item["material_type"]): str(item["preferred_open_path"])
        for item in checklist
        if item.get("exists") and item.get("preferred_open_path")
    }


def create_text_companion(path_value: Any) -> str | None:
    """Create a copy/paste TXT companion for a generated Markdown file."""
    path = Path(str(path_value or ""))
    if not path.is_file() or path.suffix.lower() != ".md":
        return None
    content = path.read_text(encoding="utf-8", errors="replace")
    content = re.sub(r"^#{1,6}\s+", "", content, flags=re.MULTILINE)
    content = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", content)
    content = content.replace("**", "")
    text_path = path.with_suffix(".txt")
    text_path.write_text(content.rstrip() + "\n", encoding="utf-8")
    return str(text_path)
