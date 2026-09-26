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
    t.add_translation("A.")
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


def test_sentence_cut_mid_word_is_not_finalised_at_3s(rec, clock):
    # Real case: Gemini held back "語。" until the speaker resumed; the bubble must not close on "日".
    t, msgs, _ = rec
    t.add_source("你現在聽到的其實我在講中文,但是你可以聽到日")
    t.add_translation("今お聞きいただいているのは、実は中国語ですが、日本語")
    clock.advance(5.0)
    t.poll()
    assert not msgs[-1].final
    t.add_source("語。")
    t.add_translation("も聞こえます。")
    assert msgs[-1].source.endswith("聽到日語。") and msgs[-1].translation.endswith("日本語も聞こえます。")
    assert len({m.id for m in msgs}) == 1


def test_finished_sentence_is_finalised_after_3s(rec, clock):
    t, msgs, _ = rec
    t.add_translation("テストします。")
    clock.advance(3.0)
    t.poll()
    assert msgs[-1].final


def test_unfinished_sentence_is_finalised_after_long_silence(rec, clock):
    t, msgs, _ = rec
    t.add_translation("今お聞きいただいているのは")
    clock.advance(7.9)
    t.poll()
    assert not msgs[-1].final
    clock.advance(0.1)
    t.poll()
    assert msgs[-1].final
