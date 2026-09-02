"""
Unit tests for cio.core.protocol (ProtocolTransport).
"""
import pytest
from cio.core.codec import LineCodec
from cio.core.exceptions import ReadTimeoutError
from cio.testing.mock import MockTransport


@pytest.mark.asyncio
async def test_protocol_transport_async():
    pipe = MockTransport(timeout=0.1)
    codec = LineCodec(delimiter=b"\n")
    proto = pipe.bind(codec)

    assert not proto.is_open
    await proto.open()
    assert proto.is_open

    # write typed
    written = await proto.write("HELLO")
    assert written == 6
    assert pipe.tx_history == [b"HELLO\n"]

    # push raw and read typed
    pipe.push_rx(b"WORLD\n")
    msg = await proto.read()
    assert msg == "WORLD"

    # flush
    await proto.flush()
    assert proto.history() is not None

    # async context manager
    async with proto as p:
        assert p.is_open

    await proto.close()
    assert not proto.is_open


def test_protocol_transport_sync():
    pipe = MockTransport()
    codec = LineCodec(delimiter=b"\n")
    pipe.add_auto_reply(b"PING\n", b"PONG\n")

    proto = pipe.bind(codec)
    with proto as p:
        p.write("PING")
        msg = p.read()
        assert msg == "PONG"


@pytest.mark.asyncio
async def test_protocol_transport_eof_timeout():
    pipe = MockTransport(timeout=0.05)
    codec = LineCodec(delimiter=b"\n")
    proto = pipe.bind(codec)

    await proto.open()
    pipe.push_rx(b"INCOMPLETE_NO_NEWLINE")
    with pytest.raises(ReadTimeoutError):
        await proto.read()
    await proto.close()
