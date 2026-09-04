"""
Comprehensive Unit and Integration tests for CarrotBridge and composite bridges.
"""
import asyncio
import pytest
from cio.composite.carrotbridge import CarrotBridge
from cio.composite.gpio import AsyncGpioBridge
from cio.composite.i2c import AsyncI2cBridge
from cio.composite.spi import AsyncSpiBridge
from cio.core.exceptions import IOOperationError, ReadTimeoutError
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

async def test_carrot_bridge_non_return_logging():
    pipe = MockTransport()
    bridge = CarrotBridge(pipe)
    await bridge.open()

    pipe.add_auto_reply(
        b"Init()\n",
        b"[MSG]: System initialization complete\nDEBUG: Sensor calibrated\n[RETURN]: 1\n",
    )

    res = await bridge.call("Init")
    assert res == 1

    entries = bridge.logger.get_entries()
    assert len(entries) >= 4
    assert any(b"[MSG]: System initialization complete" in e.data for e in entries)
    assert any(b"DEBUG: Sensor calibrated" in e.data for e in entries)
    assert any(b"[RETURN]: 1" in e.data for e in entries)

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

        # config_mode int mapping
        while len(pipe.tx_history) < 6:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"IO.MODE(A1, OUT,PP)\n"
        pipe.push_rx(b"[RETURN]: 0\n")

        # config_pull int mapping
        while len(pipe.tx_history) < 7:
            await asyncio.sleep(0.005)
        assert pipe.tx_history[-1] == b"IO.PULL(A1, UP)\n"
        pipe.push_rx(b"[RETURN]: 0\n")

    t = asyncio.create_task(respond_gpio_ops())
    await gpio.set_high()
    await gpio.toggle()
    await gpio.config_mode("OUT,PP")
    await gpio.config_pull("UP")
    await gpio.config_mode(1)
    await gpio.config_pull(1)
    await t

    # Edge detection tests
    pipe.tx_history.clear()
    pipe.auto_replies.clear()
    pipe.add_auto_reply(b"IO.R(A1)\n", b"[RETURN]: 0\n")

    async def simulate_pin_change():
        await asyncio.sleep(0.02)
        pipe.auto_replies.clear()
        pipe.add_auto_reply(b"IO.R(A1)\n", b"[RETURN]: 1\n")

    t_edge = asyncio.create_task(simulate_pin_change())
    assert await gpio.wait_for_edge("rising", timeout=0.1) is True
    await t_edge

    # Edge timeout
    pipe.auto_replies.clear()
    pipe.add_auto_reply(b"IO.R(A1)\n", b"[RETURN]: 0\n")
    assert await gpio.wait_for_edge("falling", timeout=0.03) is False

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


@pytest.mark.asyncio

async def test_i2c_bridge_scan_async():
    pipe = MockTransport()
    i2c = AsyncI2cBridge(pipe)
    await i2c.open()

    # 1. 扫描到多个从机
    pipe.add_auto_reply(b"IIC.SCAN()\n", b"[RETURN]: 0x50,0x57\n")
    addrs = await i2c.scan()
    assert addrs == [0x50, 0x57]

    # 2. 扫描到单个从机 (以 0x50 字符串返回)
    pipe.auto_replies.clear()
    pipe.add_auto_reply(b"IIC.SCAN()\n", b"[RETURN]: 0x50\n")
    addrs = await i2c.scan()
    assert addrs == [0x50]

    # 3. 扫描未发现从机 (以空串返回)
    pipe.auto_replies.clear()
    pipe.add_auto_reply(b"IIC.SCAN()\n", b"[RETURN]: \n")
    addrs = await i2c.scan()
    assert addrs == []

    await i2c.close()


def test_i2c_bridge_scan_sync():
    pipe = MockTransport()
    pipe.add_auto_reply(b"IIC.SCAN()\n", b"[RETURN]: 0x50,0x57\n")
    i2c = AsyncI2cBridge(pipe)

    with i2c as dev:
        addrs = dev.scan()
        assert addrs == [0x50, 0x57]


def test_carrot_bridge_sync_call():
    pipe = MockTransport()
    pipe.add_auto_reply(b"GetStatus()\n", b"[RETURN]: 1\n")
    bridge = CarrotBridge(pipe)

    with bridge as b:
        assert b.is_open
        res = b.call("GetStatus")
        assert res == 1


@pytest.mark.asyncio
async def test_carrot_bridge_borrowed_ownership_and_builder_methods():
    pipe = MockTransport()
    bridge = CarrotBridge(pipe)
    await bridge.open()
    assert bridge.is_open

    # Use builder methods to derive multiple logical protocol bridges
    i2c = bridge.i2c(bus=0)
    gpio = bridge.gpio(pin=2)
    spi = bridge.spi(bus=0)

    assert i2c._borrowed is True
    assert gpio._borrowed is True
    assert spi._borrowed is True

    # Closing a borrowed channel must NOT close the physical bridge
    await i2c.close()
    assert bridge.is_open
    assert gpio.is_open
    assert spi.is_open

    await gpio.close()
    assert bridge.is_open

    # Closing the owner bridge closes the physical pipe
    await bridge.close()
    assert not bridge.is_open
    assert not pipe.is_open


@pytest.mark.asyncio
async def test_carrot_bridge_multiplex_operations_async():
    pipe = MockTransport()
    pipe.add_auto_reply(b"IO.W(1, 1)\n", b"[RETURN]: 1\n")
    pipe.add_auto_reply(b"IO.W(1, 0)\n", b"[RETURN]: 1\n")
    pipe.add_auto_reply(b"IO.R(1)\n", b"[RETURN]: 0\n")
    pipe.add_auto_reply(b"IIC.W(0x57, 0x10, 1)\n", b"[RETURN]: 1\n")
    pipe.add_auto_reply(b"IIC.R(0x57, 1)\n", b"[RETURN]: 0x55\n")

    bridge = CarrotBridge(pipe)
    await bridge.open()

    i2c = bridge.i2c(bus=0, reg_len=1)
    gpio = bridge.gpio(pin=1)

    # 1. GPIO 操作
    await gpio.set_high()
    assert b"IO.W(1, 1)\n" in pipe.tx_history

    # 2. I2C 操作
    await i2c.write(0x57, b"\x10")
    res = await i2c.read(0x57, 1)
    assert res == b"\x55"

    # 3. 关闭 I2C，验证 GPIO 依旧可以继续操作且底层物理连接未被误杀
    await i2c.close()
    assert bridge.is_open
    assert gpio.is_open

    await gpio.set_low()
    level = await gpio.read_level()
    assert level is False
    assert b"IO.W(1, 0)\n" in pipe.tx_history
    assert b"IO.R(1)\n" in pipe.tx_history

    # 4. 彻底关闭底座
    await bridge.close()
    assert not bridge.is_open
    assert not pipe.is_open


def test_carrot_bridge_multiplex_operations_sync():
    pipe = MockTransport()
    pipe.add_auto_reply(b"IO.W(2, 1)\n", b"[RETURN]: 1\n")
    pipe.add_auto_reply(b"IO.W(2, 0)\n", b"[RETURN]: 1\n")
    pipe.add_auto_reply(b"IIC.W(0x50, 0x20, 1)\n", b"[RETURN]: 1\n")
    pipe.add_auto_reply(b"IIC.R(0x50, 1)\n", b"[RETURN]: 0xAA\n")

    bridge = CarrotBridge(pipe)

    with bridge as b:
        assert b.is_open
        gpio = b.gpio(pin=2)
        i2c = b.i2c(bus=0, reg_len=1)

        # 1. 同步 GPIO 操作
        with gpio as pin:
            pin.set_high()
        assert b"IO.W(2, 1)\n" in pipe.tx_history

        # 2. 同步 I2C 上下文
        with i2c as dev:
            dev.write(0x50, b"\x20")
            val = dev.read(0x50, 1)
            assert val == b"\xAA"

        # 3. i2c 退出后，gpio 依旧可正常操作，底层串口保持连接
        assert b.is_open
        with gpio as pin:
            pin.set_low()
        assert b"IO.W(2, 0)\n" in pipe.tx_history

    # 退出 bridge 后，物理底层彻底关闭
    assert not bridge.is_open
    assert not pipe.is_open


@pytest.mark.asyncio
async def test_carrot_bridge_fast_fail_on_error():
    """CarrotBridge must immediately raise IOOperationError on [ERROR]: response without waiting for timeout."""
    pipe = MockTransport()
    pipe.add_auto_reply(
        b"IIC.W(0x50, 0x01)\n",
        b"[ERROR]: Slave NACK detected\n",
    )
    bridge = CarrotBridge(pipe, timeout=2.0)
    await bridge.open()

    start_t = asyncio.get_running_loop().time()
    with pytest.raises(IOOperationError) as excinfo:
        await bridge.call("IIC.W", "0x50", b"\x01")
    elapsed = asyncio.get_running_loop().time() - start_t

    assert elapsed < 0.5
    assert "Slave NACK detected" in str(excinfo.value)
    assert "CarrotBridge call 'IIC.W' failed on device" in str(excinfo.value)
    await bridge.close()




