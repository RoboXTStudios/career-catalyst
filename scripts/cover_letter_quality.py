"""Deterministic final quality checks for assembled cover letters."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Iterable

try:
    from .employer_identity import normalize_applicant_employer_names
except ImportError:
    from employer_identity import normalize_applicant_employer_names


_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "for", "from",
    "has", "have", "i", "in", "into", "is", "it", "my", "of", "on", "or",
    "that", "the", "their", "this", "to", "was", "were", "with",
}
_TOKEN_ALIASES = {
    "advertising": "platform",
    "capabilities": "capability",
    "campaigns": "campaign",
    "executing": "execution",
    "operational": "operation",
    "operations": "operation",
    "translated": "translate",
    "translating": "translate",
    "workflows": "workflow",
}
_STYLE_LIMITS = {
    "grounded": (1, "evidence-based"),
    "alignment": (2, "coordination"),
    "practical": (2, "usable"),
    "clear": (3, "specific"),
}
_CONCEPT_MARKERS = {
    "google_youtube_activation": {
        "google", "youtube", "campaign", "activation", "measurement", "workflow"
    },
    "advertiser_cross_functional_alignment": {
        "brand", "media", "analytics", "technology", "stakeholder"
    },
    "workflow_governance": {
        "workflow", "governance", "standard", "handoff", "ownership"
    },
}


def _sentences(paragraph: str) -> list[str]:
    return [
        value.strip()
        for value in re.split(r"(?<=[.!?])\s+", paragraph.strip())
        if value.strip()
    ]


def _normalized_sentence(sentence: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", sentence.lower()))


def _tokens(value: str) -> set[str]:
    result = set()
    for token in re.findall(r"[a-z0-9]+", value.lower()):
        token = _TOKEN_ALIASES.get(token, token)
        if token not in _STOP_WORDS and len(token) > 2:
            result.add(token)
    return result


def semantic_similarity(left: str, right: str) -> float:
    """Return lightweight semantic similarity for two evidence claims."""
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return 0.0
    union = left_tokens | right_tokens
    jaccard = len(left_tokens & right_tokens) / len(union)
    sequence = SequenceMatcher(
        None, _normalized_sentence(left), _normalized_sentence(right)
    ).ratio()
    return max(jaccard, sequence if len(left_tokens & right_tokens) >= 5 else 0.0)


def _split_document(content: str) -> tuple[list[str], list[str], list[str]]:
    paragraphs = [
        value.strip()
        for value in re.split(r"\n\s*\n", str(content or "").strip())
        if value.strip()
    ]
    prefix: list[str] = []
    suffix: list[str] = []
    if paragraphs and re.fullmatch(r"(?:hello|dear[^,]*),?", paragraphs[0], re.I):
        prefix.append(paragraphs.pop(0))
    while paragraphs and (
        re.match(r"^(?:best|sincerely|warmly|thank you),?$", paragraphs[-1], re.I)
        or re.fullmatch(r"Trisha Lynch", paragraphs[-1], re.I)
    ):
        suffix.insert(0, paragraphs.pop())
    return prefix, paragraphs, suffix


def _concepts(value: str) -> set[str]:
    tokens = _tokens(value)
    return {
        concept
        for concept, markers in _CONCEPT_MARKERS.items()
        if len(tokens & markers) >= min(4, len(markers))
    }


def _remove_duplicate_sentences(
    paragraphs: list[str], diagnostics: dict[str, Any]
) -> list[str]:
    kept_sentences: list[str] = []
    cleaned: list[str] = []
    seen_concepts: set[str] = set()
    for paragraph_index, paragraph in enumerate(paragraphs):
        current: list[str] = []
        for sentence in _sentences(paragraph):
            normalized = _normalized_sentence(sentence)
            exact = next(
                (
                    prior
                    for prior in kept_sentences
                    if _normalized_sentence(prior) == normalized
                ),
                None,
            )
            if exact:
                diagnostics["duplicate_sentences_removed"].append(sentence)
                continue
            similar = next(
                (
                    (prior, semantic_similarity(prior, sentence))
                    for prior in kept_sentences
                    if len(_tokens(prior) & _tokens(sentence)) >= 5
                    and semantic_similarity(prior, sentence) >= 0.78
                ),
                None,
            )
            concepts = _concepts(sentence)
            repeated_concepts = concepts & seen_concepts
            if similar:
                diagnostics["semantic_duplicates_detected"].append(
                    {
                        "kept": similar[0],
                        "removed": sentence,
                        "similarity": round(similar[1], 3),
                    }
                )
                continue
            if repeated_concepts:
                diagnostics["repeated_concepts_detected"].append(
                    {
                        "paragraph": paragraph_index + 1,
                        "concepts": sorted(repeated_concepts),
                        "sentence": sentence,
                    }
                )
            current.append(sentence)
            kept_sentences.append(sentence)
            seen_concepts.update(concepts)
        if current:
            cleaned.append(" ".join(current))
    return cleaned


def _opening_key(paragraph: str) -> str:
    normalized = _normalized_sentence(paragraph)
    if normalized.startswith("at omg23") or normalized.startswith("during my time at omg23"):
        return "at_omg23"
    for phrase in ("i translated", "i would bring"):
        if normalized.startswith(phrase):
            return phrase.replace(" ", "_")
    return ""


def _resolve_repeated_sentence_openings(
    paragraphs: list[str], diagnostics: dict[str, Any]
) -> list[str]:
    result: list[str] = []
    for paragraph_index, paragraph in enumerate(paragraphs):
        sentences = _sentences(paragraph)
        for index in range(1, len(sentences)):
            previous = _normalized_sentence(sentences[index - 1])
            current = _normalized_sentence(sentences[index])
            phrase = next(
                (
                    value
                    for value in ("i translated", "i would bring")
                    if previous.startswith(value) and current.startswith(value)
                ),
                "",
            )
            if not phrase:
                continue
            diagnostics["repeated_sentence_openings"].append(
                {
                    "paragraph": paragraph_index + 1,
                    "sentence": index + 1,
                    "opening": phrase,
                }
            )
            if phrase == "i translated":
                sentences[index] = re.sub(
                    r"^I translated\b",
                    "The same approach translated",
                    sentences[index],
                    flags=re.I,
                )
            else:
                sentences[index] = re.sub(
                    r"^I would bring\b",
                    "That contribution would include",
                    sentences[index],
                    flags=re.I,
                )
        result.append(" ".join(sentences))
    return result


def _resolve_adjacent_openings(
    paragraphs: list[str], diagnostics: dict[str, Any]
) -> list[str]:
    result = list(paragraphs)
    for index in range(1, len(result)):
        previous_key = _opening_key(result[index - 1])
        current_key = _opening_key(result[index])
        if not previous_key or previous_key != current_key:
            continue
        diagnostics["repeated_paragraph_openings"].append(
            {"paragraphs": [index, index + 1], "opening": current_key}
        )
        if current_key == "at_omg23":
            result[index] = re.sub(
                r"^(?:At OMG23(?: / Omnicom Media Group)?|During my time at OMG23(?: / Omnicom Media Group)?),\s*",
                "",
                result[index],
                flags=re.I,
            )
        elif current_key == "i_translated":
            result[index] = re.sub(
                r"^I translated\b", "That work translated", result[index], flags=re.I
            )
        elif current_key == "i_would_bring":
            result[index] = re.sub(
                r"^I would bring\b", "That contribution would include", result[index], flags=re.I
            )
    return result


def _reduce_style_repetition(
    paragraphs: list[str], diagnostics: dict[str, Any]
) -> list[str]:
    result: list[str] = []
    for paragraph_index, paragraph in enumerate(paragraphs):
        revised = paragraph
        for word, (limit, replacement) in _STYLE_LIMITS.items():
            matches = list(re.finditer(rf"\b{re.escape(word)}\b", revised, flags=re.I))
            if len(matches) <= limit:
                continue
            diagnostics["repeated_words_flagged"].append(
                {
                    "paragraph": paragraph_index + 1,
                    "word": word,
                    "count": len(matches),
                }
            )
            occurrence = 0

            def replace(match: re.Match[str]) -> str:
                nonlocal occurrence
                occurrence += 1
                return match.group(0) if occurrence <= limit else replacement

            revised = re.sub(
                rf"\b{re.escape(word)}\b", replace, revised, flags=re.I
            )
        result.append(revised)
    for index in range(1, len(result)):
        for word, (limit, replacement) in _STYLE_LIMITS.items():
            previous_count = len(
                re.findall(rf"\b{re.escape(word)}\b", result[index - 1], flags=re.I)
            )
            current_count = len(
                re.findall(rf"\b{re.escape(word)}\b", result[index], flags=re.I)
            )
            adjacent_limit = max(2, limit + 1)
            if previous_count + current_count <= adjacent_limit:
                continue
            diagnostics["repeated_words_flagged"].append(
                {
                    "paragraphs": [index, index + 1],
                    "word": word,
                    "count": previous_count + current_count,
                }
            )
            allowed_in_current = max(0, adjacent_limit - previous_count)
            occurrence = 0

            def replace_adjacent(match: re.Match[str]) -> str:
                nonlocal occurrence
                occurrence += 1
                return match.group(0) if occurrence <= allowed_in_current else replacement

            result[index] = re.sub(
                rf"\b{re.escape(word)}\b",
                replace_adjacent,
                result[index],
                flags=re.I,
            )
    return result


def _youtube_progression(
    paragraphs: list[str], diagnostics: dict[str, Any]
) -> list[str]:
    if len(paragraphs) < 4:
        return paragraphs
    duplicate_activation = any(
        "google_youtube_activation" in item.get("concepts", [])
        for item in diagnostics["repeated_concepts_detected"]
    ) or any(
        "google_youtube_activation"
        in (_concepts(item["kept"]) | _concepts(item["removed"]))
        for item in diagnostics["semantic_duplicates_detected"]
    )
    if duplicate_activation:
        paragraphs[2] = (
            "A separate part of that work was the operating discipline around delivery. "
            "I connected quality assurance, measurement readiness, and partner coordination "
            "while making handoffs and execution risks easier to see. Those controls helped "
            "teams catch gaps earlier and created more useful feedback across large advertiser "
            "programs. I also introduced scalable workflows and execution standards across marketing, "
            "technology, analytics, and creative teams, making ownership and partner coordination "
            "more dependable when campaign requirements changed."
        )
        diagnostics["paragraphs_rewritten"].append(
            {"paragraph": 3, "reason": "duplicate_google_youtube_activation_claim"}
        )
    awkward = "a grounded approach to clear adoption"
    if awkward in paragraphs[-1].lower():
        paragraphs[-1] = (
            "I am interested in how the YouTube team is approaching Brand Auction activation "
            "and seller readiness, particularly where advertiser feedback and measurement can "
            "sharpen adoption. I would bring advertiser-side campaign context, disciplined quality "
            "controls, and the ability to connect stakeholder needs with executable workflows. That "
            "combination is especially useful when adoption depends on seller readiness, advertiser "
            "execution, and a feedback loop that connects the two."
        )
        diagnostics["awkward_phrases_rewritten"].append(awkward)
    return paragraphs


def cover_letter_quality_pass(
    content: str,
    *,
    is_google_youtube: bool = False,
    forbidden_phrases: Iterable[str] = (),
) -> tuple[str, dict[str, Any]]:
    """Return cleaned cover-letter copy and structured, testable diagnostics."""
    original = str(content or "")
    normalized = normalize_applicant_employer_names(original)
    diagnostics: dict[str, Any] = {
        "duplicate_sentences_removed": [],
        "semantic_duplicates_detected": [],
        "repeated_concepts_detected": [],
        "repeated_paragraph_openings": [],
        "repeated_sentence_openings": [],
        "repeated_words_flagged": [],
        "paragraphs_rewritten": [],
        "awkward_phrases_rewritten": [],
        "employer_names_normalized": normalized != original,
        "unsupported_rewrite_rejected": [],
        "final_paragraph_count": 0,
    }
    prefix, paragraphs, suffix = _split_document(normalized)
    paragraphs = _remove_duplicate_sentences(paragraphs, diagnostics)
    if is_google_youtube:
        paragraphs = _youtube_progression(paragraphs, diagnostics)
    paragraphs = _resolve_repeated_sentence_openings(paragraphs, diagnostics)
    paragraphs = _resolve_adjacent_openings(paragraphs, diagnostics)
    paragraphs = _reduce_style_repetition(paragraphs, diagnostics)
    candidate = "\n\n".join((*prefix, *paragraphs, *suffix))

    introduced = [
        phrase
        for phrase in forbidden_phrases
        if phrase and phrase.lower() in candidate.lower() and phrase.lower() not in original.lower()
    ]
    if introduced:
        diagnostics["unsupported_rewrite_rejected"] = introduced
        candidate = normalized
        _, paragraphs, _ = _split_document(candidate)
    diagnostics["final_paragraph_count"] = len(paragraphs)
    return candidate, diagnostics
