"""
UART Serial Protocol Abstraction (AsyncUartTransport).
"""
from __future__ import annotations

from cio.core.stream import AsyncStreamTransport


class AsyncUartTransport(AsyncStreamTransport):
    """
    Abstract base class for UART/Serial hardware interfaces.
    """

    def __init__(
        self,
        baudrate: int = 115200,
        parity: str = "N",
        stopbits: int = 1,
        bytesize: int = 8,
        rtscts: bool = False,
        timeout: float | None = None,
        buffer_size: int = 1024 * 1024,
    ) -> None:
        super().__init__(timeout=timeout, buffer_size=buffer_size)
        self.baudrate = baudrate
        self.parity = parity
        self.stopbits = stopbits
        self.bytesize = bytesize
        self.rtscts = rtscts
