import pytest

from livetranslate.events import TurnFinished
from livetranslate.gemini.turns import TurnAssembler


@pytest.fixture
def rec(clock):
    msgs, fin = [], []
    return TurnAssembler("mine", msgs.append, fin.append, now=clock, clock_text=lambda: "21:04:12"), msgs, fin


def test_chunks_update_same_turn(rec):
    t, msgs, _ = rec
    t.add_source("你好")
    t.add_translation("Hello")
    t.add_translation(" there")
    assert {m.id for m in msgs} == {msgs[0].id} and msgs[-1].translation == "Hello there" and not msgs[-1].final
    assert msgs[-1].source == "你好" and msgs[-1].time == "21:04:12"


def test_finalise_and_new_turn(rec):
    t, msgs, fin = rec
    t.add_translation("A")
    t.finalise()
    t.add_translation("B")
    assert msgs[1].final and t.count == 1 and msgs[2].id != msgs[0].id and len(fin) == 1


def test_silence_fallback(rec, clock):
    t, msgs, _ = rec
    t.add_translation("A")
    clock.advance(2.9)
    t.poll()
    assert not msgs[-1].final
    clock.advance(0.1)
    t.poll()
    assert msgs[-1].final


def test_first_text_latency(rec, clock):
    t, _, fin = rec
    clock.advance(10.0)
    t.gate_opened()
    clock.advance(0.612)
    t.add_translation("Hi")
    t.finalise()
    assert fin[0] == TurnFinished("mine", 612)


def test_finalise_without_turn_is_noop(rec):
    t, msgs, fin = rec
    t.finalise()
    t.poll()
    assert msgs == [] and fin == []
