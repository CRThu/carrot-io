"""
Unit tests for Protocol Bridges (AsyncSpiBridge, AsyncI2cBridge, RpcRemoteTransport).
"""
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
    pipe.push_rx(b"\x12\x34")
    rx = await spi.transfer(b"\xAB\xCD")

    assert rx == b"\x12\x34"
    assert pipe.tx_history == [b"\xAB\xCD"]
    assert cs.state_history == [True, False, True]


@pytest.mark.asyncio
async def test_i2c_bridge():
    pipe = MockTransport()
    i2c = AsyncI2cBridge(pipe)

    await i2c.open()
    await i2c.write_to(0x68, b"\x00")
    assert pipe.tx_history[0] == bytes([0x68, 0x00, 0x01, 0x00])

    pipe.push_rx(b"\x55")
    val = await i2c.read_from(0x68, 1)
    assert val == b"\x55"


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
