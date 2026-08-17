"""
IoLogger - Lightweight in-memory linear log queue with optional streaming trace.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal


@dataclass(frozen=True, slots=True)
class LogEntry:
    timestamp: float
    direction: Literal["IN", "OUT"]
    data: bytes
    tag: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def hex(self) -> str:
        """Hex string representation of data."""
        return " ".join(f"{b:02X}" for b in self.data)

    @property
    def time_str(self) -> str:
        """Formatted timestamp HH:MM:SS.mmm."""
        t = time.localtime(self.timestamp)
        ms = int((self.timestamp % 1) * 1000)
        return f"{time.strftime('%H:%M:%S', t)}.{ms:03d}"

    def hexdump(self, max_bytes: int = 64) -> str:
        """Render a formatted hexdump string for display on demand."""
        return self.format_line(color=False, max_bytes=max_bytes)

    def format_line(self, color: bool = False, max_bytes: int = 64) -> str:
        """Render a single formatted log line with optional ANSI colors."""
        truncated = len(self.data) > max_bytes
        view = self.data[:max_bytes]
        hex_str = " ".join(f"{b:02X}" for b in view)
        if truncated:
            hex_str += f" ... ({len(self.data)} bytes total)"

        tag_part = f" [{self.tag}]" if self.tag else ""

        # Check if ASCII representation is helpful
        ascii_repr = ""
        if any(32 <= b <= 126 for b in view):
            clean_str = "".join(chr(b) if 32 <= b <= 126 else "." for b in view)
            ascii_repr = f" | {clean_str}"

        if color:
            dir_str = "\033[32m[IN ]\033[0m" if self.direction == "IN" else "\033[36m[OUT]\033[0m"
            time_part = f"\033[90m[{self.time_str}]\033[0m"
            len_part = f"\033[33m({len(self.data)}B)\033[0m"
            return f"{time_part} {dir_str}{tag_part} {len_part} {hex_str}{ascii_repr}"
        else:
            dir_str = f"[{self.direction}]"
            return f"[{self.time_str}] {dir_str}{tag_part} ({len(self.data)}B) {hex_str}"

    def __repr__(self) -> str:
        return self.hexdump()


class IoLogger:
    """
    In-memory linear log storage for TX/RX frames.
    Preserves all logs without dropping, with zero hot-path formatting cost.
    """

    def __init__(self, trace: bool = False) -> None:
        self._entries: list[LogEntry] = []
        self.trace = trace
        self._listeners: list[Callable[[LogEntry], None]] = []

    def add_listener(self, callback: Callable[[LogEntry], None]) -> None:
        """Register a callback for new LogEntry events."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[LogEntry], None]) -> None:
        """Unregister a listener callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def _emit(self, entry: LogEntry) -> None:
        self._entries.append(entry)
        if self.trace:
            print(entry.format_line(color=sys.stdout.isatty()), flush=True)
        for listener in self._listeners:
            try:
                listener(entry)
            except Exception:
                pass

    def log_in(self, data: bytes, tag: str = "", meta: dict[str, Any] | None = None) -> None:
        if data:
            self._emit(LogEntry(timestamp=time.time(), direction="IN", data=data, tag=tag, meta=meta or {}))

    def log_out(self, data: bytes, tag: str = "", meta: dict[str, Any] | None = None) -> None:
        if data:
            self._emit(LogEntry(timestamp=time.time(), direction="OUT", data=data, tag=tag, meta=meta or {}))

    def history(self, limit: int = 100) -> list[LogEntry]:
        """Return the most recent log entries up to `limit`."""
        if limit <= 0:
            return []
        return self._entries[-limit:]

    get_entries = history

    def dump(self, limit: int = 20, color: bool = False) -> str:
        """Format and return the last `limit` log entries as a multi-line string."""
        entries = self.history(limit)
        if not entries:
            return "(No log entries recorded)"
        return "\n".join(e.format_line(color=color) for e in entries)

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
