"""
Unit tests for Backends (TcpTransport, UdpTransport, Serial, FTDI, VISA, USB stubs, silent probes).
"""
import asyncio
import pytest
import cio
from cio.core.exceptions import (
    CDllMissingError,
    DriverMissingError,
    PythonPackageMissingError,
)
from cio.core.registry import registry


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


def test_visa_stub_error():
    dev = cio.connect("visa://GPIB0::1::INSTR")
    with pytest.raises((PythonPackageMissingError, CDllMissingError, DriverMissingError)):
        dev.sync.open()


def test_usb_stub_error():
    dev = cio.connect("usb://0x0403:0x6001")
    with pytest.raises((PythonPackageMissingError, CDllMissingError, DriverMissingError)):
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
        await client.write_packet(b"HELLO UDP")
        resp = await client.read_packet(timeout=2.0)
        assert resp == b"HELLO UDP"

    transport.close()


# ==========================================
# Serial Backend Mocked Unit Tests
# ==========================================

@pytest.mark.asyncio
async def test_serial_transport_mocked_lifecycle():
    from unittest.mock import MagicMock, patch
    from cio.backends.serial import SerialTransport, _scan_serial
    from cio.core.exceptions import ConnectionError

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

        st._sync_cleanup()
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
            FtdiI2cTransport,
            FtdiSpiTransport,
            FtdiGpioPin,
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
            fu._sync_cleanup()
            await fu.close()
            assert not fu.is_open

        # 2. FTDI I2C
        mock_i2c_controller = MagicMock()
        mock_i2c_port = MagicMock()
        mock_i2c_port.read.return_value = b"\x12\x34"
        mock_i2c_controller.get_port.return_value = mock_i2c_port
        with patch("cio.backends.ftdi._probe_ftdi", return_value=True), \
             patch("pyftdi.i2c.I2cController", return_value=mock_i2c_controller):
            fi = FtdiI2cTransport(url="ftdi://ftdi:2232h/1", frequency=400e3)
            await fi.open()
            assert fi.is_open
            assert await fi.write(0x50, [0x01, 0x02]) == 2
            assert await fi.read(0x50, 2) == b"\x12\x34"
            fi._sync_cleanup()
            await fi.close()
            assert not fi.is_open

        # 3. FTDI SPI
        mock_spi_controller = MagicMock()
        mock_spi_port = MagicMock()
        mock_spi_port.exchange.return_value = b"\xAA\xBB"
        mock_spi_controller.get_port.return_value = mock_spi_port
        with patch("cio.backends.ftdi._probe_ftdi", return_value=True), \
             patch("pyftdi.spi.SpiController", return_value=mock_spi_controller):
            fs = FtdiSpiTransport(url="ftdi://ftdi:2232h/1", frequency=1e6)
            await fs.open()
            assert fs.is_open
            assert await fs.transfer(b"\x11\x22") == b"\xAA\xBB"
            assert await fs.write(b"\x11\x22") == 2
            assert await fs.read(2) == b"\xAA\xBB"
            fs._sync_cleanup()
            await fs.close()
            assert not fs.is_open

        # 4. FTDI GPIO
        mock_gpio_controller = MagicMock()
        mock_gpio_controller.read.side_effect = [0x00, 0x01, 0x00]
        pin = FtdiGpioPin(gpio_controller=mock_gpio_controller, pin_index=0)
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


# ==========================================
# Socket Error Paths
# ==========================================

@pytest.mark.asyncio
async def test_socket_error_paths():
    from cio.backends.socket import TcpTransport, UdpTransport
    from cio.core.exceptions import ConnectionError

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
        await udp._read_packet_impl()

