"""
Transport Layer Exception Hierarchy.
"""
from __future__ import annotations

BuiltinConnectionError = ConnectionError


class TransportError(Exception):
    """Base exception for all transport errors."""
    pass


class DriverMissingError(TransportError):
    """Raised when a required driver or optional dependency is missing."""
    pass


class PythonPackageMissingError(DriverMissingError):
    """Raised when a Python package (e.g. pyserial, pyftdi) is not installed."""
    def __init__(self, package_name: str, extra_name: str | None = None):
        extra = extra_name or package_name
        msg = f"Python package '{package_name}' is missing. Install it via: `pip install carrot-io[{extra}]` or `uv add carrot-io --extra {extra}`"
        super().__init__(msg)
        self.package_name = package_name
        self.extra_name = extra_name


class CDllMissingError(DriverMissingError):
    """Raised when a system dynamic link library (DLL/so/dylib) is missing."""
    def __init__(self, dll_name: str, hint: str = ""):
        msg = f"System C dynamic library '{dll_name}' is missing. {hint}".strip()
        super().__init__(msg)
        self.dll_name = dll_name
        self.hint = hint


class ConnectionError(TransportError, BuiltinConnectionError):
    """Base exception for connection failures."""
    pass


class ConnectTimeoutError(ConnectionError, TimeoutError):
    """Raised when establishing a connection times out."""
    pass


class ConnectionRefusedError(ConnectionError, BuiltinConnectionError):
    """Raised when a connection attempt is refused."""
    pass


class IOOperationError(TransportError):
    """Base exception for I/O operations."""
    pass


class ReadTimeoutError(IOOperationError, TimeoutError):
    """Raised when a read operation times out."""
    pass


class WriteTimeoutError(IOOperationError, TimeoutError):
    """Raised when a write operation times out."""
    pass


class BufferOverflowError(IOOperationError):
    """Raised when the internal buffer overflows."""
    pass


class WriteError(IOOperationError):
    """Raised when a write operation fails."""
    pass


class FrameChecksumError(IOOperationError):
    """Raised when frame CRC or checksum verification fails."""
    pass


class InvalidUrlError(TransportError, ValueError):
    """Raised when a URL scheme or format is invalid."""
    pass


class DeviceConfigError(TransportError):
    """Raised when a required device configuration or environment variable is missing."""
    pass
