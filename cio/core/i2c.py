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

    def __init__(
        self,
        timeout: float | str | None = None,
        buffer_size: int = 1024 * 1024,
        reg_len: int = 1,
    ) -> None:
        super().__init__(timeout=timeout, buffer_size=buffer_size)
        self.default_reg_len = int(reg_len)

    @abc.abstractmethod
    async def read(self, addr: int, nbytes: int, timeout: float | None = None) -> bytes:
        """Read nbytes from specified I2C device address."""
        raise NotImplementedError

    @abc.abstractmethod
    async def write(self, addr: int, data: bytes, timeout: float | None = None) -> int:
        """Write data to specified I2C device address."""
        raise NotImplementedError

    async def read_reg(
        self,
        addr: int,
        reg: int,
        nbytes: int = 1,
        regfile: int = 0,
        reg_len: int | None = None,
        timeout: float | None = None,
    ) -> bytes:
        """Read nbytes from specified device address, regfile, and register."""
        actual_reg_len = reg_len if reg_len is not None else self.default_reg_len
        reg_bytes = reg.to_bytes(actual_reg_len, byteorder="big")
        await self.write(addr, reg_bytes, timeout=timeout)
        return await self.read(addr, nbytes, timeout=timeout)

    async def write_reg(
        self,
        addr: int,
        reg: int,
        data: bytes,
        regfile: int = 0,
        reg_len: int | None = None,
        timeout: float | None = None,
    ) -> int:
        """Write data to specified device address, regfile, and register."""
        actual_reg_len = reg_len if reg_len is not None else self.default_reg_len
        reg_bytes = reg.to_bytes(actual_reg_len, byteorder="big")
        await self.write(addr, reg_bytes + data, timeout=timeout)
        return len(data)
