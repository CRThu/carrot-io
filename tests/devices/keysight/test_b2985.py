"""
Unit tests for Keysight B2980 Series (B2985 / B2985B) Driver.
CI-safe, Zero-hardware, Mocked.
"""
import math
from unittest.mock import MagicMock, patch

import pytest

import cio
from cio.devices import keysight
from cio.testing.mock import MockTransport


def test_keysight_b2985_parse_val_edge_cases():
    # 1. 多字段列表 (Sense 格式回包) 提取首字段
    raw_multi = "+2.060190E+01,-2.000000E-12,+1.000000E+09,+1.000000E+00"
    assert keysight.B2985._parse_val(raw_multi) == pytest.approx(20.6019)

    # 2. 硬件溢出值 (+9.91E37 / -9.91E37) 转换为 NaN
    assert math.isnan(keysight.B2985._parse_val("+9.910000E+37"))
    assert math.isnan(keysight.B2985._parse_val("-9.910000E+37"))
    assert math.isnan(keysight.B2985._parse_val("+9.91E+37,0,0"))

    # 3. 正常微弱数值
    assert keysight.B2985._parse_val("-1.500000E-14") == pytest.approx(-1.5e-14)


@pytest.mark.asyncio
async def test_keysight_b2985_common_interfaces_async_mock():
    mock_t = MockTransport()
    await mock_t.open()

    mock_t.auto_replies = {
        b"*IDN?\n": b"Keysight Technologies,B2985B,MY00000000,1.0\n",
        b":MEAS?\n": b"-1.234000E-12\n",
        b":MEAS:CURR?\n": b"-1.500000E-12\n",
        b":MEAS:VOLT?\n": b"+3.300000E+00\n",
        b":MEAS:RES?\n": b"+1.000000E+09\n",
        b":MEAS:CHAR?\n": b"+5.000000E-09\n",
        b":SOUR:VOLT?\n": b"+1.000000E+01\n",
        b":OUTP?\n": b"1\n",
        b":SOUR:VOLT:RLIM:STAT?\n": b"1\n",
    }

    # 推荐标准调用范式: keysight.B2985(mock_t)
    smu = keysight.B2985(mock_t)

    # 1. 常用测量
    assert await smu.measure() == pytest.approx(-1.234e-12)
    assert await smu.measure_current() == pytest.approx(-1.5e-12)
    assert await smu.measure_voltage() == pytest.approx(3.3)
    assert await smu.measure_resistance() == pytest.approx(1.0e9)
    assert await smu.measure_charge() == pytest.approx(5.0e-9)

    # 2. 测量配置（量程、NPLC、零点校准）
    await smu.set_auto_range(True, "CURR")
    await smu.set_nplc(1.0, "CURR")
    await smu.set_zero_correct(True)

    # 3. 电压源与保护
    await smu.source_voltage(10.0, output=True, protection=True)
    assert await smu.get_source_voltage() == pytest.approx(10.0)
    assert await smu.get_output() is True
    assert await smu.get_protection() is True

    await smu.set_output(False)
    await mock_t.close()


@pytest.mark.asyncio
async def test_keysight_b2985_protection_and_sourcing_sequencing():
    mock_t = MockTransport()
    await mock_t.open()

    smu = keysight.B2985(mock_t)

    # Case 1: 开启输出并同时开启保护 -> 应先配保护与电压，最后开输出
    mock_t.tx_history.clear()
    mock_t.auto_replies = {
        b":OUTP?\n": b"0\n",
    }
    await smu.source_voltage(1.0, output=True, protection=True)
    tx_cmds = [d.decode("ascii").strip() for d in mock_t.tx_history]
    assert ":SOUR:VOLT:RLIM:STAT ON" in tx_cmds
    assert ":SOUR:VOLT 1.0" in tx_cmds
    assert ":OUTP ON" in tx_cmds
    # :OUTP ON 必须在最后执行
    assert tx_cmds.index(":SOUR:VOLT 1.0") < tx_cmds.index(":OUTP ON")

    # Case 2: 关闭输出并同时关闭保护 -> 必须先关输出，再改保护
    mock_t.tx_history.clear()
    mock_t.auto_replies = {
        b":OUTP?\n": b"0\n",
    }
    await smu.source_voltage(0.0, output=False, protection=False)
    tx_cmds = [d.decode("ascii").strip() for d in mock_t.tx_history]
    assert ":OUTP OFF" in tx_cmds
    assert ":SOUR:VOLT:RLIM:STAT OFF" in tx_cmds
    # :OUTP OFF 必须在 :SOUR:VOLT:RLIM:STAT OFF 之前执行
    assert tx_cmds.index(":OUTP OFF") < tx_cmds.index(":SOUR:VOLT:RLIM:STAT OFF")

    # Case 3: 当输出已处于 ON 状态时单独调用 set_protection()
    # 驱动必须自动临时断开继电器 -> 改保护 -> 恢复闭合继电器
    mock_t.tx_history.clear()
    mock_t.auto_replies = {
        b":OUTP?\n": b"1\n",
    }
    await smu.set_protection(True)
    tx_cmds = [d.decode("ascii").strip() for d in mock_t.tx_history]
    assert tx_cmds == [":OUTP?", ":OUTP OFF", ":SOUR:VOLT:RLIM:STAT ON", ":OUTP ON"]

    await mock_t.close()


def test_keysight_b2985_sync_full_facade():
    mock_t = MockTransport()
    mock_t.auto_replies = {
        b"*IDN?\n": b"Keysight Technologies,B2985B,MY61390950,1.0\n",
        b"*OPC?\n": b"1\n",
        b":SYST:ERR?\n": b'+0,"No error"\n',
        b":MEAS?\n": b"+1.234000E-05\n",
        b":MEAS:CURR?\n": b"+1.234000E-09\n",
        b":MEAS:VOLT?\n": b"+5.000000E+00\n",
        b":MEAS:RES?\n": b"+1.000000E+11\n",
        b":MEAS:CHAR?\n": b"+2.000000E-08\n",
        b":SOUR:VOLT?\n": b"+2.500000E+00\n",
        b":OUTP?\n": b"1\n",
        b":SOUR:VOLT:RLIM:STAT?\n": b"0\n",
    }

    with keysight.B2985(mock_t) as smu:
        assert smu.is_open
        assert smu.idn() == "Keysight Technologies,B2985B,MY61390950,1.0"
        assert smu.wait_opc() is True

        # 测量
        assert smu.measure() == pytest.approx(1.234e-5)
        assert smu.measure_current() == pytest.approx(1.234e-9)
        assert smu.measure_voltage() == pytest.approx(5.0)
        assert smu.measure_resistance() == pytest.approx(1.0e11)
        assert smu.measure_charge() == pytest.approx(2.0e-8)

        # 参数配置
        smu.set_auto_range(False, "VOLT")
        smu.set_nplc(2.0, "VOLT")
        smu.set_zero_correct(False)

        # 电压源
        smu.source_voltage(2.5, output=True, protection=False)
        assert smu.get_source_voltage() == pytest.approx(2.5)
        assert smu.get_output() is True
        assert smu.get_protection() is False

        assert smu.errors() == []


def test_keysight_b2985_direct_locator_lifecycle_mocked():
    mock_rm = MagicMock()
    mock_inst = MagicMock()
    mock_rm.open_resource.return_value = mock_inst

    mock_inst.write_raw.side_effect = lambda d: len(d)
    mock_inst.read_raw.return_value = b"Keysight Technologies,B2985B,MY12345,5.0\n"

    with patch("pyvisa.ResourceManager", return_value=mock_rm):
        with keysight.B2985("visa:USB0::0x2A8D::0x9A01::MY12345::INSTR") as smu:
            assert smu.is_open
            idn = smu.idn()
            assert "B2985B" in idn
        assert not smu.is_open
