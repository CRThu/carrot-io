"""
SPI Bus Protocol Abstraction (AsyncSpiTransport).
"""
from __future__ import annotations

import abc

from cio.core.base import AsyncBaseTransport
from cio.core.converters import BytesLike, ensure_bytes


class AsyncSpiTransport(AsyncBaseTransport):
    """
    Abstract Base Class for SPI bus transports.
    """

    @abc.abstractmethod
    async def transfer(self, tx_data: BytesLike, timeout: float | None = None) -> bytes:
        """Full-duplex transfer over SPI bus."""
        raise NotImplementedError

    async def write(self, data: BytesLike, timeout: float | None = None) -> int:
        """Write data to SPI bus (discards MISO rx data)."""
        raw_data = ensure_bytes(data)
        await self.transfer(raw_data, timeout=timeout)
        return len(raw_data)

    async def read(self, nbytes: int, dummy_byte: int = 0x00, timeout: float | None = None) -> bytes:
        """Read nbytes from SPI bus by clocking dummy bytes."""
        tx_data = bytes([dummy_byte & 0xFF] * nbytes)
        return await self.transfer(tx_data, timeout=timeout)

