"""
Unit tests for Protocol Bridges (AsyncSpiBridge, AsyncI2cBridge, RpcRemoteTransport).
"""
import asyncio
import pytest
from cio.composite.i2c import AsyncI2cBridge
from cio.composite.rpc import RpcRemoteTransport
from cio.composite.spi import AsyncSpiBridge
from cio.testing.mock import MockGpioPin, MockTransport


@pytest.mark.asyncio
async def test_spi_bridge():
    pipe = MockTransport()
    cs = MockGpioPin(initial_state=True)
    spi = AsyncSpiBridge(pipe, cs_pin=cs)

    await spi.open()

    async def device_resp():
        while not pipe.tx_history:
            await asyncio.sleep(0.005)
        pipe.push_rx(b"[RETURN]: 0x1234\n")

    t = asyncio.create_task(device_resp())
    rx = await spi.transfer(b"\xAB\xCD")
    await t

    assert rx == b"\x12\x34"
    assert cs.state_history == [True, False, True]
    await spi.close()


@pytest.mark.asyncio
async def test_i2c_bridge():
    pipe = MockTransport()
    i2c = AsyncI2cBridge(pipe)

    await i2c.open()

    async def device_resp_w():
        while not pipe.tx_history:
            await asyncio.sleep(0.005)
        pipe.push_rx(b"[RETURN]: 1\n")

    t1 = asyncio.create_task(device_resp_w())
    written = await i2c.write_to(0x68, b"\x00")
    await t1
    assert written == 1

    async def device_resp_r():
        while len(pipe.tx_history) < 2:
            await asyncio.sleep(0.005)
        pipe.push_rx(b"[RETURN]: 0x55\n")

    t2 = asyncio.create_task(device_resp_r())
    val = await i2c.read_from(0x68, 1)
    await t2
    assert val == b"\x55"

    await i2c.close()


@pytest.mark.asyncio
async def test_rpc_bridge():
    pipe = MockTransport()
    rpc = RpcRemoteTransport(target_url="tcp://127.0.0.1:5025", transport=pipe)

    pipe.push_rx(b'{"jsonrpc":"2.0","result":{"status":"ok"},"id":1}\n')
    await rpc.open()
    assert pipe.tx_history[0] == b'{"jsonrpc": "2.0", "method": "open", "params": {"url": "tcp://127.0.0.1:5025"}, "id": 1}\n'

    pipe.push_rx(b'{"jsonrpc":"2.0","result":{"val":42},"id":2}\n')
    res = await rpc.call_method("get_status", {"id": 10})
    assert res == {"val": 42}
    await rpc.close()
