"""
Unit tests for layered locator factory & top-level connect API.
"""
import pytest
import cio
from cio.composite.carrotbridge import AsyncGpioBridge
from cio.composite.carrotbridge import AsyncI2cBridge
from cio.composite.rpc import RpcRemoteTransport
from cio.composite.carrotbridge import AsyncSpiBridge
from cio.transports.base import AsyncBaseTransport
from cio.exceptions import InvalidLocatorError
from cio.registry import registry
from cio.testing.mock import MockTransport


class DummyNfcBridge(AsyncBaseTransport):
    """Mock NFC bridge for testing layered locator parsing and resolution."""

    def __init__(self, transport: AsyncBaseTransport, **kwargs) -> None:
        super().__init__()
        self.transport = transport
        self.kwargs = kwargs

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass


def test_factory_connect_tcp():
    dev = cio.connect("tcp:192.168.1.50:5025")
    assert dev.host == "192.168.1.50"
    assert dev.port == 5025


def test_factory_connect_serial():
    dev = cio.connect("serial:COM3,baud=115200")
    assert dev.port == "COM3"
    assert dev.baudrate == 115200


def test_factory_spi_explicit_tcp():
    dev = cio.connect("spi[cb]:0 @ tcp:192.168.1.100:5025")
    assert isinstance(dev, AsyncSpiBridge)
    assert dev.transport.host == "192.168.1.100"
    assert dev.transport.port == 5025


def test_factory_spi_explicit_tcp_options():
    dev = cio.connect("spi[cb]:0,timeout=2.5 @ tcp:192.168.1.100:5025")
    assert isinstance(dev, AsyncSpiBridge)
    assert dev.transport.host == "192.168.1.100"
    assert dev.transport.port == 5025
    assert dev.transport.timeout == 2.5


def test_factory_i2c_explicit_tcp():
    dev = cio.connect("i2c[cb]:0,reg_len=2 @ tcp:192.168.1.100:5025,timeout=1.5")
    assert isinstance(dev, AsyncI2cBridge)
    assert dev.transport.host == "192.168.1.100"
    assert dev.transport.port == 5025
    assert dev.transport.timeout == 1.5
    assert dev.default_reg_len == 2


def test_factory_i2c_default_serial():
    dev = cio.connect("i2c[cb]:0,reg_len=2 @ serial:COM3,baud=115200")
    assert isinstance(dev, AsyncI2cBridge)
    assert dev.transport.port == "COM3"
    assert dev.transport.baudrate == 115200
    assert dev.default_reg_len == 2

    dev2 = cio.connect("gpio[cb]:3 @ serial:custom_device_name")
    assert dev2.transport.port == "custom_device_name"


def test_factory_rpc_proxy():
    dev = cio.connect("rpc:192.168.1.100:8000/5025,target_transport=tcp")
    assert isinstance(dev, RpcRemoteTransport)
    assert dev.host == "192.168.1.100"
    assert dev.port == 8000
    assert dev.target_url == "tcp:5025"


def test_factory_rpc_proxy_serial():
    dev = cio.connect("rpc:192.168.1.100:8000/COM1,baud=115200")
    assert isinstance(dev, RpcRemoteTransport)
    assert dev.host == "192.168.1.100"
    assert dev.port == 8000
    assert dev.target_url == "serial:COM1,baud=115200"


def test_factory_nfc_bridge_resolution():
    class DummyTestNfcBridge:
        def __init__(self, transport, **kwargs):
            self.transport = transport
            self.kwargs = kwargs

    registry.register_bridge("nfc", "test_pn532", DummyTestNfcBridge)
    try:
        dev = cio.connect("nfc[test_pn532]:0 @ serial:COM10,baud=115200")
        assert isinstance(dev, DummyTestNfcBridge)
        assert dev.transport.port == "COM10"
        assert dev.transport.baudrate == 115200
    finally:
        registry._bridges["nfc"].pop("test_pn532", None)


def test_factory_legacy_uri_deprecated():
    """Verify that legacy '://' URIs raise InvalidLocatorError with clear guidance."""
    with pytest.raises(InvalidLocatorError) as excinfo:
        cio.connect("serial://COM3?baud=115200")
    assert "Legacy URI scheme '://' is deprecated" in str(excinfo.value)
    assert "@" in str(excinfo.value)

    with pytest.raises(InvalidLocatorError) as excinfo2:
        cio.connect("i2c+serial://COM3")
    assert "Legacy URI scheme '://' is deprecated" in str(excinfo2.value)


def test_factory_invalid_locators():
    with pytest.raises(InvalidLocatorError):
        cio.connect("invalid_scheme_xyz:123")
    with pytest.raises(InvalidLocatorError):
        cio.connect(":malformed")
    with pytest.raises(InvalidLocatorError):
        cio.connect("")


def test_factory_gpio_with_explicit_transport():
    dev = cio.connect("gpio[cb]:5 @ mock:dev")
    assert isinstance(dev, AsyncGpioBridge)
    assert dev.pin == 5


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
    """Verify that bridged locator returns an object with trace and lifecycle methods."""
    pin = cio.connect("gpio[cb]:0,show.hex=true,trace=on @ serial:COM3")
    assert hasattr(pin, "trace")
    assert pin.trace.show.hex is True
    assert pin.trace == True
    assert pin.trace.enabled is True
    assert hasattr(pin, "open")
    assert hasattr(pin, "close")
    assert hasattr(pin, "is_open")


def test_factory_locator_boolean_options():
    """Verify that boolean false/0/off options in locator options are parsed accurately."""
    dev = cio.connect("mock:dev,show.hex=false,show.time=0,show.ascii=off,trace=1,max_bytes=128")
    assert dev.trace.show.hex is False
    assert dev.trace.show.time is False
    assert dev.trace.show.ascii is False
    assert dev.trace == True
    assert dev.trace.enabled is True
    assert dev.trace.max_bytes == 128


def test_factory_matmul_operator_overloading():
    """Verify python @ operator overloading on BusDescriptor."""
    # 1. BusDescriptor @ AsyncBaseTransport
    ser = cio.serial(port="COM3", baud=115200)
    bus = cio.i2c["cb"](0, reg_len=2) @ ser
    assert isinstance(bus, AsyncI2cBridge)
    assert bus.transport.port == "COM3"
    assert bus.default_reg_len == 2

    # 1b. Indexed BusFactory cio.i2c["cb"](...)
    bus_cb = cio.i2c["cb"](reg_len=2) @ ser
    assert isinstance(bus_cb, AsyncI2cBridge)
    assert bus_cb.default_reg_len == 2

    # 2. BusDescriptor @ str
    bus2 = cio.i2c["cb"](0, reg_len=2) @ "serial:COM4,baud=2000000"
    assert isinstance(bus2, AsyncI2cBridge)
    assert bus2.transport.port == "COM4"
    assert bus2.transport.baudrate == 2000000

    # 3. GpioDescriptor @ MockTransport
    mock_trans = MockTransport(address="dev")
    pin = cio.gpio["cb"](pin=7) @ mock_trans
    assert isinstance(pin, AsyncGpioBridge)
    assert pin.pin == 7


def test_factory_omitted_colon_and_single_device():
    """Verify colon and address can be omitted for single devices or defaults."""
    # 1. Single device without colon
    d_mock = cio.connect("mock")
    assert d_mock.address == ""

    d_ch = cio.connect("ch347")
    assert d_ch.dev_index == 0

    # 2. Dual tier omitting colon on bus or both sides
    b1 = cio.connect("i2c[cb] @ mock:dev")
    assert isinstance(b1, AsyncI2cBridge)
    assert b1.bus == 0

    b2 = cio.connect("i2c[cb],reg_len=2 @ serial:COM3,baud=115200")
    assert isinstance(b2, AsyncI2cBridge)
    assert b2.default_reg_len == 2


def test_factory_standalone_bus_and_invalid_backend_errors():
    """Verify bus without physical transport and unknown backend error branches."""
    with pytest.raises(InvalidLocatorError) as exc1:
        cio.connect("i2c:0")
    assert "Bus 'i2c' requires a physical transport" in str(exc1.value)

    with pytest.raises(InvalidLocatorError) as exc2:
        cio.connect("i2c:0 @ nonexistent_backend_xyz:0")
    assert "Unsupported or unregistered transport backend" in str(exc2.value)
