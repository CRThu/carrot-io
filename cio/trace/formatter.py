"""
Pluggable Trace Formatter Engine and Protocol Formatter Registry.
Decouples domain-specific bus/protocol formatting and rendering from TraceController core.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from cio.trace.trace import TraceEntry


@dataclass(frozen=True, slots=True)
class FormatOptions:
    """Immutable configuration container for trace line formatting options."""

    color: bool = False
    max_bytes: int = 64
    hex: bool = True
    ascii: bool = True
    time: bool = True
    len: bool = True


FormatterFn = Callable[[Any, FormatOptions], str]

_FORMATTERS: dict[str, FormatterFn] = {}


def paint(text: str, color_code: str, enabled: bool = True) -> str:
    """Render ANSI color escape sequence if enabled and color code is non-empty."""
    if not enabled or not color_code:
        return text
    return f"\033[{color_code}m{text}\033[0m"


def register_formatter(tag: str, formatter: FormatterFn) -> None:
    """Register a specialized line formatter for a trace tag."""
    _FORMATTERS[tag.upper()] = formatter


def unregister_formatter(tag: str) -> None:
    """Unregister a specialized line formatter."""
    _FORMATTERS.pop(tag.upper(), None)


def get_formatter(tag: str) -> FormatterFn | None:
    """Get the specialized formatter for a tag, if registered."""
    return _FORMATTERS.get(tag.upper())


def format_payload(data: bytes, opts: FormatOptions) -> str:
    """
    Format binary payload into orthogonal Hex, ASCII (with '.' for control chars), and length representation.
    Fully honors independent control switches (hex, ascii, len).
    """
    if not data:
        return ""
    truncated = len(data) > opts.max_bytes
    view = data[: opts.max_bytes]

    hex_str = ""
    if opts.hex:
        h = " ".join(f"{b:02X}" for b in view)
        if truncated:
            h += f" ... ({len(data)} bytes total)"
        hex_str = paint(h, "97", opts.color)

    ascii_str = ""
    if opts.ascii:
        clean_str = "".join(chr(b) if 32 <= b <= 126 else "." for b in view)
        if truncated:
            clean_str += f" ... ({len(data)} bytes total)"
        ascii_str = f" | {clean_str}" if hex_str else clean_str

    len_str = f" {paint(f'({len(data)}B)', '90', opts.color)}" if opts.len else ""
    body = f"{hex_str}{ascii_str}".strip()
    if body:
        return f"{body}{len_str}"
    return len_str.strip()


def format_raw_entry(entry: Any, opts: FormatOptions) -> str:
    """Format generic binary stream payload (Hex Dump + ASCII view + Truncation + Directional Arrows)."""
    time_part = f"{paint(f'[{entry.time_str}]', '90', opts.color)} " if opts.time else ""

    is_out = entry.direction in ("OUT", "TX")
    arrow = "->" if is_out else "<-"
    tag_name = entry.tag if entry.tag else ("TX" if is_out else "RX")

    tag_str = paint(f"[{tag_name}]", "36" if is_out else "32", opts.color)
    arrow_str = paint(arrow, "93" if is_out else "92", opts.color)

    body = format_payload(entry.data, opts)
    if body:
        return f"{time_part}{tag_str} {arrow_str} {body}".strip()
    return f"{time_part}{tag_str} {arrow_str}".strip()


def format_entry(
    entry: Any,
    options: FormatOptions | None = None,
    **kwargs: Any,
) -> str:
    """
    Single authoritative entry point for trace entry line formatting.
    Dispatches to registered protocol formatters or falls back to generic raw formatting.
    """
    opts = options if options is not None else FormatOptions(**kwargs)

    formatter = get_formatter(entry.tag)
    if formatter is not None:
        return formatter(entry, opts)

    return format_raw_entry(entry, opts)
