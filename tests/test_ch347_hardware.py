"""
Physical hardware-in-the-loop tests for CH347.
Separated into atomic, modular test methods for easy targeted execution.

How to run:
    # 运行所有硬件测试
    uv run pytest -m "hardware" -v

    # 运行指定测试方法
    uv run pytest tests/test_ch347_hardware.py -k "test_hardware_ch347_i2c_sht30_standalone" -v

    # 常规测试自动过滤排除
    uv run pytest -m "not hardware" -v
"""
from __future__ import annotations

import asyncio
import pytest

import cio


# =========================================================================
# 硬件测试 1: 设备存在性与扫描识别
# =========================================================================
@pytest.mark.hardware
def test_hardware_ch347_detection():
    """Verify CH347 physical USB device and its dual UART ports are detected."""
    ch347_devs = cio.scan("ch347")
    if not ch347_devs:
        pytest.skip("No CH347 USB hardware device detected on this host")
    assert len(ch347_devs) > 0, "No CH347 USB base device detected!"

    serial_devs = [p for p in cio.scan("serial") if "CH347" in p.get("description", "")]
    assert len(serial_devs) >= 2, f"Expected 2 CH347 UART ports, found: {len(serial_devs)}"


# =========================================================================
# 硬件测试 2: I2C 独立通信与温湿度/温度传感器回读 (支持 SHT30 / STS30 / STS40)
# =========================================================================
@pytest.mark.hardware
@pytest.mark.asyncio
async def test_hardware_ch347_i2c_sensor_standalone():
    """Verify standalone I2C bus scan and Sensirion sensor reading."""
    if not cio.scan("ch347"):
        pytest.skip("No CH347 USB hardware device detected on this host")
    async with cio.connect("i2c+ch347://0?frequency=100000") as i2c:
        # 1. 扫描验证传感器地址 (SHT30: 0x44, STS40: 0x46, STS30: 0x4A)
        found_addrs = await i2c.scan()
        sensor_addr = next((a for a in [0x44, 0x4A, 0x46] if a in found_addrs), None)
        assert sensor_addr is not None, f"No Sensirion sensor found on I2C bus! Detected: {[hex(a) for a in found_addrs]}"

        # 2. 发送测量命令并回读
        if sensor_addr == 0x46: # STS40
            await i2c.write(sensor_addr, [0xFD])
            await asyncio.sleep(0.02)
            raw = await i2c.read(sensor_addr, 3)
        else: # SHT30 / STS30
            await i2c.write(sensor_addr, [0x24, 0x00])
            await asyncio.sleep(0.02)
            raw = await i2c.read(sensor_addr, 6 if sensor_addr == 0x44 else 3)

        assert len(raw) >= 3, f"Expected at least 3 bytes, got {len(raw)}"

        temp_raw = (raw[0] << 8) | raw[1]
        temp_c = -45.0 + 175.0 * (temp_raw / 65535.0)

        # 3. 断言物理数值合理性
        assert 0.0 < temp_c < 55.0, f"Unreasonable temperature: {temp_c} ℃"


# =========================================================================
# 硬件测试 3: 独立双串口打开与波特率设置
# =========================================================================
@pytest.mark.hardware
@pytest.mark.asyncio
async def test_hardware_ch347_uarts_standalone():
    """Verify UART-A and UART-B can be opened independently and transmit bytes."""
    serial_devs = [p for p in cio.scan("serial") if "CH347" in p.get("description", "")]
    if len(serial_devs) < 2:
        pytest.skip("Requires 2 CH347 serial ports")

    port_a = serial_devs[0]["port"]
    port_b = serial_devs[1]["port"]

    async with cio.serial(port_a, baud=115200) as uart_a, cio.serial(port_b, baud=115200) as uart_b:
        assert uart_a.is_open is True
        assert uart_b.is_open is True

        # 简单发送测试（不依赖短接）
        w1 = await uart_a.write(b"PING\n")
        w2 = await uart_b.write(b"PONG\n")
        assert w1 == 5
        assert w2 == 5


# =========================================================================
# 硬件测试 4: I2C 读 SHT30 与 双串口数据发送 同时并发运行
# =========================================================================
@pytest.mark.hardware
@pytest.mark.asyncio
async def test_hardware_ch347_concurrency_i2c_and_uarts():
    """Verify simultaneous I2C sensor reading and UART streaming without contention."""
    serial_devs = [p for p in cio.scan("serial") if "CH347" in p.get("description", "")]
    if len(serial_devs) < 2:
        pytest.skip("Requires 2 CH347 serial ports")

    port_a = serial_devs[0]["port"]
    port_b = serial_devs[1]["port"]

    i2c = cio.connect("i2c+ch347://0?frequency=100000")
    uart_a = cio.serial(port_a, baud=115200)
    uart_b = cio.serial(port_b, baud=115200)

    await i2c.open()
    await uart_a.open()
    await uart_b.open()

    found_addrs = await i2c.scan()
    sensor_addr = next((a for a in [0x44, 0x4A, 0x46] if a in found_addrs), None)
    if sensor_addr is None:
        pytest.skip("No Sensirion sensor available for concurrency test")

    i2c_samples: list[float] = []
    uart_bytes_sent = 0

    # 任务 A: I2C 连续采集 5 次
    async def i2c_task():
        for _ in range(5):
            if sensor_addr == 0x46:
                await i2c.write(sensor_addr, [0xFD])
                await asyncio.sleep(0.02)
                raw = await i2c.read(sensor_addr, 3)
            else:
                await i2c.write(sensor_addr, [0x24, 0x00])
                await asyncio.sleep(0.02)
                raw = await i2c.read(sensor_addr, 6 if sensor_addr == 0x44 else 3)
            t_raw = (raw[0] << 8) | raw[1]
            temp = -45.0 + 175.0 * (t_raw / 65535.0)
            i2c_samples.append(temp)
            await asyncio.sleep(0.03)

    # 任务 B: 串口交替持续发送数据流
    async def uart_task():
        nonlocal uart_bytes_sent
        for i in range(5):
            msg_a = f"UART_A_PACKET_{i}\n".encode("utf-8")
            msg_b = f"UART_B_PACKET_{i}\n".encode("utf-8")
            w1 = await uart_a.write(msg_a)
            w2 = await uart_b.write(msg_b)
            uart_bytes_sent += (w1 + w2)
            await asyncio.sleep(0.03)

    try:
        # 并发调度两个异步任务
        await asyncio.gather(i2c_task(), uart_task())

        # 结果断言
        assert len(i2c_samples) == 5
        assert all(0.0 < t < 55.0 for t in i2c_samples)
        assert uart_bytes_sent > 0
    finally:
        await i2c.close()
        await uart_a.close()
        await uart_b.close()


# =========================================================================
# 硬件测试 5: 双串口交叉短接回环互通测试 (需要 TXD0<->RXD1, RXD0<->TXD1 短接)
# =========================================================================
@pytest.mark.hardware
@pytest.mark.loopback
@pytest.mark.asyncio
async def test_hardware_ch347_uart_cross_loopback():
    """Full-duplex loopback verification between UART-A and UART-B (requires loopback jumper wire)."""
    serial_devs = [p for p in cio.scan("serial") if "CH347" in p.get("description", "")]
    if len(serial_devs) < 2:
        pytest.skip("Requires 2 CH347 serial ports")

    port_a = serial_devs[0]["port"]
    port_b = serial_devs[1]["port"]

    async with cio.serial(port_a, baud=115200, timeout=1.0) as uart_a, cio.serial(port_b, baud=115200, timeout=1.0) as uart_b:
        test_payload = b"CROSS_LOOPBACK_PACKET_VERIFY_OK\n"
        await uart_a.write(test_payload)
        recv = await uart_b.read(len(test_payload), timeout=1.0)
        assert recv == test_payload, f"Loopback mismatch: got {recv}, expected {test_payload}"
