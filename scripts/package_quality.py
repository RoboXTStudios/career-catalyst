"""Calculate and render a practical post-generation package quality summary."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, Mapping

try:
    from .filename_utils import build_upload_filename
    from .text_cleanup import normalize_candidate_text
    from .candidate_output import validate_candidate_output
    from .career_claims import validate_public_career_claims
    from .evidence_tailoring import candidate_project_reference_violations
    from .package_context import PackageContextMismatchError, validate_material_context
    from .resume_foundation import validate_candidate_language
except ImportError:
    from filename_utils import build_upload_filename
    from text_cleanup import normalize_candidate_text
    from candidate_output import validate_candidate_output
    from career_claims import validate_public_career_claims
    from evidence_tailoring import candidate_project_reference_violations
    from package_context import PackageContextMismatchError, validate_material_context
    from resume_foundation import validate_candidate_language


_QUALITY_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in",
    "into", "is", "it", "of", "on", "or", "that", "the", "their", "this",
    "to", "was", "were", "will", "with", "i", "my", "we", "our", "would",
}
_GENERIC_ROLE_LABELS = {
    "default", "general operations", "general_operations", "operations", "inferred",
}
_KNOWN_GENERIC_FILLER = (
    "i am writing to express my interest",
    "perfect fit",
    "synergies",
    "thrilled to apply",
)

_PLACEHOLDER_PATTERNS = (
    r"\[\s*(?:company|role|hiring manager)\s*\]",
    r"\b(?:COMPANY_NAME|ROLE_TITLE|INSERT\s+(?:COMPANY|ROLE)|TBD|TODO)\b",
    r"\bHiring Manager\b",
    r"\bRole Title\b",
    r"(?:\bat|for|to|from)\s+Company\b",
    r"(?m)^\s*Company\s*$",
    r"(?m)^\s*<!--[^>]*company:\s*Company\s*-->\s*$",
)
_EXPERIENTIAL_STALE_TERMS = (
    "martech",
    "adtech",
    "marketing technology",
    "platform implementation",
)
_EXPERIENTIAL_DIRECT_CLAIM_RE = re.compile(
    r"\b(?:led|managed|owned|directed|produced|executed|oversaw|operated|coordinated)\b"
    r"[^.!?\n]{0,100}\b(?:fabrication|venues?|venue logistics|production logistics|"
    r"load[- ]?in|load[- ]?out|onsite execution|onsite builds?)\b",
    flags=re.IGNORECASE,
)


def _effective_role_family(
    parsed_job: Mapping[str, Any], tailoring_metadata: Mapping[str, Any]
) -> str:
    role_intelligence = tailoring_metadata.get("role_intelligence") or {}
    effective = role_intelligence.get("effective") or {}
    raw = str(
        effective.get("role_family")
        or parsed_job.get("role_family")
        or parsed_job.get("generation_role_family")
        or ""
    ).strip().lower()
    if "experiential" in raw and "live event" in raw:
        return "experiential_live_event_production"
    if "strategy" in raw and "operations" in raw:
        return "strategy_gtm_operations"
    return raw.replace(" ", "_")


def _readiness_reasons(
    artifact_type: str,
    text: str,
    parsed_job: Mapping[str, Any],
    tailoring_metadata: Mapping[str, Any],
) -> list[str]:
    """Apply narrow candidate-facing checks that belong at the final boundary."""
    reasons: list[str] = []
    for pattern in _PLACEHOLDER_PATTERNS:
        if re.search(pattern, text):
            reasons.append(
                f"{artifact_type.replace('_', ' ').title()} contains unresolved placeholder text."
            )
            break

    family = _effective_role_family(parsed_job, tailoring_metadata)
    if family == "experiential_live_event_production":
        if artifact_type == "cover_letter" and any(
            term in text.lower() for term in _EXPERIENTIAL_STALE_TERMS
        ):
            reasons.append(
                "Cover Letter uses stale MarTech/AdTech or platform language for an experiential role."
            )
        if _EXPERIENTIAL_DIRECT_CLAIM_RE.search(text):
            reasons.append(
                "Candidate-facing copy makes an unsupported direct experiential-production ownership claim."
            )
        lowered = text.lower()
        if "experiential production & live events leader" in lowered or "live-events operator" in lowered:
            reasons.append(
                "Candidate-facing copy replaces the candidate's supported operations identity with a direct live-event identity."
            )

    if artifact_type == "cover_letter":
        company = str(parsed_job.get("company") or "").strip()
        if (
            company
            and company.lower() not in {"company", "unknown", "unknown company"}
            and tailoring_metadata.get("role_intelligence")
            and len(str(parsed_job.get("raw_text") or "")) > 200
        ):
            normalized_company = normalize_candidate_text(company).lower()
            normalized_text = normalize_candidate_text(text).lower()
            if normalized_company not in normalized_text:
                reasons.append(
                    f"Cover Letter does not name the known employer '{company}'."
                )
        if "i bring a practical operating style:" in text.lower() and "the through line in my experience" in text.lower():
            reasons.append(
                "Cover Letter contains repetitive generic operating-style closing paragraphs."
            )
    return reasons


def _bounded(value: float) -> int:
    return int(max(0, min(100, round(value))))


def _read(path_value: Any) -> str:
    path = Path(str(path_value or ""))
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _candidate_text(value: Any) -> str:
    """Read a generated artifact and apply the final candidate-text boundary."""
    if isinstance(value, (str, Path)):
        try:
            if Path(str(value)).is_file():
                return normalize_candidate_text(_read(value))
        except OSError:
            # Long candidate text is not a filesystem path.
            pass
    return normalize_candidate_text(str(value or ""))


def _paragraphs(text: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", block).strip()
        for block in re.split(r"\n\s*\n", text)
        if len(re.findall(r"\b\w+\b", block)) >= 10
    ]


def _tokens(text: str, excluded: set[str] | None = None) -> set[str]:
    excluded = excluded or set()
    return {
        token
        for token in re.findall(r"[a-z0-9]+", text.lower())
        if len(token) > 2 and token not in _QUALITY_STOP_WORDS and token not in excluded
    }


def _project_aliases(project: Mapping[str, Any]) -> tuple[str, ...]:
    values = []
    for key in ("title", "name", "id"):
        raw = str(project.get(key) or "").strip()
        if raw:
            values.extend((raw, raw.replace("_", " ")))
    return tuple(dict.fromkeys(normalize_candidate_text(value).lower() for value in values if value))


def _duplicate_proof_reasons(
    cover_text: str, projects: list[Mapping[str, Any]]
) -> list[str]:
    """Find materially repeated proof, anchored to a named Evidence project."""
    paragraphs = _paragraphs(cover_text)
    reasons: list[str] = []
    for project in projects:
        title = str(project.get("title") or project.get("name") or project.get("id") or "").strip()
        aliases = _project_aliases(project)
        if not title or not aliases:
            continue
        anchor_terms = set()
        for alias in aliases:
            anchor_terms.update(_tokens(alias))
        matching = []
        for index, paragraph in enumerate(paragraphs):
            lower = paragraph.lower()
            if any(alias in lower for alias in aliases):
                matching.append((index, paragraph))
                continue
            if anchor_terms and len(_tokens(paragraph) & anchor_terms) >= max(1, len(anchor_terms) // 2):
                matching.append((index, paragraph))
        for left_index in range(len(matching)):
            index_a, paragraph_a = matching[left_index]
            for index_b, paragraph_b in matching[left_index + 1 :]:
                excluded = set(anchor_terms)
                tokens_a = _tokens(paragraph_a, excluded)
                tokens_b = _tokens(paragraph_b, excluded)
                if not tokens_a or not tokens_b:
                    continue
                jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
                sequence = SequenceMatcher(
                    None,
                    " ".join(sorted(tokens_a)),
                    " ".join(sorted(tokens_b)),
                ).ratio()
                if jaccard >= 0.32 and sequence >= 0.58:
                    reasons.append(
                        f"Cover letter repeats the \u201c{title}\u201d proof in multiple paragraphs."
                    )
                    break
            if reasons and reasons[-1].endswith(f"\u201c{title}\u201d proof in multiple paragraphs."):
                break
    return list(dict.fromkeys(reasons))


def _override_conflict_reasons(
    combined_text: str, tailoring_metadata: Mapping[str, Any]
) -> list[str]:
    role_intelligence = tailoring_metadata.get("role_intelligence") or {}
    inferred = role_intelligence.get("inferred") or {}
    effective = role_intelligence.get("effective") or {}
    reasons: list[str] = []
    for field, label in (
        ("company_voice", "company voice"),
        ("category", "category"),
        ("role_family", "role family"),
    ):
        inferred_value = str(
            inferred.get(field)
            or inferred.get({"company_voice": "company_voice_label", "category": "company_category_label", "role_family": "role_family_label"}[field])
            or ""
        ).strip()
        effective_value = str(effective.get(field) or "").strip()
        if not inferred_value or not effective_value:
            continue
        if inferred_value.lower().replace("_", " ") == effective_value.lower().replace("_", " "):
            continue
        if inferred_value.lower() in _GENERIC_ROLE_LABELS:
            continue
        if inferred_value.lower() in combined_text.lower():
            reasons.append(
                f"Candidate-facing copy contains stale inferred {label} language \u201c{inferred_value}\u201d despite the effective override \u201c{effective_value}\u201d."
            )
    return reasons


def evaluate_candidate_facing_quality(
    artifacts: Mapping[str, Any],
    *,
    parsed_job: Mapping[str, Any] | None = None,
    tailoring_metadata: Mapping[str, Any] | None = None,
    associated_evidence_projects: list[Mapping[str, Any]] | None = None,
    known_projects: list[Mapping[str, Any]] | None = None,
) -> Dict[str, Any]:
    """Return the authoritative PASS/BLOCKED state for staged candidate copy.

    This is deliberately deterministic and runs after each artifact has been
    normalized, but before the package is organized or promoted.
    """
    tailoring_metadata = tailoring_metadata or {}
    associated = list(associated_evidence_projects or [])
    projects = list(known_projects or associated)
    texts = {key: _candidate_text(value) for key, value in artifacts.items() if value}
    reasons: list[str] = []
    cover_text = texts.get("cover_letter", "")
    reasons.extend(_duplicate_proof_reasons(cover_text, associated or projects))

    artifact_usage = tailoring_metadata.get("artifact_usage") or {}
    provenance_context = {
        "career_data": {"data": {"projects": {"projects": projects}}},
        "associated_evidence_projects": associated,
        "evidence_scope_enforced": bool(associated),
    }
    for artifact_type, text in texts.items():
        if not text:
            continue
        reasons.extend(
            _readiness_reasons(artifact_type, text, parsed_job or {}, tailoring_metadata)
        )
        selection_key = artifact_type
        if selection_key in artifact_usage:
            selection = dict(artifact_usage[selection_key] or {})
            if not selection.get("used_projects"):
                selected_by_id = {
                    str(project.get("id") or project.get("title") or ""): project
                    for project in projects
                }
                selection["used_projects"] = [
                    dict(
                        selected_by_id.get(
                            str(entry.get("id") or entry.get("title") or ""), entry
                        )
                    )
                    for entry in selection.get("used") or []
                ]
            provenance_context[
                {
                    "ats_resume": "resume_evidence_selection",
                    "styled_resume": "resume_evidence_selection",
                    "cover_letter": "cover_letter_evidence_selection",
                }.get(selection_key, selection_key)
            ] = selection
        violations = candidate_project_reference_violations(
            text, provenance_context, artifact_type
        )
        reasons.extend(
            f"{artifact_type.replace('_', ' ').title()} references unselected Evidence/project: {value}."
            for value in violations
        )
        try:
            validate_candidate_language(text, context=f"Generated {artifact_type}")
            validate_public_career_claims(text)
            validate_candidate_output(text, context=f"Generated {artifact_type}")
        except Exception as error:
            reasons.append(str(error))
        if "\u2014" in text:
            reasons.append(f"{artifact_type.replace('_', ' ').title()} contains an em dash.")
        lower = text.lower()
        reasons.extend(
            f"{artifact_type.replace('_', ' ').title()} contains prohibited filler: {phrase}."
            for phrase in _KNOWN_GENERIC_FILLER
            if phrase in lower
        )
        if parsed_job:
            try:
                validate_material_context(text, dict(parsed_job), artifact_type)
            except PackageContextMismatchError as error:
                reasons.append(
                    f"{artifact_type.replace('_', ' ').title()} contains stale role context: "
                    + ", ".join(error.violations)
                    + "."
                )
    combined = "\n\n".join(texts.values())
    reasons.extend(_override_conflict_reasons(combined, tailoring_metadata))
    return {
        "status": "BLOCKED" if reasons else "PASS",
        "blocking_reasons": list(dict.fromkeys(reasons)),
        "artifacts_checked": list(texts),
        "checks": {
            "duplicate_proof": not any("repeats the" in reason for reason in reasons),
            "evidence_provenance": not any("unselected Evidence/project" in reason for reason in reasons),
            "role_intelligence": not any("stale inferred" in reason for reason in reasons),
            "candidate_language": not any(
                "em dash" in reason or "candidate-language" in reason.lower() or "internal orchestration" in reason.lower()
                for reason in reasons
            ),
            "placeholders": not any("placeholder" in reason.lower() for reason in reasons),
            "employer_specificity": not any("known employer" in reason.lower() for reason in reasons),
            "role_family_consistency": not any("stale martech" in reason.lower() for reason in reasons),
            "supported_experience": not any("unsupported direct experiential" in reason.lower() for reason in reasons),
            "candidate_identity": not any("supported operations identity" in reason.lower() for reason in reasons),
            "cover_letter_repetition": not any("repetitive generic" in reason.lower() for reason in reasons),
        },
    }


# Short alias for callers that prefer the gate terminology.
candidate_facing_quality_gate = evaluate_candidate_facing_quality


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
    role_intelligence = evidence_metadata.get("role_intelligence") or {}
    overrides = role_intelligence.get("overrides") or {}
    effective = role_intelligence.get("effective") or {}
    inferred = role_intelligence.get("inferred") or {}
    intelligence_lines = [
        f"- Company voice: {effective.get('company_voice') or inferred.get('company_voice_label') or inferred.get('profile_name') or 'Inferred'}",
        f"- Category: {effective.get('category') or inferred.get('company_category_label') or inferred.get('company_category') or 'Inferred'}",
        f"- Role family: {effective.get('role_family') or inferred.get('role_family_label') or inferred.get('role_family') or 'Inferred'}",
        f"- Resolution: {'Explicit override applied; inferred source retained.' if overrides else 'Inferred from the posting.'}",
    ]
    intelligence_section = "\n".join(intelligence_lines)
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
    candidate_qa = dict(quality.get("candidate_facing_qa") or {})
    qa_status = str(candidate_qa.get("status") or "Not evaluated")
    qa_lines = [f"Candidate-facing QA: {qa_status}"]
    qa_lines.extend(
        f"- {reason}" for reason in candidate_qa.get("blocking_reasons") or []
    )
    qa_section = "\n".join(qa_lines)
    interview_gate = dict(quality.get("interview_conversion_gate") or {})
    gate_lines = [
        f"- Submission Status: {interview_gate.get('submission_status') or 'Not evaluated'}"
    ]
    for label, value in (interview_gate.get("diagnostics") or {}).items():
        gate_lines.append(f"- {label}: {value}")
    conversion_section = "\n".join(gate_lines)
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

## Role Intelligence

{intelligence_section}

## Candidate-Facing Quality Report

{qa_section}

{quality_report}

## Interview Conversion Gate

{conversion_section}
"""
    path.write_text(normalize_candidate_text(content), encoding="utf-8")
    return {"output_path": str(path)}
