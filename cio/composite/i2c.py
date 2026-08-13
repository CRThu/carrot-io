"""
I2C Protocol Bridge (AsyncI2cBridge) using CarrotBridge ASCII Protocol.
"""
from __future__ import annotations

from typing import Any

from cio.composite.carrotbridge import CarrotBridge
from cio.core.base import AsyncBaseTransport
from cio.core.i2c import AsyncI2cTransport


class AsyncI2cBridge(AsyncI2cTransport):
    """
    I2C Bus Master Bridge implementing CarrotBridge ASCII Protocol over any transport.
    """

    def __init__(
        self,
        transport: AsyncBaseTransport | CarrotBridge,
        bus: int = 0,
        reg_len: int = 1,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout, reg_len=reg_len)
        if isinstance(transport, CarrotBridge):
            self._bridge = transport
        else:
            self._bridge = CarrotBridge(transport, timeout=timeout, **kwargs)
        self.bus = bus

    @property
    def bridge(self) -> CarrotBridge:
        return self._bridge

    @property
    def transport(self) -> AsyncBaseTransport:
        return self._bridge._underlying

    @property
    def is_open(self) -> bool:
        return self._bridge.is_open

    async def open(self) -> None:
        await self._bridge.open()
        self._is_open = True

    async def close(self) -> None:
        self._is_open = False
        await self._bridge.close()

    async def _write_impl(self, data: bytes) -> int:
        return await self._bridge.write(data)

    async def _read_impl(self, nbytes: int) -> bytes:
        return await self._bridge.read(nbytes)

    async def read(self, addr: int, nbytes: int, timeout: float | None = None) -> bytes:
        if not self.is_open:
            await self.open()
        addr_str = f"0x{addr:X}"
        res = await self._bridge.call("IIC.R", addr_str, nbytes, timeout=timeout)
        return CarrotBridge.to_bytes(res, nbytes)

    async def write(self, addr: int, data: bytes, timeout: float | None = None) -> int:
        if not self.is_open:
            await self.open()
        addr_str = f"0x{addr:X}"
        await self._bridge.call("IIC.W", addr_str, data, len(data), timeout=timeout)
        return len(data)

    async def config_speed(self, speed_hz: int) -> None:
        await self._bridge.call("IIC.SPEED", speed_hz)
