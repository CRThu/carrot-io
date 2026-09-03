"""
Unbounded byte stream transport abstraction (AsyncStreamTransport).
"""
from __future__ import annotations

import asyncio
from typing import Any

from cio.core.base import AsyncBaseTransport
from cio.core.buffer import FifoBuffer, OverflowPolicy
from cio.core.converters import BytesLike, ensure_bytes
from cio.core.exceptions import ReadTimeoutError, WriteTimeoutError


class AsyncStreamTransport(AsyncBaseTransport):
    """
    Abstract Base Class for byte-stream oriented transports (TCP, Serial, FTDI UART).
    """

    def __init__(
        self,
        timeout: float | None = None,
        buffer_size: int = 1024 * 1024,
        overflow_policy: OverflowPolicy = OverflowPolicy.DROP_OLDEST,
        trace: bool = False,
    ) -> None:
        super().__init__(timeout=timeout, buffer_size=buffer_size, trace=trace)
        self.fifo = FifoBuffer(max_size=buffer_size, overflow_policy=overflow_policy)
        self._read_lock: asyncio.Lock | None = None
        self._read_lock_loop: asyncio.AbstractEventLoop | None = None
        self._write_lock: asyncio.Lock | None = None
        self._write_lock_loop: asyncio.AbstractEventLoop | None = None

    def _get_read_lock(self) -> asyncio.Lock:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._read_lock is None or self._read_lock_loop != current_loop:
            self._read_lock = asyncio.Lock()
            self._read_lock_loop = current_loop
        return self._read_lock

    def _get_write_lock(self) -> asyncio.Lock:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._write_lock is None or self._write_lock_loop != current_loop:
            self._write_lock = asyncio.Lock()
            self._write_lock_loop = current_loop
        return self._write_lock


    async def _write_impl(self, data: bytes) -> int:
        """Subclass implementation for writing raw bytes."""
        raise NotImplementedError(f"{self.__class__.__name__} does not implement raw byte stream write")

    async def _read_impl(self, nbytes: int) -> bytes:
        """Subclass implementation for reading raw bytes."""
        raise NotImplementedError(f"{self.__class__.__name__} does not implement raw byte stream read")

    async def _fetch_more(self, chunk_size: int = 4096) -> bytes:
        """Internal helper to fetch chunk of data from underlying physical pipe into fifo."""
        raw_data = await self._read_impl(chunk_size)
        if raw_data:
            self.fifo.write(raw_data)
            self.logger.log_in(raw_data)
        return raw_data

    async def write(self, data: BytesLike, timeout: float | None = None) -> int:
        """Write raw bytes concurrency-safely with optional timeout."""
        if not self._is_open:
            await self.open()

        raw_data = ensure_bytes(data)
        effective_timeout = timeout if timeout is not None else self.timeout
        async with self._get_write_lock():
            if effective_timeout is not None:
                try:
                    written = await asyncio.wait_for(self._write_impl(raw_data), timeout=effective_timeout)
                except asyncio.TimeoutError as err:
                    raise WriteTimeoutError(f"Write operation timed out after {effective_timeout}s") from err
            else:
                written = await self._write_impl(raw_data)

            self.logger.log_out(raw_data[:written] if written else raw_data)
            return written

    async def read(self, nbytes: int = -1, timeout: float | None = None) -> bytes:
        """Read available bytes from FifoBuffer or stream."""
        if not self._is_open:
            await self.open()

        async with self._get_read_lock():
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

    async def query(self, cmd: BytesLike, delay: float = 0.0, timeout: float | None = None) -> bytes:
        """Write a command, wait delay if specified, and return response."""
        await self.write(cmd, timeout=timeout)
        if delay > 0:
            await asyncio.sleep(delay)
        return await self.read(-1, timeout=timeout)

    async def read_exact(self, nbytes: int, timeout: float | None = None) -> bytes:
        """Read exactly `nbytes` bytes."""
        if nbytes <= 0:
            return b""

        if not self._is_open:
            await self.open()

        effective_timeout = timeout if timeout is not None else self.timeout
        start_time = asyncio.get_running_loop().time()

        async with self._get_read_lock():
            while len(self.fifo) < nbytes:
                if effective_timeout is not None:
                    elapsed = asyncio.get_running_loop().time() - start_time
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
        start_time = asyncio.get_running_loop().time()

        async with self._get_read_lock():
            while True:
                res = self.fifo.read_until(delimiter)
                if res is not None:
                    return res

                if effective_timeout is not None:
                    elapsed = asyncio.get_running_loop().time() - start_time
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
        async with self._get_read_lock():
            self.fifo.clear()

