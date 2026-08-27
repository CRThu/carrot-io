"""
Unit tests for the hardware DSL verification & assertion subsystem (cio.testing.verify).
"""
import pytest
from cio.testing.verify import (
    CheckResult,
    VerificationSession,
    check,
    require,
    verify,
    get_current_session,
    _normalize_data,
)


def test_normalize_data():
    # Bytes & Bytearray
    b, s = _normalize_data(b"\x55\xAA")
    assert b == b"\x55\xAA"
    assert s == "55 AA"

    b, s = _normalize_data(bytearray([0x01, 0x02]))
    assert b == b"\x01\x02"
    assert s == "01 02"

    # Ints
    b, s = _normalize_data(0x57)
    assert b == b"\x57"
    assert s == "57"

    b, s = _normalize_data(0x1234)
    assert b == b"\x12\x34"
    assert s == "12 34"

    # List of ints
    b, s = _normalize_data([0x10, 0x20])
    assert b == b"\x10\x20"
    assert s == "10 20"

    # Hex Strings
    b, s = _normalize_data("55 AA")
    assert b == b"\x55\xAA"
    assert s == "55 AA"

    b, s = _normalize_data("00" * 4)
    assert b == b"\x00\x00\x00\x00"
    assert s == "00 00 00 00"

    b, s = _normalize_data("0x55 0xAA")
    assert b == b"\x55\xAA"

    # Booleans & None
    b, s = _normalize_data(True)
    assert b == b"\x01"
    b, s = _normalize_data(False)
    assert b == b"\x00"
    b, s = _normalize_data(None)
    assert b is None
    assert s == "None"


def test_check_basic_and_summary():
    with VerificationSession(print_pass=False, print_fail=False) as s:
        assert s.total_count == 0
        assert s.pass_count == 0
        assert s.fail_count == 0

        # Passing checks
        assert check(b"\x55\xAA", "55 AA", name="Bytes Match") is True
        assert check([0x12, 0x34], b"\x12\x34", name="List Match") is True
        assert check(0x57, 0x57, name="Int Match") is True

        assert s.total_count == 3
        assert s.pass_count == 3
        assert s.fail_count == 0
        assert s.summary() is True

        # Failing check (continue_on_fail)
        assert check(b"\x01\x02", b"\x01\x03", name="Mismatch") is False
        assert s.total_count == 4
        assert s.pass_count == 3
        assert s.fail_count == 1
        assert s.summary() is False

        s.reset()
        assert s.total_count == 0


def test_check_bitmask():
    with VerificationSession(print_pass=False, print_fail=False) as s:
        # 0x18 & 0x10 == 0x10 & 0x10
        assert check.mask(0x18, 0x10, mask=0x10, name="POR Mask Match") is True
        assert s.pass_count == 1

        # Multi-byte mask
        assert check(b"\x55\xFF", b"\x55\x00", mask="FF 00", name="Multi-byte Mask") is True
        assert s.pass_count == 2

        # Failing mask
        assert check(b"\x55\xFF", b"\x00\xFF", mask="FF 00", name="Mask Fail") is False
        assert s.fail_count == 1


def test_check_and_require_helpers():
    with VerificationSession(print_pass=False, print_fail=False) as s:
        # len
        assert check.len(b"\x01\x02\x03", 3, name="Len 3") is True
        assert check.len([1, 2], 3, name="Len Wrong") is False

        # not_none
        val = check.not_none("valid_card", name="Card Exists")
        assert val == "valid_card"

        # is_none
        assert check.is_none(None, name="No Error") is True
        assert check.is_none("something", name="Should Be None") is False

        # raises
        def faulty():
            raise ValueError("bad input")

        def normal():
            return 42

        assert check.raises(ValueError, faulty, name="Catches ValueError") is not None
        assert check.raises(ValueError, normal, name="Should Have Raised") is None


def test_require_raises_assertion_error():
    with VerificationSession(print_pass=False, print_fail=False) as s:
        # Success returns value / data
        ret = require(b"\x55", "55", name="Must match")
        assert ret == b"\x55"

        ret_len = require.len([1, 2, 3], 3, name="Must be len 3")
        assert ret_len == [1, 2, 3]

        card = require.not_none({"uid": [1, 2, 3, 4]}, name="Must have card")
        assert card["uid"] == [1, 2, 3, 4]

        # Failure raises AssertionError immediately
        with pytest.raises(AssertionError):
            require(b"\x01", b"\x02", name="Must fail")

        with pytest.raises(AssertionError):
            require.len(b"\x01", 4, name="Len fail")

        with pytest.raises(AssertionError):
            require.not_none(None, name="None fail")

        with pytest.raises(AssertionError):
            require.is_none("not none", name="Is None fail")

        with pytest.raises(AssertionError):
            require.raises(KeyError, lambda: 123, name="Raises fail")


def test_contextvar_session_isolation():
    # Global default session
    global_s = get_current_session()
    global_s.reset()
    check(1, 1, name="Global check")
    assert global_s.total_count == 1

    # Isolated sub-session
    with VerificationSession(print_pass=False, print_fail=False) as sub_s:
        assert get_current_session() is sub_s
        assert sub_s.total_count == 0

        check(2, 2, name="Sub check 1")
        check(3, 3, name="Sub check 2")
        assert sub_s.total_count == 2
        assert sub_s.pass_count == 2

    # After exit, restored to global
    assert get_current_session() is global_s
    assert global_s.total_count == 1


def test_sinks_and_dump_hook():
    recorded: list[CheckResult] = []

    def sink(r: CheckResult):
        recorded.append(r)

    dump_called = []

    def dummy_dump():
        dump_called.append(True)
        return "TRACE: DUMP DATA"

    printed_lines = []

    with VerificationSession(
        auto_dump_on_fail=True,
        dump_hook=dummy_dump,
        print_fn=printed_lines.append,
    ) as s:
        s.add_sink(sink)

        check(b"\xAA", b"\xAA", name="Pass Sink")
        assert len(recorded) == 1
        assert recorded[0].passed is True

        check(b"\xAA", b"\x55", name="Fail Sink")
        assert len(recorded) == 2
        assert recorded[1].passed is False
        assert len(dump_called) == 1

        s.remove_sink(sink)
        check(b"\x01", b"\x01")
        assert len(recorded) == 2


def test_verify_facade():
    with VerificationSession(print_pass=False, print_fail=False) as s:
        assert verify(1, 1, name="Verify direct call") is True
        assert verify.check(2, 2) is True
        assert verify.len(b"abc", 3) is True
        assert verify.mask(0x18, 0x10, 0x10) is True
        assert verify.not_none("ok") == "ok"
        assert verify.is_none(None) is True
        assert s.total_count == 6
        assert verify.summary() is True
