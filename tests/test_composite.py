"""
Unit tests for Protocol Bridges (AsyncSpiBridge, AsyncI2cBridge, RpcRemoteTransport).
"""
import pytest
from cio import FrameCodec, HardwareFrame, STATUS_OK
from cio.composite.i2c import AsyncI2cBridge
from cio.composite.rpc import RpcRemoteTransport
from cio.composite.spi import AsyncSpiBridge
from cio.testing.mock import MockGpioPin, MockTransport


@pytest.mark.asyncio
async def test_spi_bridge():
    pipe = MockTransport()
    cs = MockGpioPin(initial_state=True)
    spi = AsyncSpiBridge(pipe, cs_pin=cs)
    codec = FrameCodec()

    await spi.open()
    resp = HardwareFrame(peripheral=3, action=3, bus=0, status=STATUS_OK, payload=b"\x12\x34")
    pipe.push_rx(codec.encode(resp))

    rx = await spi.transfer(b"\xAB\xCD")

    assert rx == b"\x12\x34"
    assert cs.state_history == [True, False, True]


@pytest.mark.asyncio
async def test_i2c_bridge():
    pipe = MockTransport()
    i2c = AsyncI2cBridge(pipe)
    codec = FrameCodec()

    await i2c.open()

    resp_w = HardwareFrame(peripheral=2, action=2, bus=0, addr=0x68, status=STATUS_OK)
    pipe.push_rx(codec.encode(resp_w))
    written = await i2c.write_to(0x68, b"\x00")
    assert written == 1

    resp_r = HardwareFrame(peripheral=2, action=1, bus=0, addr=0x68, status=STATUS_OK, payload=b"\x55")
    pipe.push_rx(codec.encode(resp_r))
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
