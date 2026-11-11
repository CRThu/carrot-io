"""
Unit tests for TraceController, TraceEntry, and ShowController.
"""
import io
import sys
from cio.trace.trace import ShowController, TraceController, TraceEntry


def test_trace_controller_linear_preservation():
    trace = TraceController()
    trace.trace_out(b"TX1")
    trace.trace_in(b"RX1")
    trace.trace_out(b"TX2")
    trace.trace_in(b"RX2")

    # All 4 entries are preserved linearly
    assert len(trace) == 4
    hist = trace.history(limit=10)
    assert len(hist) == 4
    assert hist[0].data == b"TX1"
    assert hist[1].data == b"RX1"
    assert hist[2].data == b"TX2"
    assert hist[3].data == b"RX2"

    # History slice with limit
    hist2 = trace.history(limit=2)
    assert len(hist2) == 2
    assert hist2[0].data == b"TX2"
    assert hist2[1].data == b"RX2"

    dump = hist[3].hexdump()
    assert "<-" in dump
    assert "52 58 32" in dump


def test_trace_controller_streaming_and_listener():
    received_entries: list[TraceEntry] = []

    def on_entry(entry: TraceEntry):
        received_entries.append(entry)

    trace = TraceController(enabled=True)
    trace.add_listener(on_entry)

    # Capture stdout
    captured = io.StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdout = captured
        trace.trace_out(b"\x01\x02", tag="CMD", meta={"cmd": "test"})
        trace.trace_in(b"\x03\x04", tag="RES")
    finally:
        sys.stdout = old_stdout

    assert len(received_entries) == 2
    assert received_entries[0].tag == "CMD"
    assert received_entries[0].meta == {"cmd": "test"}
    assert received_entries[0].hex == "01 02"
    assert received_entries[0].time_str != ""
    assert "[CMD]" in captured.getvalue()

    # Test dump
    dump_out = trace.dump(limit=5)
    assert "[CMD]" in dump_out
    assert "[RES]" in dump_out

    # Test remove listener
    trace.remove_listener(on_entry)
    trace.trace_out(b"\x05")
    assert len(received_entries) == 2


def test_trace_entry_format_customization():
    entry = TraceEntry(timestamp=1700000000.123, direction="OUT", data=b"CMD\x01\x02", tag="TX")

    # 1. Default (both hex and ascii)
    line_default = entry.format_line(color=False, hex=True, ascii=True, time=True)
    assert "[TX]" in line_default
    assert "->" in line_default
    assert "(5B)" in line_default
    assert "43 4D 44 01 02" in line_default
    assert "| CMD.." in line_default

    # 2. Hide hex (ASCII only)
    line_ascii_only = entry.format_line(color=False, hex=False, ascii=True, time=True)
    assert "43 4D 44" not in line_ascii_only
    assert "CMD.." in line_ascii_only

    # 3. Hide ascii (Hex only)
    line_hex_only = entry.format_line(color=False, hex=True, ascii=False, time=True)
    assert "43 4D 44 01 02" in line_hex_only
    assert "CMD.." not in line_hex_only

    # 4. Hide time
    line_no_time = entry.format_line(color=False, time=False)
    assert line_no_time.startswith("[TX]")

    # 5. Hide length (e.g. (5B))
    line_no_len = entry.format_line(color=False, len=False)
    assert "(5B)" not in line_no_len
    assert "[TX] ->" in line_no_len

    # 6. Max bytes truncation
    line_truncated = entry.format_line(color=False, max_bytes=2, hex=True, ascii=True)
    assert "43 4D ... (5 bytes total)" in line_truncated


def test_show_controller_and_batch_configuration():
    import cio

    trace = TraceController(enabled=False)
    trace.trace_out(b"HELLO_WORLD_DATA")

    # Default dump
    d1 = trace.dump(limit=1)
    assert "48 45 4C 4C 4F" in d1
    assert "HELLO_WORLD_DATA" in d1

    # Modify via trace.show attribute access
    trace.show.hex = False
    assert trace.show.hex is False
    d2 = trace.dump(limit=1)
    assert "48 45 4C 4C 4F" not in d2
    assert "HELLO_WORLD_DATA" in d2

    # Batch functional update via trace.show(...)
    trace.show(hex=False, max_bytes=5)
    assert trace.show.hex is False
    assert trace.max_bytes == 5
    d3 = trace.dump(limit=1)
    assert "48 45 4C 4C 4F" not in d3
    assert "HELLO ... (16 bytes total)" in d3

    # Test cio.connect kwargs pass-through
    dev = cio.connect("tcp:127.0.0.1:8000", **{"show.hex": False, "show.ascii": True, "max_bytes": 8})
    assert dev.trace.show.hex is False
    assert dev.trace.show.ascii is True
    assert dev.trace.max_bytes == 8


def test_trace_ascii_protocol_formatting():
    # Test CarrotBridge CMD & RETURN formatting (clean text without messy hex)
    cmd_entry = TraceEntry(
        timestamp=1700000000.0,
        direction="OUT",
        data=b"IIC.SCAN()\n",
        tag="CMD",
    )
    cmd_line = cmd_entry.format_line(color=False)
    assert "[CMD] -> IIC.SCAN() (11B)" in cmd_line
    assert "49 49 43" not in cmd_line  # Hex suppressed for clean ASCII command

    ret_entry = TraceEntry(
        timestamp=1700000000.01,
        direction="IN",
        data=b"[RETURN]: 0x46,0x4A,0x57\r\n",
        tag="RETURN",
    )
    ret_line = ret_entry.format_line(color=False)
    assert "[RETURN] <- [RETURN]: 0x46,0x4A,0x57 (26B)" in ret_line
    assert "\r" not in ret_line
    assert "\n" not in ret_line


def test_trace_crlf_stripping_and_clean_single_line():
    entry = TraceEntry(
        timestamp=1700000000.0,
        direction="IN",
        data=b"Line with\r\nCRLF and\rtrailing\r\n",
        tag="MSG",
    )
    line = entry.format_line(color=False)
    assert "\r" not in line
    assert "\n" not in line
    assert "Line with CRLF and trailing" in line


def test_trace_color_and_msg_formatting():
    # 1. Colored output for CMD, RETURN, MSG
    cmd_entry = TraceEntry(timestamp=1700000000.0, direction="OUT", data=b"CMD_TEST\n", tag="CMD")
    ret_entry = TraceEntry(timestamp=1700000000.0, direction="IN", data=b"[RETURN]: OK\n", tag="RETURN")
    msg_entry = TraceEntry(timestamp=1700000000.0, direction="IN", data=b"Sensor ready\n", tag="MSG")

    cmd_color = cmd_entry.format_line(color=True)
    ret_color = ret_entry.format_line(color=True)
    msg_color = msg_entry.format_line(color=True)

    assert "\033[96m" in cmd_color
    assert "\033[92m" in ret_color
    assert "\033[90m" in msg_color

    # 2. Non-utf8 binary data with CMD tag falls back gracefully to hex
    binary_cmd = TraceEntry(timestamp=1700000000.0, direction="OUT", data=b"\xFF\xFE\xFD", tag="CMD")
    bin_line = binary_cmd.format_line(color=False)
    assert "FF FE FD" in bin_line

    # 3. Clear and repr
    trace = TraceController()
    trace.trace_out(b"123")
    assert len(trace) == 1
    assert repr(trace.history()[0]).startswith("[")
    trace.clear()
    assert len(trace) == 0
    assert trace.dump() == "(No trace entries recorded)"


def test_trace_max_entries_sliding_window():
    """Verify optional max_entries maintains a sliding window while default is unbounded."""
    trace_unbounded = TraceController()
    assert trace_unbounded.max_entries is None
    for i in range(200):
        trace_unbounded.trace_out(f"TX{i}".encode("utf-8"))
    assert len(trace_unbounded.history(500)) == 200

    trace_bounded = TraceController(max_entries=5)
    for i in range(12):
        trace_bounded.trace_out(f"DATA_{i}".encode("utf-8"))
    entries = trace_bounded.history(20)
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

    mock_t.trace.trace_out(b"WORLD")
    assert len(mock_t.history()) == 1

    mock_t.clear_history()
    assert len(mock_t.history()) == 0


def test_i2c_semantic_trace_entry_formatting():
    """Verify I2C semantic bus transaction formatting in TraceEntry."""
    # 1. Register Read: RD 0x57 @ 0xFFB0 <- 10 (1B)
    e1 = TraceEntry(
        timestamp=1700000000.123,
        direction="IN",
        data=b"\x10",
        tag="I2C",
        meta={"bus": "i2c", "op": "RD", "addr": 0x57, "reg": 0xFFB0, "reg_len": 2},
    )
    line1 = e1.format_line(color=False, ascii=False)
    assert "[I2C]" in line1
    assert "RD 0x57 @ 0xFFB0" in line1
    assert "<- 10 (1B)" in line1

    # Colored version
    line1_color = e1.format_line(color=True, ascii=False)
    assert "\033[36m[I2C]\033[0m" in line1_color
    assert "\033[92mRD\033[0m" in line1_color
    assert "\033[92m<-\033[0m" in line1_color

    # 2. Register Write: WR 0x57 @ 0xFFB0 -> 55 AA (2B)
    e2 = TraceEntry(
        timestamp=1700000000.124,
        direction="OUT",
        data=b"\x55\xAA",
        tag="I2C",
        meta={"bus": "i2c", "op": "WR", "addr": 0x57, "reg": 0xFFB0, "reg_len": 2},
    )
    line2 = e2.format_line(color=False, ascii=False)
    assert "WR 0x57 @ 0xFFB0" in line2
    assert "-> 55 AA (2B)" in line2

    # 3. Raw Read: RD 0x57 <- 01 02 03 04 (4B)
    e3 = TraceEntry(
        timestamp=1700000000.125,
        direction="IN",
        data=b"\x01\x02\x03\x04",
        tag="I2C",
        meta={"bus": "i2c", "op": "RD", "addr": 0x57},
    )
    line3 = e3.format_line(color=False, ascii=False)
    assert "RD 0x57" in line3
    assert "<- 01 02 03 04 (4B)" in line3

    # 4. Raw Write: WR 0x57 -> FF (1B)
    e4 = TraceEntry(
        timestamp=1700000000.126,
        direction="OUT",
        data=b"\xFF",
        tag="I2C",
        meta={"bus": "i2c", "op": "WR", "addr": 0x57},
    )
    line4 = e4.format_line(color=False, ascii=False)
    assert "WR 0x57" in line4
    assert "-> FF (1B)" in line4

    # 5. Bus Scan: SCAN <- [0x57, 0x68] (Found 2)
    e5 = TraceEntry(
        timestamp=1700000000.127,
        direction="IN",
        data=b"",
        tag="I2C",
        meta={"bus": "i2c", "op": "SCAN", "devices": [0x57, 0x68]},
    )
    line5 = e5.format_line(color=False)
    assert "SCAN" in line5
    assert "<- [0x57, 0x68] (Found 2)" in line5

    # 6. Error: RD 0x57 @ 0xFFB0 <- [NACK]
    e6 = TraceEntry(
        timestamp=1700000000.128,
        direction="IN",
        data=b"",
        tag="I2C",
        meta={"bus": "i2c", "op": "RD", "addr": 0x57, "reg": 0xFFB0, "reg_len": 2, "error": "NACK"},
    )
    line6 = e6.format_line(color=False)
    assert "RD 0x57 @ 0xFFB0" in line6
    assert "<- [NACK]" in line6


def test_trace_formatter_registry_custom_pluggability():
    """Verify pluggable formatter registry enables adding and removing domain formatters cleanly."""
    from cio.trace.formatter import get_formatter, register_formatter, unregister_formatter

    # 1. Initially CAN has no specialized formatter
    assert get_formatter("CAN") is None
    entry_can = TraceEntry(timestamp=1700000000.0, direction="OUT", data=b"\x01\x02", tag="CAN")
    raw_fmt = entry_can.format_line(color=False, ascii=False)
    assert "[CAN] -> 01 02 (2B)" in raw_fmt

    # 2. Register custom formatter
    def my_can_formatter(entry, options):
        return f"[CAN-FRAME] ID=0x123 DATA={entry.hex}"

    register_formatter("CAN", my_can_formatter)
    assert get_formatter("CAN") is my_can_formatter
    custom_fmt = entry_can.format_line(color=False)
    assert custom_fmt == "[CAN-FRAME] ID=0x123 DATA=01 02"

    # 3. Unregister restores default
    unregister_formatter("CAN")
    assert get_formatter("CAN") is None
    restored_fmt = entry_can.format_line(color=False, ascii=False)
    assert "[CAN] -> 01 02 (2B)" in restored_fmt
