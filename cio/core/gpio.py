"""
GPIO Pin Abstraction (AsyncGpioPin).
"""
from __future__ import annotations

import abc
from typing import Any, Literal

from cio.core.base import SyncTransportWrapper


class AsyncGpioPin(abc.ABC):
    """
    Abstract Base Class for GPIO pin control.
    """

    def __init__(self) -> None:
        self._sync_wrapper: SyncTransportWrapper | None = None

    @property
    def sync(self) -> SyncTransportWrapper:
        """Universal synchronous wrapper for this GPIO pin."""
        if self._sync_wrapper is None:
            self._sync_wrapper = SyncTransportWrapper(self)
        return self._sync_wrapper


    @abc.abstractmethod
    async def set_high(self) -> None:
        """Drive pin HIGH."""
        raise NotImplementedError

    @abc.abstractmethod
    async def set_low(self) -> None:
        """Drive pin LOW."""
        raise NotImplementedError

    @abc.abstractmethod
    async def toggle(self) -> None:
        """Toggle pin state."""
        raise NotImplementedError

    @abc.abstractmethod
    async def read_level(self) -> bool:
        """Read pin input level (True=HIGH, False=LOW)."""
        raise NotImplementedError

    @abc.abstractmethod
    async def wait_for_edge(
        self,
        edge: Literal["rising", "falling", "both"] = "rising",
        timeout: float | None = None,
    ) -> bool:
        """Wait for specified signal edge transition."""
        raise NotImplementedError
