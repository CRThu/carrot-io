"""
Unit tests for URL factory & top-level connect API.
"""
import pytest
import cio
from cio.composite.rpc import RpcRemoteTransport
from cio.composite.spi import AsyncSpiBridge
from cio.core.exceptions import InvalidUrlError


def test_factory_connect_tcp():
    dev = cio.connect("tcp://192.168.1.50:5025")
    assert dev.host == "192.168.1.50"
    assert dev.port == 5025


def test_factory_connect_serial():
    dev = cio.connect("serial://COM3?baud=115200")
    assert dev.port == "COM3"
    assert dev.baudrate == 115200


def test_factory_composite_spi_tcp():
    dev = cio.connect("spi+tcp://192.168.1.100:5025")
    assert isinstance(dev, AsyncSpiBridge)
    assert dev.transport.host == "192.168.1.100"
    assert dev.transport.port == 5025


def test_factory_composite_spi_tcp_query():
    dev = cio.connect("spi+tcp://192.168.1.100:5025?timeout=2.5")
    assert isinstance(dev, AsyncSpiBridge)
    assert dev.transport.host == "192.168.1.100"
    assert dev.transport.port == 5025
    assert dev.transport.timeout == 2.5


def test_factory_composite_i2c_tcp():
    from cio.composite.i2c import AsyncI2cBridge

    dev = cio.connect("i2c+tcp://192.168.1.100:5025?timeout=1.5&reg_len=2")
    assert isinstance(dev, AsyncI2cBridge)
    assert dev.transport.host == "192.168.1.100"
    assert dev.transport.port == 5025
    assert dev.transport.timeout == 1.5
    assert dev.default_reg_len == 2


def test_factory_composite_rpc_proxy():
    dev = cio.connect("rpc+tcp://192.168.1.100:8000/5025")
    assert isinstance(dev, RpcRemoteTransport)
    assert dev.host == "192.168.1.100"
    assert dev.port == 8000
    assert dev.target_url == "tcp://5025"


def test_factory_invalid_url():
    with pytest.raises(InvalidUrlError):
        cio.connect("invalid_scheme_xyz://123")


def test_top_level_factory_helpers():
    ser = cio.serial(port="COM5", baud=9600)
    assert ser.port == "COM5"
    assert ser.baudrate == 9600

    ft = cio.ftdi(url="ftdi://ftdi:232h/2", baud=57600)
    assert ft.url == "ftdi://ftdi:232h/2"
    assert ft.baudrate == 57600

