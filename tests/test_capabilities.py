"""
Unit tests for Capabilities Introspection, AsyncGpioPin Hierarchy,
UnsupportedCapabilityError, and Parent-Child Cascading Close Prevention.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

import cio
from cio.backends.serial import SerialTransport
from cio.backends.socket import TcpTransport, UdpTransport
from cio.composite.carrotbridge import CarrotBridge
from cio.composite.gpio import AsyncGpioBridge
from cio.composite.i2c import AsyncI2cBridge
from cio.composite.spi import AsyncSpiBridge
from cio.core.base import AsyncBaseTransport
from cio.core.exceptions import ConnectionError, TransportError, UnsupportedCapabilityError
from cio.core.gpio import AsyncGpioPin
from cio.testing.mock import MockGpioPin, MockTransport


def test_capabilities_declaration_across_transports():
    """Verify each transport accurately declares its capabilities frozenset."""
    mock_st = MockTransport()
    assert mock_st.capabilities == frozenset({"stream"})
    assert mock_st.sync.capabilities == frozenset({"stream"})

    ser = SerialTransport(port="COM1")
    assert ser.capabilities == frozenset({"stream", "uart"})
    assert ser.sync.capabilities == frozenset({"stream", "uart"})

    udp = UdpTransport(host="127.0.0.1", port=5025)
    assert udp.capabilities == frozenset({"packet"})

    cb = CarrotBridge(mock_st)
    assert cb.capabilities == frozenset({"i2c", "spi", "gpio"})

    i2c_bridge = cb.i2c()
    assert i2c_bridge.capabilities == frozenset({"i2c"})

    spi_bridge = cb.spi()
    assert spi_bridge.capabilities == frozenset({"spi"})

    gpio_bridge = cb.gpio(pin=0)
    assert gpio_bridge.capabilities == frozenset({"gpio"})

    mock_gpio = MockGpioPin()
    assert mock_gpio.capabilities == frozenset({"gpio"})


def test_unsupported_capability_error_behavior():
    """Verify calling an unsupported bus method raises UnsupportedCapabilityError."""
    ser = SerialTransport(port="COM1")

    # hasattr must be False (standard Python duck typing preserved)
    assert not hasattr(ser, "i2c")
    assert not hasattr(ser, "spi")
    assert not hasattr(ser, "gpio")

    # Direct call must raise UnsupportedCapabilityError with supported caps listed
    with pytest.raises(UnsupportedCapabilityError) as excinfo:
        ser.i2c()
    err_str = str(excinfo.value)
    assert "SerialTransport" in err_str
    assert "does not support 'i2c'" in err_str
    assert "stream" in err_str
    assert "uart" in err_str

    # Must be both TransportError and AttributeError
    assert isinstance(excinfo.value, TransportError)
    assert isinstance(excinfo.value, AttributeError)

    # Calling an arbitrary non-bus attribute still raises standard AttributeError
    with pytest.raises(AttributeError) as excinfo_attr:
        _ = ser.non_existent_attribute_xyz
    assert not isinstance(excinfo_attr.value, UnsupportedCapabilityError)


def test_async_gpio_pin_inherits_async_base_transport():
    """Verify AsyncGpioPin is fully integrated into AsyncBaseTransport hierarchy."""
    pin = MockGpioPin(initial_state=False)

    # Inheritance check
    assert isinstance(pin, AsyncBaseTransport)
    assert isinstance(pin, AsyncGpioPin)

    # Logger and history integration
    assert hasattr(pin, "logger")
    assert hasattr(pin, "history")
    assert hasattr(pin, "dump_history")

    # Context manager sync support
    with pin:
        pin.sync.set_high()
        assert pin.sync.read_level() is True

    assert pin.is_open is False


@pytest.mark.asyncio
async def test_carrot_bridge_borrowed_child_lifecycle():
    """Closing borrowed child must not close parent CarrotBridge, and parent remains open."""
    mock_st = MockTransport()
    await mock_st.open()

    cb = CarrotBridge(mock_st)
    await cb.open()

    i2c = cb.i2c()
    spi = cb.spi()
    gpio = cb.gpio(pin=3)

    assert cb.is_open is True

    # Closing a borrowed child only affects itself, never closes the underlying bridge
    await i2c.close()
    await spi.close()
    await gpio.close()

    assert cb.is_open is True

    # Explicitly closing the parent bridge releases the underlying transport
    await cb.close()
    assert cb.is_open is False
    assert mock_st.is_open is False


@pytest.mark.asyncio
async def test_ch347_borrowed_child_lifecycle():
    """Closing borrowed child must not close parent Ch347Device, and child auto-readies."""
    from cio.backends.ch347 import Ch347Device

    mock_dll = MagicMock()
    mock_dll.CH347OpenDevice.return_value = 100
    mock_dll.CH347CloseDevice.return_value = True
    mock_dll.CH347I2C_Set.return_value = True
    mock_dll.CH347SPI_Init.return_value = True
    mock_dll.CH347GPIO_Set.return_value = True

    device = Ch347Device(dev_index=99)
    with patch("cio.backends.ch347._load_ch347_dll", return_value=mock_dll):
        await device.open()

        i2c = device.i2c()
        spi = device.spi()
        gpio = device.gpio(pin=1)

        assert device.is_open is True

        # Closing borrowed channels
        await i2c.close()
        await spi.close()
        await gpio.close()

        # Baseboard device remains open
        assert device.is_open is True

        # Force closing baseboard releases physical handle
        await device.close(force=True)
        assert device.is_open is False
        assert mock_dll.CH347CloseDevice.called
