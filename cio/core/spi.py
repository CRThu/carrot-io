"""
SPI Bus Protocol Abstraction (AsyncSpiTransport).
"""
from __future__ import annotations

import abc
from cio.core.base import AsyncBaseTransport


class AsyncSpiTransport(AsyncBaseTransport):
    """
    Abstract Base Class for SPI bus transports.
    """

    @abc.abstractmethod
    async def transfer(self, tx_data: bytes, timeout: float | None = None) -> bytes:
        """Full-duplex transfer over SPI bus."""
        raise NotImplementedError
