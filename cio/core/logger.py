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
    direction: Literal["IN", "OUT", "EVT"] | str
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
        color: bool = False,
        max_bytes: int = 64,
        show_hex: bool = True,
        show_ascii: bool = True,
        show_time: bool = True,
        show_len: bool = True,
    ) -> str:
        """Render a single formatted log line with customizable fields and optional ANSI colors."""
        # 1. Timestamp part
        time_part = ""
        if show_time:
            time_part = f"\033[90m[{self.time_str}]\033[0m " if color else f"[{self.time_str}] "

        # 2. Direction and Tag part (3-char dir, 6-char tag for perfect grid alignment)
        if self.direction == "EVT":
            dir_code = "EVT"
            dir_str = f"\033[33m[{dir_code}]\033[0m" if color else f"[{dir_code}]"
        elif self.direction == "IN":
            dir_code = "IN "
            dir_str = f"\033[32m[{dir_code}]\033[0m" if color else f"[{dir_code}]"
        else:
            dir_code = f"{self.direction:<3}"
            dir_str = f"\033[36m[{dir_code}]\033[0m" if color else f"[{dir_code}]"

        tag_part = f" [{self.tag:<6}]" if self.tag else ""

        # 3. Length part (only for data frames, not for events)
        len_part = ""
        if show_len and self.direction != "EVT":
            len_part = f"\033[33m({len(self.data)}B)\033[0m" if color else f"({len(self.data)}B)"

        prefix_parts = [f"{time_part}{dir_str}{tag_part}".strip()]
        if len_part:
            prefix_parts.append(len_part)
        prefix = " ".join(prefix_parts)

        # Handle EVT payload directly as UTF-8 string with stripped control characters
        if self.direction == "EVT":
            msg = self.data.decode("utf-8", errors="replace").strip().replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
            return f"{prefix} {msg}".strip()

        # 4. Check if this is an ASCII protocol command/response (e.g. CarrotBridge CMD/RETURN/MSG)
        is_text_tag = self.tag in ("CMD", "RETURN", "MSG")
        is_printable_ascii = False
        if is_text_tag and show_ascii:
            try:
                decoded = self.data.decode("utf-8")
                # Ensure all characters are either printable ASCII or standard whitespace
                is_printable_ascii = bool(decoded) and all(c in "\r\n\t " or (32 <= ord(c) <= 126) for c in decoded)
            except UnicodeDecodeError:
                is_printable_ascii = False

        if is_text_tag and is_printable_ascii and show_ascii and not (show_hex and not show_ascii):
            clean_text = self.data.decode("utf-8", errors="replace").strip().replace("\r", "").replace("\n", "")
            if self.tag == "RETURN" and clean_text.startswith("[RETURN]:"):
                clean_text = clean_text[len("[RETURN]:"):].strip()
            if color:
                if self.tag == "CMD":
                    clean_text = f"\033[96m{clean_text}\033[0m"
                elif self.tag == "RETURN":
                    clean_text = f"\033[92m{clean_text}\033[0m"
                elif self.tag == "MSG":
                    clean_text = f"\033[90m{clean_text}\033[0m"
            return f"{prefix} {clean_text}".strip()

        truncated = len(self.data) > max_bytes
        view = self.data[:max_bytes]

        # 5. General Binary Data payload formatting (Hex and/or ASCII)
        hex_str = ""
        if show_hex:
            h = " ".join(f"{b:02X}" for b in view)
            if truncated:
                h += f" ... ({len(self.data)} bytes total)"
            hex_str = h

        ascii_str = ""
        if show_ascii:
            has_printable = any(32 <= b <= 126 for b in view)
            if has_printable:
                clean_str = "".join(chr(b) if 32 <= b <= 126 else "." for b in view)
                if show_hex and hex_str:
                    ascii_str = f" | {clean_str}"
                else:
                    if truncated:
                        clean_str += f" ... ({len(self.data)} bytes total)"
                    ascii_str = clean_str

        # Assemble final line
        body = f"{hex_str}{ascii_str}".strip()
        if body:
            return f"{prefix} {body}"
        return prefix

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

    def _emit(self, entry: LogEntry) -> None:
        self._entries.append(entry)
        if self.max_entries is not None and len(self._entries) > self.max_entries:
            del self._entries[: len(self._entries) - self.max_entries]
        if self.trace:
            line = entry.format_line(
                color=sys.stdout.isatty(),
                max_bytes=self.max_bytes,
                show_hex=self.show_hex,
                show_ascii=self.show_ascii,
                show_time=self.show_time,
                show_len=self.show_len,
            )
            print(line, flush=True)
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

    def log_event(self, tag: str, message: str, meta: dict[str, Any] | None = None) -> None:
        """Record an arbitrary lifecycle/diagnostic event into log queue (e.g. DELAY, INFO, SYSTEM)."""
        msg_str = str(message)
        if msg_str:
            self._emit(
                LogEntry(
                    timestamp=time.time(),
                    direction="EVT",
                    data=msg_str.encode("utf-8"),
                    tag=tag,
                    meta=meta or {},
                )
            )

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
        h = self.show_hex if show_hex is None else show_hex
        a = self.show_ascii if show_ascii is None else show_ascii
        t = self.show_time if show_time is None else show_time
        l = self.show_len if show_len is None else show_len
        mb = self.max_bytes if max_bytes is None else max_bytes
        return "\n".join(
            e.format_line(
                color=color,
                max_bytes=mb,
                show_hex=h,
                show_ascii=a,
                show_time=t,
                show_len=l,
            )
            for e in entries
        )

    def clear(self) -> None:
        self._entries.clear()

    def __len__(self) -> int:
        return len(self._entries)
