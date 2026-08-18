"""
GPIO Protocol Bridge (AsyncGpioBridge) using CarrotBridge ASCII Protocol.
"""
from __future__ import annotations

import asyncio
from typing import Any, Literal

from cio.composite.carrotbridge import CarrotBridge
from cio.core.base import AsyncBaseTransport
from cio.core.converters import parse_bool
from cio.core.gpio import AsyncGpioPin


class AsyncGpioBridge(AsyncGpioPin):
    """
    GPIO Pin Bridge implementing CarrotBridge ASCII Protocol over any transport.
    """

    def __init__(
        self,
        transport: AsyncBaseTransport | CarrotBridge,
        pin: int | str = 0,
        **kwargs: Any,
    ) -> None:
        if isinstance(transport, CarrotBridge):
            self._bridge = transport
        else:
            self._bridge = CarrotBridge(transport, **kwargs)
        self.pin = pin

    @property
    def bridge(self) -> CarrotBridge:
        return self._bridge

    async def set_high(self) -> None:
        await self._bridge.call("IO.W", self.pin, 1)

    async def set_low(self) -> None:
        await self._bridge.call("IO.W", self.pin, 0)

    async def toggle(self) -> None:
        level = await self.read_level()
        if level:
            await self.set_low()
        else:
            await self.set_high()

    async def read_level(self) -> bool:
        res = await self._bridge.call("IO.R", self.pin)
        return parse_bool(res)

    async def config_mode(self, mode: str | int) -> None:
        """
        Configure GPIO Mode: "IN", "OUT", "OUT,PP", "OUT,OD".
        """
        mode_str = mode
        if isinstance(mode, int):
            mapping = {0: "IN", 1: "OUT,PP", 2: "OUT,OD"}
            mode_str = mapping.get(mode, "OUT,PP")
        await self._bridge.call("IO.MODE", self.pin, mode_str)

    async def config_pull(self, pull: str | int) -> None:
        """
        Configure GPIO Pull: "NONE", "UP", "DOWN" or 0, 1, 2.
        """
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
