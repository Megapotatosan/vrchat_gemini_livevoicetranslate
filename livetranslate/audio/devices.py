"""Audio devices, always identified by name (Windows renumbers them on every plug/unplug)."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

DeviceKind = Literal["input", "loopback", "output"]


@dataclass(frozen=True)
class DeviceInfo:
    index: int
    name: str
    kind: DeviceKind
    is_default: bool
    sample_rate: int
    channels: int


def resolve_device(name: str, devices: Sequence[DeviceInfo]) -> tuple[DeviceInfo | None, bool]:
    """Find a device by name. Returns (device, fell_back_to_default)."""
    if name:
        for match in (lambda d: d.name == name, lambda d: d.name.casefold() == name.casefold()):
            found = next((d for d in devices if match(d)), None)
            if found:
                return found, False
    default = next((d for d in devices if d.is_default), devices[0] if devices else None)
    return default, bool(name)


def list_devices() -> dict[DeviceKind, list[DeviceInfo]]:
    import sounddevice as sd

    result: dict[DeviceKind, list[DeviceInfo]] = {"input": [], "loopback": [], "output": []}
    hostapis = sd.query_hostapis()
    wasapi = next((i for i, h in enumerate(hostapis) if "WASAPI" in h["name"]), None)
    default_in, default_out = sd.default.device
    for index, dev in enumerate(sd.query_devices()):
        if wasapi is not None and dev["hostapi"] != wasapi:
            continue
        rate = int(dev["default_samplerate"])
        if dev["max_input_channels"] > 0:
            result["input"].append(DeviceInfo(index, dev["name"], "input", index == default_in, rate,
                                              dev["max_input_channels"]))
        if dev["max_output_channels"] > 0:
            result["output"].append(DeviceInfo(index, dev["name"], "output", index == default_out, rate,
                                               dev["max_output_channels"]))
    if sys.platform == "win32":
        result["loopback"] = _list_loopbacks()
    return result


def _list_loopbacks() -> list[DeviceInfo]:
    import pyaudiowpatch as pyaudio

    pa = pyaudio.PyAudio()
    try:
        try:
            default_out = pa.get_default_wasapi_loopback()["index"]
        except (OSError, LookupError):
            default_out = None
        return [DeviceInfo(d["index"], d["name"], "loopback", d["index"] == default_out,
                           int(d["defaultSampleRate"]), d["maxInputChannels"])
                for d in pa.get_loopback_device_info_generator()]
    finally:
        pa.terminate()
