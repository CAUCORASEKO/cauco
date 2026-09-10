"""Narrow deterministic detector for standalone capability questions."""

import re
import unicodedata

_INQUIRIES = frozenset(
    {
        "que puedes hacer",
        "que sabes hacer",
        "cuales son tus capacidades",
        "dime que puedes hacer",
        "what can you do",
        "what are your capabilities",
    }
)


def is_capability_inquiry(instruction: str) -> bool:
    folded = "".join(
        character
        for character in unicodedata.normalize("NFKD", instruction.casefold())
        if not unicodedata.combining(character)
    )
    normalized = " ".join(
        part for part in re.sub(r"[^a-z0-9]+", " ", folded).split() if part
    )
    return normalized in _INQUIRIES
