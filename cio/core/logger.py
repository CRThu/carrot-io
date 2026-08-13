"""
RingBufferLogger - Zero-overhead in-memory log queue.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class LogEntry:
    timestamp: float
    direction: Literal["IN", "OUT"]
    data: bytes

    def hexdump(self, max_bytes: int = 64) -> str:
        """Render a formatted hexdump string for display on demand."""
        truncated = len(self.data) > max_bytes
        view = self.data[:max_bytes]
        hex_str = " ".join(f"{b:02X}" for b in view)
        if truncated:
            hex_str += f" ... ({len(self.data)} bytes total)"
        time_str = time.strftime("%H:%M:%S", time.localtime(self.timestamp))
        ms = int((self.timestamp % 1) * 1000)
        return f"[{time_str}.{ms:03d}] [{self.direction}] ({len(self.data)}B) {hex_str}"

    def __repr__(self) -> str:
        return self.hexdump()


class RingBufferLogger:
    """
    Fixed-size ring buffer for logging TX/RX frames with zero hot-path formatting cost.
    """

    def __init__(self, max_entries: int = 1000) -> None:
        self._max_entries = max_entries
        self._entries: deque[LogEntry] = deque(maxlen=max_entries)

    def log_in(self, data: bytes) -> None:
        if data:
            self._entries.append(LogEntry(timestamp=time.time(), direction="IN", data=data))

    def log_out(self, data: bytes) -> None:
        if data:
            self._entries.append(LogEntry(timestamp=time.time(), direction="OUT", data=data))

    def history(self, limit: int = 100) -> list[LogEntry]:
        """Return the most recent log entries up to `limit`."""
        if limit <= 0:
            return []
        items = list(self._entries)
        return items[-limit:]

    get_entries = history

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
