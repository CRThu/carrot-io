"""
Composite transport protocol bridges package.
"""
from __future__ import annotations

from cio.composite.carrotbridge import (
    AsyncGpioBridge,
    AsyncI2cBridge,
    AsyncSpiBridge,
    CarrotBridge,
)
from cio.composite.rpc import RpcRemoteTransport, RpcServer, start_rpc_server
from cio.registry import registry

# Register default CarrotBridge ("cb") for standard buses
registry.register_bridge("i2c", "cb", AsyncI2cBridge, is_default=True)
registry.register_bridge("spi", "cb", AsyncSpiBridge, is_default=True)
registry.register_bridge("gpio", "cb", AsyncGpioBridge, is_default=True)

__all__ = [
    "CarrotBridge",
    "AsyncGpioBridge",
    "AsyncI2cBridge",
    "AsyncSpiBridge",
    "RpcRemoteTransport",
    "RpcServer",
    "start_rpc_server",
]
