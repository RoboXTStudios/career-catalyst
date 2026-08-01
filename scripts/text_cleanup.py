"""Small text cleanup safeguards shared by generated career materials."""

import re


REPEATABLE_CLEANUP_WORDS = (
    "role",
    "this",
    "the",
    "opportunity",
    "that",
)


def normalize_candidate_text(text: str) -> str:
    """Normalize non-factual candidate-facing language at the output boundary.

    This function is deliberately limited to presentation policy.  It is used on
    rendered material only; source Evidence titles and historical records are not
    rewritten.
    """
    cleaned = re.sub(r"[ \t]*\u2014+[ \t]*", " - ", str(text or ""))
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
