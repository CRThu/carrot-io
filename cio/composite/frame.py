"""
Generic Frame Transport Bridge (AsyncFrameBridge).
"""
from __future__ import annotations

import asyncio
from typing import Any

from cio.core.base import AsyncBaseTransport
from cio.core.exceptions import ReadTimeoutError, TransportError
from cio.core.frame import FrameCodec, HardwareFrame, STATUS_OK


class AsyncFrameBridge(AsyncBaseTransport):
    """
    Generic Frame Transport Bridge.
    Wraps an underlying AsyncBaseTransport and provides frame send/receive interfaces.
    """

    def __init__(
        self,
        transport: AsyncBaseTransport,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout)
        self.transport = transport
        self.codec = FrameCodec()
        self._recv_buffer = bytearray()

    @property
    def is_open(self) -> bool:
        return self.transport.is_open

    async def open(self) -> None:
        if not self.transport.is_open:
            await self.transport.open()
        self._is_open = True

    async def close(self) -> None:
        self._is_open = False
        if self.transport.is_open:
            await self.transport.close()

    async def _write_impl(self, data: bytes) -> int:
        return await self.transport.write(data)

    async def _read_impl(self, nbytes: int) -> bytes:
        return await self.transport.read(nbytes)

    async def send_frame(self, frame: HardwareFrame, timeout: float | None = None) -> None:
        """
        Encode and transmit a HardwareFrame over underlying transport.
        """
        if not self.is_open:
            await self.open()
        raw = self.codec.encode(frame)
        await self.transport.write(raw, timeout=timeout)

    async def recv_frame(self, timeout: float | None = None) -> HardwareFrame:
        """
        Receive and decode a single HardwareFrame from underlying transport.
        """
        if not self.is_open:
            await self.open()

        eff_timeout = timeout if timeout is not None else self.timeout
        start_time = asyncio.get_event_loop().time()

        while True:
            # Check existing recv buffer
            frame, consumed = self.codec.decode(self._recv_buffer)
            if consumed > 0:
                del self._recv_buffer[:consumed]
            if frame is not None:
                return frame

            # Calculate remaining time
            if eff_timeout is not None:
                elapsed = asyncio.get_event_loop().time() - start_time
                remaining = eff_timeout - elapsed
                if remaining <= 0:
                    raise ReadTimeoutError(f"HardwareFrame decode timed out after {eff_timeout}s")
            else:
                remaining = None

            chunk = await self.transport.read(4096, timeout=remaining)
            if not chunk:
                if eff_timeout is not None and (asyncio.get_event_loop().time() - start_time) >= eff_timeout:
                    raise ReadTimeoutError("HardwareFrame read timed out")
                await asyncio.sleep(0.001)
                continue

            self._recv_buffer.extend(chunk)

    async def request_frame(self, frame: HardwareFrame, timeout: float | None = None) -> HardwareFrame:
        """
        Send a request frame and await its response frame with status checking.
        """
        async with self._write_lock:
            await self.send_frame(frame, timeout=timeout)
        async with self._read_lock:
            resp = await self.recv_frame(timeout=timeout)
            if resp.status != STATUS_OK:
                raise TransportError(f"Hardware frame request returned error status: 0x{resp.status:02X}")
            return resp
