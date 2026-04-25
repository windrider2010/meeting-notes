from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from exporter import SessionExporter
from schemas import Segment, SessionState


def test_export_session_writes_transcript_and_notes(tmp_path: Path) -> None:
    exporter = SessionExporter(tmp_path, retention_days=0, max_sessions=0)
    state = SessionState(session_id="demo/session:001")
    state.transcript.append(
        Segment(
            start=1.0,
            end=2.5,
            text="Let's follow up with finance tomorrow.",
            track="system",
            wall_start_ms=1000,
            wall_end_ms=2500,
        )
    )

    exports = exporter.export_session(
        state,
        {
            "summary": "Short summary.",
            "action_items": ["Let's follow up with finance tomorrow."],
            "decisions": [],
            "open_questions": [],
            "transcript_count": 1,
        },
    )

    transcript_path = Path(exports["transcript_json"])
    notes_json_path = Path(exports["notes_json"])
    notes_path = Path(exports["notes_md"])

    assert transcript_path.exists()
    assert notes_json_path.exists()
    assert notes_path.exists()

    transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
    assert transcript["session_id"] == "demo/session:001"
    assert transcript["transcript_count"] == 1
    assert transcript["segments"][0]["text"] == "Let's follow up with finance tomorrow."

    notes_json = json.loads(notes_json_path.read_text(encoding="utf-8"))
    assert notes_json["session_id"] == "demo/session:001"
    assert notes_json["notes"]["summary"] == "Short summary."

    notes_text = notes_path.read_text(encoding="utf-8")
    assert "# Meeting Notes: demo/session:001" in notes_text
    assert "## Action Items" in notes_text
    assert "Let's follow up with finance tomorrow." in notes_text

    exports_meta = exporter.get_session_exports("demo/session:001")
    assert exports_meta["exports"]["transcript_json"]["exists"] is True
    assert exports_meta["exports"]["notes_json"]["filename"] == "notes.json"
    resolved_path, content_type = exporter.resolve_export_file("demo/session:001", "notes.md")
    assert resolved_path == notes_path
    assert content_type == "text/markdown; charset=utf-8"


def test_export_session_prunes_old_and_excess_session_dirs(tmp_path: Path) -> None:
    old_dir = tmp_path / "old-session"
    old_dir.mkdir()
    old_file = old_dir / "notes.md"
    old_file.write_text("old", encoding="utf-8")

    recent_dir = tmp_path / "recent-session"
    recent_dir.mkdir()
    recent_file = recent_dir / "notes.md"
    recent_file.write_text("recent", encoding="utf-8")

    newer_dir = tmp_path / "newer-session"
    newer_dir.mkdir()
    newer_file = newer_dir / "notes.md"
    newer_file.write_text("newer", encoding="utf-8")

    stale_time = time.time() - 20 * 86400
    recent_time = time.time() - 7200
    newer_time = time.time() - 3600
    os.utime(old_dir, (stale_time, stale_time))
    os.utime(old_file, (stale_time, stale_time))
    os.utime(recent_dir, (recent_time, recent_time))
    os.utime(recent_file, (recent_time, recent_time))
    os.utime(newer_dir, (newer_time, newer_time))
    os.utime(newer_file, (newer_time, newer_time))

    exporter = SessionExporter(tmp_path, retention_days=14, max_sessions=2)
    state = SessionState(session_id="active-session")

    exporter.export_session(
        state,
        {
            "summary": "",
            "action_items": [],
            "decisions": [],
            "open_questions": [],
            "transcript_count": 0,
        },
    )

    assert not old_dir.exists()
    assert not recent_dir.exists()
    assert newer_dir.exists()
    assert (tmp_path / "active-session").exists()
