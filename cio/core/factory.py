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


def parse_url(url: str) -> tuple[str, str, dict[str, Any]]:
    """
    Parse a transport URL into (scheme, target_address, options_dict).
    Example: 'serial://COM3?baud=115200' -> ('serial', 'COM3', {'baud': '115200'})
    """
    if "://" not in url:
        raise InvalidUrlError(f"URL missing scheme: '{url}'")

    scheme_part, rest = url.split("://", 1)
    if not scheme_part.strip():
        raise InvalidUrlError(f"URL missing scheme: '{url}'")

    scheme = scheme_part.lower()
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
    Supports composite schemes like `spi+tcp://192.168.1.100:5025` and `rpc+tcp://127.0.0.1:8000/COM1`.
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

    if "+" in scheme:
        try:
            import cio.composite  # noqa: F401
        except ImportError:
            pass

        parts = scheme.split("+")

        if parts[0] == "rpc":
            from cio.composite.rpc import RpcRemoteTransport

            base_scheme = "+".join(parts[1:])
            if "/" in address:
                host_port, target_path = address.split("/", 1)
            else:
                host_port, target_path = address, ""

            if ":" in host_port:
                h, p = host_port.split(":", 1)
                r_host, r_port = h, int(p)
            else:
                r_host, r_port = host_port, 8000

            target_query = ("?" + urllib.parse.urlencode(url_params)) if url_params else ""
            target_url = f"{base_scheme}://{target_path}{target_query}"

            transport = RpcRemoteTransport(target_url=target_url, host=r_host, port=r_port, **merged_kwargs)
        elif len(parts) == 2:
            bus, base_scheme = parts[0], parts[1]
            sub_url = f"{base_scheme}://{address}"
            base_transport = connect(sub_url, **merged_kwargs)

            if hasattr(base_transport, bus) and callable(getattr(base_transport, bus)):
                transport = getattr(base_transport, bus)(**merged_kwargs)
            else:
                bridge_cls = registry.get_bridge_cls(bus)
                transport = bridge_cls(base_transport, **merged_kwargs)
        elif len(parts) == 3:
            bus, bridge_name, base_scheme = parts[0], parts[1], parts[2]
            sub_url = f"{base_scheme}://{address}"
            base_transport = connect(sub_url, **merged_kwargs)

            bridge_cls = registry.get_bridge_cls(bus, bridge_name)
            transport = bridge_cls(base_transport, **merged_kwargs)
        else:
            raise InvalidUrlError(
                f"Malformed composite scheme '{scheme}'. Expected format: '{{bus}}+{{transport}}' or '{{bus}}+{{bridge}}+{{transport}}'."
            )
    else:
        info = registry.get_backend_info(scheme)
        transport = info.factory_cls(address=address, **merged_kwargs)  # type: ignore

    if hasattr(transport, "trace") and trace_val is not None:
        transport.trace = trace_val
    if hasattr(transport, "logger"):
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
