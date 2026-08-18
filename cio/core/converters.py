"""
Core Type Aliases, Data Converters, and ASCII Formatting Utilities.
"""
from __future__ import annotations

from typing import Any, TypeAlias

# 1. 核心类型别名
BytesLike: TypeAlias = bytes | bytearray | int | list[int]


# ----------------------------------------------------------------------
# 2. 上行入参转换与格式化 (Input / Serialization)
# ----------------------------------------------------------------------

def ensure_bytes(data: BytesLike) -> bytes:
    """
    宽容性类型归一化：将 int, list[int], bytearray 或 bytes 统一转为 bytes。
    """
    if isinstance(data, (bytes, bytearray)):
        return bytes(data)
    if isinstance(data, int):
        if not 0 <= data <= 255:
            raise ValueError(f"Integer byte value out of range (0-255): {data}")
        return bytes([data])
    if isinstance(data, list):
        return bytes(data)
    raise TypeError(f"Expected bytes, int, or list of ints, got {type(data).__name__}")


def to_hex_str(data: BytesLike | int, prefix: bool = True) -> str:
    """
    将数据或整数格式化为十六进制字符串（如 '0x57' 或 '0x1234'）。
    """
    if isinstance(data, int):
        return f"0x{data:X}" if prefix else f"{data:X}"
    raw = ensure_bytes(data)
    hex_body = raw.hex().upper()
    return f"0x{hex_body}" if prefix else hex_body


def format_arg(arg: Any) -> str:
    """
    CarrotBridge ASCII 通用参数格式化（bytes/list 转 0xHEX，其余转 str）。
    """
    if isinstance(arg, (bytes, bytearray)):
        return f"0x{bytes(arg).hex().upper()}"
    if isinstance(arg, list):
        try:
            return f"0x{ensure_bytes(arg).hex().upper()}"
        except (ValueError, TypeError):
            pass
    return str(arg)


# ----------------------------------------------------------------------
# 3. 下行出参解析与反序列化 (Output / Deserialization)
# ----------------------------------------------------------------------

def parse_int(res: Any, default: int = 0) -> int:
    """
    将文本/弱类型返回值反序列化为 int。
    """
    if res is None:
        return default
    if isinstance(res, int):
        return res
    if isinstance(res, (bytes, bytearray)):
        return int.from_bytes(res, byteorder="big")
    if isinstance(res, str):
        clean = res.strip()
        if not clean:
            return default
        try:
            return int(clean, 0)
        except ValueError:
            return default
    try:
        return int(res)
    except Exception:
        return default


def parse_bool(res: Any) -> bool:
    """
    将 '1'/'0', 'true'/'false', 'HIGH'/'LOW', 'yes'/'no', 'on'/'off' 等解析为 bool。
    """
    if isinstance(res, bool):
        return res
    if isinstance(res, (int, float)):
        return bool(res)
    if isinstance(res, str):
        clean = res.strip().lower()
        return clean in ("1", "true", "yes", "on", "high")
    return bool(res)


def parse_hex_bytes(res: Any, nbytes: int | None = None) -> bytes:
    """
    将十六进制字符串、整数或原始数据反序列化为指定长度 bytes。
    """
    if isinstance(res, (bytes, bytearray)):
        data = bytes(res)
        return data[:nbytes] if nbytes is not None else data

    if isinstance(res, int):
        if nbytes is not None:
            try:
                return res.to_bytes(nbytes, byteorder="big")
            except OverflowError:
                pass
        bit_len = res.bit_length() or 8
        actual_len = (bit_len + 7) // 8
        return res.to_bytes(actual_len, byteorder="big")

    if isinstance(res, str):
        hex_str = res.strip()
        if hex_str.startswith(("0x", "0X")):
            hex_str = hex_str[2:]
        if len(hex_str) % 2 != 0:
            hex_str = "0" + hex_str
        try:
            data = bytes.fromhex(hex_str)
            return data[:nbytes] if nbytes is not None else data
        except ValueError:
            return b""

    return b""


def parse_int_list(res: Any) -> list[int]:
    """
    将逗号/方括号分隔的文本（如 '0x50,0x57' 或 '[0x50, 0x57]'）解析为 list[int]。
    """
    if res is None:
        return []
    if isinstance(res, (list, tuple)):
        return [int(x) if not isinstance(x, str) else int(x.strip(), 0) for x in res]
    if isinstance(res, int):
        return [res]
    if isinstance(res, str):
        clean = res.strip()
        if clean.startswith("[") and clean.endswith("]"):
            clean = clean[1:-1].strip()
        if not clean:
            return []
        result: list[int] = []
        for item in clean.split(","):
            item_str = item.strip()
            if item_str:
                try:
                    result.append(int(item_str, 0))
                except ValueError:
                    pass
        return result
    return []
