"""
Buffer management: FifoBuffer for byte streams and PacketQueue for message packets.
"""
from __future__ import annotations

import asyncio
from collections import deque
from enum import Enum
from cio.core.exceptions import BufferOverflowError


class OverflowPolicy(str, Enum):
    DROP_OLDEST = "drop_oldest"
    BACKPRESSURE = "backpressure"


class FifoBuffer:
    """
    High-performance FIFO byte buffer supporting overflow policies.
    """

    def __init__(
        self,
        max_size: int = 1024 * 1024,
        overflow_policy: OverflowPolicy = OverflowPolicy.DROP_OLDEST,
    ) -> None:
        self._max_size = max_size
        self._overflow_policy = overflow_policy
        self._buffer = bytearray()

    @property
    def max_size(self) -> int:
        return self._max_size

    @property
    def overflow_policy(self) -> OverflowPolicy:
        return self._overflow_policy

    def write(self, data: bytes | bytearray) -> None:
        if not data:
            return
        incoming_len = len(data)

        if len(self._buffer) + incoming_len > self._max_size:
            if self._overflow_policy == OverflowPolicy.BACKPRESSURE:
                raise BufferOverflowError(
                    f"FifoBuffer capacity overflow ({len(self._buffer) + incoming_len} > {self._max_size})"
                )
            overflow = (len(self._buffer) + incoming_len) - self._max_size
            if overflow >= len(self._buffer):
                self._buffer.clear()
                self._buffer.extend(data[-self._max_size:])
                return
            else:
                del self._buffer[:overflow]

        self._buffer.extend(data)

    def read(self, nbytes: int = -1) -> bytes:
        if not self._buffer:
            return b""
        if nbytes < 0 or nbytes >= len(self._buffer):
            data = bytes(self._buffer)
            self._buffer.clear()
            return data
        data = bytes(self._buffer[:nbytes])
        del self._buffer[:nbytes]
        return data

    def read_exact(self, nbytes: int) -> bytes | None:
        if len(self._buffer) < nbytes:
            return None
        return self.read(nbytes)

    def read_until(self, delimiter: bytes) -> bytes | None:
        if not delimiter or not self._buffer:
            return None
        idx = self._buffer.find(delimiter)
        if idx == -1:
            return None
        end = idx + len(delimiter)
        return self.read(end)

    def peek(self, nbytes: int = -1) -> bytes:
        if not self._buffer:
            return b""
        if nbytes < 0 or nbytes >= len(self._buffer):
            return bytes(self._buffer)
        return bytes(self._buffer[:nbytes])

    def clear(self) -> None:
        self._buffer.clear()

    def __len__(self) -> int:
        return len(self._buffer)


class PacketQueue:
    """
    Queue for framed packet messages preserving boundaries.
    """

    def __init__(self, max_packets: int = 1000) -> None:
        self._max_packets = max_packets
        self._queue: deque[bytes] = deque(maxlen=max_packets)

    def put(self, packet: bytes) -> None:
        self._queue.append(packet)

    def get(self) -> bytes | None:
        if not self._queue:
            return None
        return self._queue.popleft()

    def peek(self) -> bytes | None:
        if not self._queue:
            return None
        return self._queue[0]

    def clear(self) -> None:
        self._queue.clear()

    def __len__(self) -> int:
        return len(self._queue)
