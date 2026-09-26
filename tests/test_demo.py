import asyncio

from livetranslate.demo import DemoController
from livetranslate.events import MessageEvent


async def test_demo_emits_scripted_bubbles():
    events = []
    d = DemoController(events.append, step_s=0.001)
    assert (await d.start())["ok"] and d.snapshot()["running"]
    await asyncio.sleep(0.3)
    finals = [e for e in events if isinstance(e, MessageEvent) and e.final]
    assert len(finals) == 4 and {e.side for e in finals} == {"mine", "theirs"}
