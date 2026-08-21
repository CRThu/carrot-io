"""
URL parser and factory for creating transport instances.
"""
from __future__ import annotations

import urllib.parse
from typing import Any

from cio.core.base import AsyncBaseTransport
from cio.core.exceptions import InvalidUrlError
from cio.core.registry import registry


def parse_url(url: str) -> tuple[str, str, dict[str, Any]]:
    """
    Parse a transport URL into (scheme, target_address, options_dict).
    Example: 'serial://COM3?baud=115200' -> ('serial', 'COM3', {'baud': '115200'})
    """
    parsed = urllib.parse.urlparse(url)
    if not parsed.scheme:
        raise InvalidUrlError(f"URL missing scheme: '{url}'")

    scheme = parsed.scheme.lower()
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
    trace_val: bool | None = None
    if trace_opt is not None:
        if isinstance(trace_opt, bool):
            trace_val = trace_opt
        else:
            trace_val = str(trace_opt).strip().lower() in ("true", "1", "on", "yes")

    show_hex_opt = merged_kwargs.pop("show_hex", None)
    show_ascii_opt = merged_kwargs.pop("show_ascii", None)
    show_time_opt = merged_kwargs.pop("show_time", None)
    show_len_opt = merged_kwargs.pop("show_len", None)
    max_bytes_opt = merged_kwargs.pop("max_bytes", None)

    if "+" in scheme:
        parts = scheme.split("+", 1)
        high_scheme, base_scheme = parts[0], parts[1]
        sub_url = f"{base_scheme}://{address}"

        if high_scheme == "gpio":
            base_transport = connect(sub_url, **merged_kwargs)
            from cio.composite.gpio import AsyncGpioBridge

            transport: AsyncBaseTransport = AsyncGpioBridge(base_transport, **merged_kwargs)
        elif high_scheme == "i2c":
            base_transport = connect(sub_url, **merged_kwargs)
            from cio.composite.i2c import AsyncI2cBridge

            transport = AsyncI2cBridge(base_transport, **merged_kwargs)
        elif high_scheme == "spi":
            base_transport = connect(sub_url, **merged_kwargs)
            from cio.composite.spi import AsyncSpiBridge

            transport = AsyncSpiBridge(base_transport, **merged_kwargs)
        elif high_scheme == "rpc":
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

            target_query = ("?" + urllib.parse.urlencode(url_params)) if url_params else ""
            target_url = f"{base_scheme}://{target_path}{target_query}"

            transport = RpcRemoteTransport(target_url=target_url, host=r_host, port=r_port, **merged_kwargs)
        else:
            raise InvalidUrlError(f"Unsupported high-level bridge in scheme: '{high_scheme}'")
    else:
        info = registry.get_backend_info(scheme)
        transport = info.factory_cls(address=address, **merged_kwargs)  # type: ignore

    if trace_val is not None:
        transport.trace = trace_val
    if show_hex_opt is not None:
        transport.logger.show_hex = bool(show_hex_opt)
    if show_ascii_opt is not None:
        transport.logger.show_ascii = bool(show_ascii_opt)
    if show_time_opt is not None:
        transport.logger.show_time = bool(show_time_opt)
    if show_len_opt is not None:
        transport.logger.show_len = bool(show_len_opt)
    if max_bytes_opt is not None:
        transport.logger.max_bytes = int(max_bytes_opt)
    return transport
