"""
I2C Protocol Bridge (AsyncI2cBridge) using CarrotBridge ASCII Protocol.
"""
from __future__ import annotations

from typing import Any

from cio.composite.carrotbridge import CarrotBridge
from cio.core.base import AsyncBaseTransport
from cio.core.converters import (
    BytesLike,
    ensure_bytes,
    parse_hex_bytes,
    parse_int,
    parse_int_list,
    to_hex_str,
)
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
        trace: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout, reg_len=reg_len, trace=trace)
        if isinstance(transport, CarrotBridge):
            self._bridge = transport
        else:
            self._bridge = CarrotBridge(transport, timeout=timeout, trace=trace, **kwargs)
        self.logger = self._bridge.logger
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

    async def read(self, addr: int, nbytes: int, timeout: float | None = None) -> bytes:
        if not self.is_open:
            await self.open()
        res = await self._bridge.call("IIC.R", to_hex_str(addr), nbytes, timeout=timeout)
        return parse_hex_bytes(res, nbytes=nbytes)


    async def write(self, addr: int, data: BytesLike, timeout: float | None = None) -> int:
        if not self.is_open:
            await self.open()
        raw_data = ensure_bytes(data)
        res = await self._bridge.call("IIC.W", to_hex_str(addr), raw_data, len(raw_data), timeout=timeout)
        return parse_int(res, default=len(raw_data))

    async def scan(self, timeout: float | None = None) -> list[int]:
        """
        Scan I2C bus for active 7-bit slave device addresses using hardware IIC.SCAN command.
        """
        if not self.is_open:
            await self.open()
        res = await self._bridge.call("IIC.SCAN", timeout=timeout)
        return parse_int_list(res)

    async def config_speed(self, speed_hz: int) -> None:
        await self._bridge.call("IIC.SPEED", speed_hz)
