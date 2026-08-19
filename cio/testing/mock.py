"""
Mock Objects for Unit Testing (MockTransport and MockGpioPin).
"""
from __future__ import annotations

import asyncio
from typing import Literal

from cio.core.gpio import AsyncGpioPin
from cio.core.stream import AsyncStreamTransport


class MockTransport(AsyncStreamTransport):
    """
    In-memory Mock Transport for testing protocol drivers without real hardware.
    """

    def __init__(self, timeout: float | None = None, buffer_size: int = 1024 * 1024) -> None:
        super().__init__(timeout=timeout, buffer_size=buffer_size)
        self.tx_history: list[bytes] = []
        self._rx_raw = bytearray()
        self.auto_replies: dict[bytes, bytes] = {}

    async def open(self) -> None:
        self._is_open = True

    async def close(self) -> None:
        self._is_open = False

    def push_rx(self, data: bytes) -> None:
        """Inject fake data into receive buffer for read operations."""
        self._rx_raw.extend(data)

    def add_auto_reply(self, pattern: bytes, reply: bytes) -> None:
        """Register pattern -> reply mapping."""
        self.auto_replies[pattern] = reply

    async def _write_impl(self, data: bytes) -> int:
        self.tx_history.append(data)
        for pattern, reply in self.auto_replies.items():
            if pattern in data:
                self.push_rx(reply)
                break
        return len(data)

    async def _read_impl(self, nbytes: int) -> bytes:
        while self._is_open:
            if self._rx_raw:
                read_len = nbytes if nbytes > 0 else len(self._rx_raw)
                chunk = bytes(self._rx_raw[:read_len])
                del self._rx_raw[:read_len]
                return chunk
            await asyncio.sleep(0.005)
        return b""


class MockGpioPin(AsyncGpioPin):
    """
    Mock GPIO Pin for unit testing.
    """

    def __init__(self, initial_state: bool = False) -> None:
        super().__init__()
        self.state = initial_state
        self.state_history: list[bool] = [initial_state]
        self._edge_event = asyncio.Event()

    async def set_high(self) -> None:
        if not self.state:
            self.state = True
            self.state_history.append(True)
            self._edge_event.set()

    async def set_low(self) -> None:
        if self.state:
            self.state = False
            self.state_history.append(False)
            self._edge_event.set()

    async def toggle(self) -> None:
        if self.state:
            await self.set_low()
        else:
            await self.set_high()

    async def read_level(self) -> bool:
        return self.state

    async def wait_for_edge(
        self,
        edge: Literal["rising", "falling", "both"] = "rising",
        timeout: float | None = None,
    ) -> bool:
        self._edge_event.clear()
        initial = self.state

        start = asyncio.get_event_loop().time()
        while True:
            try:
                if timeout is not None:
                    elapsed = asyncio.get_event_loop().time() - start
                    rem = timeout - elapsed
                    if rem <= 0:
                        return False
                    await asyncio.wait_for(self._edge_event.wait(), timeout=rem)
                else:
                    await self._edge_event.wait()
            except asyncio.TimeoutError:
                return False

            self._edge_event.clear()
            current = self.state
            if edge == "rising" and not initial and current:
                return True
            if edge == "falling" and initial and not current:
                return True
            if edge == "both" and initial != current:
                return True
