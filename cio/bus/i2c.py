"""
I2C Bus Protocol Abstraction (AsyncI2cBus).
"""
from __future__ import annotations

import abc
from typing import Any

from cio.bus.base import AsyncBaseBus
from cio.converters import BytesLike, ensure_bytes
from cio.exceptions import IOOperationError
from cio.trace.formatter import FormatOptions, format_payload, paint, register_formatter
from cio.transports.base import DEFAULT_TIMEOUT


class AsyncI2cBus(AsyncBaseBus):
    """
    Abstract Base Class for I2C master buses.
    """

    def __init__(
        self,
        timeout: float | str | None = DEFAULT_TIMEOUT,
        reg_len: int = 1,
        trace: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout, trace=trace, **kwargs)
        self.default_reg_len = int(reg_len)

    @property
    def bus_tag(self) -> str:
        return "I2C"

    @property
    def bus_type(self) -> str:
        return "i2c"

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"i2c"})

    @abc.abstractmethod
    async def read(self, addr: int, nbytes: int, timeout: float | None = None) -> bytes:
        """Read nbytes from specified I2C device address."""
        raise NotImplementedError

    @abc.abstractmethod
    async def write(self, addr: int, data: BytesLike, timeout: float | None = None) -> int:
        """Write data to specified I2C device address."""
        raise NotImplementedError

    async def scan(self, timeout: float | None = None) -> list[int]:
        """Scan I2C bus for active 7-bit slave device addresses."""
        raise NotImplementedError("I2C bus scanning is not supported by this bus")

    async def read_reg(
        self,
        addr: int,
        reg: int,
        nbytes: int = 1,
        regfile: int = 0,
        reg_len: int | None = None,
        timeout: float | None = None,
    ) -> bytes:
        """Read nbytes from specified device address, regfile, and register."""
        needed_len = (reg.bit_length() + 7) // 8 or 1
        base_len = reg_len if reg_len is not None else self.default_reg_len
        actual_reg_len = max(base_len, needed_len) if reg_len is None else reg_len
        reg_bytes = reg.to_bytes(actual_reg_len, byteorder="big")

        async with self.trace_tx("RD", addr=addr, reg=reg, reg_len=actual_reg_len) as tx:
            await self.write(addr, reg_bytes, timeout=timeout)
            data = await self.read(addr, nbytes, timeout=timeout)
            tx.data = data
            return data

    async def write_reg(
        self,
        addr: int,
        reg: int,
        data: BytesLike,
        regfile: int = 0,
        reg_len: int | None = None,
        timeout: float | None = None,
        verify: bool = False,
    ) -> int:
        """Write data to specified device address, regfile, and register."""
        needed_len = (reg.bit_length() + 7) // 8 or 1
        base_len = reg_len if reg_len is not None else self.default_reg_len
        actual_reg_len = max(base_len, needed_len) if reg_len is None else reg_len
        reg_bytes = reg.to_bytes(actual_reg_len, byteorder="big")
        raw_data = ensure_bytes(data)

        async with self.trace_tx("WR", addr=addr, reg=reg, reg_len=actual_reg_len, data=raw_data):
            res = await self.write(addr, reg_bytes + raw_data, timeout=timeout)
            if verify:
                read_back = await self.read_reg(
                    addr=addr,
                    reg=reg,
                    nbytes=len(raw_data),
                    regfile=regfile,
                    reg_len=actual_reg_len,
                    timeout=timeout,
                )
                if read_back != raw_data:
                    raise IOOperationError(
                        f"write_reg verification failed for addr=0x{addr:02X}, reg=0x{reg:04X}: "
                        f"expected {raw_data.hex().upper()}, got {read_back.hex().upper()}"
                    )
            return res


# ==============================================================================
# I2C Semantic Trace Formatter (Domain Rendering & Self-Registration)
# ==============================================================================

_I2C_OP_COLORS: dict[str, str] = {
    "RD": "92",     # Green
    "WR": "93",     # Yellow
    "SCAN": "95",   # Magenta
}


def format_i2c_entry(
    entry: Any,
    options: FormatOptions | None = None,
    **kwargs: Any,
) -> str:
    """
    Format an I2C semantic bus transaction line.
    Format: [HH:MM:SS.mmm] [I2C] RD 0x57 @ 0xFFB0      <- 10 (1B)
    """
    opts = options if options is not None else FormatOptions(**kwargs)

    time_part = f"{paint(f'[{entry.time_str}]', '90', opts.color)} " if opts.time else ""
    tag_str = f"{paint('[I2C]', '36', opts.color)} "

    op = str(entry.meta.get("op", "RD" if entry.direction == "IN" else "WR"))
    addr = entry.meta.get("addr")
    reg = entry.meta.get("reg")
    reg_len = entry.meta.get("reg_len", 1)
    error = entry.meta.get("error")
    devices = entry.meta.get("devices")

    # 1. Format raw target string for exact column width alignment (target column: 22 chars)
    if op == "SCAN":
        raw_target = "SCAN"
    elif reg is not None and addr is not None:
        reg_width = max(2, reg_len * 2)
        raw_target = f"{op} 0x{addr:02X} @ 0x{reg:0{reg_width}X}"
    elif addr is not None:
        raw_target = f"{op} 0x{addr:02X}"
    else:
        raw_target = op

    padding = " " * max(1, 22 - len(raw_target))

    # 2. Render target string with unified domain coloring (isomorphic with/without ANSI)
    op_colored = paint(op, _I2C_OP_COLORS.get(op, ""), opts.color)
    if op == "SCAN":
        target_str = op_colored
    elif reg is not None and addr is not None:
        reg_width = max(2, reg_len * 2)
        addr_c = paint(f"0x{addr:02X}", "97", opts.color)
        at_c = paint("@", "90", opts.color)
        reg_c = paint(f"0x{reg:0{reg_width}X}", "36", opts.color)
        target_str = f"{op_colored} {addr_c} {at_c} {reg_c}"
    elif addr is not None:
        target_str = f"{op_colored} {paint(f'0x{addr:02X}', '97', opts.color)}"
    else:
        target_str = op_colored

    target_part = f"{target_str}{padding}"

    # 3. Arrow direction (Outbound WR ->, Inbound RD/SCAN <-)
    arrow = "->" if op == "WR" else "<-"
    arrow_str = paint(arrow, "93" if op == "WR" else "92", opts.color)

    # 4. Payload / Result body
    if error:
        body = paint(f"[{error}]", "91", opts.color)
    elif op == "SCAN" and devices is not None:
        devs_fmt = "[" + ", ".join(f"0x{d:02X}" for d in devices) + "]" if devices else "[]"
        body = f"{paint(devs_fmt, '97', opts.color)} {paint(f'(Found {len(devices)})', '90', opts.color)}".strip()
    else:
        body = format_payload(entry.data, opts)

    if body:
        return f"{time_part}{tag_str}{target_part}{arrow_str} {body}".rstrip()
    return f"{time_part}{tag_str}{target_part}{arrow_str}".rstrip()


# Auto-register I2C domain formatter to Trace Engine
register_formatter("I2C", format_i2c_entry)
