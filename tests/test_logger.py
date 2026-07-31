"""
Unit tests for RingBufferLogger.
"""
from cio.core.logger import RingBufferLogger


def test_ring_buffer_logger():
    logger = RingBufferLogger(max_entries=3)
    logger.log_out(b"TX1")
    logger.log_in(b"RX1")
    logger.log_out(b"TX2")
    logger.log_in(b"RX2")

    hist = logger.history(limit=10)
    assert len(hist) == 3
    assert hist[0].data == b"RX1"
    assert hist[1].data == b"TX2"
    assert hist[2].data == b"RX2"

    dump = hist[2].hexdump()
    assert "[IN]" in dump
    assert "52 58 32" in dump
