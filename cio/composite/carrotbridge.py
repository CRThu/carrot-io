"""
CarrotBridge ASCII-based MCU/Hardware Composite Protocol Bridge (CarrotBridge).
Includes derived bus bridges for I2C, SPI, and GPIO.
"""
from __future__ import annotations

import asyncio
from typing import Any, Literal

from cio.transports.base import AsyncBaseTransport, DEFAULT_BUFFER_SIZE, DEFAULT_TIMEOUT
from cio.transports.stream import AsyncStreamTransport
from cio.bus.i2c import AsyncI2cBus
from cio.bus.spi import AsyncSpiBus
from cio.bus.gpio import AsyncGpioBus
from cio.converters import (
    BytesLike,
    ensure_bytes,
    format_arg,
    parse_bool,
    parse_hex_bytes,
    parse_int,
    parse_int_list,
    to_hex_str,
)
from cio.exceptions import ConnectionError, IOOperationError, ReadTimeoutError


class CarrotBridge(AsyncBaseTransport):
    """
    CarrotBridge ASCII-based Remote Hardware Composite Protocol Bridge.
    Proxies MCU hardware function calls over stream transport using ASCII commands and responses.
    """

    def __init__(
        self,
        transport: AsyncBaseTransport,
        timeout: float | None = DEFAULT_TIMEOUT,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        trace: bool = False,
        borrowed: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout, buffer_size=buffer_size, trace=trace)
        self._underlying: AsyncBaseTransport = transport
        self._borrowed = borrowed
        self._transaction_lock: asyncio.Lock | None = None
        self._lock_loop: asyncio.AbstractEventLoop | None = None

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"i2c", "spi", "gpio"})

    def _get_transaction_lock(self) -> asyncio.Lock:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if self._transaction_lock is None or (self._lock_loop is not None and self._lock_loop.is_closed()):
            self._transaction_lock = asyncio.Lock()
            self._lock_loop = current_loop
        return self._transaction_lock

    @property
    def is_open(self) -> bool:
        return self._is_open and self._underlying.is_open

    async def open(self) -> None:
        if self._is_open:
            return
        if not self._underlying.is_open:
            await self._underlying.open()
        self._is_open = True

    async def close(self) -> None:
        if not self._is_open:
            return
        self._is_open = False
        if not self._borrowed and self._underlying.is_open:
            await self._underlying.close()

    def i2c(self, bus: int = 0, reg_len: int = 1, **kwargs: Any) -> Any:
        """Create a derived I2C bridge sharing this physical CarrotBridge connection."""
        return AsyncI2cBridge(self, bus=bus, reg_len=reg_len, borrowed=True, **kwargs)

    def spi(self, bus: int = 0, cs: int = 0, **kwargs: Any) -> Any:
        """Create a derived SPI bridge sharing this physical CarrotBridge connection."""
        return AsyncSpiBridge(self, bus=bus, cs=cs, borrowed=True, **kwargs)

    def gpio(self, pin: int = 0, mode: str = "out", **kwargs: Any) -> Any:
        """Create a derived GPIO pin bridge sharing this physical CarrotBridge connection."""
        return AsyncGpioBridge(self, pin=pin, mode=mode, borrowed=True, **kwargs)

    async def _write_impl(self, data: bytes) -> int:
        return await self._underlying.write(data)

    async def _read_impl(self, nbytes: int) -> bytes:
        return await self._underlying.read(nbytes)

    @staticmethod
    def _parse_return_val(raw_val: str) -> Any:
        if not raw_val:
            return None
        if raw_val.startswith(("0x", "0X")):
            try:
                return int(raw_val, 16)
            except ValueError:
                return raw_val
        try:
            return int(raw_val)
        except ValueError:
            try:
                return float(raw_val)
            except ValueError:
                if raw_val.lower() in ("true", "false"):
                    return raw_val.lower() == "true"
                return raw_val

    async def call(self, func: str, *args: Any, timeout: float | None = None) -> Any:
        """
        Execute an atomic remote function call over CarrotBridge ASCII protocol.
        """
        if not self.is_open:
            await self.open()

        formatted_args = [format_arg(a) for a in args]
        args_str = ", ".join(formatted_args)
        cmd_str = f"{func}({args_str})\n"
        cmd_bytes = cmd_str.encode("utf-8")

        actual_timeout = timeout if timeout is not None else self.timeout

        async with self._get_transaction_lock():
            self.logger.log_out(cmd_bytes, tag="CMD")
            await self._underlying.write(cmd_bytes, timeout=actual_timeout)

            start_time = asyncio.get_running_loop().time()
            while True:
                remaining: float | None = None
                if actual_timeout is not None:
                    elapsed = asyncio.get_running_loop().time() - start_time
                    remaining = actual_timeout - elapsed
                    if remaining <= 0:
                        raise ReadTimeoutError(f"CarrotBridge call '{func}' timed out after {actual_timeout}s")

                try:
                    if isinstance(self._underlying, AsyncStreamTransport):
                        line = await self._underlying.read_until(b"\n", timeout=remaining)
                    else:
                        line = await self._underlying.read(-1, timeout=remaining)
                except (asyncio.TimeoutError, ReadTimeoutError) as err:
                    raise ReadTimeoutError(f"CarrotBridge call '{func}' timed out after {actual_timeout}s") from err

                if not line:
                    raise ReadTimeoutError(f"EOF reached while waiting for response of '{func}'")

                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                if line_str.startswith("[RETURN]:"):
                    self.logger.log_in(line, tag="RETURN")
                    raw_val = line_str[len("[RETURN]:"):].strip()
                    return self._parse_return_val(raw_val)
                elif line_str.startswith("[ERROR]:"):
                    self.logger.log_in(line, tag="ERROR")
                    err_msg = line_str[len("[ERROR]:"):].strip()
                    raise IOOperationError(f"CarrotBridge call '{func}' failed on device: {err_msg}")
                else:
                    self.logger.log_in(line, tag="MSG")


class AsyncI2cBridge(AsyncI2cBus):
    """
    I2C Bus Master Bridge implementing CarrotBridge ASCII Protocol over any transport.
    """

    def __init__(
        self,
        transport: AsyncBaseTransport | CarrotBridge,
        bus: int = 0,
        reg_len: int = 1,
        timeout: float | None = DEFAULT_TIMEOUT,
        trace: bool = False,
        borrowed: bool | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout, reg_len=reg_len, trace=trace)
        if isinstance(transport, CarrotBridge):
            self._bridge = transport
            self._borrowed = True if borrowed is None else borrowed
        else:
            self._borrowed = False if borrowed is None else borrowed
            self._bridge = CarrotBridge(transport, timeout=timeout, trace=trace, borrowed=self._borrowed, **kwargs)
        self.logger = self._bridge.logger
        self.bus = bus

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

    async def read(self, addr: int, nbytes: int, timeout: float | None = None) -> bytes:
        if not self.is_open:
            await self.open()
        res = await self._bridge.call("IIC.R", to_hex_str(addr), nbytes, timeout=timeout)
        return parse_hex_bytes(res, nbytes=nbytes)

    async def write(self, addr: int, data: BytesLike, timeout: float | None = None) -> int:
        if not self.is_open:
            await self.open()
        raw_data = ensure_bytes(data)
        res = await self._bridge.call("IIC.W", to_hex_str(addr), raw_data, len(raw_data), timeout=timeout)
        return parse_int(res, default=len(raw_data))

    async def scan(self, timeout: float | None = None) -> list[int]:
        """
        Scan I2C bus for active 7-bit slave device addresses using hardware IIC.SCAN command.
        """
        if not self.is_open:
            await self.open()
        res = await self._bridge.call("IIC.SCAN", timeout=timeout)
        return parse_int_list(res)

    async def config_speed(self, speed_hz: int) -> None:
        if not self.is_open:
            await self.open()
        await self._bridge.call("IIC.SPEED", speed_hz)


class AsyncSpiBridge(AsyncSpiBus):
    """
    SPI Bus Master Bridge implementing CarrotBridge ASCII Protocol over any transport.
    """

    def __init__(
        self,
        transport: AsyncBaseTransport | CarrotBridge,
        cs_pin: AsyncGpioBus | None = None,
        bus: int = 0,
        cs: int = 0,
        timeout: float | None = DEFAULT_TIMEOUT,
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
        if not self.is_open:
            await self.open()
        await self._bridge.call("SPI.MODE", cpol, cpha)

    async def config_speed(self, speed_hz: int) -> None:
        if not self.is_open:
            await self.open()
        await self._bridge.call("SPI.SPEED", speed_hz)


class AsyncGpioBridge(AsyncGpioBus):
    """
    GPIO Pin Bridge implementing CarrotBridge ASCII Protocol over any transport.
    """

    def __init__(
        self,
        transport: AsyncBaseTransport | CarrotBridge,
        pin: int | str = 0,
        timeout: float | None = DEFAULT_TIMEOUT,
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
        self.pin = pin

    @property
    def bridge(self) -> CarrotBridge:
        return self._bridge

    @property
    def transport(self) -> AsyncBaseTransport:
        return self._bridge._underlying

    @property
    def is_open(self) -> bool:
        return self._bridge.is_open

    @property
    def trace(self) -> bool:
        return self._bridge.trace

    @trace.setter
    def trace(self, value: bool) -> None:
        self._bridge.trace = bool(value)

    async def _ensure_open(self) -> None:
        if not self.is_open:
            await self.open()

    async def open(self) -> None:
        await self._bridge.open()

    async def close(self) -> None:
        if not self._borrowed:
            await self._bridge.close()

    async def set_high(self) -> None:
        await self._ensure_open()
        await self._bridge.call("IO.W", self.pin, 1)

    async def set_low(self) -> None:
        await self._ensure_open()
        await self._bridge.call("IO.W", self.pin, 0)

    async def toggle(self) -> None:
        await self._ensure_open()
        level = await self.read_level()
        if level:
            await self.set_low()
        else:
            await self.set_high()

    async def read_level(self) -> bool:
        await self._ensure_open()
        res = await self._bridge.call("IO.R", self.pin)
        return parse_bool(res)

    async def config_mode(self, mode: str | int) -> None:
        """
        Configure GPIO Mode: "IN", "OUT", "OUT,PP", "OUT,OD".
        """
        await self._ensure_open()
        mode_str = mode
        if isinstance(mode, int):
            mapping = {0: "IN", 1: "OUT,PP", 2: "OUT,OD"}
            mode_str = mapping.get(mode, "OUT,PP")
        await self._bridge.call("IO.MODE", self.pin, mode_str)

    async def config_pull(self, pull: str | int) -> None:
        """
        Configure GPIO Pull: "NONE", "UP", "DOWN" or 0, 1, 2.
        """
        await self._ensure_open()
        pull_str = pull
        if isinstance(pull, int):
            mapping = {0: "NONE", 1: "UP", 2: "DOWN"}
            pull_str = mapping.get(pull, "NONE")
        await self._bridge.call("IO.PULL", self.pin, pull_str)

    async def wait_for_edge(
        self,
        edge: Literal["rising", "falling", "both"] = "rising",
        timeout: float | None = None,
    ) -> bool:
        start_time = asyncio.get_running_loop().time()
        initial_level = await self.read_level()
        while True:
            await asyncio.sleep(0.01)
            current_level = await self.read_level()
            if initial_level != current_level:
                prev = initial_level
                initial_level = current_level
                if edge == "rising" and not prev and current_level:
                    return True
                elif edge == "falling" and prev and not current_level:
                    return True
                elif edge == "both":
                    return True
            if timeout is not None and (asyncio.get_running_loop().time() - start_time) >= timeout:
                return False
