"""
Comprehensive unit tests for synchronous Verifier, ensure_bytes, and trace options.
"""
import io
import sys
import pytest
import cio
from cio.composite.carrotbridge import CarrotBridge
from cio.composite.i2c import AsyncI2cBridge
from cio.composite.spi import AsyncSpiBridge
from cio.core.converters import ensure_bytes
from cio.core.exceptions import IOOperationError, ReadTimeoutError
from cio.core.i2c import AsyncI2cTransport
from cio.testing.mock import MockTransport
from cio.testing.verifier import Verifier, _to_hex_str


def test_ensure_bytes_conversions():
    assert ensure_bytes(b"\x01\x02") == b"\x01\x02"
    assert ensure_bytes(bytearray([1, 2])) == b"\x01\x02"
    assert ensure_bytes(0x03) == b"\x03"
    assert ensure_bytes(0x00) == b"\x00"
    assert ensure_bytes(0xFF) == b"\xFF"
    assert ensure_bytes([0x01, 0x02, 0x03]) == b"\x01\x02\x03"
    assert ensure_bytes([]) == b""
    assert ensure_bytes([0x55] * 4) == b"\x55\x55\x55\x55"

    # Edge cases / invalid types & values
    with pytest.raises(ValueError):
        ensure_bytes(256)
    with pytest.raises(ValueError):
        ensure_bytes(-1)
    with pytest.raises(TypeError):
        ensure_bytes("invalid string")
    with pytest.raises(TypeError):
        ensure_bytes(None)
    with pytest.raises(TypeError):
        ensure_bytes([1.5, 2])
    with pytest.raises(TypeError):
        ensure_bytes(["a", "b"])
    with pytest.raises(TypeError):
        ensure_bytes((0x0A, 0x0B))


def test_to_hex_str_helper():
    assert _to_hex_str(True) == (b"\x01", "01")
    assert _to_hex_str(False) == (b"\x00", "00")
    assert _to_hex_str(0x1234) == (b"\x12\x34", "12 34")
    assert _to_hex_str(0x07) == (b"\x07", "07")
    assert _to_hex_str("OK") == (b"OK", "OK")
    assert _to_hex_str([0x01, 0x02]) == (b"\x01\x02", "01 02")


@pytest.mark.asyncio
async def test_transports_accept_list_and_int_inputs():
    pipe = MockTransport()
    await pipe.open()

    # Base write with int and list
    await pipe.write(0x42)
    assert pipe.tx_history[-1] == b"\x42"

    await pipe.write([0x10, 0x20, 0x30])
    assert pipe.tx_history[-1] == b"\x10\x20\x30"

    # Query with list
    pipe.add_auto_reply(b"\xAA\xBB", b"\xCC")
    res = await pipe.query([0xAA, 0xBB])
    assert res == b"\xCC"

    # Sync wrapper write with list
    pipe.sync.write([0x01, 0x02])
    assert pipe.tx_history[-1] == b"\x01\x02"

    await pipe.close()


@pytest.mark.asyncio
async def test_composite_bridges_accept_list_and_int_inputs():
    pipe = MockTransport()
    bridge = CarrotBridge(pipe)
    i2c = AsyncI2cBridge(bridge)
    spi = AsyncSpiBridge(bridge)

    await i2c.open()

    # Test I2C write with list and int
    pipe.push_rx(b"[RETURN]: 0\n")
    await i2c.write(0x57, [0x01, 0x02])
    assert b"IIC.W(0x57, 0x0102, 2)" in pipe.tx_history[-1]

    pipe.push_rx(b"[RETURN]: 0\n")
    await i2c.write_reg(0x57, 0xFFB4, 0x03)
    assert b"IIC.W(0x57, 0xFFB403, 3)" in pipe.tx_history[-1]

    pipe.push_rx(b"[RETURN]: 0\n")
    await i2c.write_reg(0x57, 0x20, [0x55] * 4, reg_len=2)
    assert b"IIC.W(0x57, 0x002055555555, 6)" in pipe.tx_history[-1]

    # Test SPI write
    pipe.push_rx(b"[RETURN]: 0\n")
    await spi.write([0xDE, 0xAD])
    assert b"SPI.W(0, 0xDEAD, 2)" in pipe.tx_history[-1]

    await i2c.close()


class MockI2cDevice(AsyncI2cTransport):
    """Mock I2C Device for verifier tests."""

    def __init__(self):
        super().__init__()
        self.regs: dict[int, bytes] = {
            0xFFB1: b"\x07",
            0xFFB0: b"\x10",
            0x0020: b"\x00" * 16,
        }

    async def open(self) -> None:
        self._is_open = True

    async def close(self) -> None:
        self._is_open = False

    async def _write_impl(self, data: bytes) -> int:
        return len(data)

    async def _read_impl(self, nbytes: int) -> bytes:
        return b"\x00" * nbytes

    async def read(self, addr: int, nbytes: int, timeout: float | None = None) -> bytes:
        return b"\xAA" * nbytes

    async def write(self, addr: int, data: bytes, timeout: float | None = None) -> int:
        return len(data)

    async def read_reg(
        self,
        addr: int,
        reg: int,
        nbytes: int = 1,
        regfile: int = 0,
        reg_len: int | None = None,
        timeout: float | None = None,
    ) -> bytes:
        return self.regs.get(reg, b"\x00" * nbytes)[:nbytes]

    async def write_reg(
        self,
        addr: int,
        reg: int,
        data: bytes,
        regfile: int = 0,
        reg_len: int | None = None,
        timeout: float | None = None,
        verify: bool = False,
    ) -> int:
        raw_data = ensure_bytes(data)
        self.regs[reg] = raw_data
        if verify:
            read_back = await self.read_reg(addr, reg, len(raw_data), regfile, reg_len, timeout)
            if read_back != raw_data:
                raise IOOperationError("write_reg verification failed")
        return len(raw_data)


def test_verifier_standalone_sync():
    v = Verifier()
    v.step("Step 1: Simple Check")
    assert v.check("Test int vs bytes", expected=0x07, actual=b"\x07")
    assert v.check("Test hex list vs bytes", expected=[0x01, 0x02], actual=b"\x01\x02")
    assert not v.check("Test mismatch", expected=0x07, actual=b"\x00")

    # Mask assertion
    v.step("Step 2: Masked Check")
    assert v.check("Test mask match", expected=0x07, actual=0xF7, mask=0x0F)
    assert not v.check("Test mask mismatch", expected=0x07, actual=0xF0, mask=0x0F)

    assert v.pass_count == 3
    assert v.fail_count == 2
    assert v.total_count == 5
    assert v.summary() is False


def test_verifier_empty_summary():
    v = Verifier()
    assert v.summary() is False


def test_verifier_print_pass_suppressed():
    v = Verifier(print_pass=False)
    captured = io.StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdout = captured
        v.check("Silent pass", expected=0x01, actual=0x01)
        v.check("Loud fail", expected=0x01, actual=0x02)
    finally:
        sys.stdout = old_stdout

    out = captured.getvalue()
    assert "Silent pass" not in out
    assert "Loud fail" in out


def test_verifier_with_i2c_device_explicit():
    dev = MockI2cDevice()
    v = Verifier(dev)

    v.step("Step 1: Read status registers")
    # 1. Test read_reg with expected assertion
    data = v.read_reg(0x57, 0xFFB1, expected=0x07, name="STATUS_REG")
    assert data == b"\x07"

    v.read_reg(0x57, 0xFFB0, expected=0x10)

    # 1b. Test read_reg with mask
    v.read_reg(0x57, 0xFFB1, expected=0x07, mask=0x07, name="STATUS_REG MASK")

    v.step("Step 2: Write registers")
    # 2. Test write_reg with check=True
    v.write_reg(0x57, 0xFFB4, 0x03, check=True)
    assert dev.regs[0xFFB4] == b"\x03"

    v.step("Step 3: Verification with read_reg and write_reg")
    # 3. Test read_reg verification
    v.read_reg(0x57, 0xFFB4, expected=0x03)
    v.read_reg(0x57, 0xFFB4, expected=0x99)  # mismatch

    # 4. Test write_reg with check=True
    v.write_reg(0x57, 0xFFB6, [0xFF], check=True)
    assert dev.regs[0xFFB6] == b"\xFF"

    # 5. Test multi-byte array write_reg and read_reg
    payload = [0x55] * 16
    v.write_reg(0x57, 0x0020, payload)
    read_payload = v.read_reg(0x57, 0x0020, nbytes=16, expected=payload)
    assert read_payload == bytes(payload)

    # 6. Test sleep helper
    v.sleep(0.01)

    assert v.fail_count == 1
    assert v.pass_count == 7
    assert v.summary() is False


def test_verifier_continue_on_fail():
    v_strict = Verifier(continue_on_fail=False)
    with pytest.raises(AssertionError, match="Verification failed"):
        v_strict.check("Strict check", expected=0x01, actual=0x02)

    class FailingDevice:
        def read_reg(self, *args, **kwargs):
            raise ReadTimeoutError("Timeout reading register")
        def write_reg(self, *args, **kwargs):
            raise IOOperationError("I/O Error writing register")
        def read(self, *args, **kwargs):
            raise ReadTimeoutError("Timeout reading stream")
        def write(self, *args, **kwargs):
            raise IOOperationError("I/O Error writing stream")

    fail_dev = FailingDevice()
    # Test strict raise
    v_strict_dev = Verifier(fail_dev, continue_on_fail=False)
    with pytest.raises(ReadTimeoutError):
        v_strict_dev.read_reg(0x57, 0x00)
    with pytest.raises(IOOperationError):
        v_strict_dev.write_reg(0x57, 0x00, 0x01)
    with pytest.raises(ReadTimeoutError):
        v_strict_dev.read(4)
    with pytest.raises(IOOperationError):
        v_strict_dev.write(b"data")

    # Test continue_on_fail=True records FAIL and returns empty
    v_lenient = Verifier(fail_dev, continue_on_fail=True)
    res = v_lenient.read_reg(0x57, 0x00, expected=0x01)
    assert res == b""
    assert v_lenient.fail_count == 1
    assert "<ERROR: ReadTimeoutError" in v_lenient.results[0].actual_hex

    res_w = v_lenient.write_reg(0x57, 0x00, 0x01)
    assert res_w == 0
    assert v_lenient.fail_count == 2


def test_verifier_unbound():
    v_unbound = Verifier()
    with pytest.raises(RuntimeError, match="No transport device bound"):
        v_unbound.read_reg(0x57, 0x00)

    with pytest.raises(RuntimeError, match="No transport device bound"):
        v_unbound.write_reg(0x57, 0x00, 0x01)


def test_verifier_with_stream_device_sync():
    pipe = MockTransport()
    pipe.add_auto_reply(b"PING", b"PONG")

    v = Verifier(pipe)
    v.write(b"PING")
    v.read(4, expected=b"PONG", name="Ping Check")

    assert v.pass_count == 1
    assert v.fail_count == 0
    assert v.summary() is True


def test_verifier_auto_dump_on_fail():
    pipe = MockTransport()
    pipe.sync.write(b"\x01\x02\x03")

    v = Verifier(pipe, auto_dump_on_fail=True)

    captured = io.StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdout = captured
        v.check("Fail check", expected=0x99, actual=0x00)
    finally:
        sys.stdout = old_stdout

    out = captured.getvalue()
    assert "[FAIL] Fail check" in out
    assert "Communication Trace on Failure" in out
    assert "01 02 03" in out


def test_factory_trace_url():
    dev = cio.connect("tcp://127.0.0.1:5025?trace=on")
    assert dev.trace is True

    dev2 = cio.connect("tcp://127.0.0.1:5025?trace=false")
    assert dev2.trace is False
