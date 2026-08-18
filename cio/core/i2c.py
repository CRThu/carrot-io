"""
I2C Bus Protocol Abstraction (AsyncI2cTransport).
"""
from __future__ import annotations

import abc
from typing import Any

from cio.core.base import AsyncBaseTransport
from cio.core.converters import BytesLike, ensure_bytes
from cio.core.exceptions import IOOperationError


class AsyncI2cTransport(AsyncBaseTransport):
    """
    Abstract Base Class for I2C master transports.
    """

    def __init__(
        self,
        timeout: float | str | None = None,
        buffer_size: int = 1024 * 1024,
        reg_len: int = 1,
        trace: bool = False,
    ) -> None:
        super().__init__(timeout=timeout, buffer_size=buffer_size, trace=trace)
        self.default_reg_len = int(reg_len)

    @abc.abstractmethod
    async def read(self, addr: int, nbytes: int, timeout: float | None = None) -> bytes:
        """Read nbytes from specified I2C device address."""
        raise NotImplementedError

    @abc.abstractmethod
    async def write(self, addr: int, data: BytesLike, timeout: float | None = None) -> int:
        """Write data to specified I2C device address."""
        raise NotImplementedError

    async def scan(self, timeout: float | None = None) -> list[int]:
        """Scan I2C bus for active 7-bit slave device addresses."""
        raise NotImplementedError("I2C bus scanning is not supported by this transport")

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
        needed_len = (reg.bit_length() + 7) // 8 or 1
        base_len = reg_len if reg_len is not None else self.default_reg_len
        actual_reg_len = max(base_len, needed_len) if reg_len is None else reg_len
        reg_bytes = reg.to_bytes(actual_reg_len, byteorder="big")
        await self.write(addr, reg_bytes, timeout=timeout)
        return await self.read(addr, nbytes, timeout=timeout)

    async def write_reg(
        self,
        addr: int,
        reg: int,
        data: BytesLike,
        regfile: int = 0,
        reg_len: int | None = None,
        timeout: float | None = None,
        verify: bool = False,
    ) -> int:
        """Write data to specified device address, regfile, and register."""
        needed_len = (reg.bit_length() + 7) // 8 or 1
        base_len = reg_len if reg_len is not None else self.default_reg_len
        actual_reg_len = max(base_len, needed_len) if reg_len is None else reg_len
        reg_bytes = reg.to_bytes(actual_reg_len, byteorder="big")
        raw_data = ensure_bytes(data)
        await self.write(addr, reg_bytes + raw_data, timeout=timeout)

        if verify:
            read_back = await self.read_reg(
                addr=addr,
                reg=reg,
                nbytes=len(raw_data),
                regfile=regfile,
                reg_len=actual_reg_len,
                timeout=timeout,
            )
            if read_back != raw_data:
                raise IOOperationError(
                    f"write_reg verification failed for addr=0x{addr:02X}, reg=0x{reg:04X}: "
                    f"expected {raw_data.hex().upper()}, got {read_back.hex().upper()}"
                )

        return len(raw_data)
