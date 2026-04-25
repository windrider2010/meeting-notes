from __future__ import annotations

from dataclasses import dataclass
import shutil
import re
import time
import json
from pathlib import Path
from typing import Any

try:
    import orjson
except ImportError:  # pragma: no cover
    orjson = None  # type: ignore[assignment]

from schemas import SessionState


def _safe_session_dir_name(session_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", session_id).strip("-")
    return cleaned or "session"


@dataclass(frozen=True)
class ExportFileSpec:
    key: str
    filename: str
    content_type: str


class SessionExporter:
    EXPORT_SPECS = (
        ExportFileSpec("transcript_json", "transcript.json", "application/json"),
        ExportFileSpec("notes_json", "notes.json", "application/json"),
        ExportFileSpec("notes_md", "notes.md", "text/markdown; charset=utf-8"),
    )

    def __init__(
        self,
        output_dir: str | Path,
        *,
        retention_days: int = 365,
        max_sessions: int = 200,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.retention_days = retention_days
        self.max_sessions = max_sessions

    def export_session(self, state: SessionState, notes: dict[str, Any]) -> dict[str, str]:
        session_dir = self.session_dir(state.session_id)
        session_dir.mkdir(parents=True, exist_ok=True)

        transcript_path = session_dir / "transcript.json"
        notes_json_path = session_dir / "notes.json"
        notes_path = session_dir / "notes.md"

        transcript_payload = {
            "session_id": state.session_id,
            "started_at_ms": state.started_at_ms,
            "updated_at_ms": int(time.time() * 1000),
            "transcript_count": len(state.transcript),
            "segments": [segment.to_dict() for segment in state.transcript],
        }

        self._write_bytes_atomic(
            transcript_path,
            self._dump_json_bytes(transcript_payload),
        )
        self._write_bytes_atomic(
            notes_json_path,
            self._dump_json_bytes(
                {
                    "session_id": state.session_id,
                    "started_at_ms": state.started_at_ms,
                    "updated_at_ms": int(time.time() * 1000),
                    "notes": notes,
                }
            ),
        )
        self._write_text_atomic(notes_path, self._render_notes_markdown(state, notes))
        self._prune_exports(exclude_dir=session_dir)

        return {
            "session_dir": str(session_dir),
            "transcript_json": str(transcript_path),
            "notes_json": str(notes_json_path),
            "notes_md": str(notes_path),
        }

    def session_dir(self, session_id: str) -> Path:
        return self.output_dir / _safe_session_dir_name(session_id)

    def get_session_exports(self, session_id: str) -> dict[str, Any]:
        session_dir = self.session_dir(session_id)
        if not session_dir.exists():
            raise FileNotFoundError(f"Unknown exported session: {session_id}")

        exports: dict[str, dict[str, Any]] = {}
        for spec in self.EXPORT_SPECS:
            path = session_dir / spec.filename
            exports[spec.key] = {
                "filename": spec.filename,
                "path": str(path),
                "content_type": spec.content_type,
                "exists": path.exists(),
            }

        return {
            "session_id": session_id,
            "session_dir": str(session_dir),
            "exports": exports,
        }

    def resolve_export_file(self, session_id: str, export_name: str) -> tuple[Path, str]:
        session_dir = self.session_dir(session_id)
        if not session_dir.exists():
            raise FileNotFoundError(f"Unknown exported session: {session_id}")

        spec = next((item for item in self.EXPORT_SPECS if item.filename == export_name), None)
        if spec is None:
            raise ValueError(f"Unsupported export name: {export_name}")

        path = session_dir / spec.filename
        if not path.exists():
            raise FileNotFoundError(f"Missing export file: {export_name}")
        return path, spec.content_type

    def _render_notes_markdown(self, state: SessionState, notes: dict[str, Any]) -> str:
        lines: list[str] = [
            f"# Meeting Notes: {state.session_id}",
            "",
            "## Summary",
            "",
            (notes.get("summary") or "_No summary yet._"),
            "",
            "## Action Items",
            "",
        ]
        lines.extend(self._markdown_list(notes.get("action_items") or []))
        lines.extend(
            [
                "",
                "## Decisions",
                "",
            ]
        )
        lines.extend(self._markdown_list(notes.get("decisions") or []))
        lines.extend(
            [
                "",
                "## Open Questions",
                "",
            ]
        )
        lines.extend(self._markdown_list(notes.get("open_questions") or []))
        lines.extend(
            [
                "",
                "## Recent Transcript",
                "",
            ]
        )

        recent_segments = state.transcript[-30:]
        if recent_segments:
            for segment in recent_segments:
                lines.append(f"- [{segment.track} {segment.start:.1f}-{segment.end:.1f}] {segment.text}")
        else:
            lines.append("- No transcript yet.")

        lines.append("")
        return "\n".join(lines)

    def _markdown_list(self, items: list[str]) -> list[str]:
        if not items:
            return ["- None yet."]
        return [f"- {item}" for item in items]

    def _write_text_atomic(self, path: Path, content: str) -> None:
        self._write_bytes_atomic(path, content.encode("utf-8"))

    def _dump_json_bytes(self, payload: dict[str, Any]) -> bytes:
        if orjson is not None:
            return orjson.dumps(payload, option=orjson.OPT_INDENT_2)
        return json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")

    def _prune_exports(self, *, exclude_dir: Path) -> None:
        if not self.output_dir.exists():
            return

        session_dirs = [path for path in self.output_dir.iterdir() if path.is_dir()]
        if not session_dirs:
            return

        now = time.time()
        kept_dirs: list[Path] = []
        for session_dir in session_dirs:
            if session_dir == exclude_dir:
                kept_dirs.append(session_dir)
                continue
            modified_at = self._session_modified_at(session_dir)
            age_days = (now - modified_at) / 86400
            if self.retention_days > 0 and age_days > self.retention_days:
                shutil.rmtree(session_dir, ignore_errors=True)
                continue
            kept_dirs.append(session_dir)

        if self.max_sessions > 0 and len(kept_dirs) > self.max_sessions:
            ranked = sorted(kept_dirs, key=self._session_modified_at, reverse=True)
            keep = {path.resolve() for path in ranked[: self.max_sessions]}
            for session_dir in kept_dirs:
                if session_dir.resolve() not in keep and session_dir != exclude_dir:
                    shutil.rmtree(session_dir, ignore_errors=True)

    def _session_modified_at(self, session_dir: Path) -> float:
        latest = session_dir.stat().st_mtime
        for child in session_dir.rglob("*"):
            try:
                latest = max(latest, child.stat().st_mtime)
            except FileNotFoundError:
                continue
        return latest

    def _write_bytes_atomic(self, path: Path, content: bytes) -> None:
        tmp_path = path.with_suffix(f"{path.suffix}.tmp")
        tmp_path.write_bytes(content)
        tmp_path.replace(path)
