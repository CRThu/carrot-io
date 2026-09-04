"""
Bounded message packet transport abstraction (AsyncPacketTransport).
"""
from __future__ import annotations

import asyncio

from cio.core.base import AsyncBaseTransport
from cio.core.buffer import PacketQueue
from cio.core.converters import BytesLike, ensure_bytes
from cio.core.exceptions import ReadTimeoutError, WriteTimeoutError


class AsyncPacketTransport(AsyncBaseTransport):
    """
    Abstract Base Class for message/packet oriented transports (UDP, CAN, Datagrams).
    """

    def __init__(
        self,
        timeout: float | None = None,
        buffer_size: int = 1000,
        trace: bool = False,
    ) -> None:
        super().__init__(timeout=timeout, buffer_size=buffer_size, trace=trace)
        self.packet_queue = PacketQueue(max_packets=buffer_size)
        self._read_lock: asyncio.Lock | None = None
        self._read_lock_loop: asyncio.AbstractEventLoop | None = None
        self._write_lock: asyncio.Lock | None = None
        self._write_lock_loop: asyncio.AbstractEventLoop | None = None

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"packet"})

    def _get_read_lock(self) -> asyncio.Lock:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._read_lock is None or (self._read_lock_loop is not None and self._read_lock_loop.is_closed()):
            self._read_lock = asyncio.Lock()
            self._read_lock_loop = current_loop
        return self._read_lock

    def _get_write_lock(self) -> asyncio.Lock:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._write_lock is None or (self._write_lock_loop is not None and self._write_lock_loop.is_closed()):
            self._write_lock = asyncio.Lock()
            self._write_lock_loop = current_loop
        return self._write_lock

    def __len__(self) -> int:
        """Return number of packets currently buffered in queue."""
        return len(self.packet_queue)

    async def _read_impl(self) -> bytes:
        """Subclass implementation for receiving a single packet message."""
        raise NotImplementedError(f"{self.__class__.__name__} does not implement packet read")

    async def _write_impl(self, data: bytes) -> int:
        """Subclass implementation for sending a single packet message."""
        raise NotImplementedError(f"{self.__class__.__name__} does not implement packet write")

    async def write(self, data: BytesLike, timeout: float | None = None) -> int:
        """Write a single message packet."""
        if not self._is_open:
            await self.open()

        raw_packet = ensure_bytes(data)
        effective_timeout = timeout if timeout is not None else self.timeout
        async with self._get_write_lock():
            if effective_timeout is not None:
                try:
                    written = await asyncio.wait_for(self._write_impl(raw_packet), timeout=effective_timeout)
                except asyncio.TimeoutError as err:
                    raise WriteTimeoutError(f"Write operation timed out after {effective_timeout}s") from err
            else:
                written = await self._write_impl(raw_packet)

            self.logger.log_out(raw_packet[:written] if written else raw_packet)
            return written

    async def read(self, nbytes: int = -1, timeout: float | None = None) -> bytes:
        """Read a single message packet preserving boundaries."""
        if not self._is_open:
            await self.open()

        effective_timeout = timeout if timeout is not None else self.timeout
        async with self._get_read_lock():
            pkt = self.packet_queue.get()
            if pkt is None:
                if effective_timeout is not None:
                    try:
                        pkt = await asyncio.wait_for(self._read_impl(), timeout=effective_timeout)
                    except asyncio.TimeoutError as err:
                        raise ReadTimeoutError(f"Read operation timed out after {effective_timeout}s") from err
                else:
                    pkt = await self._read_impl()

            data = pkt or b""
            if nbytes > 0 and len(data) > nbytes:
                data = data[:nbytes]
            if data:
                self.logger.log_in(data)
            return data

    async def query(self, cmd: BytesLike, delay: float = 0.0, timeout: float | None = None) -> bytes:
        """Send a packet, wait delay if specified, and read response packet."""
        await self.write(cmd, timeout=timeout)
        if delay > 0:
            await asyncio.sleep(delay)
        return await self.read(timeout=timeout)

    async def flush(self) -> None:
        """Clear internal packet queue."""
        async with self._get_read_lock():
            self.packet_queue.clear()

