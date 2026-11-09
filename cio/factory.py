"""
Layered locator parser and factory for creating transport and bus instances.
"""
from __future__ import annotations

from typing import Any

from cio.bus.base import AsyncBaseBus
from cio.converters import parse_bool, parse_int
from cio.exceptions import InvalidLocatorError
from cio.locator import LocatorDescriptor, parse_locator
from cio.registry import registry
from cio.transports.base import AsyncBaseTransport


def resolve_transport_name(address: str, transport: str | None = None, default: str = "serial") -> str:
    """
    确定底层物理传输名称：
    1. 显式指定的 transport 优先（如 transport=tcp, transport=ch347）
    2. 特殊虚拟地址 mock / dummy 走 mock
    3. 默认均为 serial
    """
    if transport:
        return transport.strip().lower()
    addr = (address or "").strip().lower()
    if addr in ("mock", "dev", "dummy"):
        return "mock"
    return default


def infer_transport(address: str, default: str = "serial") -> str:
    """向后兼容别名，直接委托给 resolve_transport_name。"""
    return resolve_transport_name(address=address, default=default)


def connect(locator: str, **kwargs: Any) -> AsyncBaseTransport | AsyncBaseBus:
    """
    Universal transport and bus factory from layered locator specification.

    Layered Locator Grammar:
        [bus[bridge]:[channel][,k=v...] @] transport:[target][,k=v...]

    Examples:
      - Single tier (Physical transport):
          'serial:COM3,baud=115200'
          'tcp:192.168.1.100:5025'
          'udp:192.168.1.100:5025'
          'ch347:0'
          'mock:dut'
          'visa:USB0::0x2A8D::0x9007::MY63160152::INSTR,timeout=3.5'
          'rpc:192.168.1.100:8000/COM1,baud=115200'
      - Dual tier (Bridged bus attached to physical transport):
          'i2c:0,reg_len=2 @ serial:COM3,baud=2000000'
          'i2c[cb]:0,reg_len=2 @ serial:COM3,baud=2000000'
          'spi:0,cs=1 @ serial:COM3,baud=2000000'
          'gpio:1 @ serial:COM3,baud=2000000'
          'i2c:0,frequency=400000 @ ch347:0'
    """
    if not isinstance(locator, str) or not locator.strip():
        raise InvalidLocatorError(f"Locator cannot be empty, got: {locator!r}")

    if "://" in locator:
        raise InvalidLocatorError(
            f"Legacy URI scheme '://' is deprecated. "
            f"Please use layered locator syntax: 'bus[bridge]:channel,kwargs @ transport:target,kwargs' "
            f"(e.g. 'i2c:0,reg_len=2 @ serial:COM3,baud=2000000' or 'serial:COM3,baud=115200'). Got: '{locator}'"
        )

    desc = parse_locator(locator)

    try:
        import cio.composite  # noqa: F401
    except ImportError:
        pass

    # Extract global trace and logging options
    logger_opts: dict[str, Any] = {}
    for opt in ("trace", "show_hex", "show_ascii", "show_time", "show_len", "max_bytes"):
        val = kwargs.pop(opt, None)
        if val is None and desc.bus and opt in desc.bus.kwargs:
            val = desc.bus.kwargs.pop(opt)
        if val is None and opt in desc.transport.kwargs:
            val = desc.transport.kwargs.pop(opt)
        if val is not None:
            logger_opts[opt] = val

    if not desc.is_bridged:
        # 单层物理传输 (Single Tier)
        trans_kwargs = {**desc.transport.kwargs, **kwargs}
        transport_name = desc.transport.name
        address = desc.transport.target

        if registry.has_scheme_factory(transport_name):
            factory_fn = registry.get_scheme_factory(transport_name)
            transport = factory_fn(address=address, **trans_kwargs)
        elif registry.has_backend(transport_name):
            info = registry.get_backend_info(transport_name)
            transport = info.factory_cls(address=address, **trans_kwargs)
        elif registry.has_bus(transport_name):
            raise InvalidLocatorError(
                f"Bus '{transport_name}' requires a physical transport "
                f"(e.g. '{transport_name}:0 @ serial:COM3' or '{transport_name}:0 @ ch347:0')."
            )
        else:
            raise InvalidLocatorError(
                f"Unsupported or unregistered transport backend: '{transport_name}'."
            )
    else:
        # 双层协议桥总线 (Dual Tier: 逻辑端与物理端各归各的表达式选项)
        assert desc.bus is not None
        base_kwargs = dict(desc.transport.kwargs)
        bus_kwargs = {**desc.bus.kwargs, **kwargs}

        if "timeout" in bus_kwargs and "timeout" not in base_kwargs:
            base_kwargs["timeout"] = bus_kwargs["timeout"]

        # 映射 channel
        if desc.bus.name == "gpio":
            if "pin" not in bus_kwargs:
                bus_kwargs["pin"] = desc.bus.channel
        else:
            if "bus" not in bus_kwargs and "channel" not in bus_kwargs:
                bus_kwargs["bus"] = desc.bus.channel

        base_name = desc.transport.name
        base_target = desc.transport.target

        # 1. 实例化底层物理底座
        if registry.has_scheme_factory(base_name):
            factory_fn = registry.get_scheme_factory(base_name)
            base_transport = factory_fn(address=base_target, **base_kwargs)
        elif registry.has_backend(base_name):
            info = registry.get_backend_info(base_name)
            base_transport = info.factory_cls(address=base_target, **base_kwargs)
        else:
            raise InvalidLocatorError(
                f"Unsupported or unregistered transport backend: '{base_name}'."
            )

        # 2. 硬件原生总线能力探测 (如 ch347.i2c() / ch347.spi())
        bus_name = desc.bus.name
        bridge_name = desc.bus.bridge

        if bridge_name is None and bus_name in getattr(base_transport, "capabilities", frozenset()):
            factory_method = getattr(base_transport, bus_name, None)
            if callable(factory_method):
                transport = factory_method(**bus_kwargs)
            else:
                bridge_cls = registry.get_bridge_cls(bus_name, bridge_name)
                transport = bridge_cls(base_transport, **bus_kwargs)
        else:
            bridge_cls = registry.get_bridge_cls(bus_name, bridge_name)
            transport = bridge_cls(base_transport, **bus_kwargs)

    # 统一挂载跟踪与日志配置 (基于 AsyncBaseTransport 核心契约)
    if "trace" in logger_opts:
        transport.trace = parse_bool(logger_opts["trace"])
    if "show_hex" in logger_opts:
        transport.logger.show_hex = parse_bool(logger_opts["show_hex"])
    if "show_ascii" in logger_opts:
        transport.logger.show_ascii = parse_bool(logger_opts["show_ascii"])
    if "show_time" in logger_opts:
        transport.logger.show_time = parse_bool(logger_opts["show_time"])
    if "show_len" in logger_opts:
        transport.logger.show_len = parse_bool(logger_opts["show_len"])
    if "max_bytes" in logger_opts:
        transport.logger.max_bytes = parse_int(logger_opts["max_bytes"], default=64)

    return transport
