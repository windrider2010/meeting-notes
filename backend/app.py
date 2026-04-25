from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import orjson
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from exporter import SessionExporter
from notes import build_notes
from schemas import SessionState
from session import SessionStore
from transcriber import Transcriber


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


TRANSCRIBE_WINDOW_MS = _env_int("MN_TRANSCRIBE_WINDOW_MS", 5000)
OUTPUT_DIR = os.getenv("MN_OUTPUT_DIR", "outputs")
EXPORT_RETENTION_DAYS = _env_int("MN_EXPORT_RETENTION_DAYS", 365)
EXPORT_MAX_SESSIONS = _env_int("MN_EXPORT_MAX_SESSIONS", 200)

app = FastAPI(title="Meeting Notes Backend")
store = SessionStore()
_transcriber: Transcriber | None = None
_exporter = SessionExporter(
    OUTPUT_DIR,
    retention_days=EXPORT_RETENTION_DAYS,
    max_sessions=EXPORT_MAX_SESSIONS,
)


def get_transcriber() -> Transcriber:
    global _transcriber
    if _transcriber is None:
        _transcriber = Transcriber()
    return _transcriber


@app.get("/health")
async def health() -> dict:
    return {
        "ok": True,
        "transcribe_window_ms": TRANSCRIBE_WINDOW_MS,
        "output_dir": OUTPUT_DIR,
        "export_retention_days": EXPORT_RETENTION_DAYS,
        "export_max_sessions": EXPORT_MAX_SESSIONS,
        "model_size": os.getenv("MN_MODEL_SIZE", "small"),
        "device": os.getenv("MN_DEVICE", "cpu"),
        "compute_type": os.getenv("MN_COMPUTE_TYPE", "int8"),
    }


@app.get("/sessions")
async def list_sessions() -> dict:
    return {"sessions": store.list_sessions()}


@app.get("/sessions/{session_id}/transcript")
async def get_transcript(session_id: str) -> dict:
    state = _get_session_or_404(session_id)
    return {
        "session_id": session_id,
        "segments": [segment.to_dict() for segment in state.transcript],
    }


@app.get("/sessions/{session_id}/notes")
async def get_notes(session_id: str) -> dict:
    state = _get_session_or_404(session_id)
    return {
        "session_id": session_id,
        "notes": build_notes(state.transcript),
    }


@app.get("/sessions/{session_id}/exports")
async def get_exports(session_id: str) -> dict:
    return await asyncio.to_thread(_get_exports_or_404, session_id)


@app.get("/sessions/{session_id}/exports/{export_name}")
async def download_export(session_id: str, export_name: str) -> FileResponse:
    path, content_type = await asyncio.to_thread(_get_export_file_or_error, session_id, export_name)
    return FileResponse(path=path, media_type=content_type, filename=path.name)


@app.websocket("/ws/audio")
async def ws_audio(websocket: WebSocket) -> None:
    await websocket.accept()
    current_meta: dict[str, Any] | None = None

    try:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                return

            if message.get("text") is not None:
                payload = orjson.loads(message["text"])
                current_meta = await _handle_text_message(websocket, payload)
                continue

            if message.get("bytes") is not None:
                if current_meta is None:
                    await websocket.send_json({"type": "error", "message": "Received audio bytes without metadata"})
                    continue

                await _handle_audio_bytes(websocket, current_meta, message["bytes"])
                current_meta = None
    except WebSocketDisconnect:
        return


async def _handle_text_message(websocket: WebSocket, payload: dict[str, Any]) -> dict[str, Any] | None:
    msg_type = payload.get("type")

    if msg_type == "session_start":
        session_id = str(payload["session_id"])
        state = store.get_or_create(session_id)
        notes = build_notes(state.transcript)
        exports = await asyncio.to_thread(_exporter.export_session, state, notes)
        await websocket.send_json({"type": "ack", "session_id": session_id, "exports": exports})
        return None

    if msg_type == "audio_chunk_meta":
        return payload

    await websocket.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})
    return None


async def _handle_audio_bytes(websocket: WebSocket, meta: dict[str, Any], pcm: bytes) -> None:
    session_id = str(meta["session_id"])
    track = str(meta.get("track") or "system")
    sample_rate = int(meta.get("sample_rate") or 16000)
    channels = int(meta.get("channels") or 1)
    sample_width = int(meta.get("sample_width") or 2)
    ts_ms = int(meta.get("ts_ms") or int(time.time() * 1000))

    expected_size = int(meta.get("size") or len(pcm))
    if expected_size != len(pcm):
        await websocket.send_json(
            {
                "type": "error",
                "message": f"Audio size mismatch: expected {expected_size}, received {len(pcm)}",
            }
        )
        return

    state = store.get_or_create(session_id)
    track_buffer = state.track(track)
    track_buffer.append(
        pcm,
        ts_ms=ts_ms,
        sample_rate=sample_rate,
        channels=channels,
        sample_width=sample_width,
    )

    buffer_ms = track_buffer.duration_ms()
    if buffer_ms < TRANSCRIBE_WINDOW_MS:
        await websocket.send_json(
            {
                "type": "buffered",
                "session_id": session_id,
                "track": track,
                "buffer_ms": buffer_ms,
                "target_ms": TRANSCRIBE_WINDOW_MS,
            }
        )
        return

    pcm_window, window_start_ms, sample_rate, channels, sample_width = track_buffer.drain()
    raw_segments = await asyncio.to_thread(
        _transcribe_blocking,
        pcm_window,
        track,
        sample_rate,
        channels,
        sample_width,
    )
    segments = state.add_segments(raw_segments, track=track, window_start_ms=window_start_ms)
    notes = build_notes(state.transcript)
    exports = await asyncio.to_thread(_exporter.export_session, state, notes)

    await websocket.send_json(
        {
            "type": "partial_result",
            "session_id": session_id,
            "track": track,
            "segments": [segment.to_dict() for segment in segments],
            "notes": notes,
            "exports": exports,
        }
    )


def _transcribe_blocking(
    pcm: bytes,
    track: str,
    sample_rate: int,
    channels: int,
    sample_width: int,
) -> list[dict]:
    return get_transcriber().transcribe_chunk(
        pcm,
        track=track,
        sample_rate=sample_rate,
        channels=channels,
        sample_width=sample_width,
    )


def _get_session_or_404(session_id: str) -> SessionState:
    state = store.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Unknown session: {session_id}")
    return state


def _get_exports_or_404(session_id: str) -> dict:
    try:
        return _exporter.get_session_exports(session_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _get_export_file_or_error(session_id: str, export_name: str) -> tuple[str, str]:
    try:
        path, content_type = _exporter.resolve_export_file(session_id, export_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return str(path), content_type
