"""
Unit tests for VISA Backend (Mocked, Zero-Hardware, CI-Safe).
"""
import sys
from unittest.mock import MagicMock, patch
import pytest

import cio
from cio.backends.visa import VisaTransport, _probe_visa, _scan_visa
from cio.core.exceptions import (
    CDllMissingError,
    ConnectionError,
    PythonPackageMissingError,
    ReadTimeoutError,
    WriteTimeoutError,
)


def test_visa_url_resolution():
    dev1 = cio.connect("visa://USB0::0x2A8D::0x9007::MY63160152::INSTR?timeout=3.5")
    assert isinstance(dev1, VisaTransport)
    assert dev1.resource_name == "USB0::0x2A8D::0x9007::MY63160152::INSTR"
    assert dev1.timeout == 3.5
    assert "visa" in dev1.capabilities
    assert "stream" in dev1.capabilities

    dev2 = cio.connect("gpib://GPIB0::2::INSTR")
    assert isinstance(dev2, VisaTransport)
    assert dev2.resource_name == "GPIB0::2::INSTR"
    assert dev2.timeout == 5.0  # 工业仪表 5.0s 特殊默认超时
    assert dev2.buffer_size == 16 * 1024 * 1024  # 默认 16MB 缓冲区

    dev3 = cio.connect("vxi://TCPIP0::192.168.1.100::inst0::INSTR")
    assert isinstance(dev3, VisaTransport)
    assert dev3.resource_name == "TCPIP0::192.168.1.100::inst0::INSTR"
    assert dev3.timeout == 5.0


def test_visa_helper_factory():
    dev = cio.visa("USB0::0x1AB1::0x04CE::DS1ZA123456789::INSTR")
    assert isinstance(dev, VisaTransport)
    assert dev.resource_name == "USB0::0x1AB1::0x04CE::DS1ZA123456789::INSTR"
    assert dev.timeout == 5.0  # 缺省时默认 5.0
    assert dev.buffer_size == 16 * 1024 * 1024

    dev_custom = cio.visa("USB0::0x1AB1::0x04CE::DS1ZA123456789::INSTR", timeout=2.0)
    assert dev_custom.timeout == 2.0


@pytest.mark.asyncio
async def test_visa_mock_io_operations():
    mock_rm = MagicMock()
    mock_inst = MagicMock()
    mock_rm.open_resource.return_value = mock_inst

    mock_inst.write_raw.side_effect = lambda d: len(d)
    mock_inst.read_raw.return_value = b"MOCK_SCOPE_V1.0\n"

    with patch("pyvisa.ResourceManager", return_value=mock_rm):
        transport = VisaTransport(resource_name="MOCK::INSTR", timeout=1.5)
        await transport.open()
        assert transport.is_open

        # 1. Raw write & read
        w_len = await transport.write(b"*IDN?\n")
        assert w_len == 6
        mock_inst.write_raw.assert_called_with(b"*IDN?\n")

        data = await transport.read()
        assert data == b"MOCK_SCOPE_V1.0\n"

        # 2. Query
        resp = await transport.query(b"*IDN?\n")
        assert resp == b"MOCK_SCOPE_V1.0\n"

        # 3. String command & query (SCPI overloaded support)
        w_str = await transport.write("*RST")
        assert w_str == 5
        mock_inst.write_raw.assert_called_with(b"*RST\n")

        ans_str = await transport.query("*IDN?")
        assert ans_str == "MOCK_SCOPE_V1.0"

        # 4. History log check
        assert len(transport.history()) >= 4

        await transport.close()
        assert not transport.is_open
        mock_inst.close.assert_called_once()
        mock_rm.close.assert_called_once()


def test_visa_sync_wrapper_mock():
    mock_rm = MagicMock()
    mock_inst = MagicMock()
    mock_rm.open_resource.return_value = mock_inst
    mock_inst.write_raw.side_effect = lambda d: len(d)
    mock_inst.read_raw.return_value = b"SYNC_RESULT\n"

    with patch("pyvisa.ResourceManager", return_value=mock_rm):
        with cio.visa("MOCK::SCOPE", timeout=2.0) as scope:
            ans = scope.query("*IDN?")
            assert ans == "SYNC_RESULT"
            history = scope.dump_history()
            assert "*IDN?" in history
            assert "SYNC_RESULT" in history


@pytest.mark.asyncio
async def test_visa_timeout_mapping():
    import pyvisa

    mock_rm = MagicMock()
    mock_inst = MagicMock()
    mock_rm.open_resource.return_value = mock_inst

    tmo_error = pyvisa.errors.VisaIOError(pyvisa.constants.StatusCode.error_timeout)
    mock_inst.write_raw.side_effect = tmo_error
    mock_inst.read_raw.side_effect = tmo_error

    with patch("pyvisa.ResourceManager", return_value=mock_rm):
        transport = VisaTransport(resource_name="MOCK::INSTR")
        await transport.open()

        with pytest.raises(WriteTimeoutError):
            await transport.write(b"*IDN?\n")

        with pytest.raises(ReadTimeoutError):
            await transport.read()

        await transport.close()


@pytest.mark.asyncio
async def test_visa_library_error_cdll_missing():
    import pyvisa

    lib_error = pyvisa.errors.LibraryError("Could not open visa library")

    with patch("pyvisa.ResourceManager", side_effect=lib_error):
        transport = VisaTransport(resource_name="MOCK::INSTR")
        with pytest.raises(CDllMissingError) as exc_info:
            await transport.open()
        assert "visa32.dll" in str(exc_info.value)


@pytest.mark.asyncio
async def test_visa_package_missing():
    with patch.dict(sys.modules, {"pyvisa": None}):
        transport = VisaTransport(resource_name="MOCK::INSTR")
        with pytest.raises(PythonPackageMissingError) as exc_info:
            await transport.open()
        assert "pyvisa" in exc_info.value.package_name


def test_visa_scan_mocked():
    mock_rm = MagicMock()
    mock_rm.list_resources.return_value = ("USB0::0x1234::INSTR", "TCPIP0::192.168.1.5::INSTR")

    with patch("pyvisa.ResourceManager", return_value=mock_rm):
        with patch("cio.backends.visa._probe_visa", return_value=True):
            scanned = _scan_visa()
            assert len(scanned) == 2
            assert scanned[0]["resource_name"] == "USB0::0x1234::INSTR"
            assert scanned[1]["resource_name"] == "TCPIP0::192.168.1.5::INSTR"


@pytest.mark.asyncio
async def test_visa_lifecycle_idempotent_open_close():
    mock_rm = MagicMock()
    mock_inst = MagicMock()
    mock_rm.open_resource.return_value = mock_inst

    with patch("pyvisa.ResourceManager", return_value=mock_rm):
        transport = VisaTransport(resource_name="MOCK::IDEMPOTENT")
        await transport.open()
        assert transport.is_open
        # 重复调用 open 应幂等返回
        await transport.open()
        mock_rm.open_resource.assert_called_once()

        await transport.close()
        assert not transport.is_open
        # 重复调用 close 应安全返回
        await transport.close()


@pytest.mark.asyncio
async def test_visa_options_and_termination():
    mock_rm = MagicMock()
    mock_inst = MagicMock()
    mock_rm.open_resource.return_value = mock_inst

    with patch("pyvisa.ResourceManager", return_value=mock_rm):
        transport = VisaTransport(
            resource_name="MOCK::CONFIG",
            backend="@py",
            timeout=2.5,
            read_termination="\n",
            write_termination="\r\n",
            chunk_size=8192,
        )
        await transport.open()
        assert mock_inst.timeout == 2500
        assert mock_inst.read_termination == "\n"
        assert mock_inst.write_termination == "\r\n"
        assert mock_inst.chunk_size == 8192

        # 验证自定义 write_termination 自动补齐
        mock_inst.write_raw.side_effect = lambda d: len(d)
        await transport.write("COMMAND")
        mock_inst.write_raw.assert_called_with(b"COMMAND\r\n")

        await transport.close()


@pytest.mark.asyncio
async def test_visa_open_failures():
    mock_rm = MagicMock()
    mock_rm.open_resource.side_effect = RuntimeError("Resource busy")

    # 1. 打开具体仪器失败
    with patch("pyvisa.ResourceManager", return_value=mock_rm):
        transport = VisaTransport(resource_name="MOCK::FAIL")
        with pytest.raises(ConnectionError) as exc_info:
            await transport.open()
        assert "Failed to open VISA resource" in str(exc_info.value)
        mock_rm.close.assert_called_once()

    # 2. 初始化 ResourceManager 失败
    with patch("pyvisa.ResourceManager", side_effect=RuntimeError("RM crashed")):
        transport = VisaTransport(resource_name="MOCK::FAIL")
        with pytest.raises(ConnectionError) as exc_info:
            await transport.open()
        assert "Failed to initialize VISA ResourceManager" in str(exc_info.value)


@pytest.mark.asyncio
async def test_visa_unopened_and_general_io_error():
    import pyvisa

    transport = VisaTransport(resource_name="MOCK::IO_ERR")

    # 1. 未 open 时直接调用 _write_impl / _read_impl
    with pytest.raises(ConnectionError):
        await transport._write_impl(b"TEST")
    with pytest.raises(ConnectionError):
        await transport._read_impl(10)

    # 2. 非超时的 VisaIOError 通信故障
    mock_rm = MagicMock()
    mock_inst = MagicMock()
    mock_rm.open_resource.return_value = mock_inst

    io_err = pyvisa.errors.VisaIOError(pyvisa.constants.StatusCode.error_system_error)
    mock_inst.write_raw.side_effect = io_err
    mock_inst.read_raw.side_effect = io_err

    with patch("pyvisa.ResourceManager", return_value=mock_rm):
        await transport.open()
        with pytest.raises(ConnectionError):
            await transport.write(b"FAIL")
        with pytest.raises(ConnectionError):
            await transport.read()
        await transport.close()


def test_visa_probe_and_scan_exceptions():
    # 验证 probe 与 scan 抛异常时能够静默容错降级
    with patch("pyvisa.ResourceManager", side_effect=Exception("Hardware bus locked")):
        assert not _probe_visa()
        assert _scan_visa() == []


@pytest.mark.asyncio
async def test_visa_clear_and_flush():
    mock_rm = MagicMock()
    mock_inst = MagicMock()
    mock_rm.open_resource.return_value = mock_inst

    transport = VisaTransport(resource_name="MOCK::CLEAR")

    # 未打开时调用不抛异常
    await transport.clear()
    await transport.flush()

    with patch("pyvisa.ResourceManager", return_value=mock_rm):
        await transport.open()
        await transport.clear()
        mock_inst.clear.assert_called_once()

        await transport.flush()
        assert mock_inst.clear.call_count == 2
        await transport.close()


