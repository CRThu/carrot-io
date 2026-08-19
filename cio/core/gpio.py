"""
GPIO Pin Abstraction (AsyncGpioPin).
"""
from __future__ import annotations

import abc
from typing import Any, Literal

from cio.core.base import SyncableMixin


class AsyncGpioPin(abc.ABC, SyncableMixin):
    """
    Abstract Base Class for GPIO pin control.
    """

    def __init__(self) -> None:
        super().__init__()

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
