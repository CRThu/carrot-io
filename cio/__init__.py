"""
cio (carrot-io) - A minimalist, zero-dependency, graceful-degradation hardware abstraction layer.
"""
from __future__ import annotations

import cio.backends  # Ensure backends register with global registry # noqa: F401

from cio.core.base import AsyncBaseTransport, SyncTransportWrapper
from cio.core.converters import BytesLike, ensure_bytes
from cio.core.logger import IoLogger, LogEntry
from cio.core.stream import AsyncStreamTransport
from cio.core.packet import AsyncPacketTransport
from cio.core.uart import AsyncUartTransport
from cio.core.i2c import AsyncI2cTransport
from cio.core.spi import AsyncSpiTransport
from cio.core.gpio import AsyncGpioPin
from cio.core.protocol import ProtocolTransport
from cio.core.codec import (
    BaseCodec,
    LineCodec,
    FixedLengthCodec,
    FramedBinaryCodec,
    StructCodec,
)

from cio.composite.gpio import AsyncGpioBridge
from cio.composite.i2c import AsyncI2cBridge
from cio.composite.spi import AsyncSpiBridge
from cio.composite.rpc import RpcRemoteTransport, RpcServer, start_rpc_server
from cio.core.exceptions import (
    TransportError,
    DriverMissingError,
    PythonPackageMissingError,
    CDllMissingError,
    ConnectionError,
    ConnectTimeoutError,
    ConnectionRefusedError,
    IOOperationError,
    ReadTimeoutError,
    WriteTimeoutError,
    BufferOverflowError,
    WriteError,
    FrameChecksumError,
    InvalidUrlError,
)
from cio.core.factory import connect
from cio.core.registry import registry
from cio.testing.mock import MockTransport, MockGpioPin
from cio.testing.verifier import Verifier


def scan(kind: str | None = None) -> list[dict]:
    """
    Scan available hardware/network transport devices gracefully.
    """
    return registry.scan(kind=kind)


def tcp(
    host: str = "127.0.0.1",
    port: int = 5025,
    timeout: float | None = None,
    buffer_size: int = 1024 * 1024,
    **kwargs,
) -> AsyncStreamTransport:
    """Create a TCP transport instance."""
    from cio.backends.socket import TcpTransport

    return TcpTransport(host=host, port=port, timeout=timeout, buffer_size=buffer_size, **kwargs)


def udp(
    host: str = "127.0.0.1",
    port: int = 5025,
    timeout: float | None = None,
    buffer_size: int = 1000,
    **kwargs,
) -> AsyncPacketTransport:
    """Create a UDP transport instance."""
    from cio.backends.socket import UdpTransport

    return UdpTransport(host=host, port=port, timeout=timeout, buffer_size=buffer_size, **kwargs)


def serial(
    port: str = "COM1",
    baud: int = 115200,
    timeout: float | None = None,
    **kwargs,
) -> AsyncUartTransport:
    """Create a Serial (UART) transport instance."""
    from cio.backends.serial import SerialTransport

    return SerialTransport(port=port, baud=baud, timeout=timeout, **kwargs)


def ftdi(
    url: str = "ftdi://ftdi:232h/1",
    baud: int = 115200,
    timeout: float | None = None,
    **kwargs,
) -> AsyncUartTransport:
    """Create an FTDI UART transport instance."""
    from cio.backends.ftdi import FtdiUartTransport

    return FtdiUartTransport(url=url, baud=baud, timeout=timeout, **kwargs)


__version__ = "1.4.1"

__all__ = [
    # Factory & Scan
    "connect",
    "scan",
    "tcp",
    "udp",
    "serial",
    "ftdi",
    "start_rpc_server",
    # Core Abstractions
    "AsyncBaseTransport",
    "AsyncStreamTransport",
    "AsyncPacketTransport",
    "AsyncUartTransport",
    "AsyncI2cTransport",
    "AsyncSpiTransport",
    "AsyncGpioPin",
    "ProtocolTransport",
    "SyncTransportWrapper",
    # Composite Bridges & RPC Proxy
    "AsyncGpioBridge",
    "AsyncI2cBridge",
    "AsyncSpiBridge",
    "RpcRemoteTransport",
    "RpcServer",
    # Codecs
    "BaseCodec",
    "LineCodec",
    "FixedLengthCodec",
    "FramedBinaryCodec",
    "StructCodec",
    # Exceptions
    "TransportError",
    "DriverMissingError",
    "PythonPackageMissingError",
    "CDllMissingError",
    "ConnectionError",
    "ConnectTimeoutError",
    "ConnectionRefusedError",
    "IOOperationError",
    "ReadTimeoutError",
    "WriteTimeoutError",
    "BufferOverflowError",
    "WriteError",
    "FrameChecksumError",
    "InvalidUrlError",
    "IoLogger",
    "LogEntry",
    "BytesLike",
    "ensure_bytes",
    # Testing
    "MockTransport",
    "MockGpioPin",
    "Verifier",
]
