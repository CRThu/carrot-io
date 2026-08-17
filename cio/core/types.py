"""
Core Type Aliases and Data Normalization Utilities.
"""
from __future__ import annotations

from typing import TypeAlias

# 统一类型别名：二进制数据、单个字节或整数列表
BytesLike: TypeAlias = bytes | bytearray | int | list[int]


def ensure_bytes(data: BytesLike) -> bytes:
    """
    统一将 int, list[int], bytearray 或 bytes 归一化为 bytes。
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
