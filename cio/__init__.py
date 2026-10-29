"""
cio (carrot-io) - A minimalist, zero-dependency, graceful-degradation hardware abstraction layer.
"""
from __future__ import annotations

import cio.backends  # Ensure backends register with global registry # noqa: F401
import cio.composite  # Ensure default bridges register with global registry # noqa: F401

from cio.transports.base import AsyncBaseTransport, SyncTransportWrapper, DEFAULT_BUFFER_SIZE
from cio.converters import BytesLike, ensure_bytes
from cio.trace.logger import IoLogger, LogEntry
from cio.transports.stream import AsyncStreamTransport
from cio.transports.packet import AsyncPacketTransport
from cio.transports.uart import AsyncUartTransport
from cio.bus.i2c import AsyncI2cTransport
from cio.bus.spi import AsyncSpiTransport
from cio.bus.gpio import AsyncGpioPin
from cio.protocols.protocol import ProtocolTransport
from cio.trace.collector import Collector, DataCollector, DataPoint
from cio.protocols.codec import (
    BaseCodec,
    LineCodec,
    FixedLengthCodec,
    FramedBinaryCodec,
    StructCodec,
)

from cio.composite.carrotbridge import AsyncGpioBridge
from cio.composite.carrotbridge import AsyncI2cBridge
from cio.composite.carrotbridge import AsyncSpiBridge
from cio.composite.rpc import RpcRemoteTransport, RpcServer, start_rpc_server
from cio.exceptions import (
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
    DeviceConfigError,
    UnsupportedCapabilityError,
)
from cio.env import (
    clear_history,
    close_all_devices,
    close_device,
    dev,
    reset_devices,
)
from cio.factory import connect
from cio.registry import registry
from cio.testing.mock import MockTransport, MockGpioPin
from cio.testing.verify import (
    CheckResult,
    VerificationSession,
    check,
    require,
    verify,
)


def scan(kind: str | None = None) -> list[dict]:
    """
    Scan available hardware/network transport devices gracefully.
    """
    return registry.scan(kind=kind)


def register_bridge(
    bus: str,
    name: str | list[str] | tuple[str, ...],
    bridge_cls: type,
    is_default: bool = False,
) -> None:
    """
    Register a protocol bridge implementation for a target bus (e.g. 'i2c', 'spi', 'gpio').

    :param bus: Target bus name, e.g. 'i2c', 'spi', 'gpio'.
    :param name: Bridge identifier or list of aliases, e.g. 'cb' or ['cb', 'carrot'].
    :param bridge_cls: Bridge class taking (base_transport, **kwargs).
    :param is_default: Whether this bridge should be default fallback when bridge name is omitted.
    """
    registry.register_bridge(bus=bus, name=name, bridge_cls=bridge_cls, is_default=is_default)


def tcp(
    host: str = "127.0.0.1",
    port: int = 5025,
    timeout: float | None = None,
    buffer_size: int = DEFAULT_BUFFER_SIZE,
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


def ch347(
    index: int = 0,
    timeout: float | None = None,
    **kwargs,
) -> AsyncBaseTransport:
    """Create a CH347 multi-protocol device baseboard transport instance."""
    from cio.backends.ch347 import Ch347DeviceTransport

    return Ch347DeviceTransport(index=index, timeout=timeout, **kwargs)


def visa(
    resource_name: str,
    timeout: float | None = 5.0,
    backend: str | None = None,
    read_termination: str | None = None,
    write_termination: str | None = None,
    buffer_size: int = DEFAULT_BUFFER_SIZE,
    **kwargs,
) -> AsyncStreamTransport:
    """Create a VISA instrument transport instance with default 5.0s timeout."""
    from cio.backends.visa import VisaTransport

    return VisaTransport(
        resource_name=resource_name,
        timeout=timeout,
        backend=backend,
        read_termination=read_termination,
        write_termination=write_termination,
        buffer_size=buffer_size,
        **kwargs,
    )


__version__ = "1.10.2"

__all__ = [
    # Singleton & Env Injection
    "dev",
    # Factory & Scan
    "connect",
    "scan",
    "register_bridge",
    "tcp",
    "udp",
    "serial",
    "ftdi",
    "ch347",
    "visa",
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
    "DeviceConfigError",
    "UnsupportedCapabilityError",
    "IoLogger",
    "LogEntry",
    "BytesLike",
    "ensure_bytes",
    "close_device",
    "close_all_devices",
    "reset_devices",
    "clear_history",
    # Data Ingestion & Storage Pipeline
    "Collector",
    "DataCollector",
    "DataPoint",
    # Testing
    "MockTransport",
    "MockGpioPin",
    "CheckResult",
    "VerificationSession",
    "check",
    "require",
    "verify",
]
