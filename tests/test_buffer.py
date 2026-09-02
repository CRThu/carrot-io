"""
Unit tests for FifoBuffer and PacketQueue.
"""
import pytest
from cio.core.buffer import FifoBuffer, OverflowPolicy, PacketQueue
from cio.core.exceptions import BufferOverflowError


def test_fifobuffer_basic():
    buf = FifoBuffer(max_size=100)
    buf.write(b"Hello ")
    buf.write(b"World!")
    assert len(buf) == 12
    assert buf.peek(5) == b"Hello"
    assert len(buf) == 12
    assert buf.read(5) == b"Hello"
    assert len(buf) == 7
    assert buf.read() == b" World!"
    assert len(buf) == 0


def test_fifobuffer_read_exact():
    buf = FifoBuffer(max_size=100)
    buf.write(b"1234567890")
    assert buf.read_exact(5) == b"12345"
    assert buf.read_exact(10) is None
    assert len(buf) == 5


def test_fifobuffer_read_until():
    buf = FifoBuffer(max_size=100)
    buf.write(b"CMD1\nCMD2\r\nCMD3")
    assert buf.read_until(b"\n") == b"CMD1\n"
    assert buf.read_until(b"\r\n") == b"CMD2\r\n"
    assert buf.read_until(b"\n") is None
    assert len(buf) == 4


def test_fifobuffer_overflow_drop_oldest():
    buf = FifoBuffer(max_size=10, overflow_policy=OverflowPolicy.DROP_OLDEST)
    buf.write(b"1234567890")
    assert len(buf) == 10
    buf.write(b"ABC")
    assert len(buf) == 10
    assert buf.read() == b"4567890ABC"


def test_fifobuffer_overflow_backpressure():
    buf = FifoBuffer(max_size=5, overflow_policy=OverflowPolicy.BACKPRESSURE)
    buf.write(b"12345")
    with pytest.raises(BufferOverflowError):
        buf.write(b"6")


def test_packetqueue():
    queue = PacketQueue(max_packets=3)
    assert queue.peek() is None
    queue.put(b"P1")
    queue.put(b"P2")
    assert len(queue) == 2
    assert queue.peek() == b"P1"
    assert queue.get() == b"P1"
    assert queue.get() == b"P2"
    assert queue.get() is None

    # Clear and max_packets
    queue.put(b"P3")
    assert len(queue) == 1
    queue.clear()
    assert len(queue) == 0


def test_fifobuffer_edge_cases():
    buf = FifoBuffer(max_size=10)
    buf.write(b"")  # no-op empty write
    assert len(buf) == 0
    assert buf.peek() == b""

    buf.write(b"12345")
    assert buf.peek(-1) == b"12345"
    assert buf.peek(100) == b"12345"
    assert buf.max_size == 10
    assert buf.overflow_policy == OverflowPolicy.DROP_OLDEST

    buf.clear()
    assert len(buf) == 0

