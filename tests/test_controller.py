import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from livetranslate.audio.devices import DeviceInfo
from livetranslate.controller import Controller, ControllerDeps
from livetranslate.credentials import KeyStore
from livetranslate.events import MessageEvent, StatsEvent, StatusEvent, TurnFinished
from livetranslate.outputs.chatbox import ChatboxSender
from livetranslate.settings import ChatboxSettings, SettingsStore


class FakePipeline:
    def __init__(self, side, target):
        self.side, self.target, self.stopped = side, target, False
        self._done = asyncio.Event()

    async def run(self):
        await self._done.wait()

    async def stop(self):
        self.stopped = True
        self._done.set()


class FakeVoice:
    def __init__(self, device):
        self.device, self.started, self.stopped, self.fed = device, False, False, []

    def start(self):
        self.started = True

    def feed(self, turn_id, pcm):
        self.fed.append((turn_id, pcm))

    def stop(self):
        self.stopped = True


@pytest.fixture
def ctl_factory(tmp_path):
    def make(os_locale="zh_TW", key="AIzaTestKey1234", outputs=("Speakers",)):
        ns = SimpleNamespace(events=[], pipelines=[], voices=[], slept=[], osc=[])
        ns.store = SettingsStore(tmp_path / "settings.json")
        keys = KeyStore()
        if key:
            keys.save(key)
        ns.translator = SimpleNamespace(translate=AsyncMock(return_value="Hello"))
        osc = SimpleNamespace(send_message=lambda a, v: ns.osc.append((a, v)))
        ns.chatbox = ChatboxSender(osc, ChatboxSettings())

        def make_pipeline(side, target, settings, chatbox, voice_sink, emit):
            p = FakePipeline(side, target)
            ns.pipelines.append(p)
            return p

        def make_voice(device, settings):
            v = FakeVoice(device)
            ns.voices.append(v)
            return v

        async def fake_sleep(delay):
            ns.slept.append(delay)

        devices = {"input": [], "loopback": [],
                   "output": [DeviceInfo(i, n, "output", i == 0, 48000, 2) for i, n in enumerate(outputs)]}
        deps = ControllerDeps(store=ns.store, keys=keys, emit=ns.events.append, make_pipeline=make_pipeline,
                              make_chatbox=lambda s: ns.chatbox, make_voice=make_voice,
                              make_translator=lambda k, s: ns.translator, list_devices=lambda refresh=False: devices,
                              validate_key=AsyncMock(return_value=(True, None)), os_locale=os_locale,
                              sleep=fake_sleep)
        ns.deps = deps
        return Controller(deps), ns

    return make


async def test_first_run_defaults_from_locale(ctl_factory):
    c, deps = ctl_factory(os_locale="zh_TW")
    s = c.snapshot()
    assert (s["ui_language"], s["source_lang"], s["target_lang"], s["theirs_target"]) == ("zh-Hant", "zh-Hant", "en", "zh-Hant")
    assert deps.store.load()[0].ui.source_lang == "zh-Hant"


async def test_start_requires_key(ctl_factory):
    c, _ = ctl_factory(key=None)
    assert await c.start() == {"ok": False, "error": "errors.no_api_key"}


async def test_both_starts_mine_then_theirs_with_stagger(ctl_factory):
    c, deps = ctl_factory()
    await c.set_direction("both")
    await c.start()
    assert [(p.side, p.target) for p in deps.pipelines] == [("mine", "en"), ("theirs", "zh-Hant")]
    assert deps.slept == [0.3] and c.snapshot()["running"]


async def test_language_change_restarts_only_affected(ctl_factory):
    c, deps = ctl_factory()
    await c.set_direction("both")
    await c.start()
    mine, theirs = deps.pipelines
    await c.set_languages("zh-Hant", "ja")
    assert mine.stopped and not theirs.stopped and deps.pipelines[-1].side == "mine" and deps.pipelines[-1].target == "ja"


async def test_rapid_start_stop_start_leaves_one_pipeline(ctl_factory):
    c, deps = ctl_factory()
    await asyncio.gather(c.start(), c.stop(), c.start(), c.set_languages("zh-Hant", "ko"))
    live = [p for p in deps.pipelines if not p.stopped]
    assert len(live) == 1 and live[0].target == "ko"


async def test_voice_without_cable(ctl_factory):
    c, deps = ctl_factory(outputs=["Speakers"])
    assert await c.set_output("voice", True) == {"ok": False, "error": "errors.no_virtual_cable"}
    assert c.snapshot()["outputs"]["voice"] is False and StatusEvent("error", "errors.no_virtual_cable") in deps.events


async def test_voice_toggle_while_running(ctl_factory):
    c, deps = ctl_factory(outputs=["Speakers", "CABLE Input (VB-Audio)"])
    await c.start()
    assert (await c.set_output("voice", True))["ok"] and deps.voices[-1].started
    assert deps.voices[-1].device.name == "CABLE Input (VB-Audio)"
    await c.set_output("voice", False)
    assert deps.voices[-1].stopped and len(deps.pipelines) == 1


async def test_send_text_rules(ctl_factory):
    c, deps = ctl_factory()
    assert await c.send_text("   ") == {"ok": False, "error": "errors.empty_text"}
    assert await c.send_text("hi") == {"ok": False, "error": "errors.not_running"}
    await c.start()
    assert (await c.send_text(" 你好 "))["ok"] and deps.translator.translate.await_args.args == ("你好", "en")
    msg = [e for e in deps.events if isinstance(e, MessageEvent)][-1]
    assert (msg.side, msg.source, msg.translation, msg.final) == ("mine", "你好", "Hello", True)
    assert deps.translator.translate.await_count == 1
    await c.set_direction("theirs")
    assert await c.send_text("hi") == {"ok": False, "error": "errors.direction_theirs"}


async def test_choices_persist(ctl_factory):
    c, deps = ctl_factory()
    await c.set_direction("both")
    await c.set_output("chatbox", False)
    s = deps.store.load()[0]
    assert s.ui.direction == "both" and s.ui.chatbox is False and deps.chatbox.enabled is False


async def test_bad_arguments(ctl_factory):
    c, _ = ctl_factory()
    assert await c.set_direction("sideways") == {"ok": False, "error": "errors.bad_argument"}
    assert await c.set_languages("xx", "en") == {"ok": False, "error": "errors.bad_argument"}
    assert await c.set_languages("en", "auto") == {"ok": False, "error": "errors.bad_argument"}


async def test_shutdown_stops_everything_quickly(ctl_factory):
    c, deps = ctl_factory(outputs=["CABLE Input (VB-Audio)"])
    await c.set_direction("both")
    await c.set_output("voice", True)
    await c.start()
    await asyncio.wait_for(c.shutdown(), 3.0)
    assert all(p.stopped for p in deps.pipelines) and deps.voices[-1].stopped


async def test_turn_finished_updates_stats(ctl_factory):
    c, deps = ctl_factory()
    await c.start()
    c.handle_event(TurnFinished("mine", 612))
    assert deps.events[-1] == StatsEvent(True, 1, 612)


async def test_transcripts_not_logged_by_default(ctl_factory, caplog):
    c, _ = ctl_factory()
    caplog.set_level(logging.DEBUG)
    c.handle_event(MessageEvent("m1", "mine", "秘密", "secret", True, "t"))
    assert "secret" not in caplog.text and "秘密" not in caplog.text


async def test_api_key_flow(ctl_factory):
    c, deps = ctl_factory(key=None)
    deps.deps.validate_key.return_value = (False, "errors.auth")
    assert await c.set_api_key("bad") == {"ok": False, "error": "errors.auth"}
    deps.deps.validate_key.return_value = (True, None)
    assert (await c.set_api_key(" AIzaGoodKey9876 \n"))["ok"]
    assert c.snapshot()["api_key"] == {"present": True, "masked": "AIza…9876"}
    await c.clear_api_key()
    assert c.snapshot()["api_key"]["present"] is False


async def test_list_devices_and_set_device(ctl_factory):
    c, deps = ctl_factory(outputs=["Speakers", "CABLE Input"])
    assert await c.list_devices() == {"ok": True, "inputs": [], "loopbacks": [], "outputs": ["Speakers", "CABLE Input"]}
    await c.start()
    await c.set_device("mic", "Headset Mic")
    assert deps.pipelines[0].stopped and deps.store.load()[0].devices.mic == "Headset Mic" and len(deps.pipelines) == 2


class SlowPipeline(FakePipeline):
    async def stop(self):
        await asyncio.sleep(0.3)
        await super().stop()


async def test_sides_stop_concurrently(ctl_factory):
    c, deps = ctl_factory()
    deps.deps.make_pipeline = lambda side, target, settings, chatbox, voice_sink, emit: deps.pipelines.append(
        SlowPipeline(side, target)) or deps.pipelines[-1]
    await c.set_direction("both")
    await c.start()
    loop = asyncio.get_running_loop()
    started = loop.time()
    await c.stop()
    assert loop.time() - started < 0.5


async def test_stop_clears_chatbox_typing(ctl_factory):
    c, deps = ctl_factory()
    await c.start()
    deps.chatbox.set_typing(True)
    await c.stop()
    assert deps.osc[-1] == ("/chatbox/typing", False)


async def test_debug_transcripts_are_logged_when_enabled(ctl_factory, caplog):
    c, deps = ctl_factory()
    c._settings.logging.debug_transcripts = True
    caplog.set_level(logging.INFO)
    c.handle_event(MessageEvent("m1", "mine", "你好", "hello", True, "t"))
    assert "hello" in caplog.text


async def test_device_list_refreshes_only_when_idle(ctl_factory):
    c, deps = ctl_factory()
    seen = []
    base = deps.deps.list_devices
    deps.deps.list_devices = lambda refresh=False: seen.append(refresh) or base()
    await c.list_devices()
    await c.start()
    await c.list_devices()
    assert seen == [True, False]
