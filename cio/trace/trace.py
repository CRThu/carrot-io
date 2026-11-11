"""
TraceController & ShowController - Linear trace queue with structured display controls.
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from cio.trace.formatter import FormatOptions, format_entry


@dataclass(frozen=True, slots=True)
class TraceEntry:
    """Authoritative representation of a single captured hardware I/O frame."""

    timestamp: float
    direction: Literal["IN", "OUT"] | str
    data: bytes
    tag: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def hex(self) -> str:
        """Hex string representation of payload."""
        return " ".join(f"{b:02X}" for b in self.data)

    @property
    def time_str(self) -> str:
        """Formatted timestamp HH:MM:SS.mmm."""
        t = time.localtime(self.timestamp)
        ms = int((self.timestamp % 1) * 1000)
        return f"{time.strftime('%H:%M:%S', t)}.{ms:03d}"

    def hexdump(self, max_bytes: int = 64) -> str:
        """Render a formatted hexdump string on demand."""
        return self.format_line(color=False, max_bytes=max_bytes)

    def format_line(
        self,
        options: FormatOptions | None = None,
        color: bool = False,
        max_bytes: int = 64,
        hex: bool = True,
        ascii: bool = True,
        time: bool = True,
        len: bool = True,
        **kwargs: Any,
    ) -> str:
        """Render a single formatted trace line."""
        if options is not None:
            opts = options
        else:
            opts = FormatOptions(
                color=color,
                max_bytes=max_bytes,
                hex=hex,
                ascii=ascii,
                time=time,
                len=len,
                **kwargs,
            )
        return format_entry(self, opts)

    def __repr__(self) -> str:
        return self.hexdump()


class ShowController:
    """
    Structured facade controller for trace display options.
    Supports attribute access (trace.show.hex = False) and batch calls (trace.show(ascii=False, len=False)).
    """

    __slots__ = ("_controller", "hex", "ascii", "time", "len", "color")

    def __init__(
        self,
        controller: TraceController | None = None,
        *,
        hex: bool = True,
        ascii: bool = True,
        time: bool = True,
        len: bool = True,
        color: bool | None = None,
    ) -> None:
        self._controller = controller
        self.hex = hex
        self.ascii = ascii
        self.time = time
        self.len = len
        self.color = color

    @property
    def max_bytes(self) -> int:
        if self._controller is not None:
            return self._controller.max_bytes
        return 64

    @max_bytes.setter
    def max_bytes(self, value: int) -> None:
        if self._controller is not None:
            self._controller.max_bytes = int(value)

    def __call__(
        self,
        *,
        hex: bool | None = None,
        ascii: bool | None = None,
        time: bool | None = None,
        len: bool | None = None,
        color: bool | None = None,
        max_bytes: int | None = None,
    ) -> ShowController:
        """Batch update trace display switches and parameters."""
        if hex is not None:
            self.hex = bool(hex)
        if ascii is not None:
            self.ascii = bool(ascii)
        if time is not None:
            self.time = bool(time)
        if len is not None:
            self.len = bool(len)
        if color is not None:
            self.color = bool(color)
        if max_bytes is not None and self._controller is not None:
            self._controller.max_bytes = int(max_bytes)
        return self

    def __repr__(self) -> str:
        return (
            f"ShowController(hex={self.hex}, ascii={self.ascii}, "
            f"time={self.time}, len={self.len}, color={self.color})"
        )


class TraceController:
    """
    In-memory linear trace buffer and streaming controller for TX/RX frames.
    Preserves all captured trace entries without dropping, with zero hot-path formatting cost.
    Supports structured display controls via `self.show`.
    """

    def __init__(
        self,
        enabled: bool = False,
        show: ShowController | None = None,
        max_bytes: int = 64,
        max_entries: int | None = None,
    ) -> None:
        self._entries: list[TraceEntry] = []
        self.enabled = bool(enabled)
        self.show = show if show is not None else ShowController(self)
        self.show._controller = self
        self.max_bytes = max_bytes
        self.max_entries = max_entries
        self._listeners: list[Callable[[TraceEntry], None]] = []

    def __bool__(self) -> bool:
        """Enables natural boolean checks like `if dev.trace:`."""
        return self.enabled

    def __eq__(self, other: object) -> bool:
        """Allow equality comparison with booleans (e.g. dev.trace == True)."""
        if isinstance(other, bool):
            return self.enabled is other
        return super().__eq__(other)

    def get_format_options(
        self,
        color: bool | None = None,
        max_bytes: int | None = None,
    ) -> FormatOptions:
        """Construct FormatOptions aligned with current show controller switches."""
        effective_color = self.show.color if color is None else color
        if effective_color is None:
            effective_color = sys.stdout.isatty()

        return FormatOptions(
            color=effective_color,
            max_bytes=self.max_bytes if max_bytes is None else max_bytes,
            hex=self.show.hex,
            ascii=self.show.ascii,
            time=self.show.time,
            len=self.show.len,
        )

    def clear(self) -> None:
        """Clear all stored trace entries from memory."""
        self._entries.clear()

    def add_listener(self, callback: Callable[[TraceEntry], None]) -> None:
        """Register a callback for new TraceEntry events."""
        if callback not in self._listeners:
            self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[TraceEntry], None]) -> None:
        """Unregister a listener callback."""
        if callback in self._listeners:
            self._listeners.remove(callback)

    def record(self, entry: TraceEntry) -> None:
        """Record an authoritative TraceEntry into linear memory and trace stream."""
        self._entries.append(entry)
        if self.max_entries is not None and len(self._entries) > self.max_entries:
            del self._entries[: len(self._entries) - self.max_entries]
        if self.enabled:
            line = format_entry(entry, self.get_format_options())
            print(line, flush=True)
        for listener in self._listeners:
            try:
                listener(entry)
            except Exception:
                pass

    def trace_in(self, data: bytes, tag: str = "", meta: dict[str, Any] | None = None) -> None:
        """Record an inbound (RX/<-) binary frame."""
        if data:
            self.record(TraceEntry(timestamp=time.time(), direction="IN", data=data, tag=tag, meta=meta or {}))

    def trace_out(self, data: bytes, tag: str = "", meta: dict[str, Any] | None = None) -> None:
        """Record an outbound (TX/->) binary frame."""
        if data:
            self.record(TraceEntry(timestamp=time.time(), direction="OUT", data=data, tag=tag, meta=meta or {}))

    def history(self, limit: int = 100) -> list[TraceEntry]:
        """Return the most recent trace entries up to `limit`."""
        if limit <= 0:
            return []
        return self._entries[-limit:]

    def dump(
        self,
        limit: int = 20,
        color: bool | None = None,
        max_bytes: int | None = None,
    ) -> str:
        """Format and return the last `limit` trace entries as a multi-line string."""
        entries = self.history(limit)
        if not entries:
            return "(No trace entries recorded)"
        opts = self.get_format_options(
            color=color,
            max_bytes=max_bytes,
        )
        return "\n".join(format_entry(e, opts) for e in entries)

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return f"TraceController(enabled={self.enabled}, show={self.show!r})"
