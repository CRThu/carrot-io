"""
Base Transport Abstraction (AsyncBaseTransport and SyncTransportWrapper).
"""
from __future__ import annotations

import abc
import asyncio
import inspect
import threading
import weakref
from typing import TYPE_CHECKING, Any

from cio.core.converters import BytesLike, ensure_bytes
from cio.core.exceptions import ReadTimeoutError, WriteTimeoutError
from cio.core.logger import IoLogger, LogEntry

if TYPE_CHECKING:
    from cio.core.codec import BaseCodec
    from cio.core.protocol import ProtocolTransport


def _finalize_transport(ref_dict: dict[str, Any]) -> None:
    """Finalizer callback called by weakref when transport is garbage collected."""
    try:
        cleanup_func = ref_dict.get("cleanup")
        if cleanup_func:
            cleanup_func()
    except Exception:
        pass


class SyncTransportWrapper:
    """
    Universal synchronous wrapper allowing non-async usage of any async target.
    """

    def __init__(self, async_target: Any) -> None:
        self._async = async_target
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
                self._thread.start()
            return self._loop

    def _run_sync(self, coro: Any) -> Any:
        loop = self._get_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result()

    def open(self) -> None:
        return self._run_sync(self._async.open())

    def close(self) -> None:
        try:
            if getattr(self._async, "is_open", False):
                self._run_sync(self._async.close())
        finally:
            if self._loop and self._loop.is_running():
                self._loop.call_soon_threadsafe(self._loop.stop)
                if self._thread:
                    self._thread.join(timeout=1.0)
                self._loop.close()
                self._loop = None
                self._thread = None

    @property
    def is_open(self) -> bool:
        return bool(getattr(self._async, "is_open", False))

    @property
    def trace(self) -> bool:
        return bool(getattr(self._async, "trace", False))

    @trace.setter
    def trace(self, value: bool) -> None:
        self._async.trace = value

    def history(self, limit: int = 100) -> list[LogEntry]:
        return self._async.history(limit=limit)

    def dump_history(
        self,
        limit: int = 20,
        color: bool = False,
        show_hex: bool | None = None,
        show_ascii: bool | None = None,
        show_time: bool | None = None,
        show_len: bool | None = None,
        max_bytes: int | None = None,
    ) -> str:
        return self._async.dump_history(
            limit=limit,
            color=color,
            show_hex=show_hex,
            show_ascii=show_ascii,
            show_time=show_time,
            show_len=show_len,
            max_bytes=max_bytes,
        )

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
            setattr(self, name, wrapper)
            return wrapper
        return attr

    def __enter__(self) -> SyncTransportWrapper:
        if hasattr(self._async, "open"):
            self.open()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if hasattr(self._async, "close"):
            self.close()


class AsyncBaseTransport(abc.ABC):
    """
    Abstract Base Class for all transport channels.
    Provides lifecycle management, logging/tracing, and universal synchronous adaptation.
    """

    def __init__(
        self,
        timeout: float | str | None = None,
        buffer_size: int = 1024 * 1024,
        trace: bool = False,
        show_hex: bool = True,
        show_ascii: bool = True,
        show_time: bool = True,
        show_len: bool = True,
        max_bytes: int = 64,
    ) -> None:
        self.timeout = float(timeout) if timeout is not None else None
        self.buffer_size = buffer_size
        self.logger = IoLogger(
            trace=trace,
            show_hex=show_hex,
            show_ascii=show_ascii,
            show_time=show_time,
            show_len=show_len,
            max_bytes=max_bytes,
        )

        self._is_open = False
        self._sync_wrapper: SyncTransportWrapper | None = None

        self._cleanup_dict = {"cleanup": self._sync_cleanup}
        self._finalizer = weakref.finalize(self, _finalize_transport, self._cleanup_dict)

    @property
    def sync(self) -> SyncTransportWrapper:
        """Universal synchronous wrapper for this transport."""
        if self._sync_wrapper is None:
            self._sync_wrapper = SyncTransportWrapper(self)
        return self._sync_wrapper

    def _sync_cleanup(self) -> None:
        """Synchronous cleanup logic called by finalizer."""
        self._is_open = False

    @property
    def is_open(self) -> bool:
        return self._is_open

    @property
    def trace(self) -> bool:
        return self.logger.trace

    @trace.setter
    def trace(self, value: bool) -> None:
        self.logger.trace = bool(value)

    @abc.abstractmethod
    async def open(self) -> None:
        """Open/establish physical or network connection."""
        self._is_open = True

    @abc.abstractmethod
    async def close(self) -> None:
        """Close connection and release resources."""
        self._is_open = False

    def history(self, limit: int = 100) -> list[LogEntry]:
        """Get history log entries."""
        return self.logger.history(limit=limit)

    def dump_history(
        self,
        limit: int = 20,
        color: bool = False,
        show_hex: bool | None = None,
        show_ascii: bool | None = None,
        show_time: bool | None = None,
        show_len: bool | None = None,
        max_bytes: int | None = None,
    ) -> str:
        """Get formatted dump of recent TX/RX log entries."""
        return self.logger.dump(
            limit=limit,
            color=color,
            show_hex=show_hex,
            show_ascii=show_ascii,
            show_time=show_time,
            show_len=show_len,
            max_bytes=max_bytes,
        )

    def bind(self, codec: BaseCodec) -> ProtocolTransport:
        """Bind a Codec to return a high-level ProtocolTransport."""
        from cio.core.protocol import ProtocolTransport

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

