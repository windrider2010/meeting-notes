# WebSocket Protocol

Endpoint:

```text
ws://HOST:8000/ws/audio
```

The protocol alternates one JSON text frame with one binary audio frame.

## Session Start

Text frame:

```json
{
  "type": "session_start",
  "session_id": "demo-session-001",
  "source": "windows-sidecar-v1"
}
```

Backend response:

```json
{
  "type": "ack",
  "session_id": "demo-session-001"
}
```

## Audio Chunk

Text frame:

```json
{
  "type": "audio_chunk_meta",
  "session_id": "demo-session-001",
  "track": "system",
  "sample_rate": 48000,
  "channels": 2,
  "sample_width": 2,
  "ts_ms": 1776825600000,
  "size": 192000
}
```

Immediately followed by a binary frame containing PCM16 little-endian audio bytes.

Tracks:

- `system`: default Windows speaker output captured with WASAPI loopback.
- `mic`: local microphone.

## Partial Result

Backend response:

```json
{
  "type": "partial_result",
  "session_id": "demo-session-001",
  "track": "system",
  "segments": [
    {
      "start": 12.3,
      "end": 16.8,
      "text": "Let's follow up with finance tomorrow.",
      "track": "system",
      "wall_start_ms": 1776825612300,
      "wall_end_ms": 1776825616800
    }
  ],
  "notes": {
    "summary": "Recent transcript text...",
    "action_items": ["Let's follow up with finance tomorrow."],
    "decisions": [],
    "open_questions": [],
    "transcript_count": 1
  }
}
```

`start` and `end` are seconds relative to the backend session start. Wall-clock fields are Unix milliseconds from the sidecar timestamp.
