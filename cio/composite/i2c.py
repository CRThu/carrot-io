"""
I2C Protocol Bridge (AsyncI2cBridge) using Hardware Frame Protocol.
"""
from __future__ import annotations

from typing import Any

from cio.composite.frame import AsyncFrameBridge
from cio.core.base import AsyncBaseTransport
from cio.core.frame import (
    ACTION_CFG,
    ACTION_READ_DATA,
    ACTION_READ_REG,
    ACTION_WRITE_DATA,
    ACTION_WRITE_REG,
    CFG_I2C_SPEED,
    PERIPHERAL_I2C,
    HardwareFrame,
)

from cio.core.i2c import AsyncI2cTransport


class AsyncI2cBridge(AsyncI2cTransport):
    """
    I2C Bus Master Bridge implementing Hardware Frame Protocol over any transport.
    """

    def __init__(
        self,
        transport: AsyncBaseTransport | AsyncFrameBridge,
        bus: int = 0,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout)
        if isinstance(transport, AsyncFrameBridge):
            self._bridge = transport
        else:
            self._bridge = AsyncFrameBridge(transport, timeout=timeout, **kwargs)
        self.bus = bus

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

    async def read_from(self, addr: int, nbytes: int, timeout: float | None = None) -> bytes:
        if not self.is_open:
            await self.open()
        req_payload = nbytes.to_bytes(2, byteorder="big")
        frame = HardwareFrame(
            peripheral=PERIPHERAL_I2C,
            action=ACTION_READ_DATA,
            bus=self.bus,
            addr=addr,
            payload=req_payload,
        )
        resp = await self._bridge.request_frame(frame, timeout=timeout)
        return resp.payload

    async def write_to(self, addr: int, data: bytes, timeout: float | None = None) -> int:
        if not self.is_open:
            await self.open()
        frame = HardwareFrame(
            peripheral=PERIPHERAL_I2C,
            action=ACTION_WRITE_DATA,
            bus=self.bus,
            addr=addr,
            payload=data,
        )
        resp = await self._bridge.request_frame(frame, timeout=timeout)
        return len(data)

    async def read_reg(
        self,
        addr: int,
        reg: int,
        nbytes: int = 1,
        regfile: int = 0,
        timeout: float | None = None,
    ) -> bytes:
        """
        Read register using Hardware Frame Protocol.
        Payload: [REGFILE (4 Bytes uint32_be), REG_ADDR (4 Bytes uint32_be), READ_LEN (2 Bytes uint16_be)]
        """
        if not self.is_open:
            await self.open()
        regfile_bytes = regfile.to_bytes(4, byteorder="big")
        reg_bytes = reg.to_bytes(4, byteorder="big")
        req_payload = regfile_bytes + reg_bytes + nbytes.to_bytes(2, byteorder="big")
        frame = HardwareFrame(
            peripheral=PERIPHERAL_I2C,
            action=ACTION_READ_REG,
            bus=self.bus,
            addr=addr,
            payload=req_payload,
        )
        resp = await self._bridge.request_frame(frame, timeout=timeout)
        return resp.payload

    async def write_reg(
        self,
        addr: int,
        reg: int,
        data: bytes,
        regfile: int = 0,
        timeout: float | None = None,
    ) -> int:
        """
        Write register using Hardware Frame Protocol.
        Payload: [REGFILE (4 Bytes uint32_be), REG_ADDR (4 Bytes uint32_be), DATA (N Bytes)]
        """
        if not self.is_open:
            await self.open()
        regfile_bytes = regfile.to_bytes(4, byteorder="big")
        reg_bytes = reg.to_bytes(4, byteorder="big")
        frame = HardwareFrame(
            peripheral=PERIPHERAL_I2C,
            action=ACTION_WRITE_REG,
            bus=self.bus,
            addr=addr,
            payload=regfile_bytes + reg_bytes + data,
        )
        resp = await self._bridge.request_frame(frame, timeout=timeout)
        return len(data)


    async def config_speed(self, speed_hz: int) -> None:
        """
        Configure I2C Bus Speed in Hz.
        Payload: [CFG_ITEM_ID (1 Byte), SPEED (4 Bytes uint32_be)]
        """
        payload = bytes([CFG_I2C_SPEED]) + speed_hz.to_bytes(4, byteorder="big")
        frame = HardwareFrame(
            peripheral=PERIPHERAL_I2C,
            action=ACTION_CFG,
            bus=self.bus,
            payload=payload,
        )
        await self._bridge.request_frame(frame)
