"""Truthful requirement coverage and the final human submission gate."""

from __future__ import annotations

import re
import math
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "in", "is", "it", "of", "on", "or", "our", "that", "the", "their",
    "this", "to", "with", "you", "your", "will",
}
GENERIC_PHRASES = (
    "drove impactful results",
    "leveraged synergies",
    "strategic leader",
    "results-driven professional",
    "proven track record",
    "successfully managed",
    "spearheaded initiatives",
    "collaborated with stakeholders",
    "optimized processes",
    "transformed operations",
    "dynamic leader",
)
CLICHES = GENERIC_PHRASES + (
    "perfect fit",
    "uniquely qualified",
    "thrilled to apply",
    "passionate about",
    "best-in-class",
    "world-class",
)
UNSUPPORTED_CONCEPTS = {
    "salesforce administration": ("salesforce administrator", "administer salesforce", "salesforce administration"),
    "quota ownership": ("quota ownership", "owned quotas", "sales quotas"),
    "territory design": ("territory design", "territory planning", "sales territories"),
    "compensation plans": ("compensation plans", "sales compensation"),
    "sales forecasting": ("sales forecast", "commercial forecasting", "revenue forecast"),
    "sql expertise": ("sql",),
    "p&l ownership": ("p&l", "profit and loss ownership"),
    "revenue operations ownership": ("revenue operations", "revops"),
    "label account ownership": ("owned label accounts", "label account management"),
    "artist management": ("managed artists", "artist management"),
    "label or artist negotiation": ("label deals", "artist deals", "negotiated label", "negotiated artist"),
}
SEMANTIC_CONCEPTS = {
    "marketing operations": {"marketing operations", "campaign operations", "operating workflows"},
    "marketing technology": {"marketing technology", "martech", "adtech", "advertising technology"},
    "program management": {"program management", "pmo", "delivery governance", "project management"},
    "transformation": {"transformation", "change management", "organizational change", "operationalize"},
    "workflow automation": {"workflow automation", "ai workflows", "human-in-the-loop", "structured workflows"},
    "measurement": {"measurement", "analytics", "tracking", "reporting"},
    "media operations": {"media operations", "campaign execution", "ad operations", "trafficking"},
    "creative operations": {"creative operations", "content operations", "production workflows", "post-production"},
    "executive communication": {"executive communication", "executive reporting", "senior leaders", "stakeholder"},
    "operational excellence": {"operational excellence", "process improvement", "quality assurance", "governance"},
    "product operations": {"product operations", "requirements", "acceptance criteria", "product iteration"},
    "experiential production": {"experiential", "live event production", "event production", "production readiness"},
    "partner coordination": {"partner management", "partner coordination", "stakeholder coordination", "partner strategies"},
}
KEYWORD_OVERUSE_EXCLUSIONS = {
    "business", "company", "cross-functional", "execution", "lead", "leader",
    "leadership", "management", "manager", "operations", "program", "role",
    "senior", "strategy", "team", "teams", "work",
}


def _flatten(value: Any) -> list[str]:
    if isinstance(value, Mapping):
        return [item for nested in value.values() for item in _flatten(nested)]
    if isinstance(value, (list, tuple, set)):
        return [item for nested in value for item in _flatten(nested)]
    return [str(value)] if value not in (None, "") else []


def _normalized(value: Any) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9+#&/-]+", " ", " ".join(_flatten(value)).lower())).strip()


def _tokens(value: Any) -> set[str]:
    return {
        token for token in re.findall(r"[a-z0-9]+(?:[+#-][a-z0-9]+)?", _normalized(value))
        if len(token) > 2 and token not in STOP_WORDS
    }


def _coalesce_fragments(values: Sequence[str]) -> list[str]:
    """Rejoin parser fragments that split one wrapped requirement."""
    combined: list[str] = []
    pending = ""
    for value in values:
        value = re.sub(r"\s+", " ", str(value or "")).strip(" -•\t")
        if not value:
            continue
        if pending and not (
            pending.endswith((",", ";")) or (value[:1].islower() and not re.search(r"[.!?]$", pending))
        ):
            combined.append(pending)
            pending = ""
        pending = f"{pending} {value}".strip()
        if re.search(r"[.!?]$", pending):
            combined.append(pending)
            pending = ""
    if pending:
        combined.append(pending)
    return combined


def _split_requirement(value: str) -> list[str]:
    """Split list-like qualifications while retaining honest context."""
    value = re.sub(r"\s+", " ", value).strip()
    if not value:
        return []
    sentences = [sentence for sentence in re.split(r"(?<=[.!?])\s+", value) if sentence.strip()]
    if len(sentences) > 1:
        return [piece for sentence in sentences for piece in _split_requirement(sentence)]
    pieces = [
        re.sub(r"^and\s+", "", piece.strip(" ,;."), flags=re.IGNORECASE)
        for piece in re.split(r",|;", value)
        if piece.strip(" ,;.")
    ]
    if len(pieces) <= 1:
        return [value]
    prefix = "experience in " if value.lower().startswith("experience in ") else ""
    sales_context = bool(re.search(r"\b(sales|revenue|territor|pipeline|gtm)\b", value.lower()))
    normalized: list[str] = []
    for index, piece in enumerate(pieces):
        if index == 0 or not prefix or piece.lower().startswith(("experience ", "strong ", "excellent ")):
            normalized.append(piece)
        elif sales_context and piece.lower().startswith("forecast"):
            normalized.append("sales " + piece)
        elif sales_context and piece.lower().startswith("pipeline"):
            normalized.append("sales " + piece)
        else:
            normalized.append(prefix + piece)
    return normalized


def _raw_section_sentences(parsed_job: Mapping[str, Any], heading: str) -> list[str]:
    raw = str(parsed_job.get("raw_text") or "")
    match = re.search(
        rf"(?ims)^##\s+{re.escape(heading)}\s*$\s*(.*?)(?=^##\s+|\Z)", raw
    )
    if not match:
        return []
    text = re.sub(r"\n(?!\s*[-*•])", " ", match.group(1))
    return [
        re.sub(r"\s+", " ", sentence).strip(" -•\t")
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", text)
        if len(_normalized(sentence)) >= 12
    ]


def _requirements(parsed_job: Mapping[str, Any]) -> list[dict[str, Any]]:
    requirements: list[dict[str, Any]] = []
    seen: set[str] = set()
    fields = (
        ("qualifications", "qualification", "required"),
        ("required_qualifications", "qualification", "required"),
        ("preferred_qualifications", "qualification", "preferred"),
        ("responsibilities", "responsibility", "high"),
        ("required_skills", "skill", "required"),
    )
    for field, category, importance in fields:
        raw_values = _flatten(parsed_job.get(field))
        values = _coalesce_fragments(raw_values) if "qualification" in category else raw_values
        for combined in values:
            candidates = _split_requirement(combined) if "qualification" in category else [combined]
            for original in candidates:
                original = re.sub(r"\s+", " ", original).strip(" -•\t")
                normalized = _normalized(original)
                if len(normalized) < 3 or normalized in seen:
                    continue
                seen.add(normalized)
                requirements.append(
                    {
                        "normalized_requirement": normalized,
                        "original_jd_wording": original,
                        "requirement_category": category,
                        "importance": importance,
                    }
                )
    for original in _raw_section_sentences(parsed_job, "Job Description"):
        normalized = _normalized(original)
        if normalized in seen:
            continue
        seen.add(normalized)
        requirements.append(
            {
                "normalized_requirement": normalized,
                "original_jd_wording": original,
                "requirement_category": "responsibility",
                "importance": "high",
            }
        )
    if not requirements:
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", str(parsed_job.get("raw_text") or "")):
            normalized = _normalized(sentence)
            if 12 <= len(normalized) <= 320 and normalized not in seen:
                seen.add(normalized)
                requirements.append(
                    {
                        "normalized_requirement": normalized,
                        "original_jd_wording": sentence.strip(),
                        "requirement_category": "posting requirement",
                        "importance": "medium",
                    }
                )
    return requirements[:40]


def _sections(resume_text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in str(resume_text or "").splitlines():
        heading = re.match(r"^#{2,3}\s+(.+)$", line.strip())
        if heading:
            current = heading.group(1).strip()
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


def _matching_concepts(requirement: str, record_text: str) -> list[str]:
    matches: list[str] = []
    for concept, variants in SEMANTIC_CONCEPTS.items():
        if any(variant in requirement for variant in variants) and any(
            variant in record_text for variant in variants
        ):
            matches.append(concept)
    return matches


def _direct_concepts(requirement: str, record_text: str) -> list[str]:
    return [
        concept
        for concept, variants in SEMANTIC_CONCEPTS.items()
        if any(variant in requirement and variant in record_text for variant in variants)
    ]


def _restricted_concept(requirement: str) -> str:
    direct = next(
        (
            label
            for label, variants in UNSUPPORTED_CONCEPTS.items()
            if any(variant in requirement for variant in variants)
        ),
        "",
    )
    if direct:
        return direct
    sales_context = any(term in requirement for term in ("sales", "revenue", "gtm", "territory", "pipeline"))
    if sales_context and "forecast" in requirement:
        return "sales forecasting"
    if sales_context and "pipeline" in requirement:
        return "sales pipeline ownership"
    if "label relations" in requirement or "record label" in requirement:
        return "direct label-relations ownership"
    return ""


def build_requirement_coverage_matrix(
    parsed_job: Mapping[str, Any],
    golden_resume: Mapping[str, Any],
    selected_evidence: Sequence[Mapping[str, Any]],
    resume_text: str,
) -> list[dict[str, Any]]:
    """Classify each meaningful role requirement against canonical evidence."""
    records = [
        *list(golden_resume.get("employment") or []),
        *list(golden_resume.get("achievements") or []),
        *list(golden_resume.get("projects") or []),
        *list(golden_resume.get("skill_groups") or []),
        *list(golden_resume.get("platform_categories") or []),
        *list(golden_resume.get("certifications") or []),
        *[dict(item, record_type="selected_evidence") for item in selected_evidence],
    ]
    section_map = _sections(resume_text)
    matrix: list[dict[str, Any]] = []
    for requirement in _requirements(parsed_job):
        normalized = requirement["normalized_requirement"]
        requirement_tokens = _tokens(normalized)
        restricted = _restricted_concept(normalized)
        matches: list[tuple[int, str, Mapping[str, Any], list[str], list[str]]] = []
        for record in records:
            text = _normalized(record)
            common = requirement_tokens & _tokens(text)
            concepts = _matching_concepts(normalized, text)
            direct_concepts = _direct_concepts(normalized, text)
            score = len(common) + (3 * len(concepts))
            if score:
                matches.append((score, str(record.get("canonical_id") or record.get("id") or ""), record, concepts, direct_concepts))
        matches.sort(key=lambda value: (-value[0], value[1]))
        strongest = matches[:3]
        exact = bool(strongest and strongest[0][4])
        semantic = bool(strongest and strongest[0][3])
        if restricted:
            coverage = "NOT_SUPPORTED"
            explanation = f"Canonical evidence does not establish {restricted}; Career Catalyst must not insert this claim."
            strongest = []
        elif exact:
            coverage = "PROVEN"
            explanation = "Canonical career evidence directly supports the requirement."
        elif semantic:
            coverage = "TRANSFERABLE"
            explanation = "Canonical evidence supports a semantically equivalent or adjacent operating concept."
        elif strongest:
            coverage = "WEAK"
            explanation = "Some related evidence exists, but it does not establish the full requirement."
        else:
            coverage = "NOT_SUPPORTED"
            explanation = "No canonical evidence establishes this requirement."

        if restricted:
            restricted_variants = UNSUPPORTED_CONCEPTS.get(restricted, ())
            resume_locations = [
                name for name, content in section_map.items()
                if any(variant in _normalized(content) for variant in restricted_variants)
            ]
        else:
            resume_locations = [
                name for name, content in section_map.items()
                if normalized in _normalized(content)
                or (
                    requirement_tokens
                    and len(requirement_tokens & _tokens(content)) / len(requirement_tokens) >= 0.6
                )
            ]
        confidence = {
            "PROVEN": "high",
            "TRANSFERABLE": "medium",
            "WEAK": "low",
            "NOT_SUPPORTED": "high",
        }[coverage]
        matrix.append(
            {
                **requirement,
                "coverage": coverage,
                "evidence_ids": [identifier for _score, identifier, _record, _concepts, _direct in strongest if identifier],
                "evidence_source": sorted(
                    {
                        str(record.get("source_path") or record.get("source") or "canonical career data")
                        for _score, _identifier, record, _concepts, _direct in strongest
                    }
                ),
                "explanation": explanation,
                "resume_location": resume_locations[:3],
                "confidence": confidence,
            }
        )
    return matrix


def evaluate_evidence_density(resume_text: str, golden_resume: Mapping[str, Any]) -> dict[str, Any]:
    """Flag abstraction that replaces evidence; never invent specificity."""
    bullets = [
        re.sub(r"^\s*[-*+]\s+", "", line).strip()
        for line in str(resume_text or "").splitlines()
        if re.match(r"^\s*[-*+]\s+\S", line)
    ]
    corpus = _tokens(golden_resume.get("claim_corpus") or "")
    issues: list[dict[str, Any]] = []
    for bullet in bullets:
        lower = bullet.lower()
        abstractions = [phrase for phrase in GENERIC_PHRASES if phrase in lower]
        concrete = bool(
            re.search(
                r"\b\d+(?:[,.]\d+)?%?\b|\b[A-Z][A-Za-z0-9+.-]{2,}(?:\s+[A-Z][A-Za-z0-9+.-]{2,})+\b",
                bullet,
            )
            or len(_tokens(bullet) & corpus) >= 5
        )
        if abstractions and not concrete:
            issues.append(
                {"bullet": bullet, "reason": "Generic abstraction lacks nearby canonical evidence.", "phrases": abstractions}
            )
    density = round((len(bullets) - len(issues)) / max(1, len(bullets)) * 100)
    return {
        "status": "PASS" if not issues else "REVIEW",
        "substantive_bullets": len(bullets),
        "evidence_dense_bullets": len(bullets) - len(issues),
        "evidence_density_percent": density,
        "issues": issues,
    }


def evaluate_claim_provenance(
    resume_text: str, golden_resume: Mapping[str, Any]
) -> dict[str, Any]:
    """Resolve substantive résumé claims to one or more canonical records."""
    records = [
        record
        for record in golden_resume.get("records") or []
        if record.get("record_type")
        in {
            "employment",
            "achievement",
            "project",
            "evidence_project",
            "skill_group",
            "platform_category",
            "certification",
            "personal_brand",
        }
    ]
    sections = _sections(resume_text)
    claims: list[dict[str, Any]] = []
    profile = sections.get("Profile", "")
    claims.extend(
        {"section": "Profile", "text": sentence.strip()}
        for sentence in re.split(r"(?<=[.!?])\s+", profile)
        if len(_tokens(sentence)) >= 5
    )
    for section, content in sections.items():
        if section == "Profile":
            continue
        claims.extend(
            {"section": section, "text": re.sub(r"^\s*[-*+]\s+", "", line).strip()}
            for line in content.splitlines()
            if re.match(r"^\s*[-*+]\s+\S", line)
        )

    unsupported: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    for claim in claims:
        claim_tokens = _tokens(claim["text"])
        minimum = max(2, math.ceil(len(claim_tokens) * 0.18))
        matches: list[tuple[int, str, str]] = []
        normalized_claim = _normalized(claim["text"])
        for record in records:
            record_text = _normalized(record)
            common = claim_tokens & _tokens(record_text)
            direct = _direct_concepts(normalized_claim, record_text)
            score = len(common) + (3 * len(direct))
            exact_phrase = bool(normalized_claim and normalized_claim in record_text)
            if exact_phrase or len(common) >= minimum or direct:
                matches.append(
                    (
                        score,
                        str(record.get("canonical_id") or ""),
                        str(record.get("source_path") or "canonical career data"),
                    )
                )
        matches.sort(key=lambda value: (-value[0], value[1]))
        entry = {
            **claim,
            "evidence_ids": [identifier for _score, identifier, _source in matches[:3]],
            "evidence_sources": sorted({source for _score, _identifier, source in matches[:3]}),
        }
        if matches:
            resolved.append(entry)
        else:
            unsupported.append(entry)
    return {
        "status": "PASS" if not unsupported else "BLOCKED",
        "substantive_claim_count": len(claims),
        "resolved_claim_count": len(resolved),
        "unresolved_claims": unsupported,
        "claims": [*resolved, *unsupported],
    }


def evaluate_voice_drift(texts: Mapping[str, str]) -> dict[str, Any]:
    """Check consistency with a direct, pragmatic candidate voice."""
    findings: list[dict[str, Any]] = []
    for artifact, text in texts.items():
        lower = str(text or "").lower()
        clichés = [phrase for phrase in CLICHES if phrase in lower]
        first_words = [
            match.group(0).lower()
            for sentence in re.split(r"(?<=[.!?])\s+", str(text or ""))
            if (match := re.search(r"[A-Za-z0-9]+", sentence))
        ]
        repetition = max(Counter(first_words).values(), default=0) >= 5
        adjective_stacks = re.findall(r"\b(?:strategic|dynamic|innovative|exceptional|transformational)(?:\s+(?:strategic|dynamic|innovative|exceptional|transformational)){1,}\b", lower)
        if clichés or repetition or adjective_stacks:
            findings.append(
                {
                    "artifact": artifact,
                    "cliches": clichés,
                    "repetitive_sentence_openings": repetition,
                    "adjective_stacks": adjective_stacks,
                }
            )
    return {"status": "PASS" if not findings else "REVIEW", "findings": findings}


def evaluate_keyword_overuse(
    resume_text: str, coverage: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Flag conspicuous JD repetition without pretending to model an ATS."""
    normalized_resume = _normalized(resume_text)
    resume_tokens = re.findall(r"[a-z0-9]+(?:[+#-][a-z0-9]+)?", normalized_resume)
    counts = Counter(resume_tokens)
    repeated_phrases: list[dict[str, Any]] = []
    repeated_terms: list[dict[str, Any]] = []
    seen_phrases: set[str] = set()
    jd_tokens: set[str] = set()
    for row in coverage:
        requirement = _normalized(row.get("normalized_requirement") or row.get("original_jd_wording"))
        meaningful = [
            token for token in _tokens(requirement)
            if len(token) >= 4 and token not in KEYWORD_OVERUSE_EXCLUSIONS
        ]
        jd_tokens.update(meaningful)
        if len(meaningful) >= 4 and requirement not in seen_phrases:
            seen_phrases.add(requirement)
            occurrences = normalized_resume.count(requirement)
            if occurrences >= 3:
                repeated_phrases.append({"phrase": requirement, "occurrences": occurrences})
    total = max(1, len(resume_tokens))
    for token in sorted(jd_tokens):
        occurrences = counts[token]
        density = occurrences / total
        if occurrences >= 10 and density >= 0.025:
            repeated_terms.append(
                {"term": token, "occurrences": occurrences, "density_percent": round(density * 100, 1)}
            )
    findings = [*repeated_phrases, *repeated_terms]
    return {
        "status": "PASS" if not findings else "REVIEW",
        "parseability_only": False,
        "findings": findings,
    }


def evaluate_human_credibility(resume_text: str, coverage: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Assess whether a recruiter can quickly understand the candidacy."""
    upper = "\n".join(str(resume_text or "").splitlines()[:35]).lower()
    full = str(resume_text or "").lower()
    checks = {
        "professional_identity_visible": "profile" in upper,
        "seniority_visible": any(term in upper for term in ("senior", "director", "leader", "lead")),
        "career_progression_visible": "group director" in full and "campaign manager" in full,
        "strong_qualifications_high": any(term in upper for term in ("operations", "transformation", "marketing", "media", "product")),
        "projects_are_additive": full.count("career catalyst") <= 2 and full.count("campaignos") <= 2,
        "unsupported_claims_avoided": not any(
            row.get("coverage") == "NOT_SUPPORTED" and row.get("resume_location")
            for row in coverage
        ),
    }
    return {
        "status": "PASS" if all(checks.values()) else "REVIEW",
        "checks": checks,
        "review_items": [name.replace("_", " ") for name, passed in checks.items() if not passed],
    }


def _coverage_counts(matrix: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = Counter(str(row.get("coverage") or "") for row in matrix)
    return {key: counts.get(key, 0) for key in ("PROVEN", "TRANSFERABLE", "WEAK", "NOT_SUPPORTED")}


def build_interview_conversion_gate(
    *,
    parsed_job: Mapping[str, Any],
    match_report: Mapping[str, Any],
    coverage_matrix: Sequence[Mapping[str, Any]],
    candidate_qa: Mapping[str, Any],
    voice: Mapping[str, Any],
    specificity: Mapping[str, Any],
    credibility: Mapping[str, Any],
    ats_round_trip: Mapping[str, Any],
    docx_hygiene: Mapping[str, Mapping[str, Any]],
    factual_parity: Mapping[str, Any],
    keyword_overuse: Mapping[str, Any] | None = None,
    claim_provenance: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a human-readable readiness verdict without fake ATS precision."""
    blocking: list[str] = []
    if candidate_qa.get("status") == "BLOCKED":
        blocking.extend(str(value) for value in candidate_qa.get("blocking_reasons") or [])
    for label, report in (("ATS parse", ats_round_trip), ("Styled/ATS parity", factual_parity)):
        if report.get("status") != "PASS":
            blocking.append(f"{label} failed.")
    for label, report in docx_hygiene.items():
        if report.get("status") != "PASS":
            blocking.append(f"{label} DOCX hygiene failed.")
    provenance_report = dict(claim_provenance or {"status": "PASS"})
    if provenance_report.get("status") != "PASS":
        blocking.append(
            f"{len(provenance_report.get('unresolved_claims') or [])} substantive résumé claim(s) lack canonical provenance."
        )
    counts = _coverage_counts(coverage_matrix)
    unsupported = [row for row in coverage_matrix if row.get("coverage") == "NOT_SUPPORTED"]
    weak = [row for row in coverage_matrix if row.get("coverage") == "WEAK"]
    review_items = [
        *[f"Unsupported requirement: {row.get('original_jd_wording')}" for row in unsupported[:6]],
        *[f"Weakly supported requirement: {row.get('original_jd_wording')}" for row in weak[:4]],
        *[str(item) for item in credibility.get("review_items") or []],
    ]
    status = "READY TO SUBMIT" if not blocking and not review_items and voice.get("status") == "PASS" and specificity.get("status") == "PASS" else "NEEDS REVIEW"
    strengths = [row for row in coverage_matrix if row.get("coverage") in {"PROVEN", "TRANSFERABLE"}]
    interview_reasons = [
        f"{row.get('normalized_requirement').capitalize()}: {row.get('explanation')}"
        for row in strengths[:3]
    ]
    role_text = _normalized(parsed_job)
    title_text = _normalized(parsed_job.get("job_title") or parsed_job.get("title"))
    builder_relevant = any(
        term in title_text
        for term in ("artificial intelligence", "ai ", "product", "automation", "transformation")
    ) or any(term in role_text for term in ("artificial intelligence", "human in the loop", "ai workflow"))
    contextual_third = (
        "Current builder work adds practical product and AI-workflow judgment where relevant."
        if builder_relevant
        else "Current media-production work adds practical creative and content-operations judgment."
        if any(term in role_text for term in ("music", "media", "content", "entertainment", "production"))
        else "Senior enterprise experience adds practical judgment across complex operating environments."
    )
    fallbacks = (
        "Senior progression from hands-on execution through Group Director leadership.",
        "Grounded evidence connects operating-system design with dependable cross-functional delivery.",
        contextual_third,
    )
    while len(interview_reasons) < 3:
        interview_reasons.append(fallbacks[len(interview_reasons)])
    keyword_report = dict(keyword_overuse or {"status": "PASS", "findings": []})
    if keyword_report.get("status") != "PASS":
        review_items.append("Job-description terminology is repeated conspicuously.")
    diagnostics = {
        "ROLE FIT": f"Canonical match score {match_report.get('match_score', 'Not scored')}; no proprietary ATS score inferred.",
        "ATS PARSE": ats_round_trip.get("status"),
        "REQUIREMENT COVERAGE": counts,
        "EVIDENCE GROUNDING": (
            "PASS"
            if candidate_qa.get("status") == "PASS" and provenance_report.get("status") == "PASS"
            else "BLOCKED"
        ),
        "CAREER CREDIBILITY": credibility.get("status"),
        "VOICE CONSISTENCY": voice.get("status"),
        "SPECIFICITY": specificity.get("status"),
        "GENERIC LANGUAGE": "PASS" if not specificity.get("issues") else "REVIEW",
        "KEYWORD OVERUSE": keyword_report.get("status"),
        "UNSUPPORTED CLAIMS": "PASS" if not blocking else "BLOCKED",
        "DOCX HYGIENE": "PASS" if all(report.get("status") == "PASS" for report in docx_hygiene.values()) else "BLOCKED",
        "HUMAN REVIEW ITEMS": review_items,
    }
    return {
        "submission_status": status,
        "blocking_reasons": blocking,
        "diagnostics": diagnostics,
        "why_this_candidate_merits_an_interview": interview_reasons[:3],
        "potential_elimination_risks": [row.get("original_jd_wording") for row in [*unsupported, *weak][:8]],
        "what_career_catalyst_changed": [
            "Aligned supported career language to the role's operating concepts.",
            "Selected role-relevant canonical Evidence without changing career facts.",
            "Exported and verified factually consistent Styled and ATS documents.",
        ],
        "what_career_catalyst_deliberately_did_not_claim": [
            row.get("original_jd_wording") for row in unsupported[:10]
        ],
        "requirement_coverage": counts,
    }


def render_requirement_matrix(matrix: Sequence[Mapping[str, Any]]) -> str:
    lines = ["# Requirement Coverage Matrix", ""]
    for row in matrix:
        lines.extend(
            [
                f"## {row.get('coverage')}: {row.get('original_jd_wording')}",
                f"- Category: {row.get('requirement_category')}",
                f"- Importance: {row.get('importance')}",
                f"- Evidence IDs: {', '.join(row.get('evidence_ids') or []) or 'None'}",
                f"- Evidence source: {', '.join(row.get('evidence_source') or []) or 'None'}",
                f"- Explanation: {row.get('explanation')}",
                f"- Resume location: {', '.join(row.get('resume_location') or []) or 'Not represented'}",
                f"- Confidence: {row.get('confidence')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_interview_conversion_gate(gate: Mapping[str, Any]) -> str:
    lines = ["# Interview Conversion Gate", "", "## SUBMISSION STATUS", "", str(gate.get("submission_status")), ""]
    for label, value in (gate.get("diagnostics") or {}).items():
        lines.append(f"- {label}: {value}")
    sections = (
        ("Why this candidate merits an interview", "why_this_candidate_merits_an_interview"),
        ("Potential elimination risks", "potential_elimination_risks"),
        ("What Career Catalyst changed", "what_career_catalyst_changed"),
        ("What Career Catalyst deliberately did not claim", "what_career_catalyst_deliberately_did_not_claim"),
    )
    for heading, key in sections:
        lines.extend(["", f"## {heading}", ""])
        values = list(gate.get(key) or [])
        lines.extend(f"- {value}" for value in values)
        if not values:
            lines.append("- None identified.")
    return "\n".join(lines).rstrip() + "\n"


def save_readiness_artifacts(
    root: Path,
    *,
    ats_preview: str,
    coverage_matrix: Sequence[Mapping[str, Any]],
    gate: Mapping[str, Any],
) -> dict[str, str]:
    directory = root / "exports" / "strategy_packs"
    directory.mkdir(parents=True, exist_ok=True)
    preview_path = directory / "ats_parsed_preview.txt"
    coverage_path = directory / "requirement_coverage_matrix.txt"
    gate_path = directory / "interview_conversion_gate.txt"
    preview_path.write_text("# ATS Parsed Preview\n\n" + ats_preview.strip() + "\n", encoding="utf-8")
    coverage_path.write_text(render_requirement_matrix(coverage_matrix), encoding="utf-8")
    gate_path.write_text(render_interview_conversion_gate(gate), encoding="utf-8")
    return {
        "ats_parsed_preview": str(preview_path),
        "requirement_coverage_matrix": str(coverage_path),
        "interview_conversion_gate": str(gate_path),
    }
