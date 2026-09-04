"""Keep internal evaluation language out of recruiter-facing materials."""

from __future__ import annotations

import re
from typing import Any


INTERNAL_POSITIONING_PATTERNS: dict[str, tuple[str, ...]] = {
    "alignment_language": (
        r"\badjacent\b", r"\btransferable\b",
        r"\balignment level\b",
    ),
    "scoring_language": (
        r"\bstrong fit\b", r"\bgood match\b", r"\bstretch match\b",
        r"\bmatch score\b", r"\bscoring\b",
    ),
    "confidence_language": (
        r"\bconfidence\b",
    ),
    "unsupported_language": (
        r"\bunsupported experience\b", r"\bunsupported claim", r"\bnot demonstrated\b",
    ),
    "curiosity_close": (
        r"\bi (?:would|'d) welcome the (?:chance|opportunity) to learn\b",
        r"\bi (?:would|'d) like to learn\b",
        r"\bi (?:am|'m) curious\b",
    ),
    "limitation_language": (
        r"\bi am not\b", r"\bmy experience is not\b", r"\bi have not\b",
        r"\bi haven't\b", r"\bi do not know\b", r"\bi don't know\b",
        r"\bthis is not\b", r"\bwould not claim\b", r"\bdo not claim\b",
        r"\bnot software engineering\b", r"\bnot (?:a )?traditional hr\b",
        r"\brather than (?:a )?traditional hr\b", r"\bwithout implying\b",
        r"\bnot as proof\b", r"\bthe evidence i (?:would )?bring is more\b",
        r"\bthe industry context was specific\b",
    ),
}


def positioning_review(
    text: str,
    *,
    transparency_requested: bool = False,
) -> dict[str, Any]:
    """Flag internal reasoning and unnecessary limitation language in public copy."""
    value = str(text or "")
    issues = []
    for code, patterns in INTERNAL_POSITIONING_PATTERNS.items():
        if code == "limitation_language" and transparency_requested:
            continue
        matches = [
            match.group(0)
            for pattern in patterns
            for match in re.finditer(pattern, value, flags=re.I)
        ]
        if matches:
            issues.append({"code": code, "matches": matches})
    limitation_paragraphs = [
        paragraph for paragraph in re.split(r"\n\s*\n", value)
        if any(
            re.search(pattern, paragraph, flags=re.I)
            for pattern in INTERNAL_POSITIONING_PATTERNS["limitation_language"]
        )
    ]
    if len(limitation_paragraphs) > 1:
        issues.append({
            "code": "multiple_limitation_paragraphs",
            "matches": [str(len(limitation_paragraphs))],
        })
    return {
        "valid": not issues,
        "issues": issues,
        "audience": "Recruiters and hiring managers",
        "mode": "Public Advocacy",
    }


def _sentence_is_internal(
    sentence: str,
    *,
    transparency_requested: bool = False,
) -> bool:
    for code, patterns in INTERNAL_POSITIONING_PATTERNS.items():
        if code == "limitation_language" and transparency_requested:
            continue
        if any(re.search(pattern, sentence, flags=re.I) for pattern in patterns):
            return True
    return False


def rewrite_public_advocacy(
    text: str,
    *,
    company: str = "the organization",
    role: str = "the role",
    transparency_requested: bool = False,
) -> tuple[str, dict[str, Any]]:
    """Rewrite evaluation-like copy into confident, evidence-led public positioning."""
    original = str(text or "")
    value = original.replace("with confidence", "with clarity")
    value = re.sub(
        r"I would welcome the (?:chance|opportunity) to learn (?:more )?about",
        "I would welcome the chance to contribute to",
        value,
        flags=re.I,
    )
    paragraphs = []
    removed_sentences = []
    for paragraph in re.split(r"\n\s*\n", value):
        clean = paragraph.strip()
        if not clean:
            continue
        if clean in {"Hello,", "Best,", "Trisha Lynch"} or clean.startswith("Best,"):
            paragraphs.append(clean)
            continue
        sentences = re.split(r"(?<=[.!?])\s+", clean)
        kept = []
        for sentence in sentences:
            if re.match(
                r"^(?:(?:I am|I'm) curious|(?:I would|I'd) welcome the (?:chance|opportunity) to learn|(?:I would|I'd) like to learn)\b",
                sentence,
                flags=re.I,
            ):
                kept.append(
                    f"I would welcome the opportunity to contribute to {company} and discuss how "
                    "my experience can support the team's priorities."
                )
                continue
            if _sentence_is_internal(
                sentence,
                transparency_requested=transparency_requested,
            ):
                removed_sentences.append(sentence.strip())
                continue
            kept.append(sentence.strip())
        if kept:
            rebuilt = " ".join(kept)
            if re.match(
                r"^(?:(?:I am|I'm) curious|(?:I would|I'd) welcome the (?:chance|opportunity) to learn|(?:I would|I'd) like to learn)\b",
                rebuilt,
                flags=re.I,
            ):
                rebuilt = (
                    f"I would welcome the opportunity to contribute to {company} and discuss how "
                    "my experience can support the team's priorities."
                )
            paragraphs.append(rebuilt)
    rewritten = "\n\n".join(paragraphs)
    review = positioning_review(
        rewritten,
        transparency_requested=transparency_requested,
    )
    return rewritten, {
        **review,
        "rewritten": rewritten != original,
        "removed_sentences": removed_sentences,
        "truthfulness_rule": "Every retained substantive claim must remain grounded in selected evidence.",
    }


def validate_public_advocacy(
    text: str,
    artifact: str,
    *,
    transparency_requested: bool = False,
) -> dict[str, Any]:
    review = positioning_review(
        text,
        transparency_requested=transparency_requested,
    )
    if not review["valid"]:
        first = review["issues"][0]
        raise ValueError(
            f"Generated {artifact} contains internal positioning language: {first['code']}"
        )
    return review
