"""
SPI Protocol Bridge (AsyncSpiBridge) using CarrotBridge ASCII Protocol.
"""
from __future__ import annotations

from typing import Any

from cio.composite.carrotbridge import CarrotBridge
from cio.core.base import AsyncBaseTransport
from cio.core.converters import BytesLike, ensure_bytes, parse_hex_bytes, parse_int
from cio.core.gpio import AsyncGpioPin
from cio.core.spi import AsyncSpiTransport


class AsyncSpiBridge(AsyncSpiTransport):
    """
    SPI Bus Master Bridge implementing CarrotBridge ASCII Protocol over any transport.
    """

    def __init__(
        self,
        transport: AsyncBaseTransport | CarrotBridge,
        cs_pin: AsyncGpioPin | None = None,
        bus: int = 0,
        cs: int = 0,
        timeout: float | None = None,
        trace: bool = False,
        borrowed: bool | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout, trace=trace)
        if isinstance(transport, CarrotBridge):
            self._bridge = transport
            self._borrowed = True if borrowed is None else borrowed
        else:
            self._borrowed = False if borrowed is None else borrowed
            self._bridge = CarrotBridge(transport, timeout=timeout, trace=trace, borrowed=self._borrowed, **kwargs)
        self.logger = self._bridge.logger
        self.bus = bus
        self.cs = cs
        self.cs_pin = cs_pin

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
        if not self._borrowed:
            await self._bridge.close()

    async def write(self, data: BytesLike, timeout: float | None = None) -> int:
        if not self.is_open:
            await self.open()


        raw_data = ensure_bytes(data)
        if self.cs_pin:
            await self.cs_pin.set_low()

        try:
            cs_val = self.cs if self.cs is not None else self.bus
            res = await self._bridge.call("SPI.W", cs_val, raw_data, len(raw_data), timeout=timeout)
            return parse_int(res, default=len(raw_data))
        finally:
            if self.cs_pin:
                await self.cs_pin.set_high()

    async def read(self, nbytes: int, timeout: float | None = None) -> bytes:
        if not self.is_open:
            await self.open()

        if self.cs_pin:
            await self.cs_pin.set_low()

        try:
            cs_val = self.cs if self.cs is not None else self.bus
            res = await self._bridge.call("SPI.R", cs_val, nbytes, timeout=timeout)
            return parse_hex_bytes(res, nbytes=nbytes)
        finally:
            if self.cs_pin:
                await self.cs_pin.set_high()

    async def transfer(self, tx_data: BytesLike, timeout: float | None = None) -> bytes:
        if not self.is_open:
            await self.open()

        raw_tx = ensure_bytes(tx_data)
        if self.cs_pin:
            await self.cs_pin.set_low()

        try:
            cs_val = self.cs if self.cs is not None else self.bus
            res = await self._bridge.call("SPI.T", cs_val, raw_tx, len(raw_tx), timeout=timeout)
            return parse_hex_bytes(res, nbytes=len(raw_tx))
        finally:
            if self.cs_pin:
                await self.cs_pin.set_high()

    async def config_mode(self, cpol: int, cpha: int) -> None:
        """
        Configure SPI Mode using CPOL (0/1) and CPHA (0/1).
        """
        await self._bridge.call("SPI.MODE", cpol, cpha)

    async def config_speed(self, speed_hz: int) -> None:
        await self._bridge.call("SPI.SPEED", speed_hz)
