import pytest

from livetranslate.gemini.budget import Backoff, ConnectionBudget


def test_budget_sliding_window(clock):
    b = ConnectionBudget(4, now=clock)
    for _ in range(4):
        b.record()
        clock.advance(1)
    assert b.wait_time() == pytest.approx(56.0)
    clock.advance(56)
    assert b.wait_time() == 0


def test_budget_allows_when_under_limit(clock):
    b = ConnectionBudget(4, now=clock)
    b.record()
    assert b.wait_time() == 0


def test_backoff_schedule_and_reset(clock):
    b = Backoff(now=clock)
    assert [b.next_delay() for _ in range(5)] == [2, 5, 10, 30, 30] and b.attempt == 5
    b.mark_connected()
    clock.advance(10)
    b.mark_disconnected()
    assert b.next_delay() == 30
    b.mark_connected()
    clock.advance(61)
    b.mark_disconnected()
    assert b.next_delay() == 2 and b.attempt == 1
