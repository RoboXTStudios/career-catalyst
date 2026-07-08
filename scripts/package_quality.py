"""Calculate and render a practical post-generation package quality summary."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict

try:
    from .filename_utils import build_upload_filename
except ImportError:
    from filename_utils import build_upload_filename


def _bounded(value: float) -> int:
    return int(max(0, min(100, round(value))))


def _read(path_value: Any) -> str:
    path = Path(str(path_value or ""))
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def calculate_package_quality(
    match_report: Dict[str, Any],
    resume_result: Dict[str, Any],
    cover_letter_result: Dict[str, Any],
    intelligence: Dict[str, Any],
) -> Dict[str, Any]:
    """Return normalized resume, cover-letter, ATS, voice, and confidence scores."""
    match_score = _bounded(float(match_report.get("match_score") or 55))
    cover_text = _read(cover_letter_result.get("output_path"))
    cover_words = int(cover_letter_result.get("word_count") or len(re.findall(r"\b\w+\b", cover_text)))
    cover_range_score = 100 if 275 <= cover_words <= 325 else 90 if 250 <= cover_words <= 400 else 45
    banned = ("i am writing to express my interest", "perfect fit", "synergies", "thrilled")
    voice_penalty = 15 * sum(phrase in cover_text.lower() for phrase in banned)
    voice_confidence = float(intelligence.get("confidence") or 0.5)
    voice_match = _bounded((voice_confidence * 100) - voice_penalty)
    missing = len(match_report.get("missing_keywords") or [])
    matched = len(match_report.get("top_matching_skills") or [])
    ats = _bounded(match_score + min(10, matched * 2) - min(15, missing))
    resume_score = _bounded((match_score * 0.8) + (ats * 0.2))
    cover_score = _bounded((cover_range_score * 0.55) + (voice_match * 0.45))
    confidence_score = _bounded((resume_score + cover_score + ats + voice_match) / 4)
    confidence = "High" if confidence_score >= 80 else "Medium" if confidence_score >= 60 else "Low"
    return {
        "resume_tailoring_score": resume_score,
        "cover_letter_score": cover_score,
        "ats_keyword_match": ats,
        "voice_match": voice_match,
        "confidence_level": confidence,
        "confidence_score": confidence_score,
    }


def save_package_summary(
    root: Path,
    parsed_job: Dict[str, Any],
    freshness: Dict[str, Any],
    opportunity: Dict[str, Any],
    quality: Dict[str, Any],
) -> Dict[str, Any]:
    """Write the user-facing intelligence and quality checkpoint into the package."""
    filename = build_upload_filename(
        "Trisha Lynch",
        str(parsed_job.get("job_title") or "Role"),
        str(parsed_job.get("company") or "Company"),
        "Package Summary",
        "txt",
    )
    path = root / "exports" / "strategy_packs" / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    dimensions = "\n".join(
        f"- {name}: {score}/100" for name, score in opportunity["dimensions"].items()
    )
    content = f"""# Application Package Summary

## Opportunity

- Overall Score: {opportunity['overall_score']}/100
- Apply Recommendation: {opportunity['apply_recommendation']}
- Freshness: {freshness['label']}
- Posting Status: {freshness['posting_status']}
- Posting Date: {freshness.get('posting_date') or 'Unknown'}
- Salary: {parsed_job.get('salary_range') or 'Not disclosed'}

### Score Dimensions

{dimensions}

## Package Quality Check

- Resume Tailoring Score: {quality['resume_tailoring_score']}/100
- Cover Letter Score: {quality['cover_letter_score']}/100
- ATS Keyword Match: {quality['ats_keyword_match']}/100
- Voice Match: {quality['voice_match']}/100
- Confidence Level: {quality['confidence_level']}
"""
    path.write_text(content, encoding="utf-8")
    return {"output_path": str(path)}
