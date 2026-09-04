"""
Backend Registry and Silent Probing System.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Callable, Type

from cio.core.base import AsyncBaseTransport
from cio.core.exceptions import InvalidUrlError, PythonPackageMissingError, CDllMissingError


@dataclass
class BackendInfo:
    name: str
    schemes: list[str]
    factory_cls: Type[AsyncBaseTransport]
    probe_fn: Callable[[], bool]
    scan_fn: Callable[[], list[dict[str, Any]]]


@dataclass
class BridgeInfo:
    bus: str
    name: str
    bridge_cls: Type[Any]
    is_default: bool = False


class BackendRegistry:
    """
    Registry for transport backends and composite protocol bridges with silent probing.
    """

    def __init__(self) -> None:
        self._backends: dict[str, BackendInfo] = {}
        self._scheme_map: dict[str, str] = {}
        self._bridges: dict[str, dict[str, Type[Any]]] = {}
        self._default_bridges: dict[str, str] = {}

    def register(
        self,
        name: str,
        schemes: list[str],
        factory_cls: Type[AsyncBaseTransport],
        probe_fn: Callable[[], bool],
        scan_fn: Callable[[], list[dict[str, Any]]] | None = None,
    ) -> None:
        if scan_fn is None:
            scan_fn = lambda: []

        info = BackendInfo(
            name=name,
            schemes=schemes,
            factory_cls=factory_cls,
            probe_fn=probe_fn,
            scan_fn=scan_fn,
        )
        self._backends[name] = info
        for scheme in schemes:
            self._scheme_map[scheme.lower()] = name

    def is_available(self, name_or_scheme: str) -> bool:
        backend_name = self._scheme_map.get(name_or_scheme.lower(), name_or_scheme)
        info = self._backends.get(backend_name)
        if not info:
            return False

        try:
            return info.probe_fn()
        except (ImportError, ModuleNotFoundError, OSError, FileNotFoundError):
            return False
        except Exception:
            return False

    def get_backend_info(self, scheme: str) -> BackendInfo:
        backend_name = self._scheme_map.get(scheme.lower())
        if not backend_name or backend_name not in self._backends:
            raise InvalidUrlError(f"Unsupported or unregistered transport scheme: '{scheme}'")
        return self._backends[backend_name]

    def scan(self, kind: str | None = None) -> list[dict[str, Any]]:
        """
        Scan available devices across backends.
        Quietly skips unavailable backends.
        """
        results: list[dict[str, Any]] = []
        target_names = (
            [self._scheme_map.get(kind.lower(), kind)]
            if kind
            else list(self._backends.keys())
        )

        for b_name in target_names:
            if not b_name or b_name not in self._backends:
                continue
            info = self._backends[b_name]
            try:
                if not info.probe_fn():
                    continue
            except (ImportError, ModuleNotFoundError, OSError, FileNotFoundError):
                continue
            except Exception:
                continue

            try:
                found = info.scan_fn()
                results.extend(found)
            except Exception:
                pass

        return results

    def register_bridge(
        self,
        bus: str,
        name: str | list[str] | tuple[str, ...],
        bridge_cls: Type[Any],
        is_default: bool = False,
    ) -> None:
        """
        Register a protocol bridge implementation for a target bus (e.g. 'i2c', 'spi', 'gpio').

        :param bus: Target bus protocol name, e.g. 'i2c', 'spi', 'gpio'.
        :param name: Bridge identifier or list of aliases, e.g. 'cb' or ['cb', 'carrot'].
        :param bridge_cls: Bridge class taking (base_transport, **kwargs).
        :param is_default: Whether this bridge should be the default fallback when bridge name is omitted in URL.
        """
        bus_key = bus.lower()
        names = [name] if isinstance(name, str) else list(name)
        if not names:
            raise ValueError("At least one bridge name must be specified.")

        if bus_key not in self._bridges:
            self._bridges[bus_key] = {}

        for idx, n in enumerate(names):
            name_key = n.lower()
            self._bridges[bus_key][name_key] = bridge_cls
            if (is_default and idx == 0) or bus_key not in self._default_bridges:
                self._default_bridges[bus_key] = name_key

    def set_default_bridge(self, bus: str, name: str) -> None:
        """Set default bridge for a given bus."""
        bus_key = bus.lower()
        name_key = name.lower()
        if bus_key not in self._bridges or name_key not in self._bridges[bus_key]:
            available = list(self._bridges.get(bus_key, {}).keys())
            raise InvalidUrlError(
                f"Cannot set unknown bridge '{name}' as default for bus '{bus}'. Available: {available}"
            )
        self._default_bridges[bus_key] = name_key

    def get_bridge_cls(self, bus: str, name: str | None = None) -> Type[Any]:
        """
        Get bridge class for a given bus and optional bridge name.
        If bridge name is omitted, returns the default bridge for this bus.
        """
        bus_key = bus.lower()
        if bus_key not in self._bridges or not self._bridges[bus_key]:
            raise InvalidUrlError(f"No protocol bridge registered for bus '{bus}'.")

        if name is None or not str(name).strip():
            default_name = self._default_bridges.get(bus_key)
            if not default_name or default_name not in self._bridges[bus_key]:
                raise InvalidUrlError(f"No default bridge configured for bus '{bus}'.")
            return self._bridges[bus_key][default_name]

        name_key = name.lower()
        if name_key not in self._bridges[bus_key]:
            available = list(self._bridges[bus_key].keys())
            raise InvalidUrlError(
                f"Unsupported or unregistered bridge '{name}' for bus '{bus}'. Available: {available}"
            )
        return self._bridges[bus_key][name_key]

    def list_bridges(self, bus: str | None = None) -> list[BridgeInfo]:
        """
        List registered bridges, optionally filtered by bus.
        """
        results: list[BridgeInfo] = []
        target_buses = [bus.lower()] if bus else list(self._bridges.keys())
        for b in target_buses:
            if b not in self._bridges:
                continue
            default_name = self._default_bridges.get(b)
            for n, cls in self._bridges[b].items():
                results.append(
                    BridgeInfo(
                        bus=b,
                        name=n,
                        bridge_cls=cls,
                        is_default=(n == default_name),
                    )
                )
        return results


global_registry = BackendRegistry()
registry = global_registry
