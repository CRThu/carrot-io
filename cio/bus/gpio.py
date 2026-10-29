"""
GPIO Bus & Pin Controller Abstraction (AsyncGpioBus).
"""
from __future__ import annotations

import abc
from typing import Any, Literal

from cio.bus.base import AsyncBaseBus


class AsyncGpioBus(AsyncBaseBus):
    """
    Abstract Base Class for GPIO pin and bus controllers.
    """

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"gpio"})

    async def open(self) -> None:
        self._is_open = True

    async def close(self) -> None:
        self._is_open = False

    @abc.abstractmethod
    async def set_high(self) -> None:
        """Drive GPIO pin HIGH (1)."""
        raise NotImplementedError

    @abc.abstractmethod
    async def set_low(self) -> None:
        """Drive GPIO pin LOW (0)."""
        raise NotImplementedError

    @abc.abstractmethod
    async def toggle(self) -> None:
        """Toggle GPIO pin level."""
        raise NotImplementedError

    @abc.abstractmethod
    async def read_level(self) -> bool:
        """Read GPIO pin level (True=HIGH, False=LOW)."""
        raise NotImplementedError

    @abc.abstractmethod
    async def wait_for_edge(
        self,
        edge: Literal["rising", "falling", "both"] = "rising",
        timeout: float | None = None,
    ) -> bool:
        """Wait for specified signal edge transition."""
        raise NotImplementedError
