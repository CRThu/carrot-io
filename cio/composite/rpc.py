"""
RPC Remote Hardware Transport Proxy and Gateway (RpcRemoteTransport and RpcServer).
"""
from __future__ import annotations

import asyncio
import base64
import json
from typing import Any

from cio.core.base import AsyncBaseTransport
from cio.core.exceptions import ConnectionError, IOOperationError, TransportError
from cio.core.stream import AsyncStreamTransport


class RpcRemoteTransport(AsyncStreamTransport):
    """
    Client-side transparent RPC Remote Proxy Transport.
    Proxies all transport commands (open/write/read/close) over TCP to a remote RpcServer daemon.
    """

    def __init__(
        self,
        target_url: str = "",
        host: str = "127.0.0.1",
        port: int = 8000,
        transport: AsyncBaseTransport | None = None,
        address: str | None = None,
        timeout: float | None = None,
        buffer_size: int = 1024 * 1024,
        **kwargs: Any,
    ) -> None:
        super().__init__(timeout=timeout, buffer_size=buffer_size)
        self.target_url = target_url
        self.host = host
        self.port = int(port)
        self._msg_id = 0

        if transport is not None:
            self._underlying: AsyncBaseTransport = transport
        else:
            from cio.backends.socket import TcpTransport

            actual_address = address if address else f"{self.host}:{self.port}"
            self._underlying = TcpTransport(address=actual_address, timeout=timeout)

    @property
    def is_open(self) -> bool:
        return self._is_open and self._underlying.is_open

    def _next_id(self) -> int:
        self._msg_id += 1
        return self._msg_id

    async def _send_rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        req_id = self._next_id()
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": req_id,
        }
        msg = json.dumps(payload).encode("utf-8") + b"\n"
        await self._underlying.write(msg, timeout=self.timeout)

        if isinstance(self._underlying, AsyncStreamTransport):
            resp_bytes = await self._underlying.read_until(b"\n", timeout=self.timeout)
        else:
            resp_bytes = await self._underlying.read(-1, timeout=self.timeout)

        if not resp_bytes:
            raise ConnectionError("RPC Server closed connection unexpectedly")

        try:
            resp = json.loads(resp_bytes.decode("utf-8"))
        except Exception as err:
            raise IOOperationError(f"Failed to decode RPC response: {err}") from err

        if "error" in resp and resp["error"]:
            err_msg = resp["error"].get("message") if isinstance(resp["error"], dict) else str(resp["error"])
            raise TransportError(f"Remote RPC Error: {err_msg}")

        return resp.get("result")

    async def open(self) -> None:
        if self._is_open:
            return

        if not self._underlying.is_open:
            await self._underlying.open()

        await self._send_rpc("open", {"url": self.target_url})
        self._is_open = True

    async def close(self) -> None:
        if not self._is_open:
            return
        self._is_open = False
        try:
            await self._send_rpc("close")
        except Exception:
            pass
        finally:
            if self._underlying.is_open:
                await self._underlying.close()

    async def _write_impl(self, data: bytes) -> int:
        b64_data = base64.b64encode(data).decode("ascii")
        res = await self._send_rpc("write", {"data": b64_data})
        if isinstance(res, dict) and "written" in res:
            return int(res["written"])
        return len(data)

    async def _read_impl(self, nbytes: int) -> bytes:
        res = await self._send_rpc("read", {"nbytes": nbytes})
        if isinstance(res, dict) and "data" in res:
            return base64.b64decode(res["data"].encode("ascii"))
        if isinstance(res, str):
            return base64.b64decode(res.encode("ascii"))
        return b""

    async def call_method(self, method: str, params: dict[str, Any] | None = None, timeout: float | None = None) -> Any:
        return await self._send_rpc(method, params)


class RpcServer:
    """
    Lightweight Asyncio RPC Hardware Daemon Gateway.
    Binds and exposes local cio hardware transports over TCP network.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        self.host = host
        self.port = port
        self._server: asyncio.Server | None = None

    async def start(self) -> None:
        if self._server is not None:
            return
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        active_device: AsyncBaseTransport | None = None

        try:
            while True:
                line = await reader.readline()
                if not line:
                    break

                try:
                    req = json.loads(line.decode("utf-8"))
                    req_id = req.get("id")
                    method = req.get("method")
                    params = req.get("params", {})

                    if method == "open":
                        target_url = params.get("url", "")
                        from cio.core.factory import connect

                        if active_device and active_device.is_open:
                            await active_device.close()

                        active_device = connect(target_url)
                        await active_device.open()
                        resp = {"jsonrpc": "2.0", "result": {"status": "ok"}, "id": req_id}

                    elif method == "write":
                        if not active_device or not active_device.is_open:
                            raise ConnectionError("No target hardware open on remote server")
                        raw_data = base64.b64decode(params.get("data", "").encode("ascii"))
                        written = await active_device.write(raw_data)
                        resp = {"jsonrpc": "2.0", "result": {"written": written}, "id": req_id}

                    elif method == "read":
                        if not active_device or not active_device.is_open:
                            raise ConnectionError("No target hardware open on remote server")
                        nbytes = int(params.get("nbytes", -1))
                        data = await active_device.read(nbytes)
                        b64_str = base64.b64encode(data).decode("ascii")
                        resp = {"jsonrpc": "2.0", "result": {"data": b64_str}, "id": req_id}

                    elif method == "close":
                        if active_device and active_device.is_open:
                            await active_device.close()
                            active_device = None
                        resp = {"jsonrpc": "2.0", "result": {"status": "closed"}, "id": req_id}

                    else:
                        resp = {
                            "jsonrpc": "2.0",
                            "error": {"code": -32601, "message": f"Method '{method}' not found"},
                            "id": req_id,
                        }

                except Exception as err:
                    resp = {
                        "jsonrpc": "2.0",
                        "error": {"code": -32000, "message": str(err)},
                        "id": req.get("id") if 'req' in locals() and isinstance(req, dict) else None,
                    }

                writer.write(json.dumps(resp).encode("utf-8") + b"\n")
                await writer.drain()

        except Exception:
            pass
        finally:
            if active_device and active_device.is_open:
                try:
                    await active_device.close()
                except Exception:
                    pass
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


async def start_rpc_server(host: str = "0.0.0.0", port: int = 8000) -> RpcServer:
    """Start an RpcServer daemon listening on specified host and port."""
    server = RpcServer(host=host, port=port)
    await server.start()
    return server
