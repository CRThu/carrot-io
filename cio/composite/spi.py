"""
SPI Protocol Bridge (AsyncSpiBridge) using Hardware Frame Protocol.
"""
from __future__ import annotations

from typing import Any

from cio.composite.frame import AsyncFrameBridge
from cio.core.base import AsyncBaseTransport
from cio.core.frame import (
    ACTION_CFG,
    ACTION_TRANSFER,
    CFG_SPI_BIT_ORDER,
    CFG_SPI_MODE,
    CFG_SPI_SPEED,
    PERIPHERAL_SPI,
    HardwareFrame,
)
from cio.core.gpio import AsyncGpioPin
from cio.core.spi import AsyncSpiTransport


class AsyncSpiBridge(AsyncSpiTransport):
    """
    SPI Bus Master Bridge implementing Hardware Frame Protocol over any transport.
    """

    def __init__(
        self,
        transport: AsyncBaseTransport | AsyncFrameBridge,
        cs_pin: AsyncGpioPin | None = None,
        bus: int = 0,
        cs: int = 0,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout)
        if isinstance(transport, AsyncFrameBridge):
            self._bridge = transport
        else:
            self._bridge = AsyncFrameBridge(transport, timeout=timeout, **kwargs)
        self.bus = bus
        self.cs = cs
        self.cs_pin = cs_pin

    @property
    def bridge(self) -> AsyncFrameBridge:
        return self._bridge

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
        return await self._bridge._write_impl(data)

    async def _read_impl(self, nbytes: int) -> bytes:
        return await self._bridge._read_impl(nbytes)

    async def transfer(self, tx_data: bytes, timeout: float | None = None) -> bytes:
        if not self.is_open:
            await self.open()

        if self.cs_pin:
            await self.cs_pin.set_low()

        try:
            frame = HardwareFrame(
                peripheral=PERIPHERAL_SPI,
                action=ACTION_TRANSFER,
                bus=self.cs if self.cs is not None else self.bus,
                payload=tx_data,
            )
            resp = await self._bridge.request_frame(frame, timeout=timeout)
            return resp.payload
        finally:
            if self.cs_pin:
                await self.cs_pin.set_high()

    async def config_mode(self, mode: int) -> None:
        """
        Configure SPI Mode (0..3).
        """
        payload = bytes([CFG_SPI_MODE, mode & 0xFF])
        frame = HardwareFrame(
            peripheral=PERIPHERAL_SPI,
            action=ACTION_CFG,
            bus=self.bus,
            payload=payload,
        )
        await self._bridge.request_frame(frame)

    async def config_bit_order(self, order: int) -> None:
        """
        Configure SPI Bit Order: 0 (MSB First), 1 (LSB First).
        """
        payload = bytes([CFG_SPI_BIT_ORDER, order & 0xFF])
        frame = HardwareFrame(
            peripheral=PERIPHERAL_SPI,
            action=ACTION_CFG,
            bus=self.bus,
            payload=payload,
        )
        await self._bridge.request_frame(frame)

    async def config_speed(self, speed_hz: int) -> None:
        """
        Configure SPI Speed in Hz.
        """
        payload = bytes([CFG_SPI_SPEED]) + speed_hz.to_bytes(4, byteorder="big")
        frame = HardwareFrame(
            peripheral=PERIPHERAL_SPI,
            action=ACTION_CFG,
            bus=self.bus,
            payload=payload,
        )
        await self._bridge.request_frame(frame)
