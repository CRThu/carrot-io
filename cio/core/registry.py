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


class BackendRegistry:
    """
    Registry for transport backends with silent probing and graceful degradation.
    """

    def __init__(self) -> None:
        self._backends: dict[str, BackendInfo] = {}
        self._scheme_map: dict[str, str] = {}

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


global_registry = BackendRegistry()
registry = global_registry
