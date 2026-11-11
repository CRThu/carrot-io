"""
Layered Locator Parsing Engine for Hardware Transport & Bus Stacking.

Standard Locator Grammar:
    [bus[bridge]:[channel][,k=v...] @] transport:[target][,k=v...]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

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
    bridge: str | type | None = None
    channel: int | str = 0
    kwargs: dict[str, Any] = field(default_factory=dict)

    # 映射各逻辑总线的首要通道参数名称 (单一权威定义 SSOT)
    _CHANNEL_PARAM_MAP: ClassVar[dict[str, str]] = {
        "gpio": "pin",
        "i2c": "bus",
        "spi": "bus",
    }

    def to_bus_kwargs(self) -> dict[str, Any]:
        """
        Normalize descriptor options into kwargs for bus instantiation.
        Single Source of Truth (SSOT) mapping the positional channel token
        to its canonical bus parameter name ('pin' for gpio, 'bus' for others).
        """
        res = dict(self.kwargs)
        param_name = self._CHANNEL_PARAM_MAP.get(self.name, "bus")
        if param_name not in res and "channel" not in res:
            res[param_name] = self.channel
        return res

    def to_string(self) -> str:
        if isinstance(self.bridge, type):
            bridge_str = f"[{self.bridge.__name__}]"
        elif self.bridge:
            bridge_str = f"[{self.bridge}]"
        else:
            bridge_str = ""
        opts = [str(self.channel)]
        for k, v in self.kwargs.items():
            opts.append(f"{k}={v}")
        return f"{self.name}{bridge_str}:{','.join(opts)}"

    def __matmul__(self, other: Any) -> Any:
        from cio.transports.base import AsyncBaseTransport
        from cio.bus.base import AsyncBaseBus

        if isinstance(other, (AsyncBaseTransport, AsyncBaseBus)):
            bus_kwargs = self.to_bus_kwargs()

            if self.bridge is None and self.name in getattr(other, "capabilities", frozenset()):
                factory = getattr(other, self.name, None)
                if callable(factory):
                    return factory(**bus_kwargs)

            if isinstance(self.bridge, type):
                bridge_cls = self.bridge
            else:
                from cio.registry import registry
                try:
                    bridge_cls = registry.get_bridge_cls(self.name, self.bridge)
                except InvalidLocatorError as e:
                    if self.bridge is None and self.name not in getattr(other, "capabilities", frozenset()):
                        available = list(registry._bridges.get(self.name, {}).keys())
                        other_name = getattr(other, "name", other.__class__.__name__)
                        raise InvalidLocatorError(
                            f"Transport '{other_name}' does not natively support bus '{self.name}'. "
                            f"Please specify a protocol bridge explicitly in brackets, "
                            f"e.g. '{self.name}[cb]:{self.channel}' or "
                            f"'{self.name}[nc]:{self.channel}'. Available bridges: {available}. "
                            f"(Or configure CIO_DEFAULT_BRIDGE_{self.name.upper()} in your environment/.env)."
                        ) from e
                    raise
            return bridge_cls(other, **bus_kwargs)

        if isinstance(other, (TransportDescriptor, str)):
            if isinstance(self.bridge, type):
                from cio.factory import connect
                transport_target = other.to_string() if isinstance(other, TransportDescriptor) else other
                base_transport = connect(transport_target)
                return self @ base_transport

            from cio.factory import connect
            target_str = other.to_string() if isinstance(other, TransportDescriptor) else other
            return connect(f"{self.to_string()} @ {target_str}")

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
        # 防御括号内部包含冒号或逗号 (如 i2c[pkg.mod:Class]:0)
        bracket_depth = 0
        split_idx = -1
        for idx, ch in enumerate(bus_part):
            if ch == "[":
                bracket_depth += 1
            elif ch == "]":
                bracket_depth -= 1
            elif bracket_depth == 0 and ch in (":", ","):
                split_idx = idx
                break

        if split_idx != -1:
            bus_head = bus_part[:split_idx].strip()
            bus_rest = bus_part[split_idx + 1:].strip()
        else:
            bus_head = bus_part.strip()
            bus_rest = ""

        # 解析协议特化桥，如 i2c[cb]、i2c[nc]、i2c[pkg.mod:Class]
        if "[" in bus_head:
            if not bus_head.endswith("]"):
                raise InvalidLocatorError(f"Unclosed bracket in bus specification: '{bus_head}' in '{raw}'.")
            b_name, b_bridge = bus_head[:-1].split("[", 1)
            bus_name = b_name.strip().lower()
            bridge_name = b_bridge.strip()
            if not bus_name:
                raise InvalidLocatorError(f"Missing bus name before brackets in '{bus_head}' in '{raw}'.")
            if not bridge_name:
                raise InvalidLocatorError(f"Empty bridge name inside brackets in '{bus_head}' in '{raw}'.")

            from cio.registry import registry
            if not registry.has_bridge(bus_name, bridge_name):
                available = list(registry._bridges.get(bus_name, {}).keys())
                raise InvalidLocatorError(
                    f"Unsupported bridge '{bridge_name}' in '{raw}'. "
                    f"Currently only 'cb' (or None) is supported by default. "
                    f"Available: {available}. You can register custom bridges via cio.register_bridge('{bus_name}', '{bridge_name}', BridgeClass) "
                    f"or set CIO_BRIDGE_{bridge_name.upper()} in your environment/.env."
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
                            if bus_name == "gpio":
                                bus_channel = tok
                            else:
                                raise InvalidLocatorError(
                                    f"Invalid channel/pin '{tok}' for bus '{bus_name}' in '{raw}', expected integer."
                                )
                    else:
                        raise InvalidLocatorError(
                            f"Unexpected positional argument '{tok}' in bus options of '{raw}'."
                        )

        bus_desc = BusDescriptor(name=bus_name, bridge=bridge_name, channel=bus_channel, kwargs=bus_kwargs)

    return LocatorDescriptor(raw=raw, transport=transport_desc, bus=bus_desc)


class BusFactory:
    """
    Callable and indexable bus descriptor factory supporting:
      - cio.i2c(0, reg_len=2)
      - cio.i2c["cb"](reg_len=2)
      - cio.i2c[NcI2cBridge](reg_len=2)
    """

    def __init__(self, name: str, bridge: str | type | None = None):
        self.name = name
        self.bridge = bridge

    def __getitem__(self, bridge: str | type) -> BusFactory:
        if isinstance(bridge, type):
            return BusFactory(self.name, bridge)
        if not isinstance(bridge, str) or not bridge.strip():
            raise InvalidLocatorError("Bridge must be a non-empty string identifier or a bridge class.")
        return BusFactory(self.name, bridge.strip())

    def __call__(self, channel: int | str = 0, **kwargs: Any) -> BusDescriptor:
        return BusDescriptor(name=self.name, bridge=self.bridge, channel=channel, kwargs=kwargs)

    def __repr__(self) -> str:
        if isinstance(self.bridge, type):
            br = f"[{self.bridge.__name__}]"
        elif self.bridge:
            br = f"[{self.bridge}]"
        else:
            br = ""
        return f"<BusFactory {self.name}{br}>"


i2c = BusFactory("i2c")
spi = BusFactory("spi")
gpio = BusFactory("gpio")

