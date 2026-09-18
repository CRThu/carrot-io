"""
URL parser and factory for creating transport instances.
"""
from __future__ import annotations

import urllib.parse
from typing import Any

from cio.core.base import AsyncBaseTransport
from cio.core.converters import parse_bool, parse_int
from cio.core.exceptions import InvalidUrlError
from cio.core.registry import registry


def resolve_transport_name(address: str, transport: str | None = None, default: str = "serial") -> str:
    """
    确定底层物理传输名称：
    1. 显式指定的 transport 优先（如 ?transport=tcp, ?transport=ch347）
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


def parse_url(url: str) -> tuple[str, str, dict[str, Any]]:
    """
    Parse a transport URL into (scheme, target_address, options_dict).
    Example: 'serial://COM3?baud=115200' -> ('serial', 'COM3', {'baud': '115200'})
    Example: 'i2c://COM3?reg_len=2' -> ('i2c', 'COM3', {'reg_len': '2'})
    Example: 'nfc://COM10?driver=pn532' -> ('nfc', 'COM10', {'driver': 'pn532'})
    """
    if "://" not in url:
        raise InvalidUrlError(f"URL missing scheme: '{url}'")

    scheme_part, rest = url.split("://", 1)
    scheme = scheme_part.strip().lower()
    if not scheme:
        raise InvalidUrlError(f"URL missing scheme: '{url}'")

    if "+" in scheme:
        raise InvalidUrlError(
            f"Invalid composite scheme '{scheme}'. "
            f"Please use standard RFC 3986 URI: e.g. 'i2c://{rest}' or 'nfc://{rest}'."
        )

    parsed = urllib.parse.urlparse(f"dummy://{rest}")

    if parsed.netloc:
        address = parsed.netloc + parsed.path
    else:
        address = parsed.path

    query_params: dict[str, Any] = {}
    if parsed.query:
        raw_params = urllib.parse.parse_qs(parsed.query)
        for k, v in raw_params.items():
            query_params[k] = v[0] if len(v) == 1 else v

    return scheme, address, query_params


def connect(url: str, **kwargs: Any) -> AsyncBaseTransport:
    """
    Universal transport factory from URL specification.
    Supports clean standard URIs:
      - 'serial://COM3?baud=115200'
      - 'tcp://192.168.1.100:5025'
      - 'i2c://COM3?reg_len=2' (default serial transport and cb bridge)
      - 'i2c://0?transport=ch347&reg_len=2'
      - 'spi://192.168.1.100:5025?transport=tcp&cs=0'
      - 'gpio://COM3?pin=1'
      - 'nfc://COM10?driver=pn532'
      - 'nfc://COM3?driver=pn532&bus=i2c&addr=0x24'
      - 'rpc://192.168.1.100:8000/COM1?baud=115200'
    Supports `?trace=true/on/1` to automatically enable live console tracing.
    """
    scheme, address, url_params = parse_url(url)
    merged_kwargs = {**url_params, **kwargs}

    trace_opt = merged_kwargs.pop("trace", None)
    trace_val: bool | None = parse_bool(trace_opt) if trace_opt is not None else None

    show_hex_opt = merged_kwargs.pop("show_hex", None)
    show_ascii_opt = merged_kwargs.pop("show_ascii", None)
    show_time_opt = merged_kwargs.pop("show_time", None)
    show_len_opt = merged_kwargs.pop("show_len", None)
    max_bytes_opt = merged_kwargs.pop("max_bytes", None)

    try:
        import cio.composite  # noqa: F401
    except ImportError:
        pass

    # 1. 远程 RPC 硬件代理网关 (rpc://host:port/target_path)
    if scheme == "rpc":
        from cio.composite.rpc import RpcRemoteTransport

        if "/" in address:
            host_port, target_path = address.split("/", 1)
        else:
            host_port, target_path = address, ""

        if ":" in host_port:
            h, p = host_port.split(":", 1)
            r_host, r_port = h, int(p)
        else:
            r_host, r_port = host_port, 8000

        target_url_opt = merged_kwargs.pop("target_url", None)
        if target_url_opt:
            target_url = str(target_url_opt)
        else:
            target_transport = (
                merged_kwargs.pop("target_transport", None)
                or merged_kwargs.pop("transport", None)
                or resolve_transport_name(target_path, default="serial")
            )
            target_query = ("?" + urllib.parse.urlencode(merged_kwargs)) if merged_kwargs else ""
            target_url = f"{target_transport}://{target_path}{target_query}"

        transport = RpcRemoteTransport(target_url=target_url, host=r_host, port=r_port, **merged_kwargs)

    # 2. NFC 领域应用大类 (nfc://address?driver=pn532&bus=uart/i2c/spi)
    elif scheme == "nfc":
        driver = merged_kwargs.pop("driver", None)
        bus = str(merged_kwargs.pop("bus", "uart")).lower()
        transport_name = resolve_transport_name(address, merged_kwargs.pop("transport", None), default="serial")

        if bus == "uart":
            sub_transport = connect(f"{transport_name}://{address}", **merged_kwargs)
        elif bus in ("i2c", "spi"):
            sub_transport = connect(f"{bus}://{address}?transport={transport_name}", **merged_kwargs)
        else:
            raise InvalidUrlError(f"Unsupported bus '{bus}' for nfc. Expected 'uart', 'i2c', or 'spi'.")

        bridge_cls = registry.get_bridge_cls("nfc", driver)
        transport = bridge_cls(sub_transport, **merged_kwargs)

    # 3. 通用硬件总线协议桥 (i2c, spi, gpio 或自定义总线)
    elif registry.has_bus(scheme):
        transport_name = resolve_transport_name(address, merged_kwargs.pop("transport", None), default="serial")
        bridge_name = merged_kwargs.pop("bridge", None)

        base_transport = connect(f"{transport_name}://{address}", **merged_kwargs)

        # 硬件原生具备专有总线派生能力且未指定特殊协议桥 (如 ch347.i2c() / ch347.spi())
        if bridge_name is None and scheme in base_transport.capabilities:
            factory_method = getattr(base_transport, scheme, None)
            if callable(factory_method):
                transport = factory_method(**merged_kwargs)
            else:
                bridge_cls = registry.get_bridge_cls(scheme, bridge_name)
                transport = bridge_cls(base_transport, **merged_kwargs)
        else:
            bridge_cls = registry.get_bridge_cls(scheme, bridge_name)
            transport = bridge_cls(base_transport, **merged_kwargs)

    # 4. 底层物理传输驱动 (serial, tcp, udp, ftdi, ch347, mock...)
    else:
        info = registry.get_backend_info(scheme)
        transport = info.factory_cls(address=address, **merged_kwargs)  # type: ignore

    # 统一挂载跟踪与日志配置 (基于 AsyncBaseTransport 核心契约)
    if trace_val is not None:
        transport.trace = trace_val
    if show_hex_opt is not None:
        transport.logger.show_hex = parse_bool(show_hex_opt)
    if show_ascii_opt is not None:
        transport.logger.show_ascii = parse_bool(show_ascii_opt)
    if show_time_opt is not None:
        transport.logger.show_time = parse_bool(show_time_opt)
    if show_len_opt is not None:
        transport.logger.show_len = parse_bool(show_len_opt)
    if max_bytes_opt is not None:
        transport.logger.max_bytes = parse_int(max_bytes_opt, default=64)

    return transport
