from __future__ import annotations

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from notes import build_notes


def test_build_notes_extracts_actions_decisions_and_questions() -> None:
    transcript = [
        {"text": "We agreed to use the smaller model first."},
        {"text": "Can you follow up with the finance team?"},
        {"text": "What is the deadline?"},
    ]

    notes = build_notes(transcript)

    assert notes["transcript_count"] == 3
    assert notes["decisions"] == ["We agreed to use the smaller model first."]
    assert notes["action_items"] == ["Can you follow up with the finance team?"]
    assert notes["open_questions"] == [
        "Can you follow up with the finance team?",
        "What is the deadline?",
    ]
