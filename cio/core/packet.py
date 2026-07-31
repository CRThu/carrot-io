"""
Bounded message packet transport abstraction (AsyncPacketTransport).
"""
from __future__ import annotations

import asyncio

from cio.core.base import AsyncBaseTransport
from cio.core.buffer import PacketQueue
from cio.core.exceptions import ReadTimeoutError


class AsyncPacketTransport(AsyncBaseTransport):
    """
    Abstract Base Class for message/packet oriented transports (UDP, USB HID, CAN).
    """

    def __init__(
        self,
        timeout: float | None = None,
        buffer_size: int = 1000,
    ) -> None:
        super().__init__(timeout=timeout, buffer_size=buffer_size)
        self.packet_queue = PacketQueue(max_packets=buffer_size)

    async def _read_packet_impl(self) -> bytes:
        """Subclass implementation for receiving a single packet message."""
        raise NotImplementedError

    async def _write_packet_impl(self, packet: bytes) -> int:
        """Subclass implementation for sending a single packet message."""
        return await self._write_impl(packet)

    async def _read_impl(self, nbytes: int) -> bytes:
        """Fallback read implementation mapping to read_packet."""
        return await self.read_packet()

    async def read_packet(self, timeout: float | None = None) -> bytes:
        """Read a single message packet preserving boundaries."""
        if not self._is_open:
            await self.open()

        pkt = self.packet_queue.get()
        if pkt is not None:
            return pkt

        effective_timeout = timeout if timeout is not None else self.timeout
        async with self._read_lock:
            pkt = self.packet_queue.get()
            if pkt is not None:
                return pkt

            if effective_timeout is not None:
                try:
                    packet = await asyncio.wait_for(self._read_packet_impl(), timeout=effective_timeout)
                except asyncio.TimeoutError as err:
                    raise ReadTimeoutError(f"read_packet timed out after {effective_timeout}s") from err
            else:
                packet = await self._read_packet_impl()

            self.logger.log_in(packet)
            return packet

    async def write_packet(self, packet: bytes, timeout: float | None = None) -> int:
        """Write a single message packet."""
        if not self._is_open:
            await self.open()

        effective_timeout = timeout if timeout is not None else self.timeout
        async with self._write_lock:
            if effective_timeout is not None:
                try:
                    written = await asyncio.wait_for(self._write_packet_impl(packet), timeout=effective_timeout)
                except asyncio.TimeoutError as err:
                    raise ReadTimeoutError(f"write_packet timed out after {effective_timeout}s") from err
            else:
                written = await self._write_packet_impl(packet)

            self.logger.log_out(packet[:written] if written else packet)
            return written

    async def flush(self) -> None:
        """Clear internal packet queue."""
        async with self._read_lock:
            self.packet_queue.clear()
