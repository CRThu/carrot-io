"""
Unit tests for cio.core.converters (BytesLike, ensure_bytes, format_arg, parse_*).
"""
import pytest
from cio.core.converters import (
    ensure_bytes,
    format_arg,
    parse_bool,
    parse_hex_bytes,
    parse_int,
    parse_int_list,
    to_hex_str,
)


def test_ensure_bytes():
    # Valid types
    assert ensure_bytes(b"\x12\x34") == b"\x12\x34"
    assert ensure_bytes(bytearray([0x12, 0x34])) == b"\x12\x34"
    assert ensure_bytes(0x57) == b"\x57"
    assert ensure_bytes([0x01, 0x02]) == b"\x01\x02"
    assert ensure_bytes((0x01, 0x02)) == b"\x01\x02"


    # Invalid int ranges
    with pytest.raises(ValueError, match="out of range"):
        ensure_bytes(256)
    with pytest.raises(ValueError, match="out of range"):
        ensure_bytes(-1)

    # Invalid types
    with pytest.raises(TypeError, match="Expected bytes"):
        ensure_bytes("string_not_allowed")  # type: ignore
    with pytest.raises(TypeError, match="Expected bytes"):
        ensure_bytes({"a": 1})  # type: ignore


def test_to_hex_str():
    assert to_hex_str(0x57) == "0x57"
    assert to_hex_str(0x57, prefix=False) == "57"
    assert to_hex_str(b"\x12\x34") == "0x1234"
    assert to_hex_str([0x12, 0x34]) == "0x1234"
    assert to_hex_str(b"\xAB\xCD", prefix=False) == "ABCD"


def test_format_arg():
    assert format_arg(b"\xAB\xCD") == "0xABCD"
    assert format_arg([0x01, 0x02]) == "0x0102"
    assert format_arg("A1") == "A1"
    assert format_arg(100) == "100"
    assert format_arg([300, 400]) == "[300, 400]"


def test_parse_int():
    assert parse_int(123) == 123
    assert parse_int("123") == 123
    assert parse_int("0x7B") == 123
    assert parse_int(b"\x00\x7B") == 123
    assert parse_int(b"\x02\x00") == 512
    assert parse_int(None, default=99) == 99
    assert parse_int("invalid", default=99) == 99
    assert parse_int("", default=10) == 10


def test_parse_bool():
    assert parse_bool(True) is True
    assert parse_bool(False) is False
    assert parse_bool(1) is True
    assert parse_bool(0) is False
    assert parse_bool("1") is True
    assert parse_bool("true") is True
    assert parse_bool("HIGH") is True
    assert parse_bool("yes") is True
    assert parse_bool("on") is True
    assert parse_bool("0") is False
    assert parse_bool("false") is False
    assert parse_bool("off") is False
    assert parse_bool("no") is False
    assert parse_bool(3.14) is True
    assert parse_bool(0.0) is False


def test_parse_hex_bytes():
    assert parse_hex_bytes("0x1234") == b"\x12\x34"
    assert parse_hex_bytes("1234") == b"\x12\x34"
    assert parse_hex_bytes("0xABC") == b"\x0A\xBC"
    assert parse_hex_bytes(0x1234, nbytes=2) == b"\x12\x34"
    assert parse_hex_bytes(0x123456, nbytes=1) == b"\x12\x34\x56"
    assert parse_hex_bytes(b"\x12\x34\x56", nbytes=2) == b"\x12\x34"
    assert parse_hex_bytes(None) == b""
    assert parse_hex_bytes("invalid_hex", default=b"") == b""
    with pytest.raises(ValueError):
        parse_hex_bytes("invalid_hex")


def test_parse_int_list():
    assert parse_int_list("0x50,0x57") == [0x50, 0x57]
    assert parse_int_list("[0x50, 0x57]") == [0x50, 0x57]
    assert parse_int_list("[0x10, invalid, 0x20]") == [0x10, 0x20]
    assert parse_int_list("0x50") == [0x50]
    assert parse_int_list(123) == [123]
    assert parse_int_list([0x50, 0x57]) == [0x50, 0x57]
    assert parse_int_list("") == []
    assert parse_int_list("[]") == []
    assert parse_int_list(None) == []


def test_converters_extended_edge_cases():
    """Verify format_arg, parse_bool, parse_hex_bytes, and parse_int_list fixes."""
    # Tuple support in format_arg
    assert format_arg((0x12, 0x34)) == "0x1234"

    # Bytes support in parse_bool
    assert parse_bool(b"0") is False
    assert parse_bool(b"false") is False
    assert parse_bool(b"1") is True
    assert parse_bool(b"true") is True

    # Bytes support in parse_int_list
    assert parse_int_list(b"0x50, 0x57") == [0x50, 0x57]

    # Negative int in parse_hex_bytes
    assert parse_hex_bytes(-1, default=b"") == b""
    with pytest.raises(ValueError):
        parse_hex_bytes(-1)

