"""
I2C Protocol Bridge (AsyncI2cBridge) via Dependency Injection.
"""
from __future__ import annotations

from typing import Any

from cio.core.base import AsyncBaseTransport
from cio.core.i2c import AsyncI2cTransport


class AsyncI2cBridge(AsyncI2cTransport):
    """
    Generalized I2C Bridge wrapping any underlying AsyncBaseTransport pipe.
    """

    def __init__(
        self,
        transport: AsyncBaseTransport,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout)
        self.transport = transport

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

    async def read_from(self, addr: int, nbytes: int, timeout: float | None = None) -> bytes:
        if not self.is_open:
            await self.open()
        cmd = bytes([addr & 0x7F | 0x80, (nbytes >> 8) & 0xFF, nbytes & 0xFF])
        await self.transport.write(cmd, timeout=timeout)
        return await self.transport.read(nbytes, timeout=timeout)

    async def write_to(self, addr: int, data: bytes, timeout: float | None = None) -> int:
        if not self.is_open:
            await self.open()
        nbytes = len(data)
        cmd = bytes([addr & 0x7F, (nbytes >> 8) & 0xFF, nbytes & 0xFF]) + data
        return await self.transport.write(cmd, timeout=timeout)
