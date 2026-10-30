"""
Unit tests for Backends (TcpTransport, UdpTransport, Serial, FTDI, VISA, USB stubs, silent probes).
"""
import asyncio
import pytest
import cio
from cio.exceptions import (
    CDllMissingError,
    DriverMissingError,
    PythonPackageMissingError,
)
from cio.registry import registry


def test_registry_silent_probe():
    # 1. Scan all available devices
    all_devices = cio.scan()
    assert isinstance(all_devices, list)

    # 2. Scan specific backend name
    serial_devs = cio.scan("serial")
    assert isinstance(serial_devs, list)

    # 3. Scan specific scheme alias
    uart_devs = cio.scan("uart")
    assert isinstance(uart_devs, list)

    # 4. Scan nonexistent type gracefully
    empty_devs = cio.scan("nonexistent_kind_xyz")
    assert empty_devs == []


def test_visa_backend_error_handling():
    dev = cio.connect("visa://NONEXISTENT::1::INSTR")
    with pytest.raises((PythonPackageMissingError, CDllMissingError, DriverMissingError, ConnectionError)):
        dev.sync.open()


@pytest.mark.asyncio

async def test_tcp_udp_instantiation():
    tcp_dev = cio.tcp("127.0.0.1", 9999)
    assert tcp_dev.host == "127.0.0.1"
    assert tcp_dev.port == 9999

    udp_dev = cio.udp("127.0.0.1", 9998)
    assert udp_dev.host == "127.0.0.1"
    assert udp_dev.port == 9998


@pytest.mark.asyncio
async def test_tcp_transport_integration():
    async def handle_client(reader, writer):
        data = await reader.read(100)
        writer.write(data)
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    import asyncio

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()

    async with cio.tcp(host, port) as client:
        await client.write(b"HELLO TCP\n")
        resp = await client.read_until(b"\n", timeout=2.0)
        assert resp == b"HELLO TCP\n"

    server.close()
    await server.wait_closed()


class EchoUdpServer(asyncio.DatagramProtocol):
    def __init__(self):
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, data, addr):
        self.transport.sendto(data, addr)


@pytest.mark.asyncio
async def test_udp_transport_integration():
    import asyncio

    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        EchoUdpServer, local_addr=("127.0.0.1", 0)
    )
    host, port = transport.get_extra_info("sockname")

    async with cio.udp(host, port) as client:
        await client.write(b"HELLO UDP")
        resp = await client.read(timeout=2.0)
        assert resp == b"HELLO UDP"

        # 验证 UDP 作为 StreamTransport 支持拼包与按行切割
        await client.write(b"LINE1\nLINE2\n")
        l1 = await client.read_until(b"\n", timeout=2.0)
        assert l1 == b"LINE1\n"
        l2 = await client.read_until(b"\n", timeout=2.0)
        assert l2 == b"LINE2\n"


    transport.close()


# ==========================================
# Serial Backend Mocked Unit Tests
# ==========================================

@pytest.mark.asyncio
async def test_serial_transport_mocked_lifecycle():
    from unittest.mock import MagicMock, patch
    from cio.backends.serial import SerialTransport, _scan_serial
    from cio.exceptions import ConnectionError

    mock_serial_instance = MagicMock()
    mock_serial_instance.in_waiting = 4
    mock_serial_instance.read.return_value = b"OK\r\n"
    mock_serial_instance.write.return_value = 5

    with patch("serial.Serial", return_value=mock_serial_instance):
        st = SerialTransport(port="COM99", baud=115200)
        assert not st.is_open

        await st.open()
        assert st.is_open
        await st.open()  # idempotent

        w = await st.write(b"HELLO")
        assert w == 5
        mock_serial_instance.write.assert_called_with(b"HELLO")

        r = await st.read(4)
        assert r == b"OK\r\n"

        await st.close()
        assert not st.is_open

    # Error handling
    with patch("serial.Serial", side_effect=Exception("Permission denied")):
        st_err = SerialTransport(port="COM99")
        with pytest.raises(ConnectionError, match="Failed to open serial port"):
            await st_err.open()

    st_closed = SerialTransport(port="COM99")
    with pytest.raises(ConnectionError, match="Serial port not open"):
        await st_closed._write_impl(b"TEST")

    with pytest.raises(ConnectionError, match="Serial port not open"):
        await st_closed._read_impl(1)

    # Scan test
    mock_port = MagicMock(device="COM10", description="USB Serial", hwid="USB\\VID_1234")
    with patch("serial.tools.list_ports.comports", return_value=[mock_port]):
        ports = _scan_serial()
        assert len(ports) == 1
        assert ports[0]["port"] == "COM10"


@pytest.mark.asyncio
async def test_serial_read_impl_zero_in_waiting_requests_single_byte():
    """验证当硬件缓冲区为空 (in_waiting == 0) 时，必须且仅能请求 1 字节（哨兵唤醒），
    杜绝向 Windows 串口驱动请求大块 (如 4096) 导致触发 50ms 假超时等待。"""
    from unittest.mock import MagicMock, patch
    from cio.backends.serial import SerialTransport

    mock_serial = MagicMock()
    mock_serial.in_waiting = 0
    mock_serial.read.return_value = b"["

    with patch("serial.Serial", return_value=mock_serial):
        st = SerialTransport(port="COM99", baud=115200)
        await st.open()

        # 请求读取 4096 字节（如 read_until 默认传入的 chunk_size）
        chunk = await st._read_impl(4096)

        # 核心断言：即使 nbytes=4096，在 in_waiting==0 时，传递给底层 read 的必须严格为 1！
        mock_serial.read.assert_called_with(1)
        assert chunk == b"["

        await st.close()


@pytest.mark.asyncio
async def test_serial_read_impl_positive_in_waiting_batches_available():
    """验证当硬件缓冲区已有就绪数据 (in_waiting > 0) 时，应当成块批量读取，保证高吞吐量。"""
    from unittest.mock import MagicMock, patch
    from cio.backends.serial import SerialTransport

    mock_serial = MagicMock()
    mock_serial.in_waiting = 64
    mock_serial.read.return_value = b"X" * 64

    with patch("serial.Serial", return_value=mock_serial):
        st = SerialTransport(port="COM99", baud=115200)
        await st.open()

        # 1. 当请求 4096 但缓冲区只有 64 时，应批量读取 64
        chunk = await st._read_impl(4096)
        mock_serial.read.assert_called_with(64)
        assert len(chunk) == 64

        # 2. 当请求 10 且缓冲区有 64 时，应读取 min(10, 64) = 10
        mock_serial.read.return_value = b"Y" * 10
        chunk_small = await st._read_impl(10)
        mock_serial.read.assert_called_with(10)
        assert len(chunk_small) == 10

        # 3. 当请求 -1 (读全部) 且缓冲区有 64 时，应直接批量读 64
        mock_serial.read.return_value = b"Z" * 64
        chunk_all = await st._read_impl(-1)
        mock_serial.read.assert_called_with(64)
        assert len(chunk_all) == 64

        await st.close()


@pytest.mark.asyncio
async def test_serial_read_until_two_phase_pipeline():
    """验证高层 read_until(b'\\n') 流水线在两阶段流转下的完整闭环：
    第 1 阶段（缓冲区空）: 请求 1 字节哨兵唤醒，收到首字节；
    第 2 阶段（缓冲区有数据）: 请求 min(nbytes, in_waiting) 批量拉走剩余数据；
    最终上层拼接无损且调用序列严格精确。"""
    from unittest.mock import MagicMock, call, patch
    from cio.backends.serial import SerialTransport

    mock_serial = MagicMock()
    # 模拟两阶段的 in_waiting 与 read 返回
    mock_serial.in_waiting = 0

    def mock_read_side_effect(size):
        if size == 1:
            # 首字节到达，同时后续 12 字节瞬间涌入硬件缓冲区
            mock_serial.in_waiting = 12
            return b"["
        elif size == 12:
            mock_serial.in_waiting = 0
            return b"RETURN]: 1\r\n"
        return b""

    mock_serial.read.side_effect = mock_read_side_effect

    with patch("serial.Serial", return_value=mock_serial):
        st = SerialTransport(port="COM99", baud=115200)
        await st.open()

        # 上层执行 read_until(b'\n')
        line = await st.read_until(b"\n", timeout=1.0)
        assert line == b"[RETURN]: 1\r\n"

        # 核心契约断言：底层调用序列必须严格为先 1 字节哨兵，再 12 字节成块批量拉取！
        assert mock_serial.read.call_args_list == [call(1), call(12)]

        await st.close()


@pytest.mark.asyncio
async def test_serial_hardware_timeout_graceful_break():
    """验证当下位机死锁或不回发数据时，底层 read(1) 返回空 b''，
    上层超时定时器能正确熔断抛出 ReadTimeoutError，杜绝 while 循环死锁。"""
    from unittest.mock import MagicMock, patch
    from cio.backends.serial import SerialTransport
    from cio.exceptions import ReadTimeoutError

    mock_serial = MagicMock()
    mock_serial.in_waiting = 0
    # 模拟硬件超时，底层 read(1) 每次都返回空
    mock_serial.read.return_value = b""

    with patch("serial.Serial", return_value=mock_serial):
        st = SerialTransport(port="COM99", baud=115200, timeout=0.02)
        await st.open()

        # 断言能够在设定的超时内安全熔断，抛出 ReadTimeoutError
        with pytest.raises(ReadTimeoutError):
            await st.read_until(b"\n", timeout=0.05)

        await st.close()


# ==========================================
# FTDI Backend Mocked Unit Tests
# ==========================================

@pytest.mark.asyncio
async def test_ftdi_backends_mocked():
    import sys
    from unittest.mock import MagicMock, patch

    mock_pyftdi = MagicMock()
    mock_ftdi_mod = MagicMock()
    mock_serialext = MagicMock()
    mock_i2c_mod = MagicMock()
    mock_spi_mod = MagicMock()

    with patch.dict(
        sys.modules,
        {
            "pyftdi": mock_pyftdi,
            "pyftdi.ftdi": mock_ftdi_mod,
            "pyftdi.serialext": mock_serialext,
            "pyftdi.i2c": mock_i2c_mod,
            "pyftdi.spi": mock_spi_mod,
        },
    ):
        from cio.backends.ftdi import (
            FtdiUartTransport,
            FtdiI2cBus,
            FtdiSpiBus,
            FtdiGpioBus,
            _scan_ftdi,
        )

        # 1. FTDI UART
        mock_uart_port = MagicMock()
        mock_uart_port.write.return_value = 4
        mock_uart_port.read.return_value = b"RESP"
        with patch("cio.backends.ftdi._probe_ftdi", return_value=True), \
             patch("pyftdi.serialext.serial_for_url", return_value=mock_uart_port):
            fu = FtdiUartTransport(url="ftdi://ftdi:232h/1", baud=115200)
            await fu.open()
            assert fu.is_open
            assert await fu.write(b"PING") == 4
            assert await fu.read(4) == b"RESP"
            await fu.close()
            assert not fu.is_open

        # 2. FTDI I2C
        mock_i2c_controller = MagicMock()
        mock_i2c_port = MagicMock()
        mock_i2c_port.read.return_value = b"\x12\x34"
        mock_i2c_controller.get_port.return_value = mock_i2c_port
        with patch("cio.backends.ftdi._probe_ftdi", return_value=True), \
             patch("pyftdi.i2c.I2cController", return_value=mock_i2c_controller):
            fi = FtdiI2cBus(url="ftdi://ftdi:2232h/1", frequency=400e3)
            await fi.open()
            assert fi.is_open
            assert await fi.write(0x50, [0x01, 0x02]) == 2
            assert await fi.read(0x50, 2) == b"\x12\x34"
            await fi.close()
            assert not fi.is_open

        # 3. FTDI SPI
        mock_spi_controller = MagicMock()
        mock_spi_port = MagicMock()
        mock_spi_port.exchange.return_value = b"\xAA\xBB"
        mock_spi_controller.get_port.return_value = mock_spi_port
        with patch("cio.backends.ftdi._probe_ftdi", return_value=True), \
             patch("pyftdi.spi.SpiController", return_value=mock_spi_controller):
            fs = FtdiSpiBus(url="ftdi://ftdi:2232h/1", frequency=1e6)
            await fs.open()
            assert fs.is_open
            assert await fs.transfer(b"\x11\x22") == b"\xAA\xBB"
            assert await fs.write(b"\x11\x22") == 2
            assert await fs.read(2) == b"\xAA\xBB"
            await fs.close()
            assert not fs.is_open

        # 4. FTDI GPIO
        mock_gpio_controller = MagicMock()
        mock_gpio_controller.read.side_effect = [0x00, 0x01, 0x00]
        pin = FtdiGpioBus(gpio_controller=mock_gpio_controller, pin_index=0)
        await pin.set_high()
        await pin.set_low()
        await pin.toggle()
        assert pin._state is True
        assert await pin.read_level() is False

        # 5. FTDI Scan
        mock_dev = (MagicMock(vid=0x0403, pid=0x6014, sn="FT123", description="FT232H"), 1)
        with patch("cio.backends.ftdi._probe_ftdi", return_value=True), \
             patch("pyftdi.ftdi.Ftdi.find_all", return_value=[mock_dev]):
            devs = _scan_ftdi()
            assert len(devs) == 1
            assert devs[0]["serial"] == "FT123"

        # 6. FTDI Package Missing Errors
        with patch("cio.backends.ftdi._probe_ftdi", return_value=False):
            assert _scan_ftdi() == []

            fu_err = FtdiUartTransport(url="ftdi://ftdi:232h/1")
            with pytest.raises(PythonPackageMissingError):
                await fu_err.open()

            fi_err = FtdiI2cBus(url="ftdi://ftdi:2232h/1")
            with pytest.raises(PythonPackageMissingError):
                await fi_err.open()

            fs_err = FtdiSpiBus(url="ftdi://ftdi:2232h/1")
            with pytest.raises(PythonPackageMissingError):
                await fs_err.open()


        # 7. FTDI Open Connection Errors
        with patch("cio.backends.ftdi._probe_ftdi", return_value=True), \
             patch("pyftdi.i2c.I2cController", side_effect=Exception("Device Busy")):
            fi_fail = FtdiI2cBus(url="ftdi://ftdi:2232h/1")
            with pytest.raises(ConnectionError, match="Failed to configure FTDI I2C"):
                await fi_fail.open()

        with patch("cio.backends.ftdi._probe_ftdi", return_value=True), \
             patch("pyftdi.spi.SpiController", side_effect=Exception("Device Busy")):
            fs_fail = FtdiSpiBus(url="ftdi://ftdi:2232h/1")
            with pytest.raises(ConnectionError, match="Failed to configure FTDI SPI"):
                await fs_fail.open()



# ==========================================
# Socket Error Paths
# ==========================================

@pytest.mark.asyncio
async def test_socket_error_paths():
    from cio.backends.socket import TcpTransport, UdpTransport
    from cio.exceptions import ConnectionError

    # TCP connection refused
    tcp = TcpTransport(host="127.0.0.1", port=59999, timeout=0.1)
    with pytest.raises(ConnectionError):
        await tcp.open()

    # Operations when not open
    tcp2 = TcpTransport(host="127.0.0.1", port=8000)
    with pytest.raises(ConnectionError):
        await tcp2._write_impl(b"DATA")
    with pytest.raises(ConnectionError):
        await tcp2._read_impl(10)

    # UDP operations when not open
    udp = UdpTransport(host="127.0.0.1", port=8000)
    with pytest.raises(ConnectionError):
        await udp._write_impl(b"DATA")
    with pytest.raises(ConnectionError):
        await udp._read_impl()


def test_custom_backend_registry_robustness():
    from cio.registry import BackendRegistry
    from cio.exceptions import InvalidUrlError
    from cio.testing.mock import MockTransport

    reg = BackendRegistry()

    # 1. Register with default scan_fn
    reg.register("simple", ["simp"], MockTransport, probe_fn=lambda: True)
    assert reg.is_available("simp") is True
    assert reg.is_available("simple") is True
    assert reg.is_available("unknown") is False
    assert reg.scan("simp") == []

    # 2. Probe raises exception
    def bad_probe():
        raise ImportError("Test missing module")

    def generic_bad_probe():
        raise RuntimeError("Unexpected error")

    reg.register("bad_p1", ["bp1"], MockTransport, probe_fn=bad_probe)
    reg.register("bad_p2", ["bp2"], MockTransport, probe_fn=generic_bad_probe)
    assert reg.is_available("bp1") is False
    assert reg.is_available("bp2") is False
    assert reg.scan("bp1") == []
    assert reg.scan("bp2") == []

    # 3. Scan raises exception
    def bad_scan():
        raise RuntimeError("Scan hardware failure")

    reg.register("bad_s", ["bs"], MockTransport, probe_fn=lambda: True, scan_fn=bad_scan)
    assert reg.scan("bs") == []

    # 4. Unknown scheme lookup
    with pytest.raises(InvalidUrlError):
        reg.get_backend_info("nonexistent_xyz")





