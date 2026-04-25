from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field


@dataclass
class Segment:
    start: float
    end: float
    text: str
    track: str
    wall_start_ms: int | None = None
    wall_end_ms: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TrackBuffer:
    buffer: bytearray = field(default_factory=bytearray)
    window_start_ms: int | None = None
    sample_rate: int = 16000
    channels: int = 1
    sample_width: int = 2

    def append(
        self,
        pcm: bytes,
        *,
        ts_ms: int,
        sample_rate: int,
        channels: int,
        sample_width: int,
    ) -> None:
        if not self.buffer:
            self.window_start_ms = ts_ms
            self.sample_rate = sample_rate
            self.channels = channels
            self.sample_width = sample_width
        self.buffer.extend(pcm)

    def duration_ms(self) -> int:
        bytes_per_second = self.sample_rate * self.channels * self.sample_width
        if bytes_per_second <= 0:
            return 0
        return int(len(self.buffer) * 1000 / bytes_per_second)

    def drain(self) -> tuple[bytes, int, int, int, int]:
        pcm = bytes(self.buffer)
        window_start_ms = self.window_start_ms or int(time.time() * 1000)
        sample_rate = self.sample_rate
        channels = self.channels
        sample_width = self.sample_width
        self.buffer.clear()
        self.window_start_ms = None
        return pcm, window_start_ms, sample_rate, channels, sample_width


@dataclass
class SessionState:
    session_id: str
    started_at_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    tracks: dict[str, TrackBuffer] = field(default_factory=dict)
    transcript: list[Segment] = field(default_factory=list)

    def track(self, name: str) -> TrackBuffer:
        if name not in self.tracks:
            self.tracks[name] = TrackBuffer()
        return self.tracks[name]

    def add_segments(
        self,
        raw_segments: list[dict],
        *,
        track: str,
        window_start_ms: int,
    ) -> list[Segment]:
        session_offset = (window_start_ms - self.started_at_ms) / 1000
        segments: list[Segment] = []
        for raw in raw_segments:
            start = max(0.0, session_offset + float(raw["start"]))
            end = max(start, session_offset + float(raw["end"]))
            text = str(raw.get("text", "")).strip()
            if not text:
                continue
            segment = Segment(
                start=round(start, 3),
                end=round(end, 3),
                text=text,
                track=track,
                wall_start_ms=window_start_ms + int(float(raw["start"]) * 1000),
                wall_end_ms=window_start_ms + int(float(raw["end"]) * 1000),
            )
            self.transcript.append(segment)
            segments.append(segment)
        self.transcript.sort(key=lambda item: (item.start, item.track))
        return segments
