"""
CarrotBridge ASCII-based MCU/Hardware Composite Protocol Bridge (CarrotBridge).
"""
from __future__ import annotations

import asyncio
from typing import Any

from cio.core.base import AsyncBaseTransport
from cio.core.converters import format_arg
from cio.core.exceptions import ReadTimeoutError
from cio.core.stream import AsyncStreamTransport


class CarrotBridge(AsyncBaseTransport):
    """
    CarrotBridge ASCII-based Remote Hardware Composite Protocol Bridge.
    Proxies MCU hardware function calls over stream transport using ASCII commands and responses.
    """

    def __init__(
        self,
        transport: AsyncBaseTransport,
        timeout: float | None = None,
        buffer_size: int = 1024 * 1024,
        trace: bool = False,
        borrowed: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout, buffer_size=buffer_size, trace=trace)
        self._underlying: AsyncBaseTransport = transport
        self._borrowed = borrowed
        self._transaction_lock: asyncio.Lock | None = None
        self._lock_loop: asyncio.AbstractEventLoop | None = None

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
        from cio.composite.i2c import AsyncI2cBridge
        return AsyncI2cBridge(self, bus=bus, reg_len=reg_len, borrowed=True, **kwargs)

    def spi(self, bus: int = 0, cs: int = 0, **kwargs: Any) -> Any:
        """Create a derived SPI bridge sharing this physical CarrotBridge connection."""
        from cio.composite.spi import AsyncSpiBridge
        return AsyncSpiBridge(self, bus=bus, cs=cs, borrowed=True, **kwargs)

    def gpio(self, pin: int = 0, mode: str = "out", **kwargs: Any) -> Any:
        """Create a derived GPIO pin bridge sharing this physical CarrotBridge connection."""
        from cio.composite.gpio import AsyncGpioBridge
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
                else:
                    self.logger.log_in(line, tag="MSG")
