"""
Unit tests for CH347 Multi-Protocol Bridge (DLL probing, device lifecycle, I2C, SPI, GPIO).
"""
from __future__ import annotations

import asyncio
import os
import sys
from unittest.mock import MagicMock, patch
import pytest

import cio
from cio.backends.ch347 import (
    Ch347Device,
    Ch347DeviceTransport,
    Ch347GpioPin,
    Ch347I2cTransport,
    Ch347SpiTransport,
    _find_ch347_dll_path,
    _load_ch347_dll,
    _probe_ch347,
    _scan_ch347,
)
from cio.core.exceptions import CDllMissingError, ConnectionError, IOOperationError


def test_ch347_dll_probing():
    path = _find_ch347_dll_path()
    assert path is not None
    assert "CH347" in path
    assert _probe_ch347() is True


def test_ch347_dll_probing_env_override(tmp_path):
    fake_dll = tmp_path / "fake.dll"
    fake_dll.write_text("fake")
    with patch.dict(os.environ, {"CIO_CH347_DLL": str(fake_dll)}):
        assert _find_ch347_dll_path() == str(fake_dll)


def test_ch347_dll_probing_fallback_and_none():
    with patch("cio.backends.ch347.files", side_effect=Exception("not found")):
        with patch("os.path.isfile", return_value=False):
            assert _find_ch347_dll_path() is None


def test_ch347_load_dll_none():
    with patch("cio.backends.ch347._find_ch347_dll_path", return_value=None):
        assert _load_ch347_dll() is None
        assert _probe_ch347() is False


def test_ch347_scan_graceful():
    devices = cio.scan("ch347")
    assert isinstance(devices, list)


def test_ch347_scan_with_devices():
    mock_dll = MagicMock()
    # 模拟第 0 号设备成功，其它失败
    def fake_open(idx):
        return 123 if idx == 0 else -1

    mock_dll.CH347OpenDevice.side_effect = fake_open
    mock_dll.CH347CloseDevice.return_value = True

    def fake_get_info(idx, info_ptr):
        info_ptr._obj.ProductString = b"WCH CH347 Custom Demo"
        return 1

    mock_dll.CH347GetDeviceInfor.side_effect = fake_get_info

    with patch("cio.backends.ch347._load_ch347_dll", return_value=mock_dll):
        devs = _scan_ch347()
        assert len(devs) == 1
        assert devs[0]["index"] == 0
        assert devs[0]["description"] == "WCH CH347 Custom Demo"

    # 模拟 DLL 为 None
    with patch("cio.backends.ch347._load_ch347_dll", return_value=None):
        assert _scan_ch347() == []


def test_ch347_url_factory_parsing():
    base = cio.connect("ch347://0")
    assert isinstance(base, Ch347DeviceTransport)
    assert base.dev_index == 0

    i2c = cio.connect("i2c+ch347://0?frequency=400000")
    assert isinstance(i2c, Ch347I2cTransport)
    assert i2c.frequency == 400000

    spi = cio.connect("spi+ch347://0?frequency=15000000&mode=0&cs=1")
    assert isinstance(spi, Ch347SpiTransport)
    assert spi.frequency == 15000000
    assert spi.mode == 0
    assert spi.cs == 1

    gpio = cio.connect("gpio+ch347://0?pin=4")
    assert isinstance(gpio, Ch347GpioPin)
    assert gpio.pin == 4


@pytest.mark.asyncio
async def test_ch347_open_failure_raises_actionable_error():
    mock_dll = MagicMock()
    mock_dll.CH347OpenDevice.return_value = -1

    device = Ch347Device(dev_index=99)
    with patch("cio.backends.ch347._load_ch347_dll", return_value=mock_dll):
        with pytest.raises(ConnectionError) as exc_info:
            await device.open()
        assert "CH341PAR" in str(exc_info.value)
        assert "Mode 1" in str(exc_info.value)

    # 模拟 DLL 缺失
    device_missing = Ch347Device(dev_index=98)
    with patch("cio.backends.ch347._load_ch347_dll", return_value=None):
        with pytest.raises(CDllMissingError):
            await device_missing.open()


@pytest.mark.asyncio
async def test_ch347_ownership_and_borrowing_lifecycle():
    mock_dll = MagicMock()
    mock_dll.CH347OpenDevice.return_value = 100
    mock_dll.CH347CloseDevice.return_value = True
    mock_dll.CH347I2C_Set.return_value = True

    device = Ch347Device(dev_index=88)
    with patch("cio.backends.ch347._load_ch347_dll", return_value=mock_dll):
        # 1. 衍生信道
        i2c = device.i2c(frequency=400_000)
        spi = device.spi(cs=0)
        gpio = device.gpio(pin=3)

        assert i2c._borrowed is True
        assert spi._borrowed is True
        assert gpio._borrowed is True

        # 重入打开 device
        await device.open()
        assert device._ref_count == 1
        await device.open()
        assert device._ref_count == 2

        # 正常关闭一次引用计数
        await device.close(force=False)
        assert device.is_open is True

        # 打开 I2C 信道
        await i2c.open()
        assert device.is_open is True
        assert i2c.is_open is True

        # 2. 关闭借用的 I2C 信道，底层物理底座必须保持开启
        await i2c.close()
        assert i2c.is_open is False
        assert device.is_open is True
        mock_dll.CH347CloseDevice.assert_not_called()

        # 3. 强制关闭底座
        await device.close(force=True)
        assert device.is_open is False
        mock_dll.CH347CloseDevice.assert_called_once_with(88)

        # 再次 close 不抛错
        await device.close()


@pytest.mark.asyncio
async def test_ch347_device_transport_wrapper():
    mock_dll = MagicMock()
    mock_dll.CH347OpenDevice.return_value = 100
    mock_dll.CH347CloseDevice.return_value = True

    with patch("cio.backends.ch347._load_ch347_dll", return_value=mock_dll):
        transport = cio.ch347(index=2)
        assert isinstance(transport, Ch347DeviceTransport)
        assert transport.is_open is False

        await transport.open()
        assert transport.is_open is True

        # 测试衍生
        assert isinstance(transport.i2c(), Ch347I2cTransport)
        assert isinstance(transport.spi(), Ch347SpiTransport)
        assert isinstance(transport.gpio(), Ch347GpioPin)

        with pytest.raises(NotImplementedError):
            await transport._write_impl(b"test")
        with pytest.raises(NotImplementedError):
            await transport._read_impl(10)

        await transport.close()
        assert transport.is_open is False


@pytest.mark.asyncio
async def test_ch347_i2c_operations_mocked():
    mock_dll = MagicMock()
    mock_dll.CH347OpenDevice.return_value = 100
    mock_dll.CH347CloseDevice.return_value = True
    mock_dll.CH347I2C_Set.return_value = True

    # 模拟 StreamI2C 成功
    def fake_stream_i2c(idx, wlen, wbuf, rlen, rbuf):
        if rlen > 0 and rbuf:
            for i in range(rlen):
                rbuf[i] = 0xAB + i
        return 1

    def fake_stream_i2c_ret_ack(idx, wlen, wbuf, rlen, rbuf, ack_ptr):
        if ack_ptr:
            ack_ptr._obj.value = 1
        return 1

    def fake_read_data(idx, rbuf, rlen):
        if rlen:
            rlen._obj.value = 1
        if rbuf:
            rbuf[0] = 1
        return 1

    mock_dll.CH347StreamI2C.side_effect = fake_stream_i2c
    mock_dll.CH347StreamI2C_RetACK.side_effect = fake_stream_i2c_ret_ack
    mock_dll.CH347WriteData.return_value = 1
    mock_dll.CH347ReadData.side_effect = fake_read_data

    device = Ch347Device(dev_index=77)
    with patch("cio.backends.ch347._load_ch347_dll", return_value=mock_dll):
        # 覆盖所有 4 个速度分支
        for freq, expected_mode in [(10_000, 0), (80_000, 1), (300_000, 2), (800_000, 3)]:
            i2c_test = Ch347I2cTransport(device=device, frequency=freq)
            await i2c_test.open()
            mock_dll.CH347I2C_Set.assert_called_with(77, expected_mode)
            # 重入 open 测试
            await i2c_test.open()
            await i2c_test.close()
            # 重入 close 测试
            await i2c_test.close()

        i2c = device.i2c(frequency=400_000)

        # 1. 异步写
        written = await i2c.write(0x50, [0x01, 0x02, 0x03])
        assert written == 3

        # 2. 异步读
        data = await i2c.read(0x50, nbytes=2)
        assert data == bytes([0xAB, 0xAC])

        # 3. 寄存器读 (原子事务)
        reg_data = await i2c.read_reg(0x50, reg=0x0100, nbytes=2, reg_len=2)
        assert reg_data == bytes([0xAB, 0xAC])

        # 4. 寄存器写与校验
        written_reg = await i2c.write_reg(0x50, reg=0x0100, data=[0xAB, 0xAC], verify=True)
        assert written_reg == 2

        # 5. 总线扫描
        addrs = await i2c.scan()
        assert len(addrs) > 0

        # 6. 非借用模式 close
        standalone_i2c = Ch347I2cTransport(device=0, borrowed=False)
        await standalone_i2c.open()
        await standalone_i2c.close()


@pytest.mark.asyncio
async def test_ch347_i2c_failures():
    mock_dll = MagicMock()
    mock_dll.CH347OpenDevice.return_value = 100
    mock_dll.CH347CloseDevice.return_value = True

    # 1. 设置速率失败
    mock_dll.CH347I2C_Set.return_value = False
    device = Ch347Device(dev_index=76)
    with patch("cio.backends.ch347._load_ch347_dll", return_value=mock_dll):
        i2c = device.i2c(frequency=400_000)
        with pytest.raises(IOOperationError):
            await i2c.open()

    # 2. 读写失败
    mock_dll.CH347I2C_Set.return_value = True
    mock_dll.CH347StreamI2C.return_value = 0
    with patch("cio.backends.ch347._load_ch347_dll", return_value=mock_dll):
        i2c = device.i2c(frequency=400_000)
        with pytest.raises(IOOperationError):
            await i2c.write(0x50, b"fail")
        with pytest.raises(IOOperationError):
            await i2c.read(0x50, 1)
        with pytest.raises(IOOperationError):
            await i2c.read_reg(0x50, 0x01, 1)


def test_ch347_i2c_sync_wrapper():
    mock_dll = MagicMock()
    mock_dll.CH347OpenDevice.return_value = 100
    mock_dll.CH347CloseDevice.return_value = True
    mock_dll.CH347I2C_Set.return_value = True

    def fake_stream_i2c(idx, wlen, wbuf, rlen, rbuf):
        if rlen > 0 and rbuf:
            rbuf[0] = 0x42
        return 1

    mock_dll.CH347StreamI2C.side_effect = fake_stream_i2c

    device = Ch347Device(dev_index=66)
    with patch("cio.backends.ch347._load_ch347_dll", return_value=mock_dll):
        i2c = device.i2c(frequency=100_000)
        with i2c as sync_i2c:
            sync_i2c.write(0x57, [0xAA])
            res = sync_i2c.read(0x57, 1)
            assert res == b"\x42"


@pytest.mark.asyncio
async def test_ch347_spi_operations_mocked():
    mock_dll = MagicMock()
    mock_dll.CH347OpenDevice.return_value = 100
    mock_dll.CH347CloseDevice.return_value = True
    mock_dll.CH347SPI_Init.return_value = True

    def fake_spi_writeread(idx, cs, length, io_buf):
        for i in range(length):
            io_buf[i] = (io_buf[i] + 1) & 0xFF
        return 1

    mock_dll.CH347SPI_WriteRead.side_effect = fake_spi_writeread

    device = Ch347Device(dev_index=55)
    with patch("cio.backends.ch347._load_ch347_dll", return_value=mock_dll):
        # 覆盖所有 SPI 频率分支
        freq_list = [
            65_000_000, 35_000_000, 16_000_000, 8_000_000,
            4_000_000, 2_000_000, 1_000_000, 400_000
        ]
        for f in freq_list:
            s = Ch347SpiTransport(device=device, frequency=f)
            await s.open()
            # 重入 open
            await s.open()
            await s.close()
            # 重入 close
            await s.close()

        spi = device.spi(cs=0, frequency=15_000_000, mode=0)

        # 空数据传输
        assert await spi.transfer(b"") == b""

        # 全双工传输
        rx = await spi.transfer(bytes([0x10, 0x20, 0x30]))
        assert rx == bytes([0x11, 0x21, 0x31])

        # 单向写
        wlen = await spi.write(bytes([0x01, 0x02]))
        assert wlen == 2

        # 同步视图传输
        with spi as sync_spi:
            sync_rx = sync_spi.transfer([0x50])
            assert sync_rx == bytes([0x51])

        # 独立非借用 close
        standalone_spi = Ch347SpiTransport(device=0, borrowed=False)
        await standalone_spi.open()
        await standalone_spi.close()


@pytest.mark.asyncio
async def test_ch347_spi_failures():
    mock_dll = MagicMock()
    mock_dll.CH347OpenDevice.return_value = 100
    mock_dll.CH347CloseDevice.return_value = True

    # 1. 初始化失败
    mock_dll.CH347SPI_Init.return_value = False
    device = Ch347Device(dev_index=54)
    with patch("cio.backends.ch347._load_ch347_dll", return_value=mock_dll):
        spi = device.spi()
        with pytest.raises(IOOperationError):
            await spi.open()

    # 2. 传输失败
    mock_dll.CH347SPI_Init.return_value = True
    mock_dll.CH347SPI_WriteRead.return_value = 0
    with patch("cio.backends.ch347._load_ch347_dll", return_value=mock_dll):
        spi = device.spi()
        with pytest.raises(IOOperationError):
            await spi.transfer(b"test")


@pytest.mark.asyncio
async def test_ch347_gpio_operations_mocked():
    mock_dll = MagicMock()
    mock_dll.CH347OpenDevice.return_value = 100
    mock_dll.CH347CloseDevice.return_value = True
    mock_dll.CH347GPIO_Set.return_value = True

    current_level = 0

    def fake_gpio_get(idx, dir_ptr, data_ptr):
        nonlocal current_level
        data_ptr._obj.value = current_level
        return 1

    def fake_gpio_set(idx, enable, dir_out, data_out):
        nonlocal current_level
        current_level = data_out
        return 1

    mock_dll.CH347GPIO_Get.side_effect = fake_gpio_get
    mock_dll.CH347GPIO_Set.side_effect = fake_gpio_set

    device = Ch347Device(dev_index=44)
    with patch("cio.backends.ch347._load_ch347_dll", return_value=mock_dll):
        pin = device.gpio(pin=2)

        await pin.open()
        assert pin.is_open is True
        # 重入 open
        await pin.open()

        # 1. 异步设置电平
        await pin.set_high()
        level = await pin.read_level()
        assert level is True

        await pin.set_low()
        level = await pin.read_level()
        assert level is False

        # 2. 翻转
        await pin.toggle()
        level = await pin.read_level()
        assert level is True

        # 3. 同步视图
        pin.sync.set_low()
        assert pin.sync.read_level() is False

        # 4. wait_for_edge
        # 触发 rising 边沿
        async def trigger_rising():
            await asyncio.sleep(0.02)
            current_level = 1 << 2
            mock_dll.CH347GPIO_Get.side_effect = lambda idx, d, dp: setattr(dp._obj, 'value', current_level) or 1

        current_level = 0
        t1 = asyncio.create_task(trigger_rising())
        res = await pin.wait_for_edge(edge="rising", timeout=0.1)
        assert res is True
        await t1

        # 触发 falling 边沿
        async def trigger_falling():
            await asyncio.sleep(0.02)
            current_level = 0
            mock_dll.CH347GPIO_Get.side_effect = lambda idx, d, dp: setattr(dp._obj, 'value', current_level) or 1

        current_level = 1 << 2
        t2 = asyncio.create_task(trigger_falling())
        res = await pin.wait_for_edge(edge="falling", timeout=0.1)
        assert res is True
        await t2

        # 触发 both 边沿
        t3 = asyncio.create_task(trigger_rising())
        res = await pin.wait_for_edge(edge="both", timeout=0.1)
        assert res is True
        await t3

        # 超时
        res_timeout = await pin.wait_for_edge(edge="rising", timeout=0.03)
        assert res_timeout is False

        await pin.close()
        # 重入 close
        await pin.close()

        # 独立非借用 pin close
        standalone_pin = Ch347GpioPin(device=0, pin=1, borrowed=False)
        await standalone_pin.open()
        await standalone_pin.close()


@pytest.mark.asyncio
async def test_ch347_gpio_failures():
    mock_dll = MagicMock()
    mock_dll.CH347OpenDevice.return_value = 100
    mock_dll.CH347CloseDevice.return_value = True

    device = Ch347Device(dev_index=43)
    # 1. set_high / set_low 失败
    mock_dll.CH347GPIO_Set.return_value = False
    with patch("cio.backends.ch347._load_ch347_dll", return_value=mock_dll):
        pin = device.gpio(pin=2)
        with pytest.raises(IOOperationError):
            await pin.set_high()
        with pytest.raises(IOOperationError):
            await pin.set_low()

    # 2. read_level 失败
    mock_dll.CH347GPIO_Get.return_value = False
    with patch("cio.backends.ch347._load_ch347_dll", return_value=mock_dll):
        pin = device.gpio(pin=2)
        with pytest.raises(IOOperationError):
            await pin.read_level()
