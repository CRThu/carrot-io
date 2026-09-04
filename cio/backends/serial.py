"""
Serial Port Transport Backend (SerialTransport).
"""
from __future__ import annotations

import asyncio
from typing import Any

from cio.core.exceptions import (
    ConnectionError,
    PythonPackageMissingError,
)
from cio.core.registry import registry
from cio.core.uart import AsyncUartTransport


def _probe_serial() -> bool:
    try:
        import serial  # type: ignore # noqa: F401
        return True
    except (ImportError, ModuleNotFoundError):
        return False


def _scan_serial() -> list[dict[str, Any]]:
    if not _probe_serial():
        return []
    try:
        import serial.tools.list_ports  # type: ignore

        ports = serial.tools.list_ports.comports()
        return [
            {
                "scheme": "serial",
                "port": p.device,
                "description": p.description,
                "hwid": p.hwid,
            }
            for p in ports
        ]
    except Exception:
        return []


class SerialTransport(AsyncUartTransport):
    """
    Serial (UART / RS232 / CH340) Transport using PySerial.
    """

    def __init__(
        self,
        port: str = "COM1",
        baud: int = 115200,
        baudrate: int = 115200,
        address: str | None = None,
        timeout: float | None = None,
        buffer_size: int = 1024 * 1024,
        **kwargs: Any,
    ) -> None:
        actual_baud = int(baud) if baud != 115200 else int(baudrate)
        actual_port = address if address else port
        super().__init__(
            baudrate=actual_baud,
            timeout=timeout,
            buffer_size=buffer_size,
        )
        self.port = actual_port
        self._serial: Any = None

    async def open(self) -> None:
        if self._is_open:
            return

        if not _probe_serial():
            raise PythonPackageMissingError("pyserial", "serial")

        import serial  # type: ignore

        try:
            loop = asyncio.get_running_loop()
            self._serial = await loop.run_in_executor(
                None,
                lambda: serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=self.bytesize,
                    parity=self.parity,
                    stopbits=self.stopbits,
                    rtscts=self.rtscts,
                    timeout=0.05,
                ),
            )
            self._is_open = True
        except Exception as err:
            raise ConnectionError(f"Failed to open serial port '{self.port}': {err}") from err

    async def close(self) -> None:
        if not self._is_open:
            return
        self._is_open = False
        if self._serial:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._serial.close)
            except Exception:
                pass
        self._serial = None

    async def _write_impl(self, data: bytes) -> int:
        if not self._serial or not self._is_open:
            raise ConnectionError("Serial port not open")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._serial.write, data)

    async def _read_impl(self, nbytes: int) -> bytes:
        if not self._serial or not self._is_open:
            raise ConnectionError("Serial port not open")

        loop = asyncio.get_running_loop()
        while self._is_open:
            # 优先读取硬件或驱动已就绪的缓冲区数据
            in_w = self._serial.in_waiting
            count = min(nbytes, in_w) if in_w > 0 else (1 if nbytes <= 0 else min(nbytes, 4096))
            # 由内核串口驱动阻塞唤醒，杜绝 200Hz 协程 sleep 忙等轮询
            chunk = await loop.run_in_executor(None, self._serial.read, count)
            if chunk:
                return chunk

        return b""


registry.register(
    name="serial",
    schemes=["serial", "uart"],
    factory_cls=SerialTransport,
    probe_fn=_probe_serial,
    scan_fn=_scan_serial,
)
