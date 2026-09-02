"""
Unit tests for cio.core.stream, cio.core.packet, and cio.core.base abstractions.
"""
import asyncio
import pytest
from cio.core.base import AsyncBaseTransport
from cio.core.exceptions import ReadTimeoutError, WriteTimeoutError
from cio.core.packet import AsyncPacketTransport
from cio.core.stream import AsyncStreamTransport
from cio.testing.mock import MockTransport


# ==========================================
# AsyncStreamTransport Tests
# ==========================================

@pytest.mark.asyncio
async def test_stream_transport_methods():
    dev = MockTransport(timeout=0.05)
    await dev.open()

    # read_exact 0 bytes
    assert await dev.read_exact(0) == b""

    # read_until empty delimiter
    with pytest.raises(ValueError, match="Delimiter must not be empty"):
        await dev.read_until(b"")

    # read_until timeout
    dev.push_rx(b"PARTIAL_LINE")
    with pytest.raises(ReadTimeoutError):
        await dev.read_until(b"\n")

    await dev.flush()

    # read_exact timeout
    dev.push_rx(b"123")
    with pytest.raises(ReadTimeoutError):
        await dev.read_exact(10)

    await dev.flush()

    # valid read_until and read_exact
    dev.push_rx(b"LINE1\nEXACT4B")
    assert await dev.read_until(b"\n") == b"LINE1\n"
    assert await dev.read_exact(7) == b"EXACT4B"

    await dev.close()


# ==========================================
# AsyncBaseTransport Tests
# ==========================================

@pytest.mark.asyncio
async def test_base_transport_helpers():
    dev = MockTransport()
    dev.add_auto_reply(b"PING", b"PONG\n")
    await dev.open()

    res = await dev.query(b"PING", delay=0.01)
    assert res == b"PONG\n"

    entries = dev.history(10)
    assert len(entries) >= 2
    assert "[OUT]" in dev.dump_history()

    await dev.close()


@pytest.mark.asyncio
async def test_base_transport_not_implemented():
    class MinimalTransport(AsyncBaseTransport):
        async def open(self) -> None:
            self._is_open = True
        async def close(self) -> None:
            self._is_open = False

    t = MinimalTransport()
    await t.open()
    with pytest.raises(NotImplementedError, match="does not implement raw byte stream write"):
        await t.write(b"data")
    with pytest.raises(NotImplementedError, match="does not implement raw byte stream read"):
        await t.read(10)
    await t.close()


@pytest.mark.asyncio
async def test_write_timeout_error():
    class SlowWriteTransport(MockTransport):
        async def _write_impl(self, data: bytes) -> int:
            await asyncio.sleep(0.5)
            return len(data)

    dev = SlowWriteTransport()
    await dev.open()
    with pytest.raises(WriteTimeoutError):
        await dev.write(b"HELLO", timeout=0.01)
    await dev.close()


# ==========================================
# AsyncPacketTransport Tests
# ==========================================

class DummyPacketTransport(AsyncPacketTransport):
    def __init__(self):
        super().__init__(timeout=0.1)
        self.sent = []

    async def open(self) -> None:
        self._is_open = True

    async def close(self) -> None:
        self._is_open = False

    async def _write_impl(self, data: bytes) -> int:
        self.sent.append(data)
        return len(data)

    async def _read_packet_impl(self) -> bytes:
        if self.packet_queue:
            return self.packet_queue.get() or b""
        return b""


@pytest.mark.asyncio
async def test_packet_transport_methods():
    pkt = DummyPacketTransport()
    await pkt.open()
    pkt.packet_queue.put(b"PKT1")
    assert len(pkt.packet_queue) == 1

    r = await pkt.read_packet()
    assert r == b"PKT1"

    # read via base read() fallback
    pkt.packet_queue.put(b"PKT_BASE")
    assert await pkt.read(10) == b"PKT_BASE"

    w = await pkt.write_packet(b"PKT2")
    assert w == 4
    assert pkt.sent == [b"PKT2"]

    await pkt.flush()
    assert len(pkt.packet_queue) == 0

    await pkt.close()


