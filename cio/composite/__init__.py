"""
Composite transport protocol bridges package.
"""
from __future__ import annotations

from cio.composite.carrotbridge import CarrotBridge
from cio.composite.gpio import AsyncGpioBridge
from cio.composite.i2c import AsyncI2cBridge
from cio.composite.rpc import RpcRemoteTransport
from cio.composite.spi import AsyncSpiBridge
from cio.core.registry import registry

# Register default CarrotBridge ("cb") and alias ("carrot") for standard buses
registry.register_bridge("i2c", ["cb", "carrot"], AsyncI2cBridge, is_default=True)
registry.register_bridge("spi", ["cb", "carrot"], AsyncSpiBridge, is_default=True)
registry.register_bridge("gpio", ["cb", "carrot"], AsyncGpioBridge, is_default=True)

__all__ = [
    "CarrotBridge",
    "AsyncGpioBridge",
    "AsyncI2cBridge",
    "AsyncSpiBridge",
    "RpcRemoteTransport",
]
