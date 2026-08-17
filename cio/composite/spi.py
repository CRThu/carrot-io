"""
SPI Protocol Bridge (AsyncSpiBridge) using CarrotBridge ASCII Protocol.
"""
from __future__ import annotations

from typing import Any

from cio.composite.carrotbridge import CarrotBridge
from cio.core.base import AsyncBaseTransport
from cio.core.gpio import AsyncGpioPin
from cio.core.spi import AsyncSpiTransport
from cio.core.types import BytesLike, ensure_bytes


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
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout, trace=trace)
        if isinstance(transport, CarrotBridge):
            self._bridge = transport
        else:
            self._bridge = CarrotBridge(transport, timeout=timeout, trace=trace, **kwargs)
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
        await self._bridge.close()

    async def _write_impl(self, data: bytes) -> int:
        return await self._bridge.write(data)

    async def _read_impl(self, nbytes: int) -> bytes:
        return await self._bridge.read(nbytes)

    async def write(self, data: BytesLike, timeout: float | None = None) -> int:
        if not self.is_open:
            await self.open()

        raw_data = ensure_bytes(data)
        if self.cs_pin:
            await self.cs_pin.set_low()

        try:
            cs_val = self.cs if self.cs is not None else self.bus
            await self._bridge.call("SPI.W", cs_val, raw_data, len(raw_data), timeout=timeout)
            return len(raw_data)
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
            return CarrotBridge.to_bytes(res, nbytes)
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
            return CarrotBridge.to_bytes(res, len(raw_tx))
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
