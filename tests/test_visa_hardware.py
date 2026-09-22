"""
Hardware-in-the-loop (HIL) integration tests for VISA instruments (e.g. Oscilloscopes).
NOTE: Marked with pytest.mark.hardware. Excluded from default CI runs via `pytest -m "not hardware"`.
"""
import os
import pytest

import cio

pytestmark = pytest.mark.hardware


def _get_target_visa_resource() -> str:
    """获取物理 VISA 资源名：优先读取环境变量，其次自动扫描系统已连接设备。"""
    env_target = os.environ.get("CIO_VISA_DEVICE")
    if env_target:
        return env_target

    scanned = cio.scan("visa")
    if scanned:
        return scanned[0]["resource_name"]

    pytest.skip("No physical VISA instrument detected on this machine. Skipping hardware test.")


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
