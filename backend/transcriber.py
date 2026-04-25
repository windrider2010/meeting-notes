from __future__ import annotations

import io
import os
import wave

try:
    from faster_whisper import WhisperModel
except ImportError:  # pragma: no cover
    WhisperModel = None  # type: ignore[assignment]


class Transcriber:
    def __init__(
        self,
        model_size: str | None = None,
        device: str | None = None,
        compute_type: str | None = None,
        language: str | None = None,
    ) -> None:
        if WhisperModel is None:
            raise RuntimeError("faster-whisper is not installed. Run: python -m pip install -r requirements.txt")

        self.language = language if language is not None else os.getenv("MN_LANGUAGE", "en")
        if self.language == "":
            self.language = None

        self.model = WhisperModel(
            model_size or os.getenv("MN_MODEL_SIZE", "small"),
            device=device or os.getenv("MN_DEVICE", "cpu"),
            compute_type=compute_type or os.getenv("MN_COMPUTE_TYPE", "int8"),
        )

    def pcm16_to_wav_bytes(
        self,
        pcm_bytes: bytes,
        *,
        sample_rate: int,
        channels: int,
        sample_width: int = 2,
    ) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(channels)
            wav.setsampwidth(sample_width)
            wav.setframerate(sample_rate)
            wav.writeframes(pcm_bytes)
        return buf.getvalue()

    def transcribe_chunk(
        self,
        pcm_bytes: bytes,
        *,
        track: str,
        sample_rate: int,
        channels: int,
        sample_width: int = 2,
    ) -> list[dict]:
        if not pcm_bytes:
            return []

        wav_bytes = self.pcm16_to_wav_bytes(
            pcm_bytes,
            sample_rate=sample_rate,
            channels=channels,
            sample_width=sample_width,
        )

        kwargs = {
            "vad_filter": True,
            "beam_size": 1,
            "condition_on_previous_text": False,
        }
        if self.language:
            kwargs["language"] = self.language

        segments, _info = self.model.transcribe(io.BytesIO(wav_bytes), **kwargs)
        return [
            {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text.strip(),
                "track": track,
            }
            for segment in segments
            if segment.text.strip()
        ]
