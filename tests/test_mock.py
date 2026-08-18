"""
Unit tests for MockTransport, MockGpioPin, AsyncBaseTransport, and SyncTransportWrapper.
"""
import pytest
from cio.core.codec import LineCodec
from cio.testing.mock import MockGpioPin, MockTransport


@pytest.mark.asyncio
async def test_mock_transport_async():
    dev = MockTransport()
    await dev.open()
    assert dev.is_open

    dev.push_rx(b"LINE1\nLINE2\n")
    line1 = await dev.read_until(b"\n")
    assert line1 == b"LINE1\n"

    line2 = await dev.read_until(b"\n")
    assert line2 == b"LINE2\n"

    await dev.write(b"HELLO")
    assert dev.tx_history == [b"HELLO"]
    await dev.close()
    assert not dev.is_open


@pytest.mark.asyncio
async def test_mock_transport_auto_reply():
    dev = MockTransport()
    dev.add_auto_reply(b"*IDN?", b"MOCK_DEVICE_V1.0\n")
    await dev.open()

    resp = await dev.query(b"*IDN?\n")
    assert resp == b"MOCK_DEVICE_V1.0\n"


@pytest.mark.asyncio
async def test_mock_transport_codec_bind():
    dev = MockTransport()
    proto = dev.bind(LineCodec())
    dev.push_rx(b"DATA_FRAME\n")

    async with proto:
        msg = await proto.read()
        assert msg == "DATA_FRAME"

        await proto.write("SEND_FRAME")
        assert dev.tx_history == [b"SEND_FRAME\n"]


def test_sync_transport_wrapper():
    dev = MockTransport()
    with dev as sync_dev:
        assert sync_dev.is_open
        dev.push_rx(b"SYNC_DATA\n")
        res = sync_dev.read(10)
        assert res == b"SYNC_DATA\n"
    assert not dev.is_open


@pytest.mark.asyncio
async def test_mock_gpio():
    pin = MockGpioPin(initial_state=False)
    assert not await pin.read_level()

    await pin.set_high()
    assert await pin.read_level()

    await pin.toggle()
    assert not await pin.read_level()


def test_sync_protocol_transport():
    dev = MockTransport()
    with dev as sync_dev:
        proto = sync_dev.bind(LineCodec())
        dev.push_rx(b"HELLO_SYNC\n")
        msg = proto.read()
        assert msg == "HELLO_SYNC"

        proto.write("REPLY_SYNC")
        assert dev.tx_history == [b"REPLY_SYNC\n"]


def test_sync_gpio_pin():
    pin = MockGpioPin(initial_state=False)
    assert not pin.sync.read_level()

    pin.sync.set_high()
    assert pin.sync.read_level()

    pin.sync.toggle()
    assert not pin.sync.read_level()

