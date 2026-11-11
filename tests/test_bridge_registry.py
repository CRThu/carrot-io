"""
Unit tests for Pluggable Bridge Registry and Multi-part URL Routing.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock

import cio
from cio.composite.carrotbridge import AsyncGpioBridge
from cio.composite.carrotbridge import AsyncI2cBridge
from cio.composite.carrotbridge import AsyncSpiBridge
from cio.transports.base import AsyncBaseTransport
from cio.exceptions import InvalidLocatorError
from cio.registry import BridgeInfo, registry
from cio.backends.serial import SerialTransport
from cio.testing.mock import MockTransport


class DummyCustomI2cBridge(AsyncBaseTransport):
    """Custom dummy I2C bridge for registration testing."""

    def __init__(self, transport: AsyncBaseTransport, **kwargs) -> None:
        super().__init__()
        self.transport = transport
        self.kwargs = kwargs

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass


class NativeDeviceWithI2c(AsyncBaseTransport):
    """Mock base device that natively provides an i2c() bus factory."""

    def __init__(self, address: str, **kwargs) -> None:
        super().__init__()
        self.address = address
        self.native_i2c_called = False

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"i2c"})

    def i2c(self, **kwargs) -> AsyncBaseTransport:
        self.native_i2c_called = True
        return MockTransport(address="native_i2c")

    async def open(self) -> None:
        pass

    async def close(self) -> None:
        pass


def test_standard_bridges_registered():
    """Verify cb is registered as standard bridge for i2c, spi, gpio without forcing default."""
    bridges = registry.list_bridges()
    buses = {b.bus for b in bridges}
    assert "i2c" in buses
    assert "spi" in buses
    assert "gpio" in buses

    # Explicit cb identifier is registered
    assert registry.get_bridge_cls("i2c", "cb") is AsyncI2cBridge
    assert registry.get_bridge_cls("spi", "cb") is AsyncSpiBridge
    assert registry.get_bridge_cls("gpio", "cb") is AsyncGpioBridge


def test_two_part_locator_requires_explicit_bridge_or_env_default(monkeypatch):
    """
    Bus locator i2c:0 @ serial:COM3 rejects raw stream without explicit bridge,
    unless configured via CIO_DEFAULT_BRIDGE_I2C.
    """
    # 1. Without explicit bridge or env default, raises clear InvalidLocatorError
    with pytest.raises(InvalidLocatorError) as excinfo:
        cio.connect("i2c:0 @ serial:COM3,baud=115200")
    assert "Transport 'serial' does not natively support bus 'i2c'" in str(excinfo.value)
    assert "Please specify a protocol bridge explicitly in brackets" in str(excinfo.value)

    # 1b. Direct @ operator on opened transport without native capability also gives clear error
    ser = SerialTransport("mock")
    with pytest.raises(InvalidLocatorError) as excinfo_matmul:
        _ = cio.i2c(0) @ ser
    assert "does not natively support bus 'i2c'" in str(excinfo_matmul.value)
    assert "Please specify a protocol bridge explicitly in brackets" in str(excinfo_matmul.value)

    # 2. When CIO_DEFAULT_BRIDGE_I2C is explicitly configured, it resolves to that bridge
    monkeypatch.setenv("CIO_DEFAULT_BRIDGE_I2C", "cb")
    dev = cio.connect("i2c:0 @ serial:COM3,baud=115200")
    assert isinstance(dev, AsyncI2cBridge)
    assert dev.transport.port == "COM3"
    assert dev.transport.baudrate == 115200


def test_three_part_locator_explicit_cb():
    """Explicit bridge in brackets [cb]."""
    dev_cb = cio.connect("i2c[cb]:0 @ serial:COM3")
    assert isinstance(dev_cb, AsyncI2cBridge)

    # Alias 'carrot' is not supported, only 'cb'
    with pytest.raises(InvalidLocatorError):
        cio.connect("i2c[carrot]:0 @ serial:COM3")

    dev_spi = cio.connect("spi[cb]:0 @ tcp:127.0.0.1:5025")
    assert isinstance(dev_spi, AsyncSpiBridge)

    dev_gpio = cio.connect("gpio[cb]:0 @ serial:COM3")
    assert isinstance(dev_gpio, AsyncGpioBridge)


def test_custom_bridge_registration_and_connect():
    """Custom protocol bridge can be registered and accessed via [bridge] syntax."""
    cio.register_bridge("i2c", "custom_proto", DummyCustomI2cBridge)

    # Verify registered
    cls = registry.get_bridge_cls("i2c", "custom_proto")
    assert cls is DummyCustomI2cBridge

    # Connect using layered locator and bridge bracket option
    dev = cio.connect("i2c[custom_proto]:0,speed=400 @ serial:COM4")
    assert isinstance(dev, DummyCustomI2cBridge)
    assert dev.transport.port == "COM4"
    assert dev.kwargs.get("speed") == 400


def test_custom_bridge_set_as_default():
    """Custom bridge can be registered or set as default for a bus."""
    cio.register_bridge("custom_bus", ["mb", "modbus"], DummyCustomI2cBridge, is_default=True)

    # Clean layered locator on custom bus resolves to default bridge
    dev = cio.connect("custom_bus:0 @ serial:COM5")
    assert isinstance(dev, DummyCustomI2cBridge)

    # Clean layered locator with explicit bridge alias
    dev_alias = cio.connect("custom_bus[modbus]:0 @ serial:COM5")
    assert isinstance(dev_alias, DummyCustomI2cBridge)


def test_native_hardware_priority_on_two_part_locator(monkeypatch):
    """When base transport natively implements the bus method, clean bus locator bypasses bridge."""
    # Register mock backend
    registry.register(
        name="nativedev",
        schemes=["nativedev"],
        factory_cls=NativeDeviceWithI2c,
        probe_fn=lambda: True,
    )

    # Clean locator: i2c:0 @ nativedev:0 -> calls native dev.i2c() directly
    dev = cio.connect("i2c:0 @ nativedev:0")
    assert isinstance(dev, MockTransport)
    assert dev.address == "native_i2c"

    # Explicit bridge: i2c[cb]:0 @ nativedev:0 -> explicitly wraps with cb bridge
    dev_bridged = cio.connect("i2c[cb]:0 @ nativedev:0")
    assert isinstance(dev_bridged, AsyncI2cBridge)


def test_bridge_registry_error_handling():
    """Proper strong-typed exceptions for unknown bridges, buses, or legacy '://' URIs."""
    # Unknown bridge for registered bus
    with pytest.raises(InvalidLocatorError) as excinfo:
        cio.connect("i2c[unknown_bridge_xyz]:0 @ serial:COM3")
    assert "unknown_bridge_xyz" in str(excinfo.value)
    assert "cb" in str(excinfo.value)

    # Unknown bus with no bridges registered
    with pytest.raises(InvalidLocatorError) as excinfo:
        cio.connect("unregistered_bus_xyz:0 @ serial:COM3")
    assert "unregistered_bus_xyz" in str(excinfo.value)

    # Legacy '://' URI rejected with clear guidance
    with pytest.raises(InvalidLocatorError) as excinfo:
        cio.connect("i2c+cb+serial://COM3")
    assert "Legacy URI scheme '://' is deprecated" in str(excinfo.value)

    # Setting unknown bridge as default
    with pytest.raises(InvalidLocatorError):
        registry.set_default_bridge("i2c", "nonexistent_bridge")


def test_override_default_bridge_for_standard_bus():
    """Verify that overriding default bridge for 'i2c' takes effect in locator and Python @ syntax."""
    registry.register_bridge("i2c", "new_def", DummyCustomI2cBridge)
    registry.set_default_bridge("i2c", "new_def")
    try:
        # Locator string without brackets resolves to new default
        dev1 = cio.connect("i2c:0 @ serial:COM3")
        assert isinstance(dev1, DummyCustomI2cBridge)

        # Python @ syntax without brackets resolves to new default
        dev2 = cio.i2c(0) @ cio.serial("COM3")
        assert isinstance(dev2, DummyCustomI2cBridge)
    finally:
        # Restore default cb
        registry.set_default_bridge("i2c", "cb")


def test_pass_class_directly_to_bus_factory():
    """Verify passing bridge class directly to BusFactory: cio.i2c[Class]."""
    # 1. Stacking with instantiated transport
    ser = cio.serial("COM3", baud=115200)
    dev1 = cio.i2c[DummyCustomI2cBridge](0, speed=100) @ ser
    assert isinstance(dev1, DummyCustomI2cBridge)
    assert dev1.kwargs.get("speed") == 100
    assert dev1.transport.port == "COM3"

    # 2. Stacking with string locator
    dev2 = cio.i2c[DummyCustomI2cBridge](0, speed=200) @ "serial:COM4,baud=2000000"
    assert isinstance(dev2, DummyCustomI2cBridge)
    assert dev2.kwargs.get("speed") == 200
    assert dev2.transport.port == "COM4"
    assert dev2.transport.baudrate == 2000000


def test_connect_with_explicit_bridge_class():
    """Verify cio.connect() with explicit bridge=Class parameter."""
    dev = cio.connect("i2c:0,speed=300 @ serial:COM3", bridge=DummyCustomI2cBridge)
    assert isinstance(dev, DummyCustomI2cBridge)
    assert dev.kwargs.get("speed") == 300
    assert dev.transport.port == "COM3"


def test_register_bridge_as_decorator():
    """Verify @cio.register_bridge decorator syntax."""
    @cio.register_bridge("i2c", "decorated_bridge")
    class DecoratedBridge(AsyncBaseTransport):
        def __init__(self, transport: AsyncBaseTransport, **kwargs) -> None:
            super().__init__()
            self.transport = transport
            self.kwargs = kwargs

        async def open(self) -> None:
            pass

        async def close(self) -> None:
            pass

    assert registry.has_bridge("i2c", "decorated_bridge") is True
    dev = cio.connect("i2c[decorated_bridge]:0 @ serial:COM3")
    assert isinstance(dev, DecoratedBridge)


def test_dynamic_env_bridge_loading(monkeypatch):
    """
    Verify dynamic discovery of external bridges via:
      1. CIO_BRIDGE_{NAME}
      2. CIO_BRIDGE_{BUS}_{NAME}
      3. CIO_BRIDGES multi-definition
    """
    # 1. Test CIO_BRIDGE_NC
    monkeypatch.setenv("CIO_BRIDGE_NC", "tests.test_bridge_registry:DummyCustomI2cBridge")
    dev1 = cio.connect("i2c[nc]:0,test_arg=42 @ serial:COM5,baud=2000000")
    assert type(dev1).__name__ == "DummyCustomI2cBridge"
    assert dev1.kwargs.get("test_arg") == 42
    assert dev1.transport.port == "COM5"

    # 2. Test CIO_BRIDGE_I2C_NC2
    monkeypatch.setenv("CIO_BRIDGE_I2C_NC2", "tests.test_bridge_registry:DummyCustomI2cBridge")
    dev2 = cio.connect("i2c[nc2]:0 @ serial:COM6")
    assert type(dev2).__name__ == "DummyCustomI2cBridge"

    # 3. Test CIO_BRIDGES list definition
    monkeypatch.setenv("CIO_BRIDGES", "i2c[nc_multi]=tests.test_bridge_registry:DummyCustomI2cBridge")
    dev3 = cio.connect("i2c[nc_multi]:0 @ serial:COM7")
    assert type(dev3).__name__ == "DummyCustomI2cBridge"


def test_dynamic_inline_module_bridge():
    """Verify inline module:Class in brackets: i2c[module:Class]."""
    dev = cio.connect("i2c[tests.test_bridge_registry:DummyCustomI2cBridge]:0 @ serial:COM8")
    assert type(dev).__name__ == "DummyCustomI2cBridge"
    assert dev.transport.port == "COM8"


def test_env_nc_mounting_with_dev_singleton(monkeypatch):
    """
    Full end-to-end integration:
    Mount [nc] bridge via environment variable and verify cio.dev lazy resolution.
    """
    monkeypatch.setenv("CIO_DEVICE", "i2c[my_nc]:0,speed=400 @ serial:COM9,baud=2000000")
    monkeypatch.setenv("CIO_BRIDGE_MY_NC", "tests.test_bridge_registry:DummyCustomI2cBridge")

    from cio.env import reset_devices, get_device
    reset_devices()

    # Get device without sync wrapper for raw type assertion
    raw_dev = get_device("default", sync=False)
    assert type(raw_dev).__name__ == "DummyCustomI2cBridge"
    assert raw_dev.kwargs.get("speed") == 400
    assert raw_dev.transport.port == "COM9"
    assert raw_dev.transport.baudrate == 2000000

    reset_devices()
