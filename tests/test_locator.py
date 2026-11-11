"""
Unit tests for Layered Locator Parsing Engine (cio.locator).
"""
import pytest
from cio.exceptions import InvalidLocatorError
from cio.locator import (
    BusDescriptor,
    LocatorDescriptor,
    TransportDescriptor,
    auto_convert_value,
    parse_locator,
)


def test_auto_convert_value():
    assert auto_convert_value("true") is True
    assert auto_convert_value("on") is True
    assert auto_convert_value("yes") is True
    assert auto_convert_value("false") is False
    assert auto_convert_value("off") is False
    assert auto_convert_value("no") is False
    assert auto_convert_value("115200") == 115200
    assert auto_convert_value("0x57") == 0x57
    assert auto_convert_value("0o77") == 0o77
    assert auto_convert_value("2.5") == 2.5
    assert auto_convert_value("com3") == "com3"
    assert auto_convert_value("TCPIP::192.168.1.1::INSTR") == "TCPIP::192.168.1.1::INSTR"


def test_parse_standard_i2c_over_serial():
    desc = parse_locator("i2c:0,reg_len=2 @ serial:com3,baud=2000000")
    assert isinstance(desc, LocatorDescriptor)
    assert desc.is_bridged is True

    # Bus assertions
    assert desc.bus == BusDescriptor(
        name="i2c",
        bridge=None,
        channel=0,
        kwargs={"reg_len": 2},
    )

    # Transport assertions
    assert desc.transport == TransportDescriptor(
        name="serial",
        target="com3",
        kwargs={"baud": 2000000},
    )


def test_parse_explicit_cb_bridge():
    # Explicit 'cb'
    desc1 = parse_locator("i2c[cb]:0,reg_len=2 @ serial:com3,baud=2000000")
    assert desc1.bus.name == "i2c"
    assert desc1.bus.bridge == "cb"
    assert desc1.bus.channel == 0
    assert desc1.bus.kwargs["reg_len"] == 2

    # Alias 'carrot' is not supported, only 'cb'
    with pytest.raises(InvalidLocatorError) as excinfo:
        parse_locator("i2c[carrot]:0,reg_len=2 @ serial:com3,baud=2000000")
    assert "Unsupported bridge 'carrot'" in str(excinfo.value)
    assert "only 'cb' (or None) is supported" in str(excinfo.value)


def test_parse_rejects_unsupported_bridge():
    # Only cb and None are allowed right now
    with pytest.raises(InvalidLocatorError) as excinfo:
        parse_locator("i2c[firmata]:0 @ serial:com3")
    assert "Unsupported bridge 'firmata'" in str(excinfo.value)
    assert "only 'cb' (or None) is supported" in str(excinfo.value)

    with pytest.raises(InvalidLocatorError) as excinfo:
        parse_locator("spi[custom]:0 @ serial:com3")
    assert "Unsupported bridge 'custom'" in str(excinfo.value)


def test_parse_native_hardware_ch347():
    desc_i2c = parse_locator("i2c:0,reg_len=2 @ ch347:0")
    assert desc_i2c.is_bridged is True
    assert desc_i2c.bus.name == "i2c"
    assert desc_i2c.bus.channel == 0
    assert desc_i2c.bus.kwargs == {"reg_len": 2}
    assert desc_i2c.transport.name == "ch347"
    assert desc_i2c.transport.target == "0"

    desc_spi = parse_locator("spi:0,cs=0,speed=10000000 @ ch347:0")
    assert desc_spi.bus.name == "spi"
    assert desc_spi.bus.channel == 0
    assert desc_spi.bus.kwargs == {"cs": 0, "speed": 10000000}
    assert desc_spi.transport.name == "ch347"
    assert desc_spi.transport.target == "0"


def test_parse_gpio_pin_channel():
    desc = parse_locator("gpio:1 @ serial:com3")
    assert desc.bus.name == "gpio"
    assert desc.bus.channel == 1
    assert desc.bus.kwargs["pin"] == 1
    assert desc.transport.name == "serial"
    assert desc.transport.target == "com3"

    # Explicit pin kwarg overrides channel
    desc_explicit = parse_locator("gpio:0,pin=5 @ serial:com3")
    assert desc_explicit.bus.channel == 0
    assert desc_explicit.bus.kwargs["pin"] == 5


def test_parse_single_tier_transports():
    # Serial
    desc_ser = parse_locator("serial:com1,baud=115200,timeout=2.0")
    assert desc_ser.is_bridged is False
    assert desc_ser.bus is None
    assert desc_ser.transport.name == "serial"
    assert desc_ser.transport.target == "com1"
    assert desc_ser.transport.kwargs == {"baud": 115200, "timeout": 2.0}

    # TCP
    desc_tcp = parse_locator("tcp:192.168.1.100:5025,timeout=5.0")
    assert desc_tcp.is_bridged is False
    assert desc_tcp.transport.name == "tcp"
    assert desc_tcp.transport.target == "192.168.1.100:5025"
    assert desc_tcp.transport.kwargs == {"timeout": 5.0}

    # VISA
    desc_visa = parse_locator("visa:TCPIP::192.168.1.100::INSTR")
    assert desc_visa.is_bridged is False
    assert desc_visa.transport.name == "visa"
    assert desc_visa.transport.target == "TCPIP::192.168.1.100::INSTR"
    assert desc_visa.transport.kwargs == {}

    # Mock
    desc_mock = parse_locator("mock:dev,trace=on")
    assert desc_mock.transport.name == "mock"
    assert desc_mock.transport.target == "dev"
    assert desc_mock.transport.kwargs == {"trace": True}


def test_parse_smart_defaults():
    # Omitting channel defaults to 0 with colon
    desc1 = parse_locator("i2c:reg_len=2 @ serial:com3")
    assert desc1.bus.channel == 0
    assert desc1.bus.kwargs["reg_len"] == 2

    # Entirely omitting bus params and colon
    desc2 = parse_locator("i2c @ serial:com3")
    assert desc2.bus.name == "i2c"
    assert desc2.bus.bridge is None
    assert desc2.bus.channel == 0
    assert desc2.bus.kwargs == {}
    assert desc2.transport.target == "com3"

    # Omitting colon on bus with kwargs
    desc2_kw = parse_locator("i2c,reg_len=2 @ serial:com3")
    assert desc2_kw.bus.name == "i2c"
    assert desc2_kw.bus.channel == 0
    assert desc2_kw.bus.kwargs == {"reg_len": 2}

    # Minimal transport without target or colon (single device)
    desc3 = parse_locator("serial")
    assert desc3.transport.name == "serial"
    assert desc3.transport.target == ""
    assert desc3.transport.kwargs == {}

    # ch347 single device with and without colon
    desc_ch1 = parse_locator("ch347")
    assert desc_ch1.transport.name == "ch347"
    assert desc_ch1.transport.target == ""

    desc_ch2 = parse_locator("ch347,timeout=2.0")
    assert desc_ch2.transport.name == "ch347"
    assert desc_ch2.transport.target == ""
    assert desc_ch2.transport.kwargs == {"timeout": 2.0}

    # Dual tier omitting colon on both sides
    desc_dual = parse_locator("i2c @ ch347")
    assert desc_dual.bus.name == "i2c"
    assert desc_dual.bus.channel == 0
    assert desc_dual.transport.name == "ch347"
    assert desc_dual.transport.target == ""


def test_parse_data_conversions():
    desc = parse_locator("mock:test,trace=on,show.hex=false,speed=0x400,timeout=1.25,name=custom")
    assert desc.transport.kwargs["trace"] is True
    assert desc.transport.kwargs["show.hex"] is False
    assert desc.transport.kwargs["speed"] == 1024
    assert desc.transport.kwargs["timeout"] == 1.25
    assert desc.transport.kwargs["name"] == "custom"


def test_parse_errors():
    # Empty string
    with pytest.raises(InvalidLocatorError):
        parse_locator("")
    with pytest.raises(InvalidLocatorError):
        parse_locator("   ")

    # Multiple '@' (rejecting false multi-hop)
    with pytest.raises(InvalidLocatorError) as excinfo:
        parse_locator("i2c:0 @ cb @ serial:com3")
    assert "Multiple '@' found" in str(excinfo.value)

    # Missing components around '@'
    with pytest.raises(InvalidLocatorError):
        parse_locator("i2c:0 @")
    with pytest.raises(InvalidLocatorError):
        parse_locator("@ serial:com3")

    # Unclosed bracket
    with pytest.raises(InvalidLocatorError) as excinfo:
        parse_locator("i2c[cb:0 @ serial:com3")
    assert "Unclosed bracket" in str(excinfo.value)

    # Empty bracket
    with pytest.raises(InvalidLocatorError) as excinfo:
        parse_locator("i2c[]:0 @ serial:com3")
    assert "Empty bridge name" in str(excinfo.value)

    # Non-integer channel
    with pytest.raises(InvalidLocatorError) as excinfo:
        parse_locator("i2c:not_a_number @ serial:com3")
    assert "expected integer" in str(excinfo.value)

    # Unexpected second positional argument
    with pytest.raises(InvalidLocatorError) as excinfo:
        parse_locator("i2c:0,extra_pos @ serial:com3")
    assert "Unexpected positional argument" in str(excinfo.value)

    # Unexpected second positional in transport
    with pytest.raises(InvalidLocatorError) as excinfo:
        parse_locator("serial:com3,extra_pos")
    assert "Unexpected positional argument" in str(excinfo.value)

    # Empty parameter name in transport
    with pytest.raises(InvalidLocatorError) as excinfo:
        parse_locator("serial:com3,=val")
    assert "Empty parameter name" in str(excinfo.value)

    # Empty parameter name in bus
    with pytest.raises(InvalidLocatorError) as excinfo:
        parse_locator("i2c:0,=val @ serial:com3")
    assert "Empty parameter name" in str(excinfo.value)

    # Missing bus name before brackets
    with pytest.raises(InvalidLocatorError) as excinfo:
        parse_locator("[cb]:0 @ serial:com3")
    assert "Missing bus name before brackets" in str(excinfo.value)


def test_descriptor_to_string_and_matmul_edge_cases():
    import cio
    from cio.locator import BusDescriptor, TransportDescriptor

    bus_desc = cio.spi(1, cs=2)
    assert bus_desc.name == "spi"
    assert bus_desc.channel == 1
    assert bus_desc.kwargs == {"cs": 2}
    assert bus_desc.to_string() == "spi:1,cs=2"

    trans_desc = TransportDescriptor("serial", "COM5", {"baud": 9600})
    assert trans_desc.to_string() == "serial:COM5,baud=9600"

    # BusDescriptor @ TransportDescriptor
    bus = bus_desc @ trans_desc
    assert bus.transport.port == "COM5"

    # Invalid @ operand raises TypeError
    with pytest.raises(TypeError):
        _ = bus_desc @ 12345
