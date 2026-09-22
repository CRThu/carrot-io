"""
VISA Transport Backend (PyVISA & NI-VISA / Keysight VISA / PyVISA-py).
"""
from __future__ import annotations

import asyncio
from typing import Any

from cio.core.exceptions import (
    CDllMissingError,
    ConnectionError,
    DriverMissingError,
    PythonPackageMissingError,
    ReadTimeoutError,
    WriteTimeoutError,
)
from cio.core.base import DEFAULT_BUFFER_SIZE
from cio.core.registry import registry
from cio.core.stream import AsyncStreamTransport


def _probe_visa() -> bool:
    try:
        import pyvisa  # type: ignore # noqa: F401

        rm = pyvisa.ResourceManager()  # type: ignore
        rm.close()
        return True
    except (ImportError, ModuleNotFoundError, OSError, Exception):
        return False


def _scan_visa() -> list[dict[str, Any]]:
    if not _probe_visa():
        return []
    try:
        import pyvisa  # type: ignore

        rm = pyvisa.ResourceManager()  # type: ignore
        resources = rm.list_resources()
        rm.close()
        return [
            {
                "scheme": "visa",
                "resource_name": str(res),
                "address": str(res),
                "description": f"VISA Resource ({res})",
            }
            for res in resources
        ]
    except Exception:
        return []


class VisaTransport(AsyncStreamTransport):
    """
    VISA (Virtual Instrument Software Architecture) Transport using PyVISA.
    Supports SCPI instrumentation such as oscilloscopes, multimeters, power supplies.
    """

    DEFAULT_TIMEOUT: float = 5.0  # 工业仪表 5.0s 特殊默认超时

    def __init__(
        self,
        resource_name: str = "",
        address: str | None = None,
        backend: str | None = None,
        timeout: float | None = 5.0,
        read_termination: str | None = None,
        write_termination: str | None = None,
        chunk_size: int = 4096,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        **kwargs: Any,
    ) -> None:
        actual_resource = address if address else resource_name
        actual_timeout = self.DEFAULT_TIMEOUT if timeout is None else timeout
        super().__init__(timeout=actual_timeout, buffer_size=buffer_size, **kwargs)
        self.resource_name = actual_resource
        self.backend = backend
        self.read_termination = read_termination
        self.write_termination = write_termination
        self.chunk_size = chunk_size
        self._rm: Any = None
        self._inst: Any = None

    @property
    def capabilities(self) -> frozenset[str]:
        return frozenset({"stream", "visa"})

    async def open(self) -> None:
        if self._is_open:
            return

        try:
            import pyvisa  # type: ignore # noqa: F401
        except (ImportError, ModuleNotFoundError):
            raise PythonPackageMissingError("pyvisa", "visa")

        try:
            loop = asyncio.get_running_loop()

            def _open_session() -> tuple[Any, Any]:
                try:
                    rm = (
                        pyvisa.ResourceManager(self.backend)
                        if self.backend
                        else pyvisa.ResourceManager()
                    )
                except pyvisa.errors.LibraryError as err:
                    raise CDllMissingError(
                        "visa32.dll / visa64.dll",
                        hint="Please install NI-VISA or Keysight VISA Runtime on your system.",
                    ) from err
                except Exception as err:
                    raise ConnectionError(
                        f"Failed to initialize VISA ResourceManager: {err}"
                    ) from err

                try:
                    inst = rm.open_resource(self.resource_name)
                    if self.timeout is not None:
                        inst.timeout = int(self.timeout * 1000)
                    if self.read_termination is not None:
                        inst.read_termination = self.read_termination
                    if self.write_termination is not None:
                        inst.write_termination = self.write_termination
                    if hasattr(inst, "chunk_size") and self.chunk_size > 0:
                        inst.chunk_size = self.chunk_size
                    return rm, inst
                except Exception as err:
                    try:
                        rm.close()
                    except Exception:
                        pass
                    raise ConnectionError(
                        f"Failed to open VISA resource '{self.resource_name}': {err}"
                    ) from err

            self._rm, self._inst = await loop.run_in_executor(None, _open_session)
            self._is_open = True
        except (DriverMissingError, ConnectionError):
            raise
        except Exception as err:
            raise ConnectionError(
                f"Unexpected error opening VISA resource '{self.resource_name}': {err}"
            ) from err

    async def close(self) -> None:
        if not self._is_open:
            return
        self._is_open = False
        inst = self._inst
        rm = self._rm
        self._inst = None
        self._rm = None

        def _close_session() -> None:
            if inst:
                try:
                    inst.close()
                except Exception:
                    pass
            if rm:
                try:
                    rm.close()
                except Exception:
                    pass

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _close_session)

    async def _write_impl(self, data: bytes) -> int:
        if not self._inst or not self._is_open:
            raise ConnectionError("VISA resource not open")

        import pyvisa

        loop = asyncio.get_running_loop()

        def _do_write() -> int:
            try:
                return self._inst.write_raw(data)
            except pyvisa.errors.VisaIOError as err:
                if err.error_code == pyvisa.constants.StatusCode.error_timeout:
                    raise WriteTimeoutError(f"VISA write operation timed out: {err}") from err
                raise ConnectionError(f"VISA write failed: {err}") from err

        return await loop.run_in_executor(None, _do_write)

    async def _read_impl(self, nbytes: int) -> bytes:
        if not self._inst or not self._is_open:
            raise ConnectionError("VISA resource not open")

        import pyvisa

        loop = asyncio.get_running_loop()

        def _do_read() -> bytes:
            try:
                # 在 VISA 消息型资源中，read_raw() 会按 chunk 读到终止符或 END 信号为止返回可用数据块，
                # 避免 read_bytes(nbytes) 因请求字节数大于仪器回包长度而发生超时挂起。
                return self._inst.read_raw()
            except pyvisa.errors.VisaIOError as err:
                if err.error_code == pyvisa.constants.StatusCode.error_timeout:
                    raise ReadTimeoutError(f"VISA read operation timed out: {err}") from err
                raise ConnectionError(f"VISA read failed: {err}") from err

        return await loop.run_in_executor(None, _do_read)

    async def write(self, data: BytesLike | str, timeout: float | None = None) -> int:
        """
        Write raw bytes or SCPI command string concurrency-safely.
        If data is str, automatically appends newline termination if missing.
        """
        if isinstance(data, str):
            term = self.write_termination or "\n"
            if not data.endswith(term):
                data = data + term
            raw_data = data.encode("utf-8")
        else:
            raw_data = data

        return await super().write(raw_data, timeout=timeout)

    async def query(
        self, cmd: BytesLike | str, delay: float = 0.0, timeout: float | None = None
    ) -> Any:
        """
        Write command, wait delay if specified, and return response (atomic transaction).
        - If cmd is str: returns decoded and stripped string response.
        - If cmd is BytesLike: returns raw bytes response (ideal for waveform data).
        """
        is_str = isinstance(cmd, str)
        raw_resp = await super().query(cmd, delay=delay, timeout=timeout)
        if is_str:
            return raw_resp.decode("utf-8", errors="replace").strip("\r\n")
        return raw_resp

    async def clear(self) -> None:
        """
        Clear device I/O buffers and reset message state via VISA viClear().
        Flushes and skips any stale or leftover response from previous operations.
        """
        if not self._inst or not self._is_open:
            return
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._inst.clear)
        except Exception:
            pass

    async def flush(self) -> None:
        """Alias to clear() for universal interface consistency."""
        await self.clear()


registry.register(
    name="visa",
    schemes=["visa", "gpib", "vxi"],
    factory_cls=VisaTransport,
    probe_fn=_probe_visa,
    scan_fn=_scan_visa,
)
