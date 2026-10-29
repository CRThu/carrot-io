"""
Abstract Base Class for hardware buses and controllers (I2C, SPI, GPIO).
Provides unified lifecycle, logging/tracing, capabilities introspection, and synchronous adaptation.
Zero streaming buffer overhead and zero packet codec dependencies.
"""
from __future__ import annotations

import abc
from typing import Any

from cio.trace.logger import IoLogger, LogEntry


class AsyncBaseBus(abc.ABC):
    """
    Abstract Base Class for all hardware buses and controllers (I2C, SPI, GPIO).
    """

    def __init__(
        self,
        timeout: float | str | None = None,
        trace: bool = False,
        **kwargs: Any,
    ) -> None:
        self.timeout = float(timeout) if timeout is not None else None
        self.logger = IoLogger(trace=trace)
        self._is_open = False
        self._sync_wrapper: Any = None

    @property
    def sync(self) -> Any:
        """Universal synchronous wrapper for this bus/controller."""
        from cio.transports.base import SyncTransportWrapper

        if self._sync_wrapper is None:
            self._sync_wrapper = SyncTransportWrapper(self)
        return self._sync_wrapper

    @property
    def capabilities(self) -> frozenset[str]:
        """Set of capabilities natively or logically supported by this bus."""
        return frozenset()

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
        """Open or initialize bus connection."""
        self._is_open = True

    @abc.abstractmethod
    async def close(self) -> None:
        """Close bus and release hardware resources."""
        self._is_open = False

    def history(self, limit: int = 100) -> list[LogEntry]:
        """Get history log entries."""
        return self.logger.history(limit=limit)

    def dump_history(self, **kwargs: Any) -> str:
        """Get formatted dump of recent bus log entries."""
        return self.logger.dump(**kwargs)

    def clear_history(self) -> None:
        """Clear in-memory log entries in logger."""
        self.logger.clear()

    async def __aenter__(self) -> AsyncBaseBus:
        await self.open()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def __enter__(self) -> Any:
        return self.sync.__enter__()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return self.sync.__exit__(exc_type, exc_val, exc_tb)

