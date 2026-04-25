from __future__ import annotations

import re
from typing import Any


ACTION_PATTERNS = [
    r"\bI will\b",
    r"\bwe will\b",
    r"\bwe should\b",
    r"\blet'?s\b",
    r"\bneed to\b",
    r"\bfollow up\b",
    r"\bcan you\b",
    r"\bplease\b",
]

DECISION_PATTERNS = [
    r"\bdecided\b",
    r"\bdecision\b",
    r"\bagreed\b",
    r"\bapproved\b",
    r"\bwe will go with\b",
]


def _segment_text(segment: Any) -> str:
    if isinstance(segment, dict):
        return str(segment.get("text", "")).strip()
    return str(getattr(segment, "text", "")).strip()


def build_notes(transcript: list[Any]) -> dict:
    text_blocks = [_segment_text(item) for item in transcript]
    text_blocks = [text for text in text_blocks if text]

    actions = [
        text
        for text in text_blocks
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in ACTION_PATTERNS)
    ]
    decisions = [
        text
        for text in text_blocks
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in DECISION_PATTERNS)
    ]
    questions = [text for text in text_blocks if "?" in text]

    recent = " ".join(text_blocks[-30:])
    return {
        "summary": recent[:2000],
        "action_items": actions[-10:],
        "decisions": decisions[-10:],
        "open_questions": questions[-10:],
        "transcript_count": len(text_blocks),
    }
