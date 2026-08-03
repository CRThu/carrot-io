"""
Composite transport protocol bridges package.
"""
from __future__ import annotations

from cio.composite.gpio import AsyncGpioBridge
from cio.composite.i2c import AsyncI2cBridge
from cio.composite.rpc import RpcRemoteTransport
from cio.composite.spi import AsyncSpiBridge

__all__ = [
    "AsyncGpioBridge",
    "AsyncI2cBridge",
    "AsyncSpiBridge",
    "RpcRemoteTransport",
]
