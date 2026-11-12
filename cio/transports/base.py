"""
Base Transport Abstraction (AsyncBaseTransport and SyncTransportWrapper).
"""
from __future__ import annotations

import abc
import asyncio
import inspect
import threading
from typing import TYPE_CHECKING, Any

from cio.converters import BytesLike, ensure_bytes
from cio.exceptions import ReadTimeoutError, UnsupportedCapabilityError, WriteTimeoutError
from cio.trace.trace import ShowController, TraceController, TraceEntry

if TYPE_CHECKING:
    from cio.protocols.codec import BaseCodec
    from cio.protocols.protocol import ProtocolTransport


class SyncTransportWrapper:
    """
    Universal synchronous wrapper allowing non-async usage of any async target.
    """

    def __init__(
        self,
        async_target: Any,
        loop: asyncio.AbstractEventLoop | None = None,
    ) -> None:
        self._async = async_target
        self._loop: asyncio.AbstractEventLoop | None = loop
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._owns_loop = loop is None

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
                self._thread.start()
                self._owns_loop = True
            return self._loop

    def _run_sync(self, coro: Any) -> Any:
        loop = self._get_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()

    def open(self) -> None:
        return self._run_sync(self._async.open())

    def close(self) -> None:
        try:
            if self._async.is_open:
                self._run_sync(self._async.close())
        finally:
            if self._owns_loop and self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
                if self._thread:
                    self._thread.join(timeout=1.0)
                try:
                    for task in asyncio.all_tasks(self._loop):
                        task.cancel()
                except Exception:
                    pass
                self._loop.close()
                self._loop = None
                self._thread = None

    @property
    def capabilities(self) -> frozenset[str]:
        return self._async.capabilities

    @property
    def is_open(self) -> bool:
        return self._async.is_open

    @property
    def trace(self) -> TraceController:
        return self._async.trace

    @trace.setter
    def trace(self, value: bool | TraceController) -> None:
        self._async.trace = value

    def history(self, limit: int = 100) -> list[TraceEntry]:
        return self._async.history(limit=limit)

    def dump_history(
        self,
        limit: int = 20,
        color: bool | None = None,
        max_bytes: int | None = None,
    ) -> str:
        return self._async.dump_history(
            limit=limit,
            color=color,
            max_bytes=max_bytes,
        )

    def clear_history(self) -> None:
        self._async.clear_history()

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._async, name)
        if callable(attr):
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                res = attr(*args, **kwargs)
                if inspect.isawaitable(res):
                    return self._run_sync(res)
                if hasattr(res, "sync"):
                    return res.sync
                return res

            # Fast-path caching: bind wrapper to instance __dict__ so subsequent calls bypass __getattr__ entirely
            self.__dict__[name] = wrapper
            return wrapper
        return attr

    def __setattr__(self, name: str, value: Any) -> None:
        if name in ("_async", "_loop", "_thread", "_lock") or name.startswith("_"):
            super().__setattr__(name, value)
        elif hasattr(type(self), name):
            super().__setattr__(name, value)
        elif hasattr(self._async, name):
            setattr(self._async, name, value)
        else:
            super().__setattr__(name, value)

    def __enter__(self) -> SyncTransportWrapper:
        self.open()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()


DEFAULT_TIMEOUT: float = 2.0  # 2.0 秒通用保底超时（工业级防死等熔断）
DEFAULT_BUFFER_SIZE: int = 16 * 1024 * 1024  # 16 MB default byte stream buffer capacity
DEFAULT_PACKET_QUEUE_SIZE: int = 1024  # 1024 帧默认离散报文队列深度（2^10 二进制对齐）


class AsyncBaseTransport(abc.ABC):
    """
    Abstract Base Class for all transport channels.
    Provides lifecycle management, frame packet tracing, and universal synchronous adaptation.
    """

    def __init__(
        self,
        timeout: float | str | None = DEFAULT_TIMEOUT,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        trace: bool = False,
        max_bytes: int = 64,
    ) -> None:
        self.timeout = float(timeout) if timeout is not None else None
        self.buffer_size = buffer_size
        self._trace = TraceController(
            enabled=trace,
            max_bytes=max_bytes,
        )

        self._is_open = False
        self._sync_wrapper: SyncTransportWrapper | None = None

    @property
    def sync(self) -> SyncTransportWrapper:
        """Universal synchronous wrapper for this transport."""
        if self._sync_wrapper is None:
            self._sync_wrapper = SyncTransportWrapper(self)
        return self._sync_wrapper

    @property
    def capabilities(self) -> frozenset[str]:
        """Set of capabilities natively or logically supported by this transport."""
        return frozenset()

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def trace(self) -> TraceController:
        """TraceController managing streaming trace and display switches."""
        return self._trace

    @trace.setter
    def trace(self, value: bool | TraceController) -> None:
        if isinstance(value, TraceController):
            self._trace = value
        else:
            self._trace.enabled = bool(value)

    @abc.abstractmethod
    async def open(self) -> None:
        """Open/establish physical or network connection."""
        self._is_open = True

    @abc.abstractmethod
    async def close(self) -> None:
        """Close connection and release resources."""
        self._is_open = False

    def history(self, limit: int = 100) -> list[TraceEntry]:
        """Get history trace entries."""
        return self._trace.history(limit=limit)

    def dump_history(
        self,
        limit: int = 20,
        color: bool | None = None,
        max_bytes: int | None = None,
    ) -> str:
        """Get formatted dump of recent TX/RX trace entries."""
        return self._trace.dump(
            limit=limit,
            color=color,
            max_bytes=max_bytes,
        )

    def clear_history(self) -> None:
        """Clear in-memory trace entries in trace controller."""
        self._trace.clear()

    def bind(self, codec: BaseCodec) -> ProtocolTransport:
        """Bind a Codec to return a high-level ProtocolTransport."""
        from cio.protocols.protocol import ProtocolTransport

        return ProtocolTransport(self, codec)

    async def __aenter__(self) -> AsyncBaseTransport:
        await self.open()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def __enter__(self) -> SyncTransportWrapper:
        return self.sync.__enter__()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return self.sync.__exit__(exc_type, exc_val, exc_tb)

    def __getattr__(self, name: str) -> Any:
        if name in ("i2c", "spi", "gpio", "uart", "stream", "packet"):
            caps = sorted(self.capabilities)
            raise UnsupportedCapabilityError(
                f"Transport '{self.__class__.__name__}' does not support '{name}'. "
                f"Supported capabilities: {caps}"
            )
        raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")

