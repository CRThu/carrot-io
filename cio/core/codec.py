"""
Codec Architecture (BaseCodec, LineCodec, FixedLengthCodec, FramedBinaryCodec, StructCodec).
"""
from __future__ import annotations

import abc
import struct
from typing import Any

from cio.core.exceptions import FrameChecksumError


class BaseCodec(abc.ABC):
    """
    Abstract base class for message bi-directional codec.
    """

    @abc.abstractmethod
    def encode(self, message: Any) -> bytes:
        """Encode typed business message object into bytes."""
        raise NotImplementedError

    @abc.abstractmethod
    def decode(self, buffer: bytearray) -> tuple[Any | None, int]:
        """
        Decode a single message from receive buffer.
        Returns tuple of (decoded_message, bytes_consumed).
        If data is insufficient, returns (None, 0).
        """
        raise NotImplementedError


class LineCodec(BaseCodec):
    """
    Delimiter-based text line codec (e.g. SCPI, NMEA, HTTP text).
    """

    def __init__(self, delimiter: bytes = b"\n", encoding: str = "utf-8") -> None:
        self.delimiter = delimiter
        self.encoding = encoding

    def encode(self, message: str | bytes) -> bytes:
        if isinstance(message, str):
            raw = message.encode(self.encoding)
        else:
            raw = message
        if not raw.endswith(self.delimiter):
            raw += self.delimiter
        return raw

    def decode(self, buffer: bytearray) -> tuple[str | None, int]:
        if not buffer or not self.delimiter:
            return None, 0

        idx = buffer.find(self.delimiter)
        if idx == -1:
            return None, 0

        end_idx = idx + len(self.delimiter)
        raw_line = bytes(buffer[:idx])
        text = raw_line.decode(self.encoding, errors="replace")
        return text, end_idx


class FixedLengthCodec(BaseCodec):
    """
    Fixed length N-byte frame codec.
    """

    def __init__(self, length: int) -> None:
        if length <= 0:
            raise ValueError("Length must be positive integer")
        self.length = length

    def encode(self, message: bytes | bytearray) -> bytes:
        raw = bytes(message)
        if len(raw) != self.length:
            raise ValueError(f"Expected exact {self.length} bytes, got {len(raw)}")
        return raw

    def decode(self, buffer: bytearray) -> tuple[bytes | None, int]:
        if len(buffer) < self.length:
            return None, 0
        data = bytes(buffer[: self.length])
        return data, self.length


class FramedBinaryCodec(BaseCodec):
    """
    Framed binary codec: [HEADER][PAYLOAD_LEN][PAYLOAD][CRC/CS].
    """

    def __init__(
        self,
        header: bytes = b"\xAA\x55",
        length_offset: int = 2,
        length_size: int = 2,
        byteorder: str = "big",
        length_includes_header: bool = False,
        crc_type: str | None = None,
    ) -> None:
        self.header = header
        self.length_offset = length_offset
        self.length_size = length_size
        self.byteorder = byteorder
        self.length_includes_header = length_includes_header
        self.crc_type = crc_type

    def _calc_crc(self, data: bytes) -> bytes:
        if self.crc_type == "sum8":
            s = sum(data) & 0xFF
            return bytes([s])
        elif self.crc_type == "crc16":
            crc = 0xFFFF
            for b in data:
                crc ^= b
                for _ in range(8):
                    if crc & 0x0001:
                        crc = (crc >> 1) ^ 0xA001
                    else:
                        crc >>= 1
            return crc.to_bytes(2, byteorder="little")
        return b""

    def encode(self, payload: bytes) -> bytes:
        pay_len = len(payload)
        total_len = pay_len + len(self.header) + self.length_size
        len_val = total_len if self.length_includes_header else pay_len
        len_bytes = len_val.to_bytes(self.length_size, byteorder=self.byteorder)

        frame = self.header + len_bytes + payload
        if self.crc_type:
            crc_bytes = self._calc_crc(frame)
            frame += crc_bytes
        return frame

    def decode(self, buffer: bytearray) -> tuple[bytes | None, int]:
        if not buffer:
            return None, 0

        idx = buffer.find(self.header)
        if idx == -1:
            discard = max(0, len(buffer) - len(self.header) + 1)
            if discard > 0:
                return None, discard
            return None, 0

        if idx > 0:
            return None, idx

        min_len = len(self.header) + self.length_size
        if len(buffer) < min_len:
            return None, 0

        len_start = self.length_offset
        len_end = len_start + self.length_size
        if len(buffer) < len_end:
            return None, 0

        payload_len = int.from_bytes(buffer[len_start:len_end], byteorder=self.byteorder)
        crc_len = 1 if self.crc_type == "sum8" else (2 if self.crc_type == "crc16" else 0)

        if self.length_includes_header:
            frame_len = payload_len + crc_len
        else:
            frame_len = len(self.header) + self.length_size + payload_len + crc_len

        if len(buffer) < frame_len:
            return None, 0

        frame_data = bytes(buffer[:frame_len])

        if self.crc_type:
            payload_data = frame_data[:-crc_len]
            rx_crc = frame_data[-crc_len:]
            calc_crc = self._calc_crc(payload_data)
            if rx_crc != calc_crc:
                raise FrameChecksumError(f"CRC mismatch: expected {calc_crc.hex()}, got {rx_crc.hex()}")

        payload = frame_data[len_end : frame_len - crc_len]
        return payload, frame_len


class StructCodec(BaseCodec):
    """
    Python `struct` format codec for fixed structures.
    """

    def __init__(self, fmt: str) -> None:
        self.fmt = fmt
        self.size = struct.calcsize(fmt)

    def encode(self, message: tuple[Any, ...] | list[Any]) -> bytes:
        if isinstance(message, (tuple, list)):
            return struct.pack(self.fmt, *message)
        return struct.pack(self.fmt, message)

    def decode(self, buffer: bytearray) -> tuple[tuple[Any, ...] | None, int]:
        if len(buffer) < self.size:
            return None, 0
        data = struct.unpack(self.fmt, buffer[: self.size])
        return data, self.size
