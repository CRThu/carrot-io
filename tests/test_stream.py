"""
Unit tests for cio.core.stream, cio.core.packet, and cio.core.base abstractions.
"""
import asyncio
import gc
import weakref
import pytest
from cio.transports.base import AsyncBaseTransport
from cio.exceptions import ReadTimeoutError, WriteTimeoutError
from cio.transports.packet import AsyncPacketTransport
from cio.transports.stream import AsyncStreamTransport
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
    class MinimalStreamTransport(AsyncStreamTransport):
        async def open(self) -> None:
            self._is_open = True
        async def close(self) -> None:
            self._is_open = False

    t = MinimalStreamTransport()
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

    async def _read_impl(self) -> bytes:
        if self.packet_queue:
            return self.packet_queue.get() or b""
        return b""


@pytest.mark.asyncio
async def test_packet_transport_methods():
    pkt = DummyPacketTransport()
    await pkt.open()
    pkt.packet_queue.put(b"PKT1")
    assert len(pkt.packet_queue) == 1
    assert len(pkt) == 1

    r = await pkt.read()
    assert r == b"PKT1"

    w = await pkt.write(b"PKT2")
    assert w == 4
    assert pkt.sent == [b"PKT2"]

    # Test query
    pkt.packet_queue.put(b"QUERY_RESP")
    q_resp = await pkt.query(b"QUERY_REQ")
    assert q_resp == b"QUERY_RESP"
    assert pkt.sent[-1] == b"QUERY_REQ"

    await pkt.flush()
    assert len(pkt.packet_queue) == 0

    await pkt.close()


def test_packet_transport_sync():
    pkt = DummyPacketTransport()
    with pkt as dev:
        assert dev.is_open
        pkt.packet_queue.put(b"SYNC_PKT")
        assert dev.read() == b"SYNC_PKT"

        assert dev.write(b"SYNC_OUT") == 8
        assert pkt.sent == [b"SYNC_OUT"]

        pkt.packet_queue.put(b"SYNC_Q_RESP")
        assert dev.query(b"SYNC_Q_REQ") == b"SYNC_Q_RESP"



@pytest.mark.asyncio
async def test_abstract_base_interfaces_not_implemented():
    from cio.converters import ensure_bytes
    from cio.bus.gpio import AsyncGpioBus
    from cio.bus.i2c import AsyncI2cBus
    from cio.bus.spi import AsyncSpiBus


    class BareGpio(AsyncGpioBus):
        async def set_high(self): await super().set_high()
        async def set_low(self): await super().set_low()
        async def toggle(self): await super().toggle()
        async def read_level(self): return await super().read_level()
        async def wait_for_edge(self, edge="rising", timeout=None): return await super().wait_for_edge(edge, timeout)

    gpio = BareGpio()
    with pytest.raises(NotImplementedError):
        await gpio.set_high()
    with pytest.raises(NotImplementedError):
        await gpio.set_low()
    with pytest.raises(NotImplementedError):
        await gpio.toggle()
    with pytest.raises(NotImplementedError):
        await gpio.read_level()
    with pytest.raises(NotImplementedError):
        await gpio.wait_for_edge()


    class BareSpi(AsyncSpiBus):
        async def open(self): pass
        async def close(self): pass
        async def transfer(self, tx_data, timeout=None):
            return await super().transfer(tx_data, timeout)

    spi = BareSpi()
    with pytest.raises(NotImplementedError):
        await spi.transfer(b"\x12")

    class EchoSpi(AsyncSpiBus):
        async def open(self): pass
        async def close(self): pass
        async def transfer(self, tx_data, timeout=None):
            return ensure_bytes(tx_data)

    echo_spi = EchoSpi()
    assert await echo_spi.write(b"\xAA\xBB") == 2
    assert await echo_spi.read(3, dummy_byte=0xFF) == b"\xFF\xFF\xFF"

    class BarePacket(AsyncPacketTransport):
        async def open(self): self._is_open = True
        async def close(self): self._is_open = False


    pkt = BarePacket()
    await pkt.open()
    with pytest.raises(NotImplementedError):
        await pkt.write(b"PKT")
    with pytest.raises(NotImplementedError):
        await pkt.read()
    await pkt.close()


def test_transport_gc_no_memory_leak():
    """Verify that creating and deleting a transport allows it to be garbage collected."""
    dev = MockTransport()
    r = weakref.ref(dev)
    del dev
    gc.collect()
    assert r() is None, "Transport instance leaked and was not garbage collected!"


def test_sync_wrapper_setattr_passthrough():
    """Verify that setting attributes on .sync updates the underlying async transport."""
    dev = MockTransport()
    dev.sync.timeout = 7.5
    assert dev.timeout == 7.5
    assert dev.sync.timeout == 7.5


@pytest.mark.asyncio
async def test_stream_transport_query_atomic_lock():
    """Verify query() uses atomic transaction lock and completes without interleaving."""
    mock_st = MockTransport()
    await mock_st.open()

    mock_st.auto_replies = {
        b"CMD1\n": b"RESP1\n",
        b"CMD2\n": b"RESP2\n",
    }

    r1, r2 = await asyncio.gather(
        mock_st.query(b"CMD1\n", timeout=1.0),
        mock_st.query(b"CMD2\n", timeout=1.0),
    )
    assert r1 == b"RESP1\n"
    assert r2 == b"RESP2\n"
    await mock_st.close()


def test_default_timeout_unification():
    """Verify that DEFAULT_TIMEOUT is 2.0s across all transport and bus abstractions."""
    import cio
    from cio.transports.base import DEFAULT_TIMEOUT
    from cio.backends.serial import SerialTransport
    from cio.backends.socket import TcpTransport, UdpTransport
    from cio.composite.carrotbridge import CarrotBridge, AsyncI2cBridge

    assert DEFAULT_TIMEOUT == 2.0
    assert cio.DEFAULT_TIMEOUT == 2.0

    # 1. 默认缺省均为 2.0s
    st = SerialTransport(port="COM1")
    assert st.timeout == 2.0

    tcp = TcpTransport(host="127.0.0.1", port=5025)
    assert tcp.timeout == 2.0

    udp = UdpTransport(host="127.0.0.1", port=5025)
    assert udp.timeout == 2.0

    bridge = CarrotBridge(st)
    assert bridge.timeout == 2.0

    i2c = AsyncI2cBridge(st)
    assert i2c.timeout == 2.0

    # 2. 快捷构造函数同样默认 2.0s
    assert cio.serial("COM1").timeout == 2.0
    assert cio.tcp("127.0.0.1", 5025).timeout == 2.0
    assert cio.udp("127.0.0.1", 5025).timeout == 2.0

    # 3. 显式传递 None 时允许无超时
    st_none = SerialTransport(port="COM1", timeout=None)
    assert st_none.timeout is None

    # 4. 显式传递具体值
    st_custom = SerialTransport(port="COM1", timeout=0.5)
    assert st_custom.timeout == 0.5


def test_default_buffer_size_and_queue_size_unification():
    """Verify DEFAULT_BUFFER_SIZE (16MB) and DEFAULT_PACKET_QUEUE_SIZE (1024) across all transports."""
    import cio
    from cio.transports.base import DEFAULT_BUFFER_SIZE, DEFAULT_PACKET_QUEUE_SIZE
    from cio.backends.serial import SerialTransport
    from cio.backends.socket import TcpTransport, UdpTransport
    from cio.backends.ftdi import FtdiUartTransport
    from cio.backends.ch347 import Ch347DeviceTransport

    # 1. 常量权威定义
    assert DEFAULT_BUFFER_SIZE == 16 * 1024 * 1024
    assert DEFAULT_PACKET_QUEUE_SIZE == 1024
    assert cio.DEFAULT_BUFFER_SIZE == 16 * 1024 * 1024
    assert cio.DEFAULT_PACKET_QUEUE_SIZE == 1024

    # 2. 字节流（Byte Stream）统一继承 16MB
    st = SerialTransport(port="COM1")
    assert st.buffer_size == 16 * 1024 * 1024

    tcp = TcpTransport(host="127.0.0.1", port=5025)
    assert tcp.buffer_size == 16 * 1024 * 1024

    ftdi = FtdiUartTransport()
    assert ftdi.buffer_size == 16 * 1024 * 1024

    ch347 = Ch347DeviceTransport()
    assert ch347.buffer_size == 16 * 1024 * 1024

    # 快捷工厂
    assert cio.serial("COM1").buffer_size == 16 * 1024 * 1024
    assert cio.tcp("127.0.0.1", 5025).buffer_size == 16 * 1024 * 1024
    assert cio.ftdi().buffer_size == 16 * 1024 * 1024

    # 3. UDP 作为标准 StreamTransport 同样统一继承 16MB
    udp = UdpTransport(host="127.0.0.1", port=5025)
    assert udp.buffer_size == 16 * 1024 * 1024
    assert cio.udp("127.0.0.1", 5025).buffer_size == 16 * 1024 * 1024







