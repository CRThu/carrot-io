"""
USB Raw Transport Stub Backend (PyUSB & libusb-1.0.dll).
"""
from __future__ import annotations

from typing import Any

from cio.core.packet import AsyncPacketTransport
from cio.core.exceptions import CDllMissingError, PythonPackageMissingError
from cio.core.registry import registry


def _probe_usb() -> bool:
    try:
        import usb.core  # type: ignore # noqa: F401
        return True
    except (ImportError, ModuleNotFoundError, OSError, Exception):
        return False


class UsbTransport(AsyncPacketTransport):
    """
    Raw USB Bulk/Interrupt Transport Stub.
    """

    def __init__(self, device_id: str = "", address: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.device_id = address if address else device_id

    async def open(self) -> None:
        try:
            import usb.core  # type: ignore # noqa: F401
        except (ImportError, ModuleNotFoundError):
            raise PythonPackageMissingError("pyusb", "usb")

        raise CDllMissingError(
            "libusb-1.0.dll",
            hint="Please install libusb-1.0 backend library.",
        )

    async def close(self) -> None:
        self._is_open = False

    async def _write_impl(self, data: bytes) -> int:
        return len(data)

    async def _read_packet_impl(self) -> bytes:
        return b""


registry.register(
    name="usb",
    schemes=["usb", "hid"],
    factory_cls=UsbTransport,
    probe_fn=_probe_usb,
    scan_fn=lambda: [],
)
