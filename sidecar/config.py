from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _env_optional_int(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or value == "":
        return None
    return int(value)


def _default_session_id() -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"meeting-{stamp}"


@dataclass(frozen=True)
class Settings:
    ws_url: str = os.getenv("MN_WS_URL", "ws://YOUR_ORACLE_IP:8000/ws/audio")
    session_id: str = os.getenv("MN_SESSION_ID", _default_session_id())
    chunk_ms: int = _env_int("MN_CHUNK_MS", 1000)
    sample_rate: int | None = _env_optional_int("MN_SAMPLE_RATE")
    channels: int | None = _env_optional_int("MN_CHANNELS")
    sample_width: int = 2
    system_device_index: int | None = _env_optional_int("MN_SYSTEM_DEVICE_INDEX")
    mic_device_index: int | None = _env_optional_int("MN_MIC_DEVICE_INDEX")
    include_system: bool = os.getenv("MN_INCLUDE_SYSTEM", "1") not in {"0", "false", "False"}
    include_mic: bool = os.getenv("MN_INCLUDE_MIC", "1") not in {"0", "false", "False"}
