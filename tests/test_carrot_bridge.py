"""
Comprehensive Unit and Integration tests for CarrotBridge and composite bridges.
"""
import asyncio
import pytest
from cio.composite.carrotbridge import CarrotBridge
from cio.composite.gpio import AsyncGpioBridge
from cio.composite.i2c import AsyncI2cBridge
from cio.composite.spi import AsyncSpiBridge
from cio.core.exceptions import ReadTimeoutError
from cio.testing.mock import MockGpioPin, MockTransport


@pytest.mark.asyncio
async def test_carrot_bridge_basic_call():
    pipe = MockTransport()
    bridge = CarrotBridge(pipe)
    await bridge.open()

    async def device_response():
        while True:
            if pipe.tx_history:
                tx_cmd = pipe.tx_history[-1]
                if b"Motor_SetSpeed(1, 100)" in tx_cmd:
                    pipe.push_rx(b"[RETURN]: 0\n")
                    break
            await asyncio.sleep(0.01)

    task = asyncio.create_task(device_response())
    res = await bridge.call("Motor_SetSpeed", 1, 100)
    await task

    assert res == 0
    assert pipe.tx_history[0] == b"Motor_SetSpeed(1, 100)\n"
    entries = bridge.logger.get_entries()
    assert len(entries) == 2
    assert entries[0].direction == "OUT"
    assert b"Motor_SetSpeed" in entries[0].data
    assert entries[1].direction == "IN"
    assert b"[RETURN]: 0" in entries[1].data
    await bridge.close()


@pytest.mark.asyncio
async def test_carrot_bridge_to_bytes_helper():
    assert CarrotBridge.to_bytes(b"\x12\x34", 2) == b"\x12\x34"
    assert CarrotBridge.to_bytes(0x1234, 2) == b"\x12\x34"
    assert CarrotBridge.to_bytes("0x1234", 2) == b"\x12\x34"
    assert CarrotBridge.to_bytes("1234", 2) == b"\x12\x34"
    assert CarrotBridge.to_bytes("ABC", 2) == b"\x0A\xBC"
    assert CarrotBridge.to_bytes(None, 2) == b""


@pytest.mark.asyncio
async def test_carrot_bridge_non_return_logging():
    pipe = MockTransport()
    bridge = CarrotBridge(pipe)
    await bridge.open()

    pipe.push_rx(b"[MSG]: System initialization complete\n")
    pipe.push_rx(b"DEBUG: Sensor calibrated\n")

    await asyncio.sleep(0.05)

    entries = bridge.logger.get_entries()
    assert len(entries) >= 2
    assert b"[MSG]: System initialization complete" in entries[0].data
    assert b"DEBUG: Sensor calibrated" in entries[1].data

    await bridge.close()


@pytest.mark.asyncio
async def test_gpio_bridge_full_coverage():
    pipe = MockTransport()
    gpio = AsyncGpioBridge(pipe, pin="A1")
    await gpio.bridge.open()

    # 1. set_high & set_low & toggle
    async def respond_gpio_ops():
        # set_high
        while not pipe.tx_history:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"IO.W(A1, 1)\n"
        pipe.push_rx(b"[RETURN]: 1\n")

        # read_level (for toggle)
        while len(pipe.tx_history) < 2:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"IO.R(A1)\n"
        pipe.push_rx(b"[RETURN]: 1\n")

        # set_low (triggered by toggle)
        while len(pipe.tx_history) < 3:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"IO.W(A1, 0)\n"
        pipe.push_rx(b"[RETURN]: 0\n")

        # config_mode
        while len(pipe.tx_history) < 4:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"IO.MODE(A1, OUT,PP)\n"
        pipe.push_rx(b"[RETURN]: 0\n")

        # config_pull
        while len(pipe.tx_history) < 5:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"IO.PULL(A1, UP)\n"
        pipe.push_rx(b"[RETURN]: 0\n")

    t = asyncio.create_task(respond_gpio_ops())
    await gpio.set_high()
    await gpio.toggle()
    await gpio.config_mode("OUT,PP")
    await gpio.config_pull("UP")
    await t

    await gpio.bridge.close()


@pytest.mark.asyncio
async def test_i2c_bridge_full_coverage():
    pipe = MockTransport()
    i2c = AsyncI2cBridge(pipe)
    await i2c.open()

    async def respond_i2c_ops():
        # write_to
        while not pipe.tx_history:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"IIC.W(0x50, 0x1234, 2)\n"
        pipe.push_rx(b"[RETURN]: 2\n")

        # read_from
        while len(pipe.tx_history) < 2:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"IIC.R(0x50, 2)\n"
        pipe.push_rx(b"[RETURN]: 0xAABB\n")

        # config_speed
        while len(pipe.tx_history) < 3:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"IIC.SPEED(400000)\n"
        pipe.push_rx(b"[RETURN]: 0\n")

        # write_reg (write_to 0x50, 0x01AA)
        while len(pipe.tx_history) < 4:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"IIC.W(0x50, 0x01AA, 2)\n"
        pipe.push_rx(b"[RETURN]: 2\n")

    t = asyncio.create_task(respond_i2c_ops())
    written = await i2c.write(0x50, b"\x12\x34")
    assert written == 2

    data = await i2c.read(0x50, 2)
    assert data == b"\xAA\xBB"

    await i2c.config_speed(400000)
    await i2c.write_reg(0x50, reg=1, data=b"\xAA")

    await t
    await i2c.close()


@pytest.mark.asyncio
async def test_i2c_bridge_reg_len_default_and_override():
    pipe = MockTransport()
    i2c = AsyncI2cBridge(pipe, reg_len=2)
    await i2c.open()

    async def respond_ops():
        # 1. 继承默认 reg_len=2：读 0xFFB1 自动发 2 字节地址 0xFFB1
        while not pipe.tx_history:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"IIC.W(0x57, 0xFFB1, 2)\n"
        pipe.push_rx(b"[RETURN]: 2\n")

        while len(pipe.tx_history) < 2:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"IIC.R(0x57, 1)\n"
        pipe.push_rx(b"[RETURN]: 0x07\n")

        # 2. 单次覆盖 reg_len=1：写 0x05 显式传 reg_len=1 应该发 1 字节地址 0x05
        while len(pipe.tx_history) < 3:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"IIC.W(0x57, 0x05AA, 2)\n"
        pipe.push_rx(b"[RETURN]: 2\n")

    t = asyncio.create_task(respond_ops())
    data = await i2c.read_reg(0x57, 0xFFB1, nbytes=1)
    assert data == b"\x07"

    await i2c.write_reg(0x57, 0x05, b"\xAA", reg_len=1)
    await t
    await i2c.close()


@pytest.mark.asyncio
async def test_spi_bridge_full_coverage():
    pipe = MockTransport()
    cs = MockGpioPin(initial_state=True)
    spi = AsyncSpiBridge(pipe, cs_pin=cs, cs=0)
    await spi.open()

    async def respond_spi_ops():
        # write
        while not pipe.tx_history:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"SPI.W(0, 0x1122, 2)\n"
        pipe.push_rx(b"[RETURN]: 2\n")

        # read
        while len(pipe.tx_history) < 2:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"SPI.R(0, 2)\n"
        pipe.push_rx(b"[RETURN]: 0x3344\n")

        # transfer
        while len(pipe.tx_history) < 3:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"SPI.T(0, 0xABCD, 2)\n"
        pipe.push_rx(b"[RETURN]: 0x5566\n")

        # config_mode
        while len(pipe.tx_history) < 4:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"SPI.MODE(0, 1)\n"
        pipe.push_rx(b"[RETURN]: 0\n")

        # config_speed
        while len(pipe.tx_history) < 5:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"SPI.SPEED(10000000)\n"
        pipe.push_rx(b"[RETURN]: 0\n")

    t = asyncio.create_task(respond_spi_ops())
    w = await spi.write(b"\x11\x22")
    assert w == 2

    r = await spi.read(2)
    assert r == b"\x33\x44"

    tx = await spi.transfer(b"\xAB\xCD")
    assert tx == b"\x55\x66"

    await spi.config_mode(0, 1)
    await spi.config_speed(10000000)

    await t
    await spi.close()


@pytest.mark.asyncio
async def test_carrot_bridge_timeout():
    pipe = MockTransport()
    bridge = CarrotBridge(pipe, timeout=0.1)
    await bridge.open()

    with pytest.raises(ReadTimeoutError):
        await bridge.call("SlowFunction")

    await bridge.close()


def test_i2c_bridge_sync_context():
    pipe = MockTransport()
    pipe.add_auto_reply(b"IIC.W(0x57, 0x0102, 2)\n", b"[RETURN]: 2\n")
    pipe.add_auto_reply(b"IIC.R(0x57, 1)\n", b"[RETURN]: 0xAA\n")
    pipe.add_auto_reply(b"IIC.W(0x57, 0x1122, 2)\n", b"[RETURN]: 2\n")
    i2c = AsyncI2cBridge(pipe, reg_len=2)

    with i2c as dev:
        data = dev.read_reg(0x57, 0x0102, nbytes=1)
        assert data == b"\xAA"

        # Direct multi-argument read and write
        r = dev.read(0x57, 1)
        assert r == b"\xAA"

        w = dev.write(0x57, [0x11, 0x22])
        assert w == 2


def test_spi_bridge_sync_context():
    pipe = MockTransport()
    pipe.add_auto_reply(b"SPI.T(0, 0x1234, 2)\n", b"[RETURN]: 0x5678\n")
    spi = AsyncSpiBridge(pipe, cs=0)

    with spi as dev:
        rx = dev.transfer(b"\x12\x34")
        assert rx == b"\x56\x78"


def test_gpio_bridge_sync_usage():
    pipe = MockTransport()
    pipe.add_auto_reply(b"IO.W(A1, 1)\n", b"[RETURN]: 1\n")
    pipe.add_auto_reply(b"IO.R(A1)\n", b"[RETURN]: 1\n")
    gpio = AsyncGpioBridge(pipe, pin="A1")

    gpio.sync.set_high()
    assert gpio.sync.read_level() is True
