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
