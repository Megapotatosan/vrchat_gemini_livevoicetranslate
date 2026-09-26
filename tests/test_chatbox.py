from types import SimpleNamespace

import pytest

from livetranslate.events import MessageEvent
from livetranslate.outputs.chatbox import ChatboxSender, fit_in_progress, split_final
from livetranslate.settings import ChatboxSettings


def ev(tr, final=False, id="m1"):
    return MessageEvent(id, "mine", "src", tr, final, "t")


@pytest.fixture
def cb(clock):
    osc = SimpleNamespace(sent=[])
    osc.send_message = lambda a, v: osc.sent.append((a, v))
    return ChatboxSender(osc, ChatboxSettings(), now=clock), osc


def test_first_immediate_then_every_2s(cb, clock):
    s, osc = cb
    s.update(ev("Hello"))
    s.poll()
    clock.advance(0.5)
    s.update(ev("Hello there"))
    s.poll()
    assert osc.sent == [("/chatbox/input", ["Hello", True, False])]
    clock.advance(1.5)
    s.poll()
    assert osc.sent[-1] == ("/chatbox/input", ["Hello there", True, False])


def test_final_always_sent_with_sound_then_typing_off(cb, clock):
    s, osc = cb
    s.update(ev("Hi"))
    s.poll()
    s.update(ev("Hi all.", True))
    clock.advance(0.4)
    s.poll()
    assert osc.sent[-2:] == [("/chatbox/input", ["Hi all.", True, True]), ("/chatbox/typing", False)]


def test_bucket_limits_and_never_drops_finals(cb, clock):
    s, osc = cb
    for i in range(6):
        s.send_final_text(f"m{i}")
    times = []
    for _ in range(60):
        n = len(osc.sent)
        s.poll()
        if any(a == "/chatbox/input" for a, _ in osc.sent[n:]):
            times.append(round(clock(), 1))
        clock.advance(0.1)
    assert times == [0.0, 0.4, 0.8, 1.2, 1.6, 5.0]


def test_long_monologue_stays_within_limits(cb, clock):
    s, osc = cb
    for i in range(1, 21):
        s.update(ev("word " * 20 * i))
        clock.advance(2.0)
        s.poll()
    s.update(ev("word " * 400, True))
    for _ in range(40):
        s.poll()
        clock.advance(1)
    inputs = [v for a, v in osc.sent if a == "/chatbox/input"]
    assert all(len(v[0]) <= 144 for v in inputs) and inputs[-1][2] is True


def test_empty_in_progress_ignored(cb):
    s, osc = cb
    s.update(ev(""))
    s.poll()
    assert osc.sent == []


def test_typing_indicator(cb):
    s, osc = cb
    s.set_typing(True)
    assert osc.sent == [("/chatbox/typing", True)]


def test_fit_and_split():
    t = fit_in_progress("x" * 200)
    assert len(t) == 144 and t.startswith("…") and t.endswith("x")
    en = "This is sentence number one. " * 10
    parts = split_final(en)
    assert all(len(p) <= 144 for p in parts) and " ".join(parts) == en.strip()
    zh = "今天天氣很好。" * 30
    assert all(p.endswith("。") and len(p) <= 144 for p in split_final(zh))
    assert [len(p) for p in split_final("字" * 300)] == [144, 144, 12]


def test_fit_limits_lines():
    t = fit_in_progress("\n".join(f"l{i}" for i in range(12)))
    assert t.count("\n") <= 8 and t.startswith("…") and t.endswith("l11")


def test_disabled_sends_nothing(cb):
    s, osc = cb
    s.enabled = False
    s.update(ev("Hi", True))
    s.poll()
    assert osc.sent == []
