"""
Unbounded byte stream transport abstraction (AsyncStreamTransport).
"""
from __future__ import annotations

import asyncio
from typing import Any

from cio.core.base import AsyncBaseTransport
from cio.core.buffer import FifoBuffer, OverflowPolicy
from cio.core.exceptions import ReadTimeoutError


class AsyncStreamTransport(AsyncBaseTransport):
    """
    Abstract Base Class for byte-stream oriented transports (TCP, Serial, FTDI UART).
    """

    def __init__(
        self,
        timeout: float | None = None,
        buffer_size: int = 1024 * 1024,
        overflow_policy: OverflowPolicy = OverflowPolicy.DROP_OLDEST,
    ) -> None:
        super().__init__(timeout=timeout, buffer_size=buffer_size)
        self.fifo = FifoBuffer(max_size=buffer_size, overflow_policy=overflow_policy)

    async def _fetch_more(self, chunk_size: int = 4096) -> bytes:
        """Internal helper to fetch chunk of data from underlying physical pipe into fifo."""
        raw_data = await self._read_impl(chunk_size)
        if raw_data:
            self.fifo.write(raw_data)
            self.logger.log_in(raw_data)
        return raw_data

    async def read(self, nbytes: int = -1, timeout: float | None = None) -> bytes:
        """Read available bytes from FifoBuffer or stream."""
        if not self._is_open:
            await self.open()

        async with self._read_lock:
            if len(self.fifo) > 0:
                return self.fifo.read(nbytes)

            effective_timeout = timeout if timeout is not None else self.timeout
            if effective_timeout is not None:
                try:
                    await asyncio.wait_for(self._fetch_more(), timeout=effective_timeout)
                except asyncio.TimeoutError as err:
                    raise ReadTimeoutError(f"Stream read timed out after {effective_timeout}s") from err
            else:
                await self._fetch_more()

            return self.fifo.read(nbytes)

    async def read_exact(self, nbytes: int, timeout: float | None = None) -> bytes:
        """Read exactly `nbytes` bytes."""
        if nbytes <= 0:
            return b""

        if not self._is_open:
            await self.open()

        effective_timeout = timeout if timeout is not None else self.timeout
        start_time = asyncio.get_event_loop().time()

        async with self._read_lock:
            while len(self.fifo) < nbytes:
                if effective_timeout is not None:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    remaining = effective_timeout - elapsed
                    if remaining <= 0:
                        raise ReadTimeoutError(f"read_exact({nbytes}) timed out after {effective_timeout}s")
                    try:
                        fetched = await asyncio.wait_for(self._fetch_more(), timeout=remaining)
                    except asyncio.TimeoutError as err:
                        raise ReadTimeoutError(f"read_exact({nbytes}) timed out after {effective_timeout}s") from err
                else:
                    fetched = await self._fetch_more()

                if not fetched and len(self.fifo) < nbytes:
                    break

            res = self.fifo.read_exact(nbytes)
            if res is None:
                raise ReadTimeoutError(f"Insufficient bytes read before EOF ({len(self.fifo)}/{nbytes})")
            return res

    async def read_until(self, delimiter: bytes = b"\n", timeout: float | None = None) -> bytes:
        """Read until delimiter is found."""
        if not delimiter:
            raise ValueError("Delimiter must not be empty")

        if not self._is_open:
            await self.open()

        effective_timeout = timeout if timeout is not None else self.timeout
        start_time = asyncio.get_event_loop().time()

        async with self._read_lock:
            while True:
                res = self.fifo.read_until(delimiter)
                if res is not None:
                    return res

                if effective_timeout is not None:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    remaining = effective_timeout - elapsed
                    if remaining <= 0:
                        raise ReadTimeoutError(f"read_until({delimiter!r}) timed out after {effective_timeout}s")
                    try:
                        fetched = await asyncio.wait_for(self._fetch_more(), timeout=remaining)
                    except asyncio.TimeoutError as err:
                        raise ReadTimeoutError(f"read_until({delimiter!r}) timed out after {effective_timeout}s") from err
                else:
                    fetched = await self._fetch_more()

                if not fetched:
                    res = self.fifo.read_until(delimiter)
                    if res is not None:
                        return res
                    raise ReadTimeoutError(f"EOF reached without finding delimiter {delimiter!r}")

    async def flush(self) -> None:
        """Clear internal fifo buffer."""
        async with self._read_lock:
            self.fifo.clear()
