"""
Unit tests for cio.core.exceptions hierarchy and formatting.
"""
from cio.core.exceptions import (
    CDllMissingError,
    DriverMissingError,
    PythonPackageMissingError,
    TransportError,
    ConnectionError,
    ConnectTimeoutError,
    ConnectionRefusedError,
    ReadTimeoutError,
    WriteTimeoutError,
    BufferOverflowError,
    IOOperationError,
    FrameChecksumError,
    InvalidUrlError,
    DeviceConfigError,
)


def test_exception_hierarchy():
    assert issubclass(DriverMissingError, TransportError)
    assert issubclass(PythonPackageMissingError, DriverMissingError)
    assert issubclass(CDllMissingError, DriverMissingError)
    assert issubclass(ConnectionError, TransportError)
    assert issubclass(ConnectTimeoutError, ConnectionError)
    assert issubclass(ConnectionRefusedError, ConnectionError)
    assert issubclass(ReadTimeoutError, TransportError)
    assert issubclass(WriteTimeoutError, TransportError)
    assert issubclass(BufferOverflowError, TransportError)
    assert issubclass(IOOperationError, TransportError)
    assert issubclass(FrameChecksumError, TransportError)
    assert issubclass(InvalidUrlError, TransportError)
    assert issubclass(DeviceConfigError, TransportError)


def test_exception_formatting():
    err_pkg = PythonPackageMissingError("pyserial", "serial")
    assert "pip install carrot-io[serial]" in str(err_pkg) or "pip install" in str(err_pkg)
    assert err_pkg.package_name == "pyserial"
    assert err_pkg.extra_name == "serial"

    err_dll = CDllMissingError("visa32.dll", hint="Please install NI-VISA")
    assert "visa32.dll" in str(err_dll)
    assert "Please install NI-VISA" in str(err_dll)
    assert err_dll.dll_name == "visa32.dll"

