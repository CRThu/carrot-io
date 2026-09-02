"""
End-to-End Integration and Unit Tests for RPC Remote Hardware Transport Proxy & Gateway.
"""
import asyncio
import pytest
import cio
from cio.composite.rpc import RpcServer, start_rpc_server


@pytest.mark.asyncio
async def test_rpc_server_daemon_end_to_end():
    # 1. Start a local target Echo TCP Server
    async def handle_target_echo(reader, writer):
        while True:
            data = await reader.readline()
            if not data:
                break
            writer.write(data)
            await writer.drain()
        writer.close()
        await writer.wait_closed()

    echo_server = await asyncio.start_server(handle_target_echo, "127.0.0.1", 0)
    echo_host, echo_port = echo_server.sockets[0].getsockname()

    # 2. Start RpcServer daemon
    rpc_server = await start_rpc_server("127.0.0.1", 0)
    rpc_host, rpc_port = rpc_server._server.sockets[0].getsockname()

    # 3. Client connects via rpc+tcp URL scheme
    url = f"rpc+tcp://{rpc_host}:{rpc_port}/{echo_host}:{echo_port}"
    async with cio.connect(url) as client:
        # Write bytes over RPC proxy
        written = await client.write(b"PING RPC PROXY\n")
        assert written == 15

        # Read bytes over RPC proxy
        resp = await client.read_until(b"\n", timeout=2.0)
        assert resp == b"PING RPC PROXY\n"

    # 4. Clean up servers
    await rpc_server.stop()
    echo_server.close()
    await echo_server.wait_closed()


@pytest.mark.asyncio
async def test_rpc_server_error_handling():
    rpc_server = await start_rpc_server("127.0.0.1", 0)
    rpc_host, rpc_port = rpc_server._server.sockets[0].getsockname()

    # Connect to invalid target backend over RPC
    url = f"rpc+invalidscheme://{rpc_host}:{rpc_port}/device123"
    client = cio.connect(url)
    with pytest.raises(cio.TransportError):
        await client.open()
    await client.close()

    await rpc_server.stop()


@pytest.mark.asyncio
async def test_rpc_server_sync_client():
    rpc_server = await start_rpc_server("127.0.0.1", 0)
    rpc_host, rpc_port = rpc_server._server.sockets[0].getsockname()

    def sync_client_run():
        url = f"rpc+mock://{rpc_host}:{rpc_port}"
        with cio.connect(url).sync as client:
            assert client.is_open
            written = client.write(b"SYNC RPC PING\n")
            assert written == 14

    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, sync_client_run)
    finally:
        await rpc_server.stop()


