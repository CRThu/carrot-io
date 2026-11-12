"""
Base SCPI Instrument Abstraction (BaseScpiDevice).
"""
from __future__ import annotations

from typing import Any, TypeVar

import cio
from cio.transports.base import AsyncBaseTransport, SyncTransportWrapper

T = TypeVar("T", bound="BaseScpiDevice")


class BaseScpiDevice:
    """
    SCPI 仪器设备基类，封装底层流传输（VisaTransport / TcpTransport 等实际支持层）。
    """

    def __init__(self, transport: AsyncBaseTransport | SyncTransportWrapper | str, **kwargs: Any) -> None:
        self._sync_wrapper: SyncTransportWrapper | None = None
        self._external_loop = None
        if isinstance(transport, str):
            self.transport = cio.connect(transport, **kwargs)
            self._owns_transport = True
        elif isinstance(transport, SyncTransportWrapper):
            self.transport = transport._async
            self._owns_transport = False
            self._external_loop = transport._loop
        else:
            self.transport = transport
            self._owns_transport = False

    @property
    def capabilities(self) -> frozenset[str]:
        return self.transport.capabilities | frozenset({"scpi"})

    @property
    def is_open(self) -> bool:
        return bool(self.transport.is_open)

    @property
    def trace(self) -> Any:
        return self.transport.trace

    @trace.setter
    def trace(self, value: Any) -> None:
        self.transport.trace = value

    def history(self, limit: int = 100) -> list[Any]:
        return self.transport.history(limit=limit)

    def dump_history(self, **kwargs: Any) -> str:
        return self.transport.dump_history(**kwargs)

    def clear_history(self) -> None:
        self.transport.clear_history()

    async def open(self) -> None:
        if not self.transport.is_open:
            await self.transport.open()

    async def close(self) -> None:
        if self._owns_transport:
            await self.transport.close()

    @property
    def sync(self) -> Any:
        if self._sync_wrapper is None:
            self._sync_wrapper = SyncTransportWrapper(self, loop=self._external_loop)
        return self._sync_wrapper

    def __enter__(self) -> Any:
        return self.sync.__enter__()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return self.sync.__exit__(exc_type, exc_val, exc_tb)

    async def __aenter__(self: T) -> T:
        await self.open()
        return self

    async def __aexit__(self: T, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def _format_cmd(self, cmd: str | bytes) -> bytes:
        if isinstance(cmd, str):
            if not cmd.endswith("\n"):
                cmd = cmd + "\n"
            return cmd.encode("ascii")
        return cmd

    async def write(self, data: str | bytes, timeout: float | None = None) -> int:
        if not self.is_open:
            await self.open()
        return await self.transport.write(self._format_cmd(data), timeout=timeout)

    async def query(self, cmd: str | bytes, delay: float = 0.0, timeout: float | None = None) -> str:
        if not self.is_open:
            await self.open()
        raw = await self.transport.query(self._format_cmd(cmd), delay=delay, timeout=timeout)
        if isinstance(raw, bytes):
            return raw.decode("ascii", errors="replace").strip("\r\n")
        return str(raw).strip("\r\n")

    # -------------------------------------------------------------
    # IEEE 488.2 常用标准指令
    # -------------------------------------------------------------

    async def idn(self) -> str:
        """查询仪器标识符 (*IDN?)。"""
        return await self.query("*IDN?")

    async def reset(self) -> None:
        """复位仪器出厂状态 (*RST)。"""
        await self.write("*RST")

    async def clear(self) -> None:
        """清空通信缓冲区与复位状态 (viClear / *CLS)。"""
        if "visa" in self.transport.capabilities:
            await self.transport.clear()
        else:
            await self.write("*CLS")

    async def wait_opc(self) -> bool:
        """等待上一步操作执行完成 (*OPC?)。"""
        ans = await self.query("*OPC?")
        return str(ans).strip() == "1"

    async def errors(self) -> list[str]:
        """读取系统错误队列中的全部错误 (:SYST:ERR?)。"""
        errs: list[str] = []
        for _ in range(30):
            res = str(await self.query(":SYST:ERR?")).strip()
            if not res or res.startswith("+0") or res.startswith("0") or "No error" in res:
                break
            errs.append(res)
        return errs


BaseVisaDevice = BaseScpiDevice
