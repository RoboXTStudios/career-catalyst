"""Calculate and render a practical post-generation package quality summary."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Mapping

try:
    from .filename_utils import build_upload_filename
    from .text_cleanup import normalize_candidate_text
except ImportError:
    from filename_utils import build_upload_filename
    from text_cleanup import normalize_candidate_text


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
    tailoring_metadata: Mapping[str, Any] | None = None,
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
        f"- {name}: {score}/100" if isinstance(score, (int, float)) else f"- {name}: Not scored (neutral)"
        for name, score in opportunity["dimensions"].items()
    )
    compensation = parsed_job.get("compensation") or {}
    salary_display = (
        parsed_job.get("salary_range")
        or compensation.get("status_message")
        or "Compensation unknown — verify posting or recruiter details."
    )
    evidence_metadata = dict(tailoring_metadata or {})
    artifact_usage = evidence_metadata.get("artifact_usage") or {}
    evidence_lines = []
    for selected in evidence_metadata.get("selected_evidence") or []:
        evidence_id = str(selected.get("id") or "")
        title = str(selected.get("title") or "Untitled Evidence")
        uses = []
        for artifact_key, label in (
            ("ats_resume", "ATS résumé"),
            ("styled_resume", "styled résumé"),
            ("cover_letter", "cover letter"),
        ):
            selection = artifact_usage.get(artifact_key) or {}
            used = next(
                (item for item in selection.get("used") or [] if str(item.get("id") or "") == evidence_id),
                None,
            )
            omitted = next(
                (item for item in selection.get("omitted") or [] if str(item.get("id") or "") == evidence_id),
                None,
            )
            if used:
                uses.append(f"{label}: Used")
            elif omitted:
                uses.append(f"{label}: Not used ({omitted.get('reason')})")
            else:
                uses.append(f"{label}: Not used (Better suited to another package artifact.)")
        supported = ", ".join(str(value) for value in selected.get("matched_signals") or []) or "No direct requirement signal recorded"
        evidence_lines.append(
            f"- {title} — Requirements supported: {supported}. " + "; ".join(uses)
        )
    fallback_lines = [
        f"- {item.get('title')} ({item.get('source')})"
        for item in evidence_metadata.get("unselected_fallback_used") or []
    ]
    evidence_section = "\n".join(evidence_lines) or "- No Relevant Evidence was selected."
    fallback_section = "\n".join(fallback_lines) or "- None"
    report = dict(quality.get("quality_report") or {})
    quality_report = "\n".join(
        f"- {label}: {report.get(key, 'Not evaluated')}"
        for key, label in (
            ("role_requirements_referenced", "Role requirements referenced"),
            ("evidence_used", "Evidence used"),
            ("unsupported_claim_check", "Unsupported-claim check"),
            ("generic_language_check", "Generic-language check"),
            ("employer_name_check", "Employer-name check"),
            ("age_language_check", "Age-language check"),
            ("punctuation_check", "Punctuation check"),
            ("page_length_result", "Page-length result"),
        )
    )
    content = f"""# Application Package Summary

## Opportunity

- Overall Score: {opportunity['overall_score']}/100
- Apply Recommendation: {opportunity['apply_recommendation']}
- Freshness: {freshness['label']}
- Posting Status: {freshness['posting_status']}
- Posting Date: {freshness.get('posting_date') or 'Unknown'}
- Salary: {salary_display}

### Score Dimensions

{dimensions}

## Package Quality Check

- Resume Tailoring Score: {quality['resume_tailoring_score']}/100
- Cover Letter Score: {quality['cover_letter_score']}/100
- ATS Keyword Match: {quality['ats_keyword_match']}/100
- Voice Match: {quality['voice_match']}/100
- Confidence Level: {quality['confidence_level']}

## Evidence Usage

- Selected: {evidence_metadata.get('selected_count', 0)}
- Used anywhere: {evidence_metadata.get('used_anywhere_count', 0)}
- Omitted from the entire package: {evidence_metadata.get('omitted_from_package_count', 0)}

{evidence_section}

### Unselected Fallback Evidence

{fallback_section}

## Candidate-Facing Quality Report

{quality_report}
"""
    path.write_text(normalize_candidate_text(content), encoding="utf-8")
    return {"output_path": str(path)}
