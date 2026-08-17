"""
Unit tests for IoLogger and LogEntry.
"""
import io
import sys
from cio.core.logger import IoLogger, LogEntry


def test_io_logger_linear_preservation():
    logger = IoLogger()
    logger.log_out(b"TX1")
    logger.log_in(b"RX1")
    logger.log_out(b"TX2")
    logger.log_in(b"RX2")

    # All 4 entries are preserved linearly
    assert len(logger) == 4
    hist = logger.history(limit=10)
    assert len(hist) == 4
    assert hist[0].data == b"TX1"
    assert hist[1].data == b"RX1"
    assert hist[2].data == b"TX2"
    assert hist[3].data == b"RX2"

    # History slice with limit
    hist2 = logger.history(limit=2)
    assert len(hist2) == 2
    assert hist2[0].data == b"TX2"
    assert hist2[1].data == b"RX2"

    dump = hist[3].hexdump()
    assert "[IN]" in dump
    assert "52 58 32" in dump


def test_io_logger_trace_and_listener():
    received_entries: list[LogEntry] = []

    def on_entry(entry: LogEntry):
        received_entries.append(entry)

    logger = IoLogger(trace=True)
    logger.add_listener(on_entry)

    # Capture stdout
    captured = io.StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdout = captured
        logger.log_out(b"\x01\x02", tag="CMD", meta={"cmd": "test"})
        logger.log_in(b"\x03\x04", tag="RES")
    finally:
        sys.stdout = old_stdout

    assert len(received_entries) == 2
    assert received_entries[0].tag == "CMD"
    assert received_entries[0].meta == {"cmd": "test"}
    assert received_entries[0].hex == "01 02"
    assert received_entries[0].time_str != ""
    assert "[CMD]" in captured.getvalue()

    # Test dump
    dump_out = logger.dump(limit=5)
    assert "[CMD]" in dump_out
    assert "[RES]" in dump_out

    # Test remove listener
    logger.remove_listener(on_entry)
    logger.log_out(b"\x05")
    assert len(received_entries) == 2
