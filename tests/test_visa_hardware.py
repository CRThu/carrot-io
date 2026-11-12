"""
Hardware-in-the-loop (HIL) integration tests for VISA instruments (e.g. Oscilloscopes).
NOTE: Marked with pytest.mark.hardware. Excluded from default CI runs via `pytest -m "not hardware"`.
"""
import os
import pytest

import cio


def _get_target_visa_resource() -> str:
    """获取物理 VISA 资源名：优先读取环境变量，其次自动扫描系统已连接设备。"""
    env_target = os.environ.get("CIO_VISA_DEVICE")
    if env_target:
        return env_target

    scanned = cio.scan("visa")
    if scanned:
        return scanned[0]["resource_name"]

    pytest.skip("No physical VISA instrument detected on this machine. Skipping hardware test.")


@pytest.mark.hardware
def test_visa_hardware_idn_query_sync():
    """验证真实物理示波器通过标准同步上下文与 SCPI *IDN? 响应。"""
    res_name = _get_target_visa_resource()

    with cio.visa(res_name, timeout=5.0) as scope:
        assert scope.is_open
        assert "visa" in scope.capabilities
        assert "stream" in scope.capabilities

        # 1. 询问仪器识别码 (直接传入 SCPI 字符串，自动返回解码后的 str)
        idn = scope.query("*IDN?")
        assert len(idn) > 0

        # 2. 检查通讯历史记录
        history = scope.dump_history()
        assert "*IDN?" in history

        # 3. 使用 cio 验证契约进行断言
        cio.check(len(idn) > 0, name="Instrument *IDN? response should not be empty")


@pytest.mark.hardware
@pytest.mark.asyncio
async def test_visa_hardware_async_query():
    """验证真实物理示波器原生纯异步调用。"""
    res_name = _get_target_visa_resource()

    async with cio.visa(res_name, timeout=5.0) as scope:
        assert scope.is_open

        # 1. 异步清除状态 (*CLS)
        await scope.write("*CLS")

        # 2. 异步查询 (*IDN?)
        idn = await scope.query("*IDN?")
        assert len(idn) > 0


@pytest.mark.hardware
def test_keysight_b2985_hardware_device_driver():
    """验证真实物理 Keysight B2985B 静电计通过专属高层驱动 keysight.B2985 进行常用测量与源控制。"""
    from cio.devices import keysight

    res_name = _get_target_visa_resource()

    # 传入底层实际 VISA 支持层
    with cio.visa(res_name, timeout=5.0) as inst:
        with keysight.B2985(inst) as smu:
            assert smu.is_open
            assert "scpi" in smu.capabilities
            assert "visa" in smu.capabilities

            idn = smu.idn()
            if "B298" not in idn:
                pytest.skip(f"Connected instrument is not a Keysight B2980 series (found: {idn}). Skipping.")

            # 1. 基础识别与状态就绪
            assert "Keysight" in idn
            assert smu.wait_opc() is True

            # 2. 常用微弱物理量测量
            curr = smu.measure_current()
            assert isinstance(curr, float)

            volt = smu.measure_voltage()
            assert isinstance(volt, float)

            res = smu.measure_resistance()
            assert isinstance(res, float)

            meas = smu.measure()
            assert isinstance(meas, float)

            # 3. 测量参数与零点校准
            smu.set_nplc(1.0, "CURR")
            smu.set_auto_range(True, "CURR")
            smu.set_zero_correct(True)
            smu.set_zero_correct(False)

            # 4. 电源设置与开关 (同时配置 1.0V、开启输出、启用 20MΩ 保护电阻)
            smu.source_voltage(1.0, output=True, protection=True)
            assert smu.get_source_voltage() == pytest.approx(1.0)
            assert smu.get_output() is True
            assert smu.get_protection() is True

            # 5. 安全复原
            smu.source_voltage(0.0, output=False, protection=False)
            assert smu.get_output() is False
            assert smu.get_protection() is False
            assert smu.get_source_voltage() == pytest.approx(0.0)
            assert smu.errors() == []



