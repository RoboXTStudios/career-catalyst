"""Small text cleanup safeguards shared by generated career materials."""

import re
from html import unescape

try:
    from .filename_utils import canonicalize_employer_mentions
except ImportError:
    from filename_utils import canonicalize_employer_mentions


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


# Age-signaling phrasings and neutral rewrites, most specific first.  Tenure
# stated as experience ("over a decade of experience", "15+ years") becomes
# "extensive experience"; a project duration ("the slate over a decade")
# keeps its meaning as "over many years".
_DECADES = r"(?:a|one|two|three|several|multiple)\s+decades?"
AGE_SIGNAL_REPLACEMENTS = (
    (rf"\b(?:over|more than|nearly|almost|about|well over|close to)\s+{_DECADES}\s+of\s+(?:experience|expertise)\b", "extensive experience"),
    (rf"\b{_DECADES}\s+of\s+(?:experience|expertise)\b", "extensive experience"),
    (r"\b(?:[1-9]\d)\+?\s*(?:\+\s*)?years?\s+of\s+(?:experience|expertise)\b", "extensive experience"),
    (r"\b(?:[1-9]\d)\+\s*years\b", "extensive experience"),
    (r"\bnearly\s+two\s+decades\b", "extensive experience"),
    (r"\btwo\s+decades\b", "extensive experience"),
    (rf"\b(?:over|more than|nearly|almost|well over|close to)\s+{_DECADES}\b", "over many years"),
    (r"\bdecades?-long\b", "long-running"),
    (r"\blong-tenured\b", "experienced"),
    (r"\bseasoned\b", "experienced"),
    (r"\bveteran\b", "experienced"),
)
AGE_SIGNAL_RE = re.compile(
    "|".join(f"(?:{pattern})" for pattern, _replacement in AGE_SIGNAL_REPLACEMENTS),
    flags=re.IGNORECASE,
)


def normalize_candidate_text(text: str, *, employer: str = "") -> str:
    """Normalize non-factual candidate-facing language at the output boundary.

    This function is deliberately limited to presentation policy.  It is used on
    rendered material only; source Evidence titles and historical records are not
    rewritten.
    """
    # Job boards commonly double-escape role titles and prose (for example,
    # ``&amp;``). Decode standard HTML entities only at the candidate-facing
    # boundary; source tracker/Evidence records remain unchanged.
    text = str(text or "")
    # Candidate-facing prose should describe the work, not narrate claim checks.
    for phrase in (
        "while staying precise about the scope of my direct experience",
        "based on the evidence available", "where my experience directly aligns",
    ):
        text = re.sub(r"\s*,?\s*" + re.escape(phrase), "", text, flags=re.I)
    text = text.replace("keep claims close to the facts", "make ownership and decisions clear")
    text = text.replace("an approach grounded in the role's actual priorities rather than assumptions about the company", "a practical approach to the team's priorities")
    cleaned = unescape(str(text or ""))
    cleaned = re.sub(r"[ \t]*\u2014+[ \t]*", " - ", cleaned)
    replacements = (
        (r"\bOMG23\s*\(\s*Omnicom Media Group\s*\)", "OMG23 / OMD Entertainment, Omnicom Media Group"),
        (r"\bOMG23\s*/\s*OMD Entertainment(?:,\s*Omnicom Media Group)?\b", "OMG23 / OMD Entertainment, Omnicom Media Group"),
        (r"(?<!OMG23 / )\bOMD Entertainment\b", "OMG23 / OMD Entertainment, Omnicom Media Group"),
        *AGE_SIGNAL_REPLACEMENTS,
    )
    for pattern, replacement in replacements:
        cleaned = re.sub(
            pattern,
            lambda match, value=replacement: (
                value[:1].upper() + value[1:]
                if match.group(0)[:1].isupper()
                or re.search(r"(?:^|[.!?]\s+|\n\s*(?:[-*]\s+)?)$", match.string[: match.start()])
                else value
            ),
            cleaned,
            flags=re.IGNORECASE,
        )
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
    cleaned = re.sub(
        r"\b([Aa])\s+experienced\b",
        lambda match: ("An" if match.group(1) == "A" else "an") + " experienced",
        cleaned,
    )
    cleaned = canonicalize_employer_mentions(cleaned, employer)
    return cleaned


def cleanup_repeated_words(text: str, *, employer: str = "") -> str:
    """Collapse adjacent repeats for a small set of safe, common words."""
    cleaned = normalize_candidate_text(text, employer=employer)
    for word in REPEATABLE_CLEANUP_WORDS:
        pattern = re.compile(rf"\b({re.escape(word)})\b(\s+)\1\b", re.IGNORECASE)
        while pattern.search(cleaned):
            cleaned = pattern.sub(r"\1", cleaned)
    return cleaned
