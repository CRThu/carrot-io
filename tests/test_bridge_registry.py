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


def test_default_bridges_registered():
    """Verify cb is registered by default for i2c, spi, gpio."""
    bridges = registry.list_bridges()
    buses = {b.bus for b in bridges}
    assert "i2c" in buses
    assert "spi" in buses
    assert "gpio" in buses

    # Default bridge for i2c must be AsyncI2cBridge
    i2c_default_cls = registry.get_bridge_cls("i2c")
    assert i2c_default_cls is AsyncI2cBridge

    # Explicit cb identifier
    assert registry.get_bridge_cls("i2c", "cb") is AsyncI2cBridge
    assert registry.get_bridge_cls("spi", "cb") is AsyncSpiBridge
    assert registry.get_bridge_cls("gpio", "cb") is AsyncGpioBridge


def test_two_part_locator_fallback_to_default_cb(monkeypatch):
    """Bus locator i2c:0 @ serial:COM3 falls back to default 'cb' bridge."""
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
