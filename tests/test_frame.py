"""
Unit tests for Hardware Control Frame Protocol (HardwareFrame, FrameCodec, Composite Bridges).
"""
from __future__ import annotations

import asyncio
import pytest
import cio
from cio.composite.frame import AsyncFrameBridge
from cio.composite.gpio import AsyncGpioBridge
from cio.composite.i2c import AsyncI2cBridge
from cio.composite.spi import AsyncSpiBridge
from cio.core.exceptions import FrameChecksumError, ReadTimeoutError, TransportError
from cio.core.frame import (
    ACTION_CFG,
    ACTION_READ_DATA,
    ACTION_READ_REG,
    ACTION_TRANSFER,
    ACTION_WRITE_DATA,
    ACTION_WRITE_REG,
    CFG_GPIO_MODE,
    CFG_GPIO_PULL,
    CFG_I2C_SPEED,
    CFG_SPI_BIT_ORDER,
    CFG_SPI_MODE,
    CFG_SPI_SPEED,
    PERIPHERAL_GPIO,
    PERIPHERAL_I2C,
    PERIPHERAL_SPI,
    STATUS_ERR,
    STATUS_OK,
    FrameCodec,
    HardwareFrame,
    calc_crc16_modbus,
)

from cio.testing.mock import MockGpioPin, MockTransport


def test_calc_crc16_modbus():
    # Known test vector: b"123456789" -> CRC16-MODBUS is 0x4B37
    test_data = b"123456789"
    crc = calc_crc16_modbus(test_data)
    assert crc == 0x4B37


def test_frame_codec_encode_decode():
    codec = FrameCodec()
    frame = HardwareFrame(
        protocol=0x10,
        peripheral=PERIPHERAL_I2C,
        action=ACTION_READ_DATA,
        bus=1,
        addr=0x68,
        status=STATUS_OK,
        payload=b"\x00\x02",
    )

    encoded = codec.encode(frame)
    assert encoded.startswith(b"<")
    assert encoded.endswith(b">")
    assert len(encoded) == 9 + 2 + 3  # 14 bytes

    buf = bytearray(encoded)
    decoded, consumed = codec.decode(buf)
    assert consumed == 14
    assert decoded is not None
    assert decoded.protocol == 0x10
    assert decoded.peripheral == PERIPHERAL_I2C
    assert decoded.action == ACTION_READ_DATA
    assert decoded.bus == 1
    assert decoded.addr == 0x68
    assert decoded.status == STATUS_OK
    assert decoded.payload == b"\x00\x02"


def test_frame_codec_invalid_type():
    codec = FrameCodec()
    with pytest.raises(TypeError):
        codec.encode("invalid_string_type")


def test_frame_codec_resync():
    codec = FrameCodec()
    frame = HardwareFrame(peripheral=PERIPHERAL_GPIO, action=ACTION_WRITE_DATA, bus=5, payload=b"\x01")
    encoded = codec.encode(frame)


    # Prepend garbage data before header
    buf = bytearray(b"GARBAGE_HEADER" + encoded)
    decoded, consumed = codec.decode(buf)
    assert decoded is None
    assert consumed == len("GARBAGE_HEADER")  # Skips until '<'

    # Now decode starting from header
    del buf[:consumed]
    decoded, consumed = codec.decode(buf)
    assert decoded is not None
    assert decoded.peripheral == PERIPHERAL_GPIO
    assert decoded.bus == 5
    assert decoded.payload == b"\x01"


def test_frame_codec_crc_mismatch():
    codec = FrameCodec()
    frame = HardwareFrame(peripheral=PERIPHERAL_SPI, action=ACTION_TRANSFER, bus=0, payload=b"\xAA\xBB")
    encoded = bytearray(codec.encode(frame))

    # Corrupt a payload byte
    encoded[9] ^= 0xFF

    with pytest.raises(FrameChecksumError):
        codec.decode(encoded)


@pytest.mark.asyncio
async def test_gpio_bridge():
    mock_trans = MockTransport()
    gpio = AsyncGpioBridge(mock_trans, pin=5)
    await gpio.open()
    assert gpio.bridge.is_open

    codec = FrameCodec()

    # 1. Test set_high & set_low
    resp_frame = HardwareFrame(peripheral=PERIPHERAL_GPIO, action=ACTION_WRITE_DATA, bus=5, status=STATUS_OK)
    mock_trans.feed_read_data(codec.encode(resp_frame))
    await gpio.set_high()

    mock_trans.feed_read_data(codec.encode(resp_frame))
    await gpio.set_low()

    # 2. Test read_level & toggle
    resp_high = HardwareFrame(peripheral=PERIPHERAL_GPIO, action=ACTION_READ_DATA, bus=5, status=STATUS_OK, payload=b"\x01")
    mock_trans.feed_read_data(codec.encode(resp_high))
    assert await gpio.read_level() is True

    # Toggle from HIGH -> LOW
    mock_trans.feed_read_data(codec.encode(resp_high))
    mock_trans.feed_read_data(codec.encode(resp_frame))
    await gpio.toggle()

    # 3. Test config_mode & config_pull
    mock_trans.feed_read_data(codec.encode(resp_frame))
    await gpio.config_mode(1)

    mock_trans.feed_read_data(codec.encode(resp_frame))
    await gpio.config_pull(2)
    tx_cfg, _ = codec.decode(bytearray(mock_trans.write_history[-1]))
    assert tx_cfg.payload == bytes([CFG_GPIO_PULL, 2])


@pytest.mark.asyncio
async def test_gpio_wait_for_edge():
    mock_trans = MockTransport()
    gpio = AsyncGpioBridge(mock_trans, pin=5)
    await gpio.open()
    codec = FrameCodec()

    resp_low = HardwareFrame(peripheral=PERIPHERAL_GPIO, action=ACTION_READ_DATA, bus=5, status=STATUS_OK, payload=b"\x00")
    resp_high = HardwareFrame(peripheral=PERIPHERAL_GPIO, action=ACTION_READ_DATA, bus=5, status=STATUS_OK, payload=b"\x01")

    # Initial level LOW, then transitions to HIGH (rising edge)
    mock_trans.feed_read_data(codec.encode(resp_low))
    mock_trans.feed_read_data(codec.encode(resp_high))

    res = await gpio.wait_for_edge(edge="rising", timeout=1.0)
    assert res is True


@pytest.mark.asyncio
async def test_i2c_bridge():
    mock_trans = MockTransport()
    i2c = AsyncI2cBridge(mock_trans, bus=0)
    await i2c.open()
    assert i2c.is_open

    codec = FrameCodec()

    # 1. Test read_from & write_to
    resp_read = HardwareFrame(peripheral=PERIPHERAL_I2C, action=ACTION_READ_DATA, bus=0, addr=0x68, status=STATUS_OK, payload=b"\x12\x34")
    mock_trans.feed_read_data(codec.encode(resp_read))
    assert await i2c.read_from(0x68, 2) == b"\x12\x34"

    resp_write = HardwareFrame(peripheral=PERIPHERAL_I2C, action=ACTION_WRITE_DATA, bus=0, addr=0x68, status=STATUS_OK)
    mock_trans.feed_read_data(codec.encode(resp_write))
    assert await i2c.write_to(0x68, b"\x00") == 1


    # 2. Test read_reg & write_reg with regfile
    resp_reg_r = HardwareFrame(peripheral=PERIPHERAL_I2C, action=ACTION_READ_REG, bus=0, addr=0x68, status=STATUS_OK, payload=b"\x75")
    mock_trans.feed_read_data(codec.encode(resp_reg_r))
    reg_val = await i2c.read_reg(0x68, reg=0x75, nbytes=1, regfile=1)
    assert reg_val == b"\x75"
    tx_r, _ = codec.decode(bytearray(mock_trans.write_history[-1]))
    assert tx_r.action == ACTION_READ_REG
    assert tx_r.payload == b"\x00\x00\x00\x01\x00\x00\x00\x75\x00\x01"

    resp_reg_w = HardwareFrame(peripheral=PERIPHERAL_I2C, action=ACTION_WRITE_REG, bus=0, addr=0x68, status=STATUS_OK)
    mock_trans.feed_read_data(codec.encode(resp_reg_w))
    written = await i2c.write_reg(0x68, reg=0x10, data=b"\xAA\xBB", regfile=0)
    assert written == 2
    tx_w, _ = codec.decode(bytearray(mock_trans.write_history[-1]))
    assert tx_w.action == ACTION_WRITE_REG
    assert tx_w.payload == b"\x00\x00\x00\x00\x00\x00\x00\x10\xAA\xBB"

    # 3. Test config_speed
    resp_cfg = HardwareFrame(peripheral=PERIPHERAL_I2C, action=ACTION_CFG, status=STATUS_OK)
    mock_trans.feed_read_data(codec.encode(resp_cfg))
    await i2c.config_speed(400000)
    tx_cfg, _ = codec.decode(bytearray(mock_trans.write_history[-1]))
    assert tx_cfg.payload == bytes([CFG_I2C_SPEED]) + (400000).to_bytes(4, "big")


@pytest.mark.asyncio
async def test_spi_bridge():
    mock_trans = MockTransport()
    cs_pin = MockGpioPin(initial_state=True)
    spi = AsyncSpiBridge(mock_trans, cs_pin=cs_pin, bus=0, cs=1)
    await spi.open()
    assert spi.is_open

    codec = FrameCodec()

    # 1. Test transfer
    resp_tx = HardwareFrame(peripheral=PERIPHERAL_SPI, action=ACTION_TRANSFER, bus=1, status=STATUS_OK, payload=b"\xFF\xAB")
    mock_trans.feed_read_data(codec.encode(resp_tx))
    rx = await spi.transfer(b"\x90\x00")
    assert rx == b"\xFF\xAB"
    assert cs_pin.state_history == [True, False, True]

    # 2. Test config_mode, config_bit_order, config_speed
    resp_cfg = HardwareFrame(peripheral=PERIPHERAL_SPI, action=ACTION_CFG, bus=0, status=STATUS_OK)
    
    mock_trans.feed_read_data(codec.encode(resp_cfg))
    await spi.config_mode(3)
    tx_m, _ = codec.decode(bytearray(mock_trans.write_history[-1]))
    assert tx_m.payload == bytes([CFG_SPI_MODE, 3])

    mock_trans.feed_read_data(codec.encode(resp_cfg))
    await spi.config_bit_order(1)
    tx_o, _ = codec.decode(bytearray(mock_trans.write_history[-1]))
    assert tx_o.payload == bytes([CFG_SPI_BIT_ORDER, 1])

    mock_trans.feed_read_data(codec.encode(resp_cfg))
    await spi.config_speed(10_000_000)
    tx_s, _ = codec.decode(bytearray(mock_trans.write_history[-1]))
    assert tx_s.payload == bytes([CFG_SPI_SPEED]) + (10_000_000).to_bytes(4, "big")

    # Close bridge
    await spi.close()
    assert not spi.is_open


@pytest.mark.asyncio
async def test_frame_bridge_timeout():
    mock_trans = MockTransport()
    frame_bridge = AsyncFrameBridge(mock_trans, timeout=0.05)
    await frame_bridge.open()

    req = HardwareFrame(peripheral=PERIPHERAL_GPIO, action=ACTION_READ_DATA, bus=1)
    with pytest.raises(ReadTimeoutError):
        await frame_bridge.request_frame(req)

    await frame_bridge.close()



def test_factory_frame_connect():
    dev_gpio = cio.connect("gpio+tcp://127.0.0.1:5025")
    assert isinstance(dev_gpio, AsyncGpioBridge)

    dev_i2c = cio.connect("i2c+tcp://127.0.0.1:5025")
    assert isinstance(dev_i2c, AsyncI2cBridge)

    dev_spi = cio.connect("spi+tcp://127.0.0.1:5025")
    assert isinstance(dev_spi, AsyncSpiBridge)

    dev_frame = cio.connect("frame+tcp://127.0.0.1:5025")
    assert isinstance(dev_frame, AsyncFrameBridge)
