"""
Layered Locator Parsing Engine for Hardware Transport & Bus Stacking.

Standard Locator Grammar:
    [bus[bridge]:[channel][,k=v...] @] transport:[target][,k=v...]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cio.exceptions import InvalidLocatorError


def auto_convert_value(val: str) -> Any:
    """
    Auto-convert string token to bool, int, float, or stripped string.
    Preserves numerical representations and standard booleans.
    """
    clean = val.strip()
    clean_lower = clean.lower()

    if clean_lower in ("true", "on", "yes"):
        return True
    if clean_lower in ("false", "off", "no"):
        return False

    # Attempt integer conversion (supports decimal, hex 0x..., octal 0o...)
    try:
        return int(clean, 0)
    except ValueError:
        pass

    # Attempt float conversion
    try:
        return float(clean)
    except ValueError:
        pass

    return clean


@dataclass(frozen=True)
class BusDescriptor:
    """
    Descriptor for high-level logical bus contract and protocol bridge.
    """
    name: str
    bridge: str | None = None
    channel: int = 0
    kwargs: dict[str, Any] = field(default_factory=dict)

    def to_string(self) -> str:
        bridge_str = f"[{self.bridge}]" if self.bridge else ""
        opts = [str(self.channel)]
        for k, v in self.kwargs.items():
            opts.append(f"{k}={v}")
        return f"{self.name}{bridge_str}:{','.join(opts)}"

    def __matmul__(self, other: Any) -> Any:
        from cio.transports.base import AsyncBaseTransport
        from cio.bus.base import AsyncBaseBus

        if isinstance(other, (AsyncBaseTransport, AsyncBaseBus)):
            bus_kwargs = dict(self.kwargs)
            if self.name == "gpio":
                bus_kwargs.setdefault("pin", self.channel)
            else:
                bus_kwargs.setdefault("bus", self.channel)

            if self.bridge is None and self.name in getattr(other, "capabilities", frozenset()):
                factory = getattr(other, self.name, None)
                if callable(factory):
                    return factory(**bus_kwargs)

            from cio.registry import registry
            bridge_cls = registry.get_bridge_cls(self.name, self.bridge or "cb")
            return bridge_cls(other, **bus_kwargs)

        if isinstance(other, TransportDescriptor):
            from cio.factory import connect
            return connect(f"{self.to_string()} @ {other.to_string()}")

        if isinstance(other, str):
            from cio.factory import connect
            return connect(f"{self.to_string()} @ {other}")

        return NotImplemented


@dataclass(frozen=True)
class TransportDescriptor:
    """
    Descriptor for physical transport carrier and link parameters.
    """
    name: str
    target: str = ""
    kwargs: dict[str, Any] = field(default_factory=dict)

    def to_string(self) -> str:
        parts = [self.target] if self.target else []
        for k, v in self.kwargs.items():
            parts.append(f"{k}={v}")
        return f"{self.name}:{','.join(parts)}"


@dataclass(frozen=True)
class LocatorDescriptor:
    """
    Unified result descriptor after parsing a layered hardware locator.
    """
    raw: str
    transport: TransportDescriptor
    bus: BusDescriptor | None = None

    @property
    def is_bridged(self) -> bool:
        """Return True if locator represents a logical bus attached to a transport."""
        return self.bus is not None


def parse_locator(locator: str) -> LocatorDescriptor:
    """
    Parse a layered device locator string into a structured LocatorDescriptor.

    Examples:
      - 'i2c:0,reg_len=2 @ serial:com3,baud=2000000'
      - 'i2c[cb]:0,reg_len=2 @ serial:com3,baud=2000000'
      - 'spi:0,cs=0,speed=10000000 @ serial:com3'
      - 'gpio:1 @ serial:com3'
      - 'i2c:0,reg_len=2 @ ch347:0'
      - 'serial:com1,baud=115200'
      - 'tcp:192.168.1.100:5025'
      - 'visa:TCPIP::192.168.1.100::INSTR'
    """
    if not locator or not locator.strip():
        raise InvalidLocatorError("Locator string cannot be empty.")

    raw = locator.strip()
    parts = [p.strip() for p in raw.split("@")]

    if len(parts) > 2:
        raise InvalidLocatorError(
            f"Multiple '@' found in '{raw}'. Only a single '@' is allowed to separate bus from transport."
        )
    if any(not p for p in parts):
        raise InvalidLocatorError(f"Malformed locator '{raw}': empty component around '@'.")

    # 1. 划分逻辑端与物理端
    if len(parts) == 2:
        bus_part: str | None = parts[0]
        transport_part: str = parts[1]
    else:
        bus_part = None
        transport_part = parts[0]

    # 2. 解析物理传输端 (Physical Transport)
    if ":" in transport_part:
        trans_name, trans_rest = transport_part.split(":", 1)
        trans_name = trans_name.strip().lower()
        trans_rest = trans_rest.strip()
    elif "," in transport_part:
        trans_name, trans_rest = transport_part.split(",", 1)
        trans_name = trans_name.strip().lower()
        trans_rest = trans_rest.strip()
    else:
        trans_name = transport_part.strip().lower()
        trans_rest = ""

    if not trans_name:
        raise InvalidLocatorError(f"Missing transport name in locator: '{raw}'.")

    trans_target = ""
    trans_kwargs: dict[str, Any] = {}

    if trans_rest:
        tokens = [t.strip() for t in trans_rest.split(",") if t.strip()]
        for i, tok in enumerate(tokens):
            if "=" in tok:
                k, v = tok.split("=", 1)
                k = k.strip()
                if not k:
                    raise InvalidLocatorError(f"Empty parameter name in transport option '{tok}' in '{raw}'.")
                trans_kwargs[k] = auto_convert_value(v)
            else:
                if i == 0:
                    trans_target = tok
                else:
                    raise InvalidLocatorError(
                        f"Unexpected positional argument '{tok}' in transport options of '{raw}'."
                    )

    transport_desc = TransportDescriptor(name=trans_name, target=trans_target, kwargs=trans_kwargs)

    # 3. 解析逻辑总线端 (Logical Bus & Bridge)
    bus_desc: BusDescriptor | None = None
    if bus_part is not None:
        if ":" in bus_part:
            bus_head, bus_rest = bus_part.split(":", 1)
            bus_head = bus_head.strip()
            bus_rest = bus_rest.strip()
        elif "," in bus_part:
            bus_head, bus_rest = bus_part.split(",", 1)
            bus_head = bus_head.strip()
            bus_rest = bus_rest.strip()
        else:
            bus_head = bus_part.strip()
            bus_rest = ""

        # 解析协议特化桥，如 i2c[cb]
        if "[" in bus_head:
            if not bus_head.endswith("]"):
                raise InvalidLocatorError(f"Unclosed bracket in bus specification: '{bus_head}' in '{raw}'.")
            b_name, b_bridge = bus_head[:-1].split("[", 1)
            bus_name = b_name.strip().lower()
            bridge_name = b_bridge.strip().lower()
            if not bus_name:
                raise InvalidLocatorError(f"Missing bus name before brackets in '{bus_head}' in '{raw}'.")
            if not bridge_name:
                raise InvalidLocatorError(f"Empty bridge name inside brackets in '{bus_head}' in '{raw}'.")

            # 约束：默认仅支持 'cb' 或在注册表中显式注册的桥
            if bridge_name == "cb":
                pass
            else:
                from cio.registry import registry
                valid_bridges = {"cb"}
                if registry.has_bus(bus_name):
                    valid_bridges.update(registry._bridges.get(bus_name, {}).keys())
                if bridge_name not in valid_bridges:
                    raise InvalidLocatorError(
                        f"Unsupported bridge '{bridge_name}' in '{raw}'. Currently only 'cb' (or None) is supported."
                    )
        else:
            bus_name = bus_head.lower()
            bridge_name = None

        if not bus_name:
            raise InvalidLocatorError(f"Missing bus name in '{raw}'.")

        bus_channel = 0
        bus_kwargs: dict[str, Any] = {}

        if bus_rest:
            tokens = [t.strip() for t in bus_rest.split(",") if t.strip()]
            for i, tok in enumerate(tokens):
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    k = k.strip()
                    if not k:
                        raise InvalidLocatorError(f"Empty parameter name in bus option '{tok}' in '{raw}'.")
                    bus_kwargs[k] = auto_convert_value(v)
                else:
                    if i == 0:
                        try:
                            bus_channel = int(tok, 0)
                        except ValueError:
                            raise InvalidLocatorError(
                                f"Invalid channel/pin '{tok}' for bus '{bus_name}' in '{raw}', expected integer."
                            )
                    else:
                        raise InvalidLocatorError(
                            f"Unexpected positional argument '{tok}' in bus options of '{raw}'."
                        )

        # GPIO 语义增强：channel 默认为 pin
        if bus_name == "gpio" and "pin" not in bus_kwargs:
            bus_kwargs["pin"] = bus_channel

        bus_desc = BusDescriptor(name=bus_name, bridge=bridge_name, channel=bus_channel, kwargs=bus_kwargs)

    return LocatorDescriptor(raw=raw, transport=transport_desc, bus=bus_desc)


class BusFactory:
    """
    Callable and indexable bus descriptor factory supporting both:
      - cio.i2c(0, reg_len=2)
      - cio.i2c["cb"](reg_len=2)
    """

    def __init__(self, name: str, bridge: str | None = None):
        self.name = name
        self.bridge = bridge

    def __getitem__(self, bridge: str) -> BusFactory:
        if not isinstance(bridge, str) or not bridge.strip():
            raise InvalidLocatorError("Bridge name must be a non-empty string.")
        return BusFactory(self.name, bridge.strip())

    def __call__(self, channel: int = 0, **kwargs: Any) -> BusDescriptor:
        if self.name == "gpio" and "pin" not in kwargs:
            kwargs["pin"] = channel
        return BusDescriptor(name=self.name, bridge=self.bridge, channel=channel, kwargs=kwargs)

    def __repr__(self) -> str:
        br = f"[{self.bridge}]" if self.bridge else ""
        return f"<BusFactory {self.name}{br}>"


i2c = BusFactory("i2c")
spi = BusFactory("spi")
gpio = BusFactory("gpio")

