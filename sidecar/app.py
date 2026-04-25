from __future__ import annotations

import argparse
import asyncio
import contextlib
import time
import textwrap
from dataclasses import replace

import orjson

from audio_capture import CaptureDevice, WasapiDevices
from config import Settings
from ws_client import WSClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Windows meeting audio sidecar")
    parser.add_argument("--ws-url", help="Backend WebSocket URL")
    parser.add_argument("--session-id", help="Session id")
    parser.add_argument("--chunk-ms", type=int, help="Chunk size in milliseconds")
    parser.add_argument("--sample-rate", type=int, help="Force capture sample rate")
    parser.add_argument("--channels", type=int, help="Force capture channel count")
    parser.add_argument("--system-device-index", type=int, help="Force WASAPI loopback device index")
    parser.add_argument("--mic-device-index", type=int, help="Force microphone device index")
    parser.add_argument("--no-system", action="store_true", help="Disable speaker loopback capture")
    parser.add_argument("--no-mic", action="store_true", help="Disable microphone capture")
    parser.add_argument("--list-devices", action="store_true", help="Print PyAudio devices and exit")
    return parser.parse_args()


def settings_from_args(args: argparse.Namespace) -> Settings:
    settings = Settings()
    updates = {}
    for field_name in (
        "ws_url",
        "session_id",
        "chunk_ms",
        "sample_rate",
        "channels",
        "system_device_index",
        "mic_device_index",
    ):
        value = getattr(args, field_name)
        if value is not None:
            updates[field_name] = value
    if args.no_system:
        updates["include_system"] = False
    if args.no_mic:
        updates["include_mic"] = False
    return replace(settings, **updates)


def print_devices(devices: WasapiDevices) -> None:
    print(orjson.dumps(devices.list_devices(), option=orjson.OPT_INDENT_2).decode("utf-8"))


def frames_per_chunk(device: CaptureDevice, settings: Settings) -> int:
    return max(1, device.sample_rate * settings.chunk_ms // 1000)


async def stream_audio_track(
    ws_client: WSClient,
    stream,
    device: CaptureDevice,
    track_name: str,
    settings: Settings,
) -> None:
    frames = frames_per_chunk(device, settings)

    while True:
        data = await asyncio.to_thread(stream.read, frames, exception_on_overflow=False)
        if not data:
            await asyncio.sleep(0)
            continue

        await ws_client.send_audio_chunk(
            {
                "type": "audio_chunk_meta",
                "session_id": settings.session_id,
                "track": track_name,
                "sample_rate": device.sample_rate,
                "channels": device.channels,
                "sample_width": settings.sample_width,
                "ts_ms": int(time.time() * 1000),
                "size": len(data),
            },
            data,
        )
        await asyncio.sleep(0)


async def print_backend_messages(ws_client: WSClient) -> None:
    last_summary = ""
    last_actions: tuple[str, ...] = ()

    while True:
        message = await ws_client.recv()
        if isinstance(message, bytes):
            continue

        payload = orjson.loads(message)
        msg_type = payload.get("type")
        if msg_type == "ack":
            print(f"Connected session {payload.get('session_id')}")
            exports = payload.get("exports") or {}
            session_dir = exports.get("session_dir")
            if session_dir:
                print(f"Export dir: {session_dir}")
        elif msg_type == "buffered":
            print(
                f"Buffered {payload.get('track')} "
                f"{payload.get('buffer_ms')}ms/{payload.get('target_ms')}ms"
            )
        elif msg_type == "partial_result":
            for segment in payload.get("segments", []):
                text = segment.get("text", "")
                if text:
                    print(
                        f"[{segment.get('track')} "
                        f"{segment.get('start'):.1f}-{segment.get('end'):.1f}] {text}"
                    )
            notes = payload.get("notes") or {}
            summary = str(notes.get("summary") or "").strip()
            if summary and summary != last_summary:
                print("Summary:")
                for line in textwrap.wrap(summary, width=100):
                    print(f"  {line}")
                last_summary = summary

            actions = tuple(notes.get("action_items") or [])
            if actions and actions != last_actions:
                print("Recent action items:")
                for item in actions[-3:]:
                    print(f"  - {item}")
                last_actions = actions
        elif msg_type == "error":
            print(f"Backend error: {payload.get('message')}")


async def run(settings: Settings) -> None:
    if not settings.include_system and not settings.include_mic:
        raise ValueError("At least one of system or mic capture must be enabled")

    devices = WasapiDevices()
    streams = []
    tasks: list[asyncio.Task] = []
    ws_client = WSClient(settings.ws_url)

    try:
        if settings.include_system:
            system_device = devices.resolve_loopback(
                settings.system_device_index,
                settings.sample_rate,
                settings.channels,
            )
            system_stream = devices.open_input_stream(
                system_device,
                frames_per_chunk(system_device, settings),
            )
            streams.append(system_stream)
            print(
                "system:",
                system_device.index,
                system_device.name,
                f"{system_device.sample_rate}Hz",
                f"{system_device.channels}ch",
            )
        else:
            system_device = None
            system_stream = None

        if settings.include_mic:
            mic_device = devices.resolve_mic(
                settings.mic_device_index,
                settings.sample_rate,
                settings.channels,
            )
            mic_stream = devices.open_input_stream(mic_device, frames_per_chunk(mic_device, settings))
            streams.append(mic_stream)
            print(
                "mic:",
                mic_device.index,
                mic_device.name,
                f"{mic_device.sample_rate}Hz",
                f"{mic_device.channels}ch",
            )
        else:
            mic_device = None
            mic_stream = None

        await ws_client.connect()
        await ws_client.send_json(
            {
                "type": "session_start",
                "session_id": settings.session_id,
                "source": "windows-sidecar-v1",
            }
        )

        tasks.append(asyncio.create_task(print_backend_messages(ws_client)))
        if system_stream is not None and system_device is not None:
            tasks.append(
                asyncio.create_task(
                    stream_audio_track(ws_client, system_stream, system_device, "system", settings)
                )
            )
        if mic_stream is not None and mic_device is not None:
            tasks.append(asyncio.create_task(stream_audio_track(ws_client, mic_stream, mic_device, "mic", settings)))

        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for stream in streams:
            with contextlib.suppress(Exception):
                stream.stop_stream()
                stream.close()
        await ws_client.close()
        devices.close()


async def main() -> None:
    args = parse_args()
    settings = settings_from_args(args)

    if args.list_devices:
        devices = WasapiDevices()
        try:
            print_devices(devices)
        finally:
            devices.close()
        return

    await run(settings)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped")
