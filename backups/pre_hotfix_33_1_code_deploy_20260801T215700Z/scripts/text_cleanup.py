"""Small text cleanup safeguards shared by generated career materials."""

import re


REPEATABLE_CLEANUP_WORDS = (
    "role",
    "this",
    "the",
    "opportunity",
    "that",
)


def cleanup_repeated_words(text: str) -> str:
    """Collapse adjacent repeats for a small set of safe, common words."""
    cleaned = text
    for word in REPEATABLE_CLEANUP_WORDS:
        pattern = re.compile(rf"\b({re.escape(word)})\b(\s+)\1\b", re.IGNORECASE)
        while pattern.search(cleaned):
            cleaned = pattern.sub(r"\1", cleaned)
    return cleaned
