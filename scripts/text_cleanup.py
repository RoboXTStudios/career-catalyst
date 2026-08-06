"""Small text cleanup safeguards shared by generated career materials."""

import re
from html import unescape


REPEATABLE_CLEANUP_WORDS = (
    "role",
    "this",
    "the",
    "opportunity",
    "that",
)


class CampaignOSClaimError(ValueError):
    """Raised when candidate copy overstates the CampaignOS prototype."""


CAMPAIGNOS_PROHIBITED_PATTERNS = (
    r"\bCampaignOS\s+systems?\s+at\s+scale\b",
    r"\bCampaignOS\s+(?:deployed|rolled\s+out|shipped)\s+at\s+scale\b",
    r"\b(?:enterprise|company-wide)\s+rollout\s+of\s+CampaignOS\b",
    r"\bCampaignOS\s+(?:production|enterprise)\s+(?:platform|system)\b",
    r"\bCampaignOS\s+(?:live\s+customer\s+adoption|proven\s+business\s+outcomes)\b",
)


def normalize_campaignos_claims(text: str) -> str:
    """Identify CampaignOS only as a working, non-production prototype."""
    cleaned = str(text or "")
    repairs = (
        (
            r"\bCampaignOS\s+systems?\s+at\s+scale\b",
            "a working CampaignOS prototype",
        ),
        (
            r"\bCampaignOS\s+(?:deployed|rolled\s+out|shipped)\s+at\s+scale\b",
            "CampaignOS, a working prototype that was not production-deployed",
        ),
        (
            r"\b(?:enterprise|company-wide)\s+rollout\s+of\s+CampaignOS\b",
            "iteration of CampaignOS as a working prototype",
        ),
        (
            r"\bCampaignOS\s+(?:production|enterprise)\s+(?:platform|system)\b",
            "working CampaignOS prototype",
        ),
        (
            r"\bCampaignOS\s+(?:live\s+customer\s+adoption|proven\s+business\s+outcomes)\b",
            "CampaignOS prototype testing without claimed production outcomes",
        ),
        (
            r"\bCampaignOS\s+product\s+thinking\b",
            "product thinking demonstrated through a working CampaignOS prototype",
        ),
        (
            r"\bCampaignOS\s+is\s+(?:a|an)\s+(?:platform|product|system)\b",
            "CampaignOS is a working campaign-operations prototype",
        ),
        (
            r"(?m)^CampaignOS\s*$",
            "CampaignOS (Working Prototype)",
        ),
        (
            r"(?m)^(#{1,6}\s*)CampaignOS\s*$",
            r"\1CampaignOS (Working Prototype)",
        ),
        (
            r"(?m)^(-\s+)CampaignOS\s+-",
            r"\1CampaignOS (working prototype) -",
        ),
        (
            r"\bBuilding\s+CampaignOS\b(?![^.!?\n]*\bprototype\b)",
            "Building CampaignOS as a working campaign-operations prototype",
        ),
        (
            r"\bbuilt\s+CampaignOS\b(?![^.!?\n]*\bprototype\b)",
            "built and iterated CampaignOS as a working campaign-operations prototype",
        ),
        (
            r"\bCampaignOS\b(?=\s+(?:adds|added|reflects|remains|provides|gave|gives|grew|shows)\b)(?![^.!?\n]*\bprototype\b)",
            "CampaignOS, a working campaign-operations prototype,",
        ),
    )
    for pattern, replacement in repairs:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)

    segments = re.split(r"((?<=[.!?])\s+|\n+)", cleaned)
    for index in range(0, len(segments), 2):
        segment = segments[index]
        if "campaignos" in segment.lower() and "prototype" not in segment.lower():
            first_nonspace = len(segment) - len(segment.lstrip())
            match = re.search(r"\bCampaignOS\b", segment, flags=re.IGNORECASE)
            if match:
                label = (
                    "The working CampaignOS prototype"
                    if match.start() == first_nonspace
                    else "the working CampaignOS prototype"
                )
                segment = segment[: match.start()] + label + segment[match.end() :]
                segments[index] = segment
    cleaned = "".join(segments)

    prohibited = [
        match.group(0)
        for pattern in CAMPAIGNOS_PROHIBITED_PATTERNS
        if (match := re.search(pattern, cleaned, flags=re.IGNORECASE))
    ]
    if prohibited:
        raise CampaignOSClaimError(
            "Candidate-facing CampaignOS language implies unsupported deployment or scale: "
            + prohibited[0]
        )

    for sentence in re.split(r"(?<=[.!?])\s+|\n+", cleaned):
        if "campaignos" not in sentence.lower():
            continue
        if "prototype" not in sentence.lower():
            raise CampaignOSClaimError(
                "Every candidate-facing CampaignOS reference must identify it as a working prototype: "
                + sentence.strip()
            )
    return cleaned


def missing_subject_prose_fragments(text: str) -> list[str]:
    """Return prose sentences that begin with an unsupported implied subject."""
    fragments: list[str] = []
    bare_past_verb = re.compile(
        r"^(?:Improved|Established|Led|Coordinated|Built|Created|Designed|Founded|"
        r"Directed|Introduced|Helped|Managed|Developed|Delivered|Launched|Implemented|Translated)\b"
    )
    preposition_then_verb = re.compile(
        r"^(?:In|Through|At)\s+[^,.]+,\s*(?:led|improved|coordinated|built|created|"
        r"designed|founded|directed|introduced|helped|managed|developed|delivered|"
        r"launched|implemented|translated)\b",
        flags=re.IGNORECASE,
    )
    for paragraph in str(text or "").splitlines():
        value = paragraph.strip()
        if not value or value.startswith(("-", "*", "#")):
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", value):
            candidate = sentence.strip()
            if bare_past_verb.search(candidate) or preposition_then_verb.search(candidate):
                fragments.append(candidate)
    return fragments


def normalize_candidate_text(text: str) -> str:
    """Normalize non-factual candidate-facing language at the output boundary.

    This function is deliberately limited to presentation policy.  It is used on
    rendered material only; source Evidence titles and historical records are not
    rewritten.
    """
    # Job boards commonly double-escape role titles and prose (for example,
    # ``&amp;``). Decode standard HTML entities only at the candidate-facing
    # boundary; source tracker/Evidence records remain unchanged.
    cleaned = unescape(str(text or ""))
    cleaned = re.sub(r"[ \t]*\u2014+[ \t]*", " - ", cleaned)
    replacements = (
        (r"\bOMG23\s*/\s*OMD Entertainment\b", "OMG23 (Omnicom Media Group)"),
        (r"\bOMD Entertainment\b", "OMG23 (Omnicom Media Group)"),
        (r"\b20\+\s+years\b", "extensive experience"),
        (r"\bnearly\s+two\s+decades\b", "extensive experience"),
        (r"\btwo\s+decades(?:\s+of\s+experience)?\b", "extensive experience"),
        (r"\bdecades\s+of\s+experience\b", "extensive experience"),
        (r"\bseasoned\b", "experienced"),
        (r"\bveteran\b", "experienced"),
    )
    for pattern, replacement in replacements:
        cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"\bIn\s+(RoboXT Studios|Career Catalyst|CampaignOS)\s*,\s*(founded|led|built|created|designed)\b",
        r"At \1, I \2",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"(?m)(^|[.!?]\s+)(Built|Created|Designed|Led|Founded)\b",
        lambda match: f"{match.group(1)}I {match.group(2).lower()}",
        cleaned,
    )
    cleaned = re.sub(
        r"\b(?:led|managed)\s+(?:a\s+)?(?:team|organization)\s+of\s+(?:60\+?|64)\b",
        "provided strategic and operational leadership across an integrated 64-person organization",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = normalize_campaignos_claims(cleaned)
    cleaned = re.sub(r"\ba\s+experienced\b", "an experienced", cleaned, flags=re.IGNORECASE)
    return cleaned


def cleanup_repeated_words(text: str) -> str:
    """Collapse adjacent repeats for a small set of safe, common words."""
    cleaned = normalize_candidate_text(text)
    for word in REPEATABLE_CLEANUP_WORDS:
        pattern = re.compile(rf"\b({re.escape(word)})\b(\s+)\1\b", re.IGNORECASE)
        while pattern.search(cleaned):
            cleaned = pattern.sub(r"\1", cleaned)
    return cleaned
