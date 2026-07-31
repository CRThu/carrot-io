"""
GPIO Protocol Bridge (AsyncGpioBridge) using Hardware Frame Protocol.
"""
from __future__ import annotations

import asyncio
from typing import Any, Literal

from cio.composite.frame import AsyncFrameBridge
from cio.core.base import AsyncBaseTransport
from cio.core.frame import (
    ACTION_CFG,
    ACTION_READ_DATA,
    ACTION_WRITE_DATA,
    CFG_GPIO_MODE,
    CFG_GPIO_PULL,
    PERIPHERAL_GPIO,
    HardwareFrame,
)

from cio.core.gpio import AsyncGpioPin


class AsyncGpioBridge(AsyncGpioPin):
    """
    GPIO Pin Bridge implementing Hardware Frame Protocol over any transport.
    """

    def __init__(
        self,
        transport: AsyncBaseTransport | AsyncFrameBridge,
        pin: int = 0,
        **kwargs: Any,
    ) -> None:
        if isinstance(transport, AsyncFrameBridge):
            self._bridge = transport
        else:
            self._bridge = AsyncFrameBridge(transport, **kwargs)
        self.pin = pin

    @property
    def bridge(self) -> AsyncFrameBridge:
        return self._bridge

    async def set_high(self) -> None:
        frame = HardwareFrame(
            peripheral=PERIPHERAL_GPIO,
            action=ACTION_WRITE_DATA,
            bus=self.pin,
            payload=b"\x01",
        )
        await self._bridge.request_frame(frame)

    async def set_low(self) -> None:
        frame = HardwareFrame(
            peripheral=PERIPHERAL_GPIO,
            action=ACTION_WRITE_DATA,
            bus=self.pin,
            payload=b"\x00",
        )
        await self._bridge.request_frame(frame)

    async def toggle(self) -> None:
        level = await self.read_level()
        if level:
            await self.set_low()
        else:
            await self.set_high()

    async def read_level(self) -> bool:
        frame = HardwareFrame(
            peripheral=PERIPHERAL_GPIO,
            action=ACTION_READ_DATA,
            bus=self.pin,
            payload=b"",
        )
        resp = await self._bridge.request_frame(frame)
        return bool(resp.payload[0]) if resp.payload else False


    async def config_mode(self, mode: int) -> None:
        """
        Configure GPIO Mode: 0 (Input), 1 (Output Push-Pull), 2 (Output Open-Drain).
        """
        frame = HardwareFrame(
            peripheral=PERIPHERAL_GPIO,
            action=ACTION_CFG,
            bus=self.pin,
            payload=bytes([CFG_GPIO_MODE, mode & 0xFF]),
        )
        await self._bridge.request_frame(frame)

    async def config_pull(self, pull: int) -> None:
        """
        Configure GPIO Pull: 0 (None), 1 (Pull-Up), 2 (Pull-Down).
        """
        frame = HardwareFrame(
            peripheral=PERIPHERAL_GPIO,
            action=ACTION_CFG,
            bus=self.pin,
            payload=bytes([CFG_GPIO_PULL, pull & 0xFF]),
        )
        await self._bridge.request_frame(frame)

    async def wait_for_edge(
        self,
        edge: Literal["rising", "falling", "both"] = "rising",
        timeout: float | None = None,
    ) -> bool:
        start_time = asyncio.get_event_loop().time()
        initial_level = await self.read_level()
        while True:
            await asyncio.sleep(0.01)
            current_level = await self.read_level()
            if initial_level != current_level:
                if edge == "rising" and current_level:
                    return True
                elif edge == "falling" and not current_level:
                    return True
                elif edge == "both":
                    return True
            if timeout is not None and (asyncio.get_event_loop().time() - start_time) >= timeout:
                return False
