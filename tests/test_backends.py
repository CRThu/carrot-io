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
