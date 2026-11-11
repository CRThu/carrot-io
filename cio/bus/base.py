"""
Abstract Base Class for hardware buses and controllers (I2C, SPI, GPIO).
Provides unified lifecycle, logging/tracing, capabilities introspection, and synchronous adaptation.
Zero streaming buffer overhead and zero packet codec dependencies.
"""
from __future__ import annotations

import abc
import time
from typing import Any

from cio.transports.base import DEFAULT_TIMEOUT
from cio.trace.trace import ShowController, TraceController, TraceEntry


class BusTransaction:
    """
    Lightweight re-entrant async context manager for hardware bus transactions.
    Automatically manages nesting suppression, exception capture,
    and single-point authoritative trace log emission.
    """

    __slots__ = ("_bus", "op", "addr", "data", "meta")

    def __init__(
        self,
        bus: AsyncBaseBus,
        op: str,
        addr: int | None = None,
        data: bytes = b"",
        **meta: Any,
    ) -> None:
        self._bus = bus
        self.op = op
        self.addr = addr
        self.data = data
        self.meta = meta

    async def __aenter__(self) -> BusTransaction:
        self._bus._suppress_depth += 1
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self._bus._suppress_depth -= 1
        if self._bus._suppress_depth == 0:
            direction = "OUT" if self.op in ("WR", "WRITE", "TX") else "IN"
            entry_meta = {
                "bus": self._bus.bus_type,
                "op": self.op,
                **self.meta,
            }
            if self.addr is not None:
                entry_meta["addr"] = self.addr
            if exc_val is not None:
                entry_meta["error"] = str(exc_val) or exc_val.__class__.__name__

            self._bus.trace.record(
                TraceEntry(
                    timestamp=time.time(),
                    direction=direction,
                    data=self.data,
                    tag=self._bus.bus_tag,
                    meta=entry_meta,
                )
            )


class AsyncBaseBus(abc.ABC):
    """
    Abstract Base Class for all hardware buses and controllers (I2C, SPI, GPIO).
    """

    def __init__(
        self,
        timeout: float | str | None = DEFAULT_TIMEOUT,
        trace: bool = False,
        **kwargs: Any,
    ) -> None:
        self.timeout = float(timeout) if timeout is not None else None
        self._trace = TraceController(enabled=trace)
        self._is_open = False
        self._sync_wrapper: Any = None
        self._suppress_depth = 0

    @property
    def bus_tag(self) -> str:
        """Tag used for trace entries."""
        return "BUS"

    @property
    def bus_type(self) -> str:
        """Bus category identifier."""
        return "base"

    def trace_tx(
        self,
        op: str,
        addr: int | None = None,
        data: bytes = b"",
        **meta: Any,
    ) -> BusTransaction:
        """Create a managed bus transaction context for tracing."""
        return BusTransaction(self, op=op, addr=addr, data=data, **meta)

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
        """Open or initialize bus connection."""
        self._is_open = True

    @abc.abstractmethod
    async def close(self) -> None:
        """Close bus and release hardware resources."""
        self._is_open = False

    def history(self, limit: int = 100) -> list[TraceEntry]:
        """Get history trace entries."""
        return self._trace.history(limit=limit)

    def dump_history(self, **kwargs: Any) -> str:
        """Get formatted dump of recent bus log entries."""
        return self._trace.dump(**kwargs)

    def clear_history(self) -> None:
        """Clear in-memory log entries in trace controller."""
        self._trace.clear()

    async def __aenter__(self) -> AsyncBaseBus:
        await self.open()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def __enter__(self) -> Any:
        return self.sync.__enter__()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return self.sync.__exit__(exc_type, exc_val, exc_tb)

