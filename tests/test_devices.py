from livetranslate.audio.devices import DeviceInfo, resolve_device


def D(i, n, d=False):
    return DeviceInfo(i, n, "input", d, 48000, 2)


DEVS = [D(0, "Realtek Mic", True), D(1, "Headset Microphone (Index)")]


def test_resolve():
    assert resolve_device("Headset Microphone (Index)", DEVS) == (DEVS[1], False)
    assert resolve_device("headset microphone (index)", DEVS) == (DEVS[1], False)
    assert resolve_device("", DEVS) == (DEVS[0], False)
    assert resolve_device("Unplugged Mic", DEVS) == (DEVS[0], True)
    assert resolve_device("x", []) == (None, True)
    assert resolve_device("", []) == (None, False)


class FakeSd:
    """Stands in for the sounddevice module: MME (host API 0) is PortAudio's global default."""

    def __init__(self):
        self.calls = []
        self.default = type("D", (), {"device": (0, 1)})()

    def query_hostapis(self, index=None):
        apis = [{"name": "MME", "default_input_device": 0, "default_output_device": 1},
                {"name": "Windows WASAPI", "default_input_device": 3, "default_output_device": 5}]
        return apis if index is None else apis[index]

    def query_devices(self):
        return [
            {"name": "Mic (MME)", "hostapi": 0, "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 44100},
            {"name": "Speakers (MME)", "hostapi": 0, "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 44100},
            {"name": "CABLE Output (VB-Audio Virtual Cable)", "hostapi": 1, "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 48000},
            {"name": "Headset Microphone (Index)", "hostapi": 1, "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 48000},
            {"name": "CABLE Input (VB-Audio Virtual Cable)", "hostapi": 1, "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 44100},
            {"name": "Speakers (Realtek)", "hostapi": 1, "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 48000},
        ]

    def _terminate(self):
        self.calls.append("terminate")

    def _initialize(self):
        self.calls.append("initialize")


def test_wasapi_defaults_come_from_the_wasapi_host_api(monkeypatch):
    import sys

    from livetranslate.audio import devices

    fake = FakeSd()
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    monkeypatch.setattr(devices.sys, "platform", "linux")
    found = devices.list_devices()
    default_in, _ = resolve_device("", found["input"])
    default_out, _ = resolve_device("", found["output"])
    assert default_in.name == "Headset Microphone (Index)" and default_out.name == "Speakers (Realtek)"
    assert [d.name for d in found["input"]] == ["CABLE Output (VB-Audio Virtual Cable)", "Headset Microphone (Index)"]


def test_refresh_reinitialises_portaudio(monkeypatch):
    import sys

    from livetranslate.audio import devices

    fake = FakeSd()
    monkeypatch.setitem(sys.modules, "sounddevice", fake)
    monkeypatch.setattr(devices.sys, "platform", "linux")
    devices.list_devices()
    assert fake.calls == []
    devices.list_devices(refresh=True)
    assert fake.calls == ["terminate", "initialize"]
