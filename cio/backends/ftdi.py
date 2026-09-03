"""
FTDI Hardware Adapter Backend (UART, I2C, SPI, GPIO using pyftdi).
"""
from __future__ import annotations

import asyncio
from typing import Any, Literal

from cio.core.converters import BytesLike, ensure_bytes
from cio.core.exceptions import ConnectionError, PythonPackageMissingError
from cio.core.gpio import AsyncGpioPin
from cio.core.i2c import AsyncI2cTransport
from cio.core.registry import registry
from cio.core.spi import AsyncSpiTransport
from cio.core.uart import AsyncUartTransport


def _probe_ftdi() -> bool:
    try:
        import pyftdi  # type: ignore # noqa: F401
        import pyftdi.ftdi  # type: ignore # noqa: F401
        return True
    except (ImportError, ModuleNotFoundError, OSError):
        return False


def _scan_ftdi() -> list[dict[str, Any]]:
    if not _probe_ftdi():
        return []
    try:
        from pyftdi.ftdi import Ftdi  # type: ignore

        devices = Ftdi.find_all()
        return [
            {
                "scheme": "ftdi",
                "vendor_id": hex(dev[0].vid),
                "product_id": hex(dev[0].pid),
                "serial": dev[0].sn,
                "description": dev[0].description,
            }
            for dev in devices
        ]
    except Exception:
        return []


class FtdiUartTransport(AsyncUartTransport):
    """
    FTDI Serial/UART Transport.
    """

    def __init__(
        self,
        url: str = "ftdi://ftdi:232h/1",
        address: str | None = None,
        baud: int = 115200,
        baudrate: int = 115200,
        timeout: float | None = None,
        buffer_size: int = 1024 * 1024,
        **kwargs: Any,
    ) -> None:
        actual_url = address if address else url
        actual_baud = int(baud) if baud != 115200 else int(baudrate)
        super().__init__(baudrate=actual_baud, timeout=timeout, buffer_size=buffer_size)
        self.url = actual_url
        self._port: Any = None

    async def open(self) -> None:
        if self._is_open:
            return

        if not _probe_ftdi():
            raise PythonPackageMissingError("pyftdi", "ftdi")

        from pyftdi.serialext import serial_for_url  # type: ignore

        try:
            loop = asyncio.get_running_loop()
            self._port = await loop.run_in_executor(
                None,
                lambda: serial_for_url(
                    self.url,
                    baudrate=self.baudrate,
                    timeout=0,
                ),
            )
            self._is_open = True
        except Exception as err:
            raise ConnectionError(f"Failed to open FTDI UART at '{self.url}': {err}") from err

    async def close(self) -> None:
        if not self._is_open:
            return
        self._is_open = False
        if self._port:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._port.close)
            except Exception:
                pass
        self._port = None

    async def _write_impl(self, data: bytes) -> int:
        if not self._port or not self._is_open:
            raise ConnectionError("FTDI UART not open")
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._port.write, data)

    async def _read_impl(self, nbytes: int) -> bytes:
        if not self._port or not self._is_open:
            raise ConnectionError("FTDI UART not open")
        loop = asyncio.get_running_loop()
        read_len = nbytes if nbytes > 0 else 4096
        return await loop.run_in_executor(None, self._port.read, read_len)


class FtdiI2cTransport(AsyncI2cTransport):
    """
    FTDI I2C Controller Transport using PyFTDI.
    """

    def __init__(
        self,
        url: str = "ftdi://ftdi:2232h/1",
        address: str | None = None,
        frequency: float = 100E3,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout)
        self.url = address if address else url
        self.frequency = float(frequency)
        self._i2c: Any = None

    async def open(self) -> None:
        if self._is_open:
            return
        if not _probe_ftdi():
            raise PythonPackageMissingError("pyftdi", "ftdi")

        from pyftdi.i2c import I2cController  # type: ignore

        try:
            loop = asyncio.get_running_loop()
            controller = I2cController()

            def _init_i2c():
                controller.configure(self.url, frequency=self.frequency)
                return controller

            self._i2c = await loop.run_in_executor(None, _init_i2c)
            self._is_open = True
        except Exception as err:
            raise ConnectionError(f"Failed to configure FTDI I2C at '{self.url}': {err}") from err

    async def close(self) -> None:
        if not self._is_open:
            return
        self._is_open = False
        if self._i2c:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._i2c.terminate)
            except Exception:
                pass
        self._i2c = None

    async def read(self, addr: int, nbytes: int, timeout: float | None = None) -> bytes:
        if not self._is_open:
            await self.open()
        loop = asyncio.get_running_loop()
        port = self._i2c.get_port(addr)
        return await loop.run_in_executor(None, port.read, nbytes)

    async def write(self, addr: int, data: BytesLike, timeout: float | None = None) -> int:
        if not self._is_open:
            await self.open()
        raw_data = ensure_bytes(data)
        loop = asyncio.get_running_loop()
        port = self._i2c.get_port(addr)
        await loop.run_in_executor(None, port.write, raw_data)
        return len(raw_data)



class FtdiSpiTransport(AsyncSpiTransport):
    """
    FTDI SPI Controller Transport using PyFTDI.
    """

    def __init__(
        self,
        url: str = "ftdi://ftdi:2232h/1",
        address: str | None = None,
        frequency: float = 1E6,
        mode: int = 0,
        cs_count: int = 1,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout)
        self.url = address if address else url
        self.frequency = float(frequency)
        self.mode = int(mode)
        self.cs_count = int(cs_count)
        self._spi: Any = None
        self._port: Any = None

    async def open(self) -> None:
        if self._is_open:
            return
        if not _probe_ftdi():
            raise PythonPackageMissingError("pyftdi", "ftdi")

        from pyftdi.spi import SpiController  # type: ignore

        try:
            loop = asyncio.get_running_loop()
            controller = SpiController(cs_count=self.cs_count)

            def _init_spi():
                controller.configure(self.url)
                port = controller.get_port(cs=0, freq=self.frequency, mode=self.mode)
                return controller, port

            self._spi, self._port = await loop.run_in_executor(None, _init_spi)
            self._is_open = True
        except Exception as err:
            raise ConnectionError(f"Failed to configure FTDI SPI at '{self.url}': {err}") from err

    async def close(self) -> None:
        if not self._is_open:
            return
        self._is_open = False
        if self._spi:
            try:
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, self._spi.terminate)
            except Exception:
                pass
        self._spi = None
        self._port = None

    async def transfer(self, tx_data: BytesLike, timeout: float | None = None) -> bytes:
        if not self._is_open:
            await self.open()
        raw_tx = ensure_bytes(tx_data)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._port.exchange, raw_tx)



class FtdiGpioPin(AsyncGpioPin):
    """
    FTDI GPIO Pin Control.
    """

    def __init__(self, gpio_controller: Any, pin_index: int) -> None:
        self.controller = gpio_controller
        self.pin_index = pin_index
        self._state = False

    async def set_high(self) -> None:
        self._state = True
        loop = asyncio.get_running_loop()
        mask = 1 << self.pin_index
        await loop.run_in_executor(None, lambda: self.controller.write(mask, mask))

    async def set_low(self) -> None:
        self._state = False
        loop = asyncio.get_running_loop()
        mask = 1 << self.pin_index
        await loop.run_in_executor(None, lambda: self.controller.write(0, mask))

    async def toggle(self) -> None:
        if self._state:
            await self.set_low()
        else:
            await self.set_high()

    async def read_level(self) -> bool:
        loop = asyncio.get_running_loop()
        val = await loop.run_in_executor(None, self.controller.read)
        self._state = bool((val >> self.pin_index) & 0x01)
        return self._state

    async def wait_for_edge(
        self,
        edge: Literal["rising", "falling", "both"] = "rising",
        timeout: float | None = None,
    ) -> bool:
        initial = await self.read_level()
        start = asyncio.get_running_loop().time()
        while True:
            await asyncio.sleep(0.01)
            current = await self.read_level()
            if initial != current:
                prev = initial
                initial = current
                if edge == "rising" and not prev and current:
                    return True
                elif edge == "falling" and prev and not current:
                    return True
                elif edge == "both":
                    return True
            if timeout is not None and (asyncio.get_running_loop().time() - start) >= timeout:
                return False


registry.register(
    name="ftdi",
    schemes=["ftdi"],
    factory_cls=FtdiUartTransport,
    probe_fn=_probe_ftdi,
    scan_fn=_scan_ftdi,
)
