"""
SPI Protocol Bridge (AsyncSpiBridge) via Dependency Injection.
"""
from __future__ import annotations

from typing import Any

from cio.core.base import AsyncBaseTransport
from cio.core.gpio import AsyncGpioPin
from cio.core.spi import AsyncSpiTransport


class AsyncSpiBridge(AsyncSpiTransport):
    """
    Generalized SPI Bridge wrapping any underlying AsyncBaseTransport pipe.
    """

    def __init__(
        self,
        transport: AsyncBaseTransport,
        cs_pin: AsyncGpioPin | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout)
        self.transport = transport
        self.cs_pin = cs_pin

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

    async def transfer(self, tx_data: bytes, timeout: float | None = None) -> bytes:
        """
        Execute full-duplex SPI transfer over underlying transport.
        """
        if not self.is_open:
            await self.open()

        if self.cs_pin:
            await self.cs_pin.set_low()

        try:
            await self.transport.write(tx_data, timeout=timeout)
            rx_data = await self.transport.read(len(tx_data), timeout=timeout)
            return rx_data
        finally:
            if self.cs_pin:
                await self.cs_pin.set_high()
