"""
Unit tests for URL factory & top-level connect API.
"""
import pytest
import cio
from cio.composite.gpio import AsyncGpioBridge
from cio.composite.i2c import AsyncI2cBridge
from cio.composite.rpc import RpcRemoteTransport
from cio.composite.spi import AsyncSpiBridge
from cio.core.base import AsyncBaseTransport
from cio.core.exceptions import InvalidUrlError
from cio.core.registry import registry


class DummyNfcBridge(AsyncBaseTransport):
    """Mock NFC bridge for testing nfc:// URI parsing and resolution."""

    def __init__(self, transport: AsyncBaseTransport, **kwargs) -> None:
        super().__init__()
        self.transport = transport
        self.kwargs = kwargs

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass


def test_factory_connect_tcp():
    dev = cio.connect("tcp://192.168.1.50:5025")
    assert dev.host == "192.168.1.50"
    assert dev.port == 5025


def test_factory_connect_serial():
    dev = cio.connect("serial://COM3?baud=115200")
    assert dev.port == "COM3"
    assert dev.baudrate == 115200


def test_factory_spi_explicit_tcp():
    dev = cio.connect("spi://192.168.1.100:5025?transport=tcp")
    assert isinstance(dev, AsyncSpiBridge)
    assert dev.transport.host == "192.168.1.100"
    assert dev.transport.port == 5025


def test_factory_spi_explicit_tcp_query():
    dev = cio.connect("spi://192.168.1.100:5025?transport=tcp&timeout=2.5")
    assert isinstance(dev, AsyncSpiBridge)
    assert dev.transport.host == "192.168.1.100"
    assert dev.transport.port == 5025
    assert dev.transport.timeout == 2.5


def test_factory_i2c_explicit_tcp():
    dev = cio.connect("i2c://192.168.1.100:5025?transport=tcp&timeout=1.5&reg_len=2")
    assert isinstance(dev, AsyncI2cBridge)
    assert dev.transport.host == "192.168.1.100"
    assert dev.transport.port == 5025
    assert dev.transport.timeout == 1.5
    assert dev.default_reg_len == 2


def test_factory_i2c_default_serial():
    dev = cio.connect("i2c://COM3?baud=115200&reg_len=2")
    assert isinstance(dev, AsyncI2cBridge)
    assert dev.transport.port == "COM3"
    assert dev.transport.baudrate == 115200
    assert dev.default_reg_len == 2

    # 任何非显式 transport 的地址默认均走 serial
    dev2 = cio.connect("gpio://custom_device_name?pin=3")
    assert dev2.transport.port == "custom_device_name"


def test_factory_rpc_proxy():
    dev = cio.connect("rpc://192.168.1.100:8000/5025?target_transport=tcp")
    assert isinstance(dev, RpcRemoteTransport)
    assert dev.host == "192.168.1.100"
    assert dev.port == 8000
    assert dev.target_url == "tcp://5025"


def test_factory_rpc_proxy_serial():
    dev = cio.connect("rpc://192.168.1.100:8000/COM1?baud=115200")
    assert isinstance(dev, RpcRemoteTransport)
    assert dev.host == "192.168.1.100"
    assert dev.port == 8000
    assert dev.target_url == "serial://COM1?baud=115200"


def test_factory_nfc_scheme_resolution():
    from cio.composite.carrotbridge import CarrotBridge
    from cio.core.registry import registry

    class DummyNfcBridge:
        def __init__(self, transport, **kwargs):
            self.transport = transport
            self.kwargs = kwargs

    registry.register_bridge("nfc", "test_pn532", DummyNfcBridge)
    try:
        dev = cio.connect("nfc://COM10?driver=test_pn532&baud=115200")
        assert isinstance(dev, DummyNfcBridge)
        assert dev.transport.port == "COM10"
        assert dev.transport.baudrate == 115200
    finally:
        registry._bridges["nfc"].pop("test_pn532", None)


def test_factory_composite_plus_deprecated():
    """Verify that legacy '+' composite schemes raise InvalidUrlError with clear guidance."""
    with pytest.raises(InvalidUrlError) as excinfo:
        cio.connect("i2c+serial://COM3")
    assert "Invalid composite scheme 'i2c+serial'" in str(excinfo.value)
    assert "i2c://" in str(excinfo.value)


def test_factory_invalid_url():
    with pytest.raises(InvalidUrlError):
        cio.connect("invalid_scheme_xyz://123")
    with pytest.raises(InvalidUrlError):
        cio.connect("://malformed")
    with pytest.raises(InvalidUrlError):
        cio.connect("")


def test_factory_gpio_with_explicit_transport():
    dev = cio.connect("gpio://dev?transport=mock&pin=5")
    assert isinstance(dev, AsyncGpioBridge)
    assert dev.pin == "5"


def test_top_level_factory_helpers():
    ser = cio.serial(port="COM5", baud=9600)
    assert ser.port == "COM5"
    assert ser.baudrate == 9600

    u = cio.udp(host="10.0.0.1", port=9000)
    assert u.host == "10.0.0.1"
    assert u.port == 9000

    ft = cio.ftdi(url="ftdi://ftdi:232h/2", baud=57600)
    assert ft.url == "ftdi://ftdi:232h/2"
    assert ft.baudrate == 57600

    # Scan test
    scanned = cio.scan()
    assert isinstance(scanned, list)

    scanned_mock = cio.scan(kind="mock")
    assert isinstance(scanned_mock, list)


def test_gpio_bridge_factory_attributes():
    """Verify that gpio:// URL returns an object with logger, trace, and lifecycle methods."""
    pin = cio.connect("gpio://COM3?show_hex=true&trace=on")
    assert hasattr(pin, "logger")
    assert pin.logger.show_hex is True
    assert pin.trace is True
    assert hasattr(pin, "open")
    assert hasattr(pin, "close")
    assert hasattr(pin, "is_open")


def test_factory_url_query_boolean_options():
    """Verify that boolean false/0/off options in URL query strings are parsed accurately."""
    dev = cio.connect("mock://dev?show_hex=false&show_time=0&show_ascii=off&trace=1&max_bytes=128")
    assert dev.logger.show_hex is False
    assert dev.logger.show_time is False
    assert dev.logger.show_ascii is False
    assert dev.trace is True
    assert dev.logger.max_bytes == 128
