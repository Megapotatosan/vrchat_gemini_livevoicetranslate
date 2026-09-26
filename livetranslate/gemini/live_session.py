"""One Gemini Live translation session per direction, kept alive across drops and server hand-overs."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from typing import Any, Literal, Protocol

from google.genai import errors, types

from livetranslate.events import StatusEvent
from livetranslate.gemini.budget import Backoff, ConnectionBudget
from livetranslate.gemini.turns import TurnAssembler

log = logging.getLogger(__name__)

AUDIO_MIME = "audio/pcm;rate=16000"
ErrorKind = Literal["auth", "quota", "model", "network"]


class LiveConnection(Protocol):
    async def send_realtime_input(self, **kwargs: Any) -> None: ...

    def receive(self) -> AsyncIterator[types.LiveServerMessage]: ...


ConnectFn = Callable[[str, types.LiveConnectConfig], AbstractAsyncContextManager[LiveConnection]]


def gemini_connect(api_key: str) -> ConnectFn:
    from google import genai

    client = genai.Client(api_key=api_key)

    def connect(model: str, config: types.LiveConnectConfig) -> AbstractAsyncContextManager[LiveConnection]:
        return client.aio.live.connect(model=model, config=config)

    return connect


def build_config(target_code: str, handle: str | None) -> types.LiveConnectConfig:
    return types.LiveConnectConfig(
        response_modalities=[types.Modality.AUDIO],
        translation_config=types.TranslationConfig(target_language_code=target_code, echo_target_language=False),
        input_audio_transcription=types.AudioTranscriptionConfig(),
        output_audio_transcription=types.AudioTranscriptionConfig(),
        session_resumption=types.SessionResumptionConfig(handle=handle),
    )


def classify_error(exc: BaseException) -> ErrorKind:
    if isinstance(exc, errors.APIError) and exc.code < 1000:
        if exc.code in (400, 401, 403):
            return "auth"
        if exc.code == 429:
            return "quota"
        if exc.code == 404:
            return "model"
        return "network"
    try:
        from websockets.exceptions import ConnectionClosed
    except ImportError:  # pragma: no cover - websockets ships with google-genai
        ConnectionClosed = ()  # type: ignore[assignment]  # noqa: N806
    # The SDK reports Live API websocket closes as APIError(close_code, reason); classify by reason.
    if isinstance(exc, (errors.APIError, ConnectionClosed)):
        reason = str(exc).lower()
        if "api key" in reason or "permission" in reason or "unauthenticated" in reason:
            return "auth"
        if "quota" in reason or "exceeded" in reason or "rate limit" in reason:
            return "quota"
        if "not found" in reason or "not supported" in reason:
            return "model"
        if isinstance(exc, errors.APIError) and exc.code == 1007:
            return "auth"
    return "network"


class LiveSession:
    def __init__(self, *, connect: ConnectFn, model: str, target_code: str, turns: TurnAssembler,
                 on_status: Callable[[StatusEvent], None], on_audio: Callable[[str, bytes], None] | None = None,
                 budget: ConnectionBudget | None = None, backoff: Backoff | None = None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        self._connect = connect
        self._model = model
        self._target = target_code
        self._turns = turns
        self._on_status = on_status
        self._on_audio = on_audio
        self._budget = budget or ConnectionBudget()
        self._backoff = backoff or Backoff()
        self._sleep = sleep
        self._conn: LiveConnection | None = None
        self._connected = asyncio.Event()
        self._stopping = asyncio.Event()
        self._tasks: set[asyncio.Task] = set()
        self._audio_turn = 0
        self._bubbles_seen = 0
        self._recovering = False
        self.handle: str | None = None

    @property
    def connected(self) -> bool:
        return self._conn is not None and self._connected.is_set()

    # ---- lifecycle -------------------------------------------------------------------------------

    async def run(self) -> None:
        """Connect, receive and reconnect until stop() or a fatal error."""
        while not self._stopping.is_set():
            wait = self._budget.wait_time()
            if wait > 0 and not await self._sleep_or_stop(wait):
                break
            self._budget.record()
            task = self._spawn(self._connection(self.handle, asyncio.Event()))
            try:
                while True:
                    result = await task
                    if isinstance(result, asyncio.Task):  # go_away hand-over: follow the new connection
                        task = result
                        continue
                    break
                if self._stopping.is_set():
                    break
                raise ConnectionError("connection closed by server")
            except asyncio.CancelledError:
                if self._stopping.is_set():
                    break
                raise
            except Exception as exc:  # noqa: BLE001 - every failure is classified and reported
                if not await self._handle_error(exc):
                    break

    async def stop(self, timeout_s: float = 0.5) -> None:
        """Stop promptly; a close handshake that hangs (half-open connection) is abandoned after timeout_s."""
        self._stopping.set()
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait(tasks, timeout=timeout_s)

    # ---- audio in --------------------------------------------------------------------------------

    async def send_audio(self, frame: bytes) -> None:
        await self._send(audio=types.Blob(data=frame, mime_type=AUDIO_MIME))

    async def end_audio(self) -> None:
        await self._send(audio_stream_end=True)

    async def _send(self, **kwargs: Any) -> None:
        if not await self._wait_connected():
            return
        try:
            await self._conn.send_realtime_input(**kwargs)
        except Exception as exc:  # noqa: BLE001 - the receive side reports and reconnects
            log.debug("send failed: %s", exc)

    async def _wait_connected(self) -> bool:
        while not self.connected:
            if self._stopping.is_set():
                return False
            waiters = [asyncio.ensure_future(self._connected.wait()), asyncio.ensure_future(self._stopping.wait())]
            try:
                await asyncio.wait(waiters, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for w in waiters:
                    w.cancel()
        return True

    # ---- internals -------------------------------------------------------------------------------

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.ensure_future(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _sleep_or_stop(self, delay: float) -> bool:
        """Sleep for delay; returns False if stop() was called meanwhile."""
        sleeper = self._spawn(self._sleep(delay))
        stopper = asyncio.ensure_future(self._stopping.wait())
        try:
            await asyncio.wait([sleeper, stopper], return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            pass
        finally:
            sleeper.cancel()
            stopper.cancel()
        return not self._stopping.is_set()

    async def _handle_error(self, exc: BaseException) -> bool:
        """Report the error; returns True when the session should retry."""
        kind = classify_error(exc)
        log.warning("gemini session error (%s): %s", kind, exc)
        if kind == "auth":
            self._on_status(StatusEvent("error", "errors.auth", {}))
            return False
        if kind == "model":
            self._on_status(StatusEvent("error", "errors.model_unavailable", {"model": self._model}))
            return False
        self._recovering = True
        delay = self._backoff.next_delay()
        if kind == "quota":
            self._on_status(StatusEvent("warn", "status.quota_retry", {"seconds": delay}))
        else:
            self._on_status(StatusEvent("warn", "status.reconnecting", {"attempt": self._backoff.attempt}))
        return await self._sleep_or_stop(delay)

    async def _connection(self, handle: str | None, ready: asyncio.Event) -> asyncio.Task | None:
        """Own one connection. Returns the replacement task after a go_away hand-over, else None."""
        async with self._connect(self._model, build_config(self._target, handle)) as conn:
            self._conn = conn
            self._connected.set()
            ready.set()
            if self._recovering:
                self._recovering = False
                self._on_status(StatusEvent("info", "status.reconnected", {}))
            self._backoff.mark_connected()
            try:
                if not await self._receive(conn):
                    return None
                next_ready = asyncio.Event()
                successor = self._spawn(self._connection(self.handle, next_ready))
                waiter = asyncio.ensure_future(next_ready.wait())
                try:
                    await asyncio.wait([waiter, successor], return_when=asyncio.FIRST_COMPLETED)
                finally:
                    waiter.cancel()
                return successor
            finally:
                if self._conn is conn:
                    self._conn = None
                    self._connected.clear()
                    self._backoff.mark_disconnected()

    async def _receive(self, conn: LiveConnection) -> bool:
        """Dispatch server messages. Returns True when the server asked us to move (go_away)."""
        while True:
            async for msg in conn.receive():
                if self._dispatch(msg):
                    return True

    def _dispatch(self, msg: types.LiveServerMessage) -> bool:
        sc = msg.server_content
        if sc is not None:
            if sc.input_transcription and sc.input_transcription.text:
                self._turns.add_source(sc.input_transcription.text)
            if sc.output_transcription and sc.output_transcription.text:
                self._turns.add_translation(sc.output_transcription.text)
            if self._turns.count != self._bubbles_seen:
                # A bubble ended (turn_complete or the silence fallback): later audio is a new sentence.
                self._bubbles_seen = self._turns.count
                self._audio_turn += 1
            if sc.model_turn and sc.model_turn.parts and self._on_audio is not None:
                for part in sc.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        self._on_audio(f"a{self._audio_turn}", part.inline_data.data)
            if sc.turn_complete:
                self._turns.finalise()
        upd = msg.session_resumption_update
        if upd is not None and upd.resumable and upd.new_handle:
            self.handle = upd.new_handle
        return msg.go_away is not None
