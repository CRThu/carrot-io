"""
Socket Backends (TcpTransport and UdpTransport).
"""
from __future__ import annotations

import asyncio
from typing import Any

from cio.core.exceptions import ConnectionRefusedError, ConnectTimeoutError, ConnectionError
from cio.core.packet import AsyncPacketTransport
from cio.core.registry import registry
from cio.core.stream import AsyncStreamTransport


class TcpTransport(AsyncStreamTransport):
    """
    TCP Socket Stream Transport.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5025,
        address: str | None = None,
        timeout: float | None = None,
        buffer_size: int = 1024 * 1024,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout, buffer_size=buffer_size)
        if address:
            if ":" in address:
                h, p = address.split(":", 1)
                self.host = h
                self.port = int(p)
            else:
                self.host = address
                self.port = port
        else:
            self.host = host
            self.port = int(port)

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None

    async def open(self) -> None:
        if self._is_open:
            return

        try:
            if self.timeout is not None:
                self._reader, self._writer = await asyncio.wait_for(
                    asyncio.open_connection(self.host, self.port), timeout=self.timeout
                )
            else:
                self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
            self._is_open = True
        except asyncio.TimeoutError as err:
            raise ConnectTimeoutError(f"TCP connection to {self.host}:{self.port} timed out") from err
        except OSError as err:
            raise ConnectionRefusedError(f"Failed to connect to TCP {self.host}:{self.port}: {err}") from err

    async def close(self) -> None:
        if not self._is_open:
            return
        self._is_open = False
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        self._reader = None
        self._writer = None

    async def _write_impl(self, data: bytes) -> int:
        if not self._writer:
            raise ConnectionError("TCP socket not open")
        self._writer.write(data)
        await self._writer.drain()
        return len(data)

    async def _read_impl(self, nbytes: int) -> bytes:
        if not self._reader:
            raise ConnectionError("TCP socket not open")
        read_len = nbytes if nbytes > 0 else 4096
        return await self._reader.read(read_len)


class _UdpProtocol(asyncio.DatagramProtocol):

    def __init__(self, queue: asyncio.Queue[bytes]) -> None:
        self.queue = queue

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        self.queue.put_nowait(data)

    def error_received(self, exc: Exception) -> None:
        pass


class UdpTransport(AsyncPacketTransport):
    """
    UDP Datagram Packet Transport.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 5025,
        address: str | None = None,
        timeout: float | None = None,
        buffer_size: int = 1000,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout, buffer_size=buffer_size)
        if address:
            if ":" in address:
                h, p = address.split(":", 1)
                self.host = h
                self.port = int(p)
            else:
                self.host = address
                self.port = port
        else:
            self.host = host
            self.port = int(port)

        self._transport: asyncio.DatagramTransport | None = None
        self._async_queue: asyncio.Queue[bytes] = asyncio.Queue()

    async def open(self) -> None:
        if self._is_open:
            return

        loop = asyncio.get_running_loop()
        self._async_queue = asyncio.Queue()
        try:
            transport, _ = await loop.create_datagram_endpoint(
                lambda: _UdpProtocol(self._async_queue),
                remote_addr=(self.host, self.port),
            )
            self._transport = transport
            self._is_open = True
        except OSError as err:
            raise ConnectionRefusedError(f"Failed to open UDP socket to {self.host}:{self.port}: {err}") from err

    async def close(self) -> None:
        if not self._is_open:
            return
        self._is_open = False
        if self._transport:
            self._transport.close()
            self._transport = None

    async def _write_impl(self, data: bytes) -> int:
        if not self._transport:
            raise ConnectionError("UDP socket not open")
        self._transport.sendto(data)
        return len(data)

    async def _read_impl(self) -> bytes:
        if not self._is_open:
            raise ConnectionError("UDP socket not open")
        return await self._async_queue.get()




registry.register(
    name="tcp",
    schemes=["tcp"],
    factory_cls=TcpTransport,
    probe_fn=lambda: True,
    scan_fn=lambda: [],
)

registry.register(
    name="udp",
    schemes=["udp"],
    factory_cls=UdpTransport,
    probe_fn=lambda: True,
    scan_fn=lambda: [],
)
