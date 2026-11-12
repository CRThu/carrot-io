"""
Unit tests for cio.devices base abstractions (BaseScpiDevice, BaseVisaDevice).
"""
import asyncio
from unittest.mock import MagicMock

import pytest

from cio.devices import BaseScpiDevice, BaseVisaDevice, keysight
from cio.testing.mock import MockTransport


def test_base_scpi_device_alias():
    assert BaseVisaDevice is BaseScpiDevice
    assert hasattr(keysight, "B2985")


@pytest.mark.asyncio
async def test_base_scpi_device_async_mock():
    mock_t = MockTransport()
    await mock_t.open()

    mock_t.auto_replies = {
        b"*IDN?\n": b"MOCK_MANUFACTURER,MODEL_123,SN001,V1.0\n",
        b"*OPC?\n": b"1\n",
        b":SYST:ERR?\n": b'+0,"No error"\n',
        b"CUSTOM?\n": b"CUSTOM_REPLY\n",
    }

    dev = BaseScpiDevice(mock_t)
    assert dev.is_open

    # 1. Standard IEEE 488.2 commands
    idn = await dev.idn()
    assert idn == "MOCK_MANUFACTURER,MODEL_123,SN001,V1.0"

    opc = await dev.wait_opc()
    assert opc is True

    errs = await dev.errors()
    assert errs == []

    # 2. Passthrough query and write
    await dev.reset()
    assert any(b"*RST" in d for d in mock_t.tx_history)

    ans = await dev.query("CUSTOM?")
    assert ans == "CUSTOM_REPLY"

    await mock_t.close()


def test_base_scpi_device_sync_usage():
    mock_t = MockTransport()
    mock_t.auto_replies = {
        b"*IDN?\n": b"SYNC_MODEL,SN123\n",
        b"*OPC?\n": b"1\n",
        b":SYST:ERR?\n": b'+0,"No error"\n',
    }

    # 传入实际支持层实例并在同步上下文中调用
    with BaseScpiDevice(mock_t) as dev:
        assert dev.idn() == "SYNC_MODEL,SN123"
        assert dev.wait_opc() is True
        assert dev.errors() == []

    # 传入已包装的同步支持层 (SyncTransportWrapper)
    with mock_t.sync as sync_t:
        with BaseScpiDevice(sync_t) as dev:
            assert dev.idn() == "SYNC_MODEL,SN123"
            assert dev.wait_opc() is True
            assert dev.errors() == []


@pytest.mark.asyncio
async def test_base_scpi_device_error_drain():
    mock_t = MockTransport()
    await mock_t.open()

    # 模拟连续两次错误后返回正常 "+0,No error"
    mock_t.auto_replies[b":SYST:ERR?\n"] = [
        b'-113,"Undefined header"\n',
        b'-213,"Output relay must be off"\n',
        b'+0,"No error"\n',
    ]

    dev = BaseScpiDevice(mock_t)
    errs = await dev.errors()
    assert len(errs) == 2
    assert '-113,"Undefined header"' in errs[0]
    assert '-213,"Output relay must be off"' in errs[1]

    # 再次查询已空
    mock_t.auto_replies[b":SYST:ERR?\n"] = b'+0,"No error"\n'
    assert await dev.errors() == []
    await mock_t.close()


@pytest.mark.asyncio
async def test_base_scpi_device_clear_dispatch():
    # 1. 普通 StreamTransport (无 visa capability): 发送 *CLS
    mock_t = MockTransport()
    await mock_t.open()
    dev = BaseScpiDevice(mock_t)
    await dev.clear()
    assert any(b"*CLS" in d for d in mock_t.tx_history)
    await mock_t.close()

    # 2. 具备 "visa" capability: 优先调用底层 clear()
    class MockVisaTransport(MockTransport):
        def __init__(self):
            super().__init__()
            self.clear_called = False

        @property
        def capabilities(self) -> frozenset[str]:
            return frozenset({"stream", "visa"})

        async def clear(self) -> None:
            self.clear_called = True

    mock_visa_t = MockVisaTransport()
    await mock_visa_t.open()
    dev_visa = BaseScpiDevice(mock_visa_t)
    await dev_visa.clear()
    assert mock_visa_t.clear_called is True
    await mock_visa_t.close()


def test_base_scpi_device_trace_and_history():
    mock_t = MockTransport()
    mock_t.auto_replies = {
        b"*IDN?\n": b"Keysight,B2985B\n",
        b"*OPC?\n": b"1\n",
        b":SYST:ERR?\n": b'+0,"No error"\n',
    }

    dev = BaseScpiDevice(mock_t)
    dev.trace = True
    assert dev.trace.enabled is True
    assert bool(dev.trace) is True
    dev.trace = False
    assert dev.trace.enabled is False
    assert bool(dev.trace) is False

    with dev as sync_dev:
        sync_dev.idn()
        sync_dev.wait_opc()
        history = sync_dev.dump_history()
        assert "*IDN?" in history
        assert "*OPC?" in history
        assert len(sync_dev.history()) > 0

        sync_dev.clear_history()
        assert len(sync_dev.history()) == 0
