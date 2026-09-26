import threading

from livetranslate.events import EventBatcher, MessageEvent, StatsEvent, StatusEvent, to_wire


def test_to_wire_message():
    assert to_wire(MessageEvent("m1", "mine", "你好", "Hi", False, "21:04:12")) == {
        "type": "message", "id": "m1", "side": "mine", "source": "你好", "translation": "Hi",
        "final": False, "time": "21:04:12"}


def test_flush_coalesces():
    sent = []
    b = EventBatcher(sent.append)
    b.emit(MessageEvent("m1", "mine", "a", "A", False, "t"))
    b.emit(StatusEvent("info", "status.running"))
    b.emit(MessageEvent("m1", "mine", "ab", "AB", True, "t"))
    b.emit(StatsEvent(True, 1, 500))
    b.emit(StatsEvent(True, 2, 400))
    b.emit(StatusEvent("warn", "status.reconnecting", {"attempt": 1}))
    b.flush()
    types_ = [e["type"] for e in sent[0]]
    assert types_ == ["message", "status", "stats", "status"]
    assert sent[0][0]["translation"] == "AB" and sent[0][2]["count"] == 2


def test_flush_empty_sends_nothing():
    sent = []
    EventBatcher(sent.append).flush()
    assert sent == []


def test_emit_from_other_thread():
    sent = []
    b = EventBatcher(sent.append)
    t = threading.Thread(target=b.emit, args=(StatsEvent(False, 0, None),))
    t.start()
    t.join()
    b.flush()
    assert sent[0][0]["type"] == "stats"
