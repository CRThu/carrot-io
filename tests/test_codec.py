"""
Unit tests for Codecs (LineCodec, FixedLengthCodec, FramedBinaryCodec, StructCodec).
"""
import pytest
from cio.core.codec import (
    FixedLengthCodec,
    FramedBinaryCodec,
    LineCodec,
    StructCodec,
)
from cio.core.exceptions import FrameChecksumError


def test_line_codec():
    codec = LineCodec(delimiter=b"\n")
    encoded = codec.encode("HELLO")
    assert encoded == b"HELLO\n"

    buf = bytearray(b"FOO\nBAR\nBAZ")
    msg, consumed = codec.decode(buf)
    assert msg == "FOO"
    assert consumed == 4
    del buf[:consumed]

    msg, consumed = codec.decode(buf)
    assert msg == "BAR"
    assert consumed == 4
    del buf[:consumed]

    msg, consumed = codec.decode(buf)
    assert msg is None
    assert consumed == 0


def test_fixed_length_codec():
    codec = FixedLengthCodec(length=4)
    assert codec.encode(b"1234") == b"1234"

    buf = bytearray(b"1234567")
    msg, consumed = codec.decode(buf)
    assert msg == b"1234"
    assert consumed == 4


def test_framed_binary_codec():
    codec = FramedBinaryCodec(header=b"\xAA\x55", length_offset=2, length_size=2, crc_type="sum8")
    payload = b"\x01\x02\x03"
    frame = codec.encode(payload)

    buf = bytearray(b"\xFF") + bytearray(frame)
    msg, consumed = codec.decode(buf)
    assert msg is None
    assert consumed == 1
    del buf[:consumed]

    msg, consumed = codec.decode(buf)
    assert msg == payload
    assert consumed == len(frame)


def test_framed_binary_codec_bad_crc():
    codec = FramedBinaryCodec(header=b"\xAA\x55", crc_type="sum8")
    frame = bytearray(codec.encode(b"ABC"))
    frame[-1] ^= 0xFF

    with pytest.raises(FrameChecksumError):
        codec.decode(frame)


def test_struct_codec():
    codec = StructCodec(fmt=">IH")
    data = (0x12345678, 0xABCD)
    encoded = codec.encode(data)
    assert len(encoded) == 6

    buf = bytearray(encoded)
    msg, consumed = codec.decode(buf)
    assert msg == data
    assert consumed == 6

    # Incomplete buffer
    incomplete = bytearray(b"\x12\x34")
    msg, consumed = codec.decode(incomplete)
    assert msg is None
    assert consumed == 0


def test_framed_binary_codec_custom_callable_crc():
    def custom_xor_crc(data: bytes) -> bytes:
        val = 0
        for b in data:
            val ^= b
        return bytes([val])

    codec = FramedBinaryCodec(header=b"\xAA\x55", crc_type=custom_xor_crc, crc_size=1)
    payload = b"HELLO_CUSTOM_CRC"
    frame = codec.encode(payload)

    msg, consumed = codec.decode(bytearray(frame))
    assert msg == payload
    assert consumed == len(frame)


def test_framed_binary_codec_xor8_and_crc16():
    # xor8
    codec_xor = FramedBinaryCodec(header=b"\xAA\x55", crc_type="xor8")
    payload = b"DATA_XOR"
    frame = codec_xor.encode(payload)
    msg, consumed = codec_xor.decode(bytearray(frame))
    assert msg == payload
    assert consumed == len(frame)

    # crc16 & length_includes_header
    codec_crc16 = FramedBinaryCodec(
        header=b"\xAA\x55",
        length_offset=2,
        length_size=2,
        length_includes_header=True,
        crc_type="crc16",
    )
    frame16 = codec_crc16.encode(b"PAYLOAD_16")
    msg16, consumed16 = codec_crc16.decode(bytearray(frame16))
    assert msg16 == b"PAYLOAD_16"
    assert consumed16 == len(frame16)


