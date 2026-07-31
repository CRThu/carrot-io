"""
Comprehensive Edge Cases and Boundary Condition Tests.
"""
from unittest.mock import patch
import asyncio
import pytest
import cio
from cio.core.buffer import FifoBuffer, OverflowPolicy, PacketQueue
from cio.core.codec import (
    FixedLengthCodec,
    FramedBinaryCodec,
    LineCodec,
    StructCodec,
)
from cio.core.exceptions import (
    BufferOverflowError,
    CDllMissingError,
    FrameChecksumError,
    PythonPackageMissingError,
    ReadTimeoutError,
)
from cio.testing.mock import MockGpioPin, MockTransport


@pytest.mark.asyncio
async def test_stream_edge_cases():
    dev = MockTransport(timeout=0.05)
    await dev.open()

    assert await dev.read_exact(0) == b""

    with pytest.raises(ValueError, match="Delimiter must not be empty"):
        await dev.read_until(b"")

    dev.push_rx(b"PARTIAL_LINE")
    with pytest.raises(ReadTimeoutError):
        await dev.read_until(b"\n")

    await dev.flush()

    dev.push_rx(b"123")
    with pytest.raises(ReadTimeoutError):
        await dev.read_exact(10)

    await dev.close()


@pytest.mark.asyncio
async def test_query_delay():
    dev = MockTransport()
    dev.add_auto_reply(b"PING", b"PONG\n")
    await dev.open()

    res = await dev.query(b"PING", delay=0.01)
    assert res == b"PONG\n"
    await dev.close()


def test_exception_formatting():
    err_pkg = PythonPackageMissingError("pyserial", "serial")
    assert "pip install carrot-io[serial]" in str(err_pkg) or "pip install" in str(err_pkg)
    assert err_pkg.package_name == "pyserial"

    err_dll = CDllMissingError("visa32.dll", hint="Install NI-VISA")
    assert "visa32.dll" in str(err_dll)
    assert "Install NI-VISA" in str(err_dll)


def test_fixed_length_codec_invalid_size():
    codec = FixedLengthCodec(length=4)
    with pytest.raises(ValueError, match="Expected exact 4 bytes"):
        codec.encode(b"123")

    with pytest.raises(ValueError, match="Length must be positive integer"):
        FixedLengthCodec(length=0)


def test_framed_binary_crc16_and_length_includes_header():
    codec = FramedBinaryCodec(
        header=b"\xAA\x55",
        length_offset=2,
        length_size=2,
        length_includes_header=True,
        crc_type="crc16",
    )
    payload = b"TEST_PAYLOAD"
    frame = codec.encode(payload)

    msg, consumed = codec.decode(bytearray(frame))
    assert msg == payload
    assert consumed == len(frame)


def test_line_codec_bytes_input():
    codec = LineCodec(delimiter=b"\r\n")
    assert codec.encode(b"COMMAND\r\n") == b"COMMAND\r\n"
    assert codec.encode(b"COMMAND") == b"COMMAND\r\n"


@pytest.mark.asyncio
async def test_gpio_edge_cases():
    pin = MockGpioPin(initial_state=False)

    res = await pin.wait_for_edge("falling", timeout=0.02)
    assert not res

    async def trigger():
        await asyncio.sleep(0.01)
        await pin.set_high()

    asyncio.create_task(trigger())
    res = await pin.wait_for_edge("rising", timeout=0.1)
    assert res


@pytest.mark.asyncio
async def test_backend_missing_package_triggers():
    with patch("cio.backends.serial._probe_serial", return_value=False):
        ser = cio.serial("COM99")
        with pytest.raises(PythonPackageMissingError):
            await ser.open()

    with patch("cio.backends.ftdi._probe_ftdi", return_value=False):
        ftdi_uart = cio.ftdi("ftdi://ftdi:232h/1")
        with pytest.raises(PythonPackageMissingError):
            await ftdi_uart.open()

        from cio.backends.ftdi import FtdiI2cTransport, FtdiSpiTransport

        ftdi_i2c = FtdiI2cTransport()
        with pytest.raises(PythonPackageMissingError):
            await ftdi_i2c.open()

        ftdi_spi = FtdiSpiTransport()
        with pytest.raises(PythonPackageMissingError):
            await ftdi_spi.open()


def test_fifobuffer_edge_cases():
    buf = FifoBuffer(max_size=5)
    buf.write(b"")
    assert len(buf) == 0

    assert buf.read_until(b"") is None
    assert buf.read(0) == b""
    assert buf.peek(0) == b""

    buf.write(b"123456789")
    assert len(buf) == 5
    assert buf.read() == b"56789"
