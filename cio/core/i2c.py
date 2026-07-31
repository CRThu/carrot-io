"""
I2C Bus Protocol Abstraction (AsyncI2cTransport).
"""
from __future__ import annotations

import abc
from cio.core.base import AsyncBaseTransport


class AsyncI2cTransport(AsyncBaseTransport):
    """
    Abstract Base Class for I2C master transports.
    """

    @abc.abstractmethod
    async def read_from(self, addr: int, nbytes: int, timeout: float | None = None) -> bytes:
        """Read nbytes from specified I2C device address."""
        raise NotImplementedError

    @abc.abstractmethod
    async def write_to(self, addr: int, data: bytes, timeout: float | None = None) -> int:
        """Write data to specified I2C device address."""
        raise NotImplementedError

    async def read_reg(
        self,
        addr: int,
        reg: int,
        nbytes: int = 1,
        regfile: int = 0,
        timeout: float | None = None,
    ) -> bytes:
        """Read nbytes from specified device address, regfile, and register."""
        reg_bytes = reg.to_bytes(4, byteorder="big")
        await self.write_to(addr, reg_bytes, timeout=timeout)
        return await self.read_from(addr, nbytes, timeout=timeout)

    async def write_reg(
        self,
        addr: int,
        reg: int,
        data: bytes,
        regfile: int = 0,
        timeout: float | None = None,
    ) -> int:
        """Write data to specified device address, regfile, and register."""
        reg_bytes = reg.to_bytes(4, byteorder="big")
        return await self.write_to(addr, reg_bytes + data, timeout=timeout)

