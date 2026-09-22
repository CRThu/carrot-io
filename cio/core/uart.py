"""
UART Serial Protocol Abstraction (AsyncUartTransport).
"""
from __future__ import annotations

from cio.core.base import DEFAULT_BUFFER_SIZE
from cio.core.stream import AsyncStreamTransport


class AsyncUartTransport(AsyncStreamTransport):
    """
    UART / Serial Transport Contract.
    Extends stream with baudrate, parity, stopbits, etc.
    """

    def __init__(
        self,
        baudrate: int = 115200,
        parity: str = "N",
        stopbits: int = 1,
        bytesize: int = 8,
        rtscts: bool = False,
        timeout: float | None = None,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
    ) -> None:
        super().__init__(timeout=timeout, buffer_size=buffer_size)
        self.baudrate = baudrate
        self.parity = parity
        self.stopbits = stopbits
        self.bytesize = bytesize
        self.rtscts = rtscts

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"stream", "uart"})
