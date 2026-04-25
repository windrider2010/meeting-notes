from __future__ import annotations

from schemas import SessionState


class SessionStore:
    def __init__(self) -> None:
        self.sessions: dict[str, SessionState] = {}

    def get_or_create(self, session_id: str) -> SessionState:
        if session_id not in self.sessions:
            self.sessions[session_id] = SessionState(session_id=session_id)
        return self.sessions[session_id]

    def get(self, session_id: str) -> SessionState | None:
        return self.sessions.get(session_id)

    def list_sessions(self) -> list[dict]:
        return [
            {
                "session_id": state.session_id,
                "started_at_ms": state.started_at_ms,
                "transcript_count": len(state.transcript),
            }
            for state in self.sessions.values()
        ]
