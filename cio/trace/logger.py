"""
IoLogger - Lightweight in-memory linear log queue with optional streaming trace.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from cio.trace.formatter import FormatOptions, format_entry


@dataclass(frozen=True, slots=True)
class LogEntry:
    timestamp: float
    direction: Literal["IN", "OUT"] | str
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

    def format_line(
        self,
        options: FormatOptions | None = None,
        color: bool = False,
        max_bytes: int = 64,
        show_hex: bool = True,
        show_ascii: bool = True,
        show_time: bool = True,
        show_len: bool = True,
        **kwargs: Any,
    ) -> str:
        """Render a single formatted log line via unified TraceFormatter."""
        if options is not None:
            opts = options
        else:
            opts = FormatOptions(
                color=color,
                max_bytes=max_bytes,
                show_hex=show_hex,
                show_ascii=show_ascii,
                show_time=show_time,
                show_len=show_len,
                **kwargs,
            )
        return format_entry(self, opts)

    def __repr__(self) -> str:
        return self.hexdump()


class IoLogger:
    """
    In-memory linear log storage for TX/RX frames.
    Preserves all logs without dropping, with zero hot-path formatting cost.
    Supports customizable display formatting (hex, ascii, timestamp, length, truncation).
    """

    def __init__(
        self,
        trace: bool = False,
        show_hex: bool = True,
        show_ascii: bool = True,
        show_time: bool = True,
        show_len: bool = True,
        max_bytes: int = 64,
        max_entries: int | None = None,
    ) -> None:
        self._entries: list[LogEntry] = []
        self.trace = trace
        self.show_hex = show_hex
        self.show_ascii = show_ascii
        self.show_time = show_time
        self.show_len = show_len
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self._listeners: list[Callable[[LogEntry], None]] = []

    def get_format_options(
        self,
        color: bool | None = None,
        max_bytes: int | None = None,
        show_hex: bool | None = None,
        show_ascii: bool | None = None,
        show_time: bool | None = None,
        show_len: bool | None = None,
    ) -> FormatOptions:
        """Construct FormatOptions aligned with current logger configuration."""
        return FormatOptions(
            color=sys.stdout.isatty() if color is None else color,
            max_bytes=self.max_bytes if max_bytes is None else max_bytes,
            show_hex=self.show_hex if show_hex is None else show_hex,
            show_ascii=self.show_ascii if show_ascii is None else show_ascii,
            show_time=self.show_time if show_time is None else show_time,
            show_len=self.show_len if show_len is None else show_len,
        )

    def configure(
        self,
        *,
        trace: bool | None = None,
        show_hex: bool | None = None,
        show_ascii: bool | None = None,
        show_time: bool | None = None,
        show_len: bool | None = None,
        max_bytes: int | None = None,
        max_entries: int | None = None,
    ) -> IoLogger:
        """Batch configure logger formatting and trace options."""
        if trace is not None:
            self.trace = trace
        if show_hex is not None:
            self.show_hex = show_hex
        if show_ascii is not None:
            self.show_ascii = show_ascii
        if show_time is not None:
            self.show_time = show_time
        if show_len is not None:
            self.show_len = show_len
        if max_bytes is not None:
            self.max_bytes = max_bytes
        if max_entries is not None:
            self.max_entries = max_entries
        return self

    def clear(self) -> None:
        """Clear all stored log entries from memory."""
        self._entries.clear()

    def add_listener(self, callback: Callable[[LogEntry], None]) -> None:
        """Register a callback for new LogEntry events."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[LogEntry], None]) -> None:
        """Unregister a listener callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def record(self, entry: LogEntry) -> None:
        """Record an authoritative LogEntry into linear log memory and trace stream."""
        self._entries.append(entry)
        if self.max_entries is not None and len(self._entries) > self.max_entries:
            del self._entries[: len(self._entries) - self.max_entries]
        if self.trace:
            line = format_entry(entry, self.get_format_options())
            print(line, flush=True)
        for listener in self._listeners:
            try:
                listener(entry)
            except Exception:
                pass

    _emit = record

    def log_in(self, data: bytes, tag: str = "", meta: dict[str, Any] | None = None) -> None:
        if data:
            self.record(LogEntry(timestamp=time.time(), direction="IN", data=data, tag=tag, meta=meta or {}))

    def log_out(self, data: bytes, tag: str = "", meta: dict[str, Any] | None = None) -> None:
        if data:
            self.record(LogEntry(timestamp=time.time(), direction="OUT", data=data, tag=tag, meta=meta or {}))

    def history(self, limit: int = 100) -> list[LogEntry]:
        """Return the most recent log entries up to `limit`."""
        if limit <= 0:
            return []
        return self._entries[-limit:]

    get_entries = history

    def dump(
        self,
        limit: int = 20,
        color: bool = False,
        show_hex: bool | None = None,
        show_ascii: bool | None = None,
        show_time: bool | None = None,
        show_len: bool | None = None,
        max_bytes: int | None = None,
    ) -> str:
        """Format and return the last `limit` log entries as a multi-line string."""
        entries = self.history(limit)
        if not entries:
            return "(No log entries recorded)"
        opts = self.get_format_options(
            color=color,
            max_bytes=max_bytes,
            show_hex=show_hex,
            show_ascii=show_ascii,
            show_time=show_time,
            show_len=show_len,
        )
        return "\n".join(format_entry(e, opts) for e in entries)

    def __len__(self) -> int:
        return len(self._entries)
