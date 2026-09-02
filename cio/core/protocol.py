"""
ProtocolTransport - Higher-level protocol binding wrapper.
"""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from cio.core.base import SyncTransportWrapper
from cio.core.exceptions import ReadTimeoutError

if TYPE_CHECKING:
    from cio.core.base import AsyncBaseTransport
    from cio.core.codec import BaseCodec


class ProtocolTransport:
    """
    High-level bound protocol object operating on typed messages.
    """

    def __init__(self, transport: AsyncBaseTransport, codec: BaseCodec) -> None:
        self.transport = transport
        self.codec = codec
        self._buffer = bytearray()
        self._sync_wrapper: SyncTransportWrapper | None = None

    def _get_lock(self) -> asyncio.Lock:

        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if getattr(self, "_lock", None) is None or getattr(self, "_lock_loop", None) != current_loop:
            self._lock = asyncio.Lock()
            self._lock_loop = current_loop
        return self._lock

    @property
    def sync(self) -> SyncTransportWrapper:
        """Universal synchronous wrapper for this protocol transport."""
        if self._sync_wrapper is None:
            self._sync_wrapper = SyncTransportWrapper(self)
        return self._sync_wrapper

    @property
    def is_open(self) -> bool:
        return self.transport.is_open

    async def open(self) -> None:
        await self.transport.open()

    async def close(self) -> None:
        await self.transport.close()

    async def write(self, message: Any, timeout: float | None = None) -> int:
        """Encode message and write raw bytes via transport."""
        data = self.codec.encode(message)
        return await self.transport.write(data, timeout=timeout)

    async def read(self, timeout: float | None = None) -> Any:
        """Read raw bytes from transport, feed codec buffer, and return decoded message."""
        async with self._get_lock():
            msg, consumed = self.codec.decode(self._buffer)
            if consumed > 0:
                del self._buffer[:consumed]
            if msg is not None:
                return msg

            effective_timeout = timeout if timeout is not None else self.transport.timeout
            start_time = asyncio.get_event_loop().time()

            while True:
                if effective_timeout is not None:
                    elapsed = asyncio.get_event_loop().time() - start_time
                    remaining = effective_timeout - elapsed
                    if remaining <= 0:
                        raise ReadTimeoutError(f"Protocol read timed out after {effective_timeout}s")
                    chunk = await self.transport.read(-1, timeout=remaining)
                else:
                    chunk = await self.transport.read(-1)

                if not chunk:
                    msg, consumed = self.codec.decode(self._buffer)
                    if consumed > 0:
                        del self._buffer[:consumed]
                    if msg is not None:
                        return msg
                    raise ReadTimeoutError("EOF reached before decoding complete message frame")

                self._buffer.extend(chunk)
                msg, consumed = self.codec.decode(self._buffer)
                if consumed > 0:
                    del self._buffer[:consumed]
                if msg is not None:
                    return msg

    async def query(self, message: Any, delay: float = 0.0, timeout: float | None = None) -> Any:
        """Encode and write message, optionally delay, and return decoded response."""
        await self.write(message, timeout=timeout)
        if delay > 0:
            await asyncio.sleep(delay)
        return await self.read(timeout=timeout)

    async def flush(self) -> None:
        async with self._get_lock():
            self._buffer.clear()
            await self.transport.flush()

    def history(self, limit: int = 100) -> Any:
        return self.transport.history(limit=limit)

    def dump_history(
        self,
        limit: int = 20,
        color: bool = False,
        show_hex: bool | None = None,
        show_ascii: bool | None = None,
        show_time: bool | None = None,
        show_len: bool | None = None,
        max_bytes: int | None = None,
    ) -> str:
        return self.transport.dump_history(
            limit=limit,
            color=color,
            show_hex=show_hex,
            show_ascii=show_ascii,
            show_time=show_time,
            show_len=show_len,
            max_bytes=max_bytes,
        )


    async def __aenter__(self) -> ProtocolTransport:
        await self.open()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    def __enter__(self) -> Any:
        return self.sync.__enter__()

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return self.sync.__exit__(exc_type, exc_val, exc_tb)
