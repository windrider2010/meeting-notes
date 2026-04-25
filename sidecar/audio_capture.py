from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pyaudiowpatch as pyaudio


FORMAT = pyaudio.paInt16


@dataclass(frozen=True)
class CaptureDevice:
    index: int
    name: str
    sample_rate: int
    channels: int
    host_api: str


class WasapiDevices:
    def __init__(self) -> None:
        self.p = pyaudio.PyAudio()

    def list_devices(self) -> list[dict[str, Any]]:
        devices: list[dict[str, Any]] = []
        for index in range(self.p.get_device_count()):
            info = self.p.get_device_info_by_index(index)
            devices.append(self._summarize_device(info))
        return devices

    def get_default_loopback_device(self) -> dict[str, Any]:
        return self.p.get_default_wasapi_loopback()

    def get_default_mic_device(self) -> dict[str, Any]:
        return self.p.get_default_input_device_info()

    def get_device(self, index: int) -> dict[str, Any]:
        return self.p.get_device_info_by_index(index)

    def resolve_loopback(
        self,
        device_index: int | None,
        requested_rate: int | None,
        requested_channels: int | None,
    ) -> CaptureDevice:
        info = self.get_device(device_index) if device_index is not None else self.get_default_loopback_device()
        return self._to_capture_device(info, requested_rate, requested_channels)

    def resolve_mic(
        self,
        device_index: int | None,
        requested_rate: int | None,
        requested_channels: int | None,
    ) -> CaptureDevice:
        info = self.get_device(device_index) if device_index is not None else self.get_default_mic_device()
        return self._to_capture_device(info, requested_rate, requested_channels)

    def open_input_stream(self, device: CaptureDevice, frames_per_buffer: int) -> pyaudio.Stream:
        return self.p.open(
            format=FORMAT,
            channels=device.channels,
            rate=device.sample_rate,
            input=True,
            input_device_index=device.index,
            frames_per_buffer=frames_per_buffer,
        )

    def close(self) -> None:
        self.p.terminate()

    def _to_capture_device(
        self,
        info: dict[str, Any],
        requested_rate: int | None,
        requested_channels: int | None,
    ) -> CaptureDevice:
        index = int(info["index"])
        name = str(info.get("name", f"device-{index}"))
        host_api = self._host_api_name(info)
        sample_rate = int(requested_rate or int(float(info.get("defaultSampleRate") or 16000)))

        max_input_channels = int(info.get("maxInputChannels") or 0)
        max_output_channels = int(info.get("maxOutputChannels") or 0)
        max_channels = max(max_input_channels, max_output_channels, 1)
        channels = int(requested_channels or min(max_channels, 2))

        if channels < 1:
            raise ValueError(f"Invalid channel count for {name}: {channels}")
        if channels > max_channels:
            raise ValueError(f"Requested {channels} channels for {name}, but device supports {max_channels}")

        return CaptureDevice(
            index=index,
            name=name,
            sample_rate=sample_rate,
            channels=channels,
            host_api=host_api,
        )

    def _summarize_device(self, info: dict[str, Any]) -> dict[str, Any]:
        return {
            "index": int(info["index"]),
            "name": info.get("name", ""),
            "host_api": self._host_api_name(info),
            "default_sample_rate": int(float(info.get("defaultSampleRate") or 0)),
            "max_input_channels": int(info.get("maxInputChannels") or 0),
            "max_output_channels": int(info.get("maxOutputChannels") or 0),
        }

    def _host_api_name(self, info: dict[str, Any]) -> str:
        try:
            host_api_index = int(info.get("hostApi", -1))
            if host_api_index >= 0:
                return str(self.p.get_host_api_info_by_index(host_api_index).get("name", ""))
        except Exception:
            return ""
        return ""
