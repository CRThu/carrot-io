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
    assert "[IN ]" in dump
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
    assert "[CMD   ]" in captured.getvalue()

    # Test dump
    dump_out = logger.dump(limit=5)
    assert "[CMD   ]" in dump_out
    assert "[RES   ]" in dump_out

    # Test remove listener
    logger.remove_listener(on_entry)
    logger.log_out(b"\x05")
    assert len(received_entries) == 2


def test_log_entry_format_customization():
    entry = LogEntry(timestamp=1700000000.123, direction="OUT", data=b"CMD\x01\x02", tag="TX")

    # 1. Default (both hex and ascii)
    line_default = entry.format_line(color=False, show_hex=True, show_ascii=True, show_time=True)
    assert "[OUT]" in line_default
    assert "[TX    ]" in line_default
    assert "(5B)" in line_default
    assert "43 4D 44 01 02" in line_default
    assert "| CMD.." in line_default

    # 2. Hide hex (ASCII only)
    line_ascii_only = entry.format_line(color=False, show_hex=False, show_ascii=True, show_time=True)
    assert "43 4D 44" not in line_ascii_only
    assert "CMD.." in line_ascii_only

    # 3. Hide ascii (Hex only)
    line_hex_only = entry.format_line(color=False, show_hex=True, show_ascii=False, show_time=True)
    assert "43 4D 44 01 02" in line_hex_only
    assert "CMD.." not in line_hex_only

    # 4. Hide time
    line_no_time = entry.format_line(color=False, show_time=False)
    assert not line_no_time.startswith("[") or line_no_time.startswith("[OUT]")

    # 5. Hide length (e.g. (5B))
    line_no_len = entry.format_line(color=False, show_len=False)
    assert "(5B)" not in line_no_len
    assert "[OUT] [TX    ]" in line_no_len

    # 6. Max bytes truncation
    line_truncated = entry.format_line(color=False, max_bytes=2, show_hex=True, show_ascii=True)
    assert "43 4D ... (5 bytes total)" in line_truncated


def test_io_logger_configure_and_dump_overrides():
    import cio

    logger = IoLogger(trace=False)
    logger.log_out(b"HELLO_WORLD_DATA")

    # Default dump
    d1 = logger.dump(limit=1)
    assert "48 45 4C 4C 4F" in d1
    assert "HELLO_WORLD_DATA" in d1

    # Dump override: show_hex=False
    d2 = logger.dump(limit=1, show_hex=False)
    assert "48 45 4C 4C 4F" not in d2
    assert "HELLO_WORLD_DATA" in d2

    # Logger configure
    logger.configure(show_hex=False, max_bytes=5)
    assert logger.show_hex is False
    assert logger.max_bytes == 5
    d3 = logger.dump(limit=1)
    assert "48 45 4C 4C 4F" not in d3
    assert "HELLO ... (16 bytes total)" in d3

    # Test cio.connect kwargs pass-through
    dev = cio.connect("tcp://127.0.0.1:8000", show_hex=False, show_ascii=True, max_bytes=8)
    assert dev.logger.show_hex is False
    assert dev.logger.show_ascii is True
    assert dev.logger.max_bytes == 8


def test_io_logger_log_delay_and_event():
    logger = IoLogger(trace=False)
    logger.log_event("DELAY", "50ms", meta={"seconds": 0.05, "ms": 50})
    logger.log_event("CUSTOM", "State changed to READY", meta={"state": "READY"})

    hist = logger.history(limit=10)
    assert len(hist) == 2
    assert hist[0].direction == "EVT"
    assert hist[0].tag == "DELAY"
    assert hist[0].meta["ms"] == 50

    assert hist[1].direction == "EVT"
    assert hist[1].tag == "CUSTOM"

    dump_text = logger.dump(limit=2)
    assert "[EVT] [DELAY ] 50ms" in dump_text
    assert "[EVT] [CUSTOM] State changed to READY" in dump_text


def test_io_logger_ascii_protocol_formatting():
    # Test CarrotBridge CMD & RETURN formatting (clean text without messy hex)
    cmd_entry = LogEntry(
        timestamp=1700000000.0,
        direction="OUT",
        data=b"IIC.SCAN()\n",
        tag="CMD",
    )
    cmd_line = cmd_entry.format_line(color=False)
    assert "[OUT] [CMD   ] (11B) IIC.SCAN()" in cmd_line
    assert "49 49 43" not in cmd_line  # Hex suppressed for clean ASCII command

    ret_entry = LogEntry(
        timestamp=1700000000.01,
        direction="IN",
        data=b"[RETURN]: 0x46,0x4A,0x57\r\n",
        tag="RETURN",
    )
    ret_line = ret_entry.format_line(color=False)
    assert "[IN ] [RETURN] (26B) 0x46,0x4A,0x57" in ret_line
    assert "\r" not in ret_line
    assert "\n" not in ret_line


def test_io_logger_crlf_stripping_and_clean_single_line():
    entry = LogEntry(
        timestamp=1700000000.0,
        direction="EVT",
        data=b"Line with\r\nCRLF and\rtrailing\r\n",
        tag="CLEAN",
    )
    line = entry.format_line(color=False)
    assert "\r" not in line
    assert "\n" not in line
    assert "Line with CRLF and trailing" in line


def test_io_logger_color_and_msg_formatting():
    # 1. Colored output for CMD, RETURN, MSG, EVT
    cmd_entry = LogEntry(timestamp=1700000000.0, direction="OUT", data=b"CMD_TEST\n", tag="CMD")
    ret_entry = LogEntry(timestamp=1700000000.0, direction="IN", data=b"[RETURN]: OK\n", tag="RETURN")
    msg_entry = LogEntry(timestamp=1700000000.0, direction="IN", data=b"Sensor ready\n", tag="MSG")
    evt_entry = LogEntry(timestamp=1700000000.0, direction="EVT", data=b"State OK", tag="EVT")

    cmd_color = cmd_entry.format_line(color=True)
    ret_color = ret_entry.format_line(color=True)
    msg_color = msg_entry.format_line(color=True)
    evt_color = evt_entry.format_line(color=True)

    assert "\033[96m" in cmd_color
    assert "\033[92m" in ret_color
    assert "\033[90m" in msg_color
    assert "\033[33m[EVT]\033[0m" in evt_color

    # 2. Non-utf8 binary data with CMD tag falls back gracefully to hex
    binary_cmd = LogEntry(timestamp=1700000000.0, direction="OUT", data=b"\xFF\xFE\xFD", tag="CMD")
    bin_line = binary_cmd.format_line(color=False)
    assert "FF FE FD" in bin_line

    # 3. Clear and repr
    logger = IoLogger()
    logger.log_out(b"123")
    assert len(logger) == 1
    assert repr(logger.history()[0]).startswith("[")
    logger.clear()
    assert len(logger) == 0
    assert logger.dump() == "(No log entries recorded)"


def test_io_logger_max_entries_sliding_window():
    """Verify optional max_entries maintains a sliding window while default is unbounded."""
    logger_unbounded = IoLogger()
    assert logger_unbounded.max_entries is None
    for i in range(200):
        logger_unbounded.log_out(f"TX{i}".encode("utf-8"))
    assert len(logger_unbounded.history(500)) == 200

    logger_bounded = IoLogger(max_entries=5)
    for i in range(12):
        logger_bounded.log_out(f"DATA_{i}".encode("utf-8"))
    entries = logger_bounded.history(20)
    assert len(entries) == 5
    assert entries[-1].data == b"DATA_11"
    assert entries[0].data == b"DATA_7"


def test_transport_and_sync_clear_history():
    """Verify clear_history on transport and its sync wrapper."""
    from cio.testing.mock import MockTransport

    mock_t = MockTransport()
    mock_t.sync.write(b"HELLO")
    assert len(mock_t.history()) == 1

    mock_t.sync.clear_history()
    assert len(mock_t.history()) == 0

    mock_t.logger.log_out(b"WORLD")
    assert len(mock_t.history()) == 1

    mock_t.clear_history()
    assert len(mock_t.history()) == 0



