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
    """Normalize punctuation at the candidate-facing output boundary."""
    return re.sub(r"[ \t]*\u2014+[ \t]*", " - ", str(text or ""))


def cleanup_repeated_words(text: str) -> str:
    """Collapse adjacent repeats for a small set of safe, common words."""
    cleaned = normalize_candidate_text(text)
    for word in REPEATABLE_CLEANUP_WORDS:
        pattern = re.compile(rf"\b({re.escape(word)})\b(\s+)\1\b", re.IGNORECASE)
        while pattern.search(cleaned):
            cleaned = pattern.sub(r"\1", cleaned)
    return cleaned
