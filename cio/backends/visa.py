"""
VISA Transport Stub Backend (PyVISA & NI-VISA DLL).
"""
from __future__ import annotations

from typing import Any

from cio.core.exceptions import CDllMissingError, PythonPackageMissingError
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


class VisaTransport(AsyncStreamTransport):
    """
    VISA Instrumentation Transport Stub.
    """


    def __init__(self, resource_name: str = "", address: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.resource_name = address if address else resource_name

    async def open(self) -> None:
        try:
            import pyvisa  # type: ignore # noqa: F401
        except (ImportError, ModuleNotFoundError):
            raise PythonPackageMissingError("pyvisa", "visa")

        raise CDllMissingError(
            "visa32.dll / visa64.dll",
            hint="Please install NI-VISA or Keysight VISA Runtime on your system.",
        )

    async def close(self) -> None:
        self._is_open = False

    async def _write_impl(self, data: bytes) -> int:
        return len(data)

    async def _read_impl(self, nbytes: int) -> bytes:
        return b""


registry.register(
    name="visa",
    schemes=["visa", "gpib", "vxi"],
    factory_cls=VisaTransport,
    probe_fn=_probe_visa,
    scan_fn=lambda: [],
)
