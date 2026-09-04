"""
Physical hardware-in-the-loop tests for CarrotBridge (ASCII Protocol MCU/Bridge).
Tests actual physical I2C bus with Sensirion STS30, STS40 sensors, and EEPROM.

How to run:
    # 运行所有物理硬件测试
    uv run pytest -m "hardware" -v

    # 运行指定 CarrotBridge 硬件测试
    uv run pytest tests/test_carrotbridge_hardware.py -v

    # 常规测试与 CI 自动排除
    uv run pytest -m "not hardware" -v
"""
from __future__ import annotations

import asyncio
import os
import time
import pytest

import cio
from cio import check, require, verify


def crc8(data: bytes) -> int:
    """Sensirion CRC-8 polynomial 0x31 (x^8 + x^5 + x^4 + 1), init 0xFF."""
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ 0x31) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


def get_carrot_url() -> str:
    port = os.environ.get("CIO_CARROT_PORT", "COM3")
    baud = os.environ.get("CIO_CARROT_BAUD", "2000000")
    return f"i2c+serial://{port}?baud={baud}&reg_len=2"


@pytest.fixture(scope="module")
def carrot_i2c():
    """Module-level fixture to probe physical CarrotBridge presence."""
    url = get_carrot_url()
    try:
        dev = cio.connect(url, timeout=1.0)
        # Probe connection and bus scan
        with dev as i2c:
            addrs = i2c.scan(timeout=1.5)
            if not addrs:
                pytest.skip(f"CarrotBridge on {url} responded but found no I2C devices.")
        return url
    except Exception as e:
        pytest.skip(f"Physical CarrotBridge hardware not available ({url}): {e}")


# =========================================================================
# 硬件测试 1: 设备存在性与 I2C 总线扫描
# =========================================================================
@pytest.mark.hardware
def test_hardware_carrotbridge_scan(carrot_i2c):
    """Verify physical CarrotBridge scans I2C bus and finds STS30/STS40 sensors."""
    with cio.connect(carrot_i2c) as i2c:
        addrs = i2c.scan()
        assert len(addrs) >= 2, f"Expected at least 2 I2C devices, found: {[hex(a) for a in addrs]}"
        # Ensure either STS30 (0x4A) or STS40 (0x46) is present
        assert 0x4A in addrs or 0x46 in addrs, f"No STS sensor found in {[hex(a) for a in addrs]}"


# =========================================================================
# 硬件测试 2: Sensirion STS30 (0x4A) 测温与 CRC8 校验
# =========================================================================
@pytest.mark.hardware
def test_hardware_carrotbridge_sts30_temperature(carrot_i2c):
    """Verify STS30 temperature measurement, valid CRC8 checksum, and reasonable room temp."""
    with cio.connect(carrot_i2c) as i2c:
        addrs = i2c.scan()
        if 0x4A not in addrs:
            pytest.skip("STS30 (0x4A) not detected on I2C bus")

        # 触发单次高重复性测量 (0x2400)
        i2c.write(0x4A, b"\x24\x00")
        time.sleep(0.02)  # 转换时间 15ms
        raw = i2c.read(0x4A, 6)

        assert len(raw) == 6, f"Expected 6 bytes, got {len(raw)}"
        t_raw = (raw[0] << 8) | raw[1]
        t_crc = raw[2]
        calc_crc = crc8(raw[:2])

        # 断言 CRC-8 校验正确
        assert t_crc == calc_crc, f"STS30 CRC8 mismatch: expected 0x{calc_crc:02X}, got 0x{t_crc:02X}"

        # 断言物理温度合理性 (15℃ ~ 45℃ 室温范围)
        temp_c = -45.0 + 175.0 * (t_raw / 65535.0)
        assert 15.0 <= temp_c <= 45.0, f"STS30 temperature {temp_c:.2f}℃ outside reasonable room temp!"


# =========================================================================
# 硬件测试 3: Sensirion STS40 (0x46) 测温与 CRC8 校验
# =========================================================================
@pytest.mark.hardware
def test_hardware_carrotbridge_sts40_temperature(carrot_i2c):
    """Verify STS40 temperature measurement, valid CRC8 checksum, and reasonable room temp."""
    with cio.connect(carrot_i2c) as i2c:
        addrs = i2c.scan()
        if 0x46 not in addrs:
            pytest.skip("STS40 (0x46) not detected on I2C bus")

        # 触发高精度测温指令 (0xFD)
        i2c.write(0x46, b"\xFD")
        time.sleep(0.015)  # 转换时间 8.2ms
        raw = i2c.read(0x46, 6)

        assert len(raw) >= 3, f"Expected at least 3 bytes, got {len(raw)}"
        t_raw = (raw[0] << 8) | raw[1]
        t_crc = raw[2]
        calc_crc = crc8(raw[:2])

        # 断言 CRC-8 校验正确
        assert t_crc == calc_crc, f"STS40 CRC8 mismatch: expected 0x{calc_crc:02X}, got 0x{t_crc:02X}"

        # 断言物理温度合理性 (15℃ ~ 45℃ 室温范围)
        temp_c = -45.0 + 175.0 * (t_raw / 65535.0)
        assert 15.0 <= temp_c <= 45.0, f"STS40 temperature {temp_c:.2f}℃ outside reasonable room temp!"


# =========================================================================
# 硬件测试 4: 双传感器物理一致性（STS30 与 STS40 温差对比）
# =========================================================================
@pytest.mark.hardware
def test_hardware_carrotbridge_dual_sensors_consistency(carrot_i2c):
    """Verify physical temperature consistency between STS30 and STS40 in the same environment."""
    with cio.connect(carrot_i2c) as i2c:
        addrs = i2c.scan()
        if 0x4A not in addrs or 0x46 not in addrs:
            pytest.skip("Both STS30 (0x4A) and STS40 (0x46) required for consistency test")

        # 读取 STS30
        i2c.write(0x4A, b"\x24\x00")
        time.sleep(0.02)
        raw30 = i2c.read(0x4A, 3)
        t30 = -45.0 + 175.0 * (((raw30[0] << 8) | raw30[1]) / 65535.0)

        # 读取 STS40
        i2c.write(0x46, b"\xFD")
        time.sleep(0.015)
        raw40 = i2c.read(0x46, 3)
        t40 = -45.0 + 175.0 * (((raw40[0] << 8) | raw40[1]) / 65535.0)

        # 物理断言：同环境下的高精度温度计温差应小于 1.0 ℃
        delta = abs(t30 - t40)
        assert delta < 1.0, f"Temperature delta too high between sensors: STS30={t30:.2f}℃, STS40={t40:.2f}℃, delta={delta:.2f}℃"


# =========================================================================
# 硬件测试 5: 板载 EEPROM (0x57) 寄存器级读写回环
# =========================================================================
@pytest.mark.hardware
def test_hardware_carrotbridge_eeprom_roundtrip(carrot_i2c):
    """Verify EEPROM register-level read/write transaction if 0x57 is present."""
    with cio.connect(carrot_i2c) as i2c:
        addrs = i2c.scan()
        if 0x57 not in addrs:
            pytest.skip("EEPROM (0x57) not detected on I2C bus")

        # 读取地址 0x00 处 4 字节数据
        original = i2c.read_reg(0x57, 0x0000, 4)
        assert len(original) == 4
