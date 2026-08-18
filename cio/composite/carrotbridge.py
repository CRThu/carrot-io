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
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout, buffer_size=buffer_size, trace=trace)
        self._underlying: AsyncBaseTransport = transport
        self._pending_futures: list[asyncio.Future[Any]] = []
        self._recv_task: asyncio.Task[None] | None = None

    @property
    def is_open(self) -> bool:
        return self._is_open and self._underlying.is_open

    async def open(self) -> None:
        if self._is_open:
            return
        if not self._underlying.is_open:
            await self._underlying.open()
        self._is_open = True
        self._start_recv_loop()

    async def close(self) -> None:
        if not self._is_open:
            return
        self._is_open = False
        self._stop_recv_loop()
        if self._underlying.is_open:
            await self._underlying.close()

    async def _write_impl(self, data: bytes) -> int:
        return await self._underlying.write(data)

    async def _read_impl(self, nbytes: int) -> bytes:
        return await self._underlying.read(nbytes)

    def _start_recv_loop(self) -> None:
        if self._recv_task is None or self._recv_task.done():
            self._recv_task = asyncio.create_task(self._receive_loop())

    def _stop_recv_loop(self) -> None:
        if self._recv_task is not None:
            self._recv_task.cancel()
            self._recv_task = None

    async def _receive_loop(self) -> None:
        while self._is_open:
            try:
                if isinstance(self._underlying, AsyncStreamTransport):
                    line = await self._underlying.read_until(b"\n")
                else:
                    line = await self._underlying.read(-1)

                if not line:
                    await asyncio.sleep(0.005)
                    continue

                line_str = line.decode("utf-8", errors="replace").strip()
                if not line_str:
                    continue

                if line_str.startswith("[RETURN]:"):
                    self.logger.log_in(line, tag="RETURN")
                    raw_val = line_str[len("[RETURN]:"):].strip()
                    parsed = self._parse_return_val(raw_val)
                    while self._pending_futures:
                        fut = self._pending_futures.pop(0)
                        if not fut.done():
                            fut.set_result(parsed)
                            break
                else:
                    self.logger.log_in(line, tag="MSG")
            except asyncio.CancelledError:
                break
            except Exception:
                if not self._is_open:
                    break
                await asyncio.sleep(0.01)

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
        if not self.is_open:
            await self.open()
        else:
            self._start_recv_loop()

        self._pending_futures = [f for f in self._pending_futures if not f.done()]

        formatted_args = [format_arg(a) for a in args]
        args_str = ", ".join(formatted_args)
        cmd_str = f"{func}({args_str})\n"
        cmd_bytes = cmd_str.encode("utf-8")

        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self._pending_futures.append(fut)

        actual_timeout = timeout if timeout is not None else self.timeout

        async with self._write_lock:
            self.logger.log_out(cmd_bytes, tag="CMD")
            await self._underlying.write(cmd_bytes)

        try:
            if actual_timeout is not None:
                return await asyncio.wait_for(fut, timeout=actual_timeout)
            else:
                return await fut
        except asyncio.TimeoutError:
            if fut in self._pending_futures:
                self._pending_futures.remove(fut)
            raise ReadTimeoutError(f"CarrotBridge call '{func}' timed out after {actual_timeout}s")
        except Exception:
            if fut in self._pending_futures:
                self._pending_futures.remove(fut)
            raise
