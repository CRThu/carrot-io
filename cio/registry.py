"""
Backend Registry and Silent Probing System.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Callable, Type

from cio.transports.base import AsyncBaseTransport
from cio.exceptions import InvalidLocatorError, PythonPackageMissingError, CDllMissingError


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
        self._scheme_factories: dict[str, Callable[..., Any]] = {}

    def register_scheme_factory(self, scheme: str, factory_fn: Callable[..., Any]) -> None:
        """Register a custom URL factory for a specialized or composite scheme."""
        self._scheme_factories[scheme.lower()] = factory_fn

    def has_scheme_factory(self, scheme: str) -> bool:
        """Check whether a custom scheme factory is registered."""
        return scheme.lower() in self._scheme_factories

    def get_scheme_factory(self, scheme: str) -> Callable[..., Any]:
        """Get registered custom scheme factory."""
        scheme_key = scheme.lower()
        if scheme_key not in self._scheme_factories:
            raise InvalidLocatorError(f"No custom scheme factory registered for '{scheme}'.")
        return self._scheme_factories[scheme_key]

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
            raise InvalidLocatorError(f"Unsupported or unregistered transport backend: '{scheme}'")
        return self._backends[backend_name]

    def has_backend(self, name_or_scheme: str) -> bool:
        """Check whether a backend is registered by name or scheme."""
        backend_name = self._scheme_map.get(name_or_scheme.lower(), name_or_scheme.lower())
        return backend_name in self._backends

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
            if is_default and idx == 0:
                self._default_bridges[bus_key] = name_key

    def set_default_bridge(self, bus: str, name: str) -> None:
        """Set default bridge for a given bus."""
        bus_key = bus.lower()
        name_key = name.lower()
        if bus_key not in self._bridges or name_key not in self._bridges[bus_key]:
            available = list(self._bridges.get(bus_key, {}).keys())
            raise InvalidLocatorError(
                f"Cannot set unknown bridge '{name}' as default for bus '{bus}'. Available: {available}"
            )
        self._default_bridges[bus_key] = name_key

    @staticmethod
    def _resolve_class_from_string(target: str) -> Type[Any]:
        """
        Resolve a class object dynamically from a string specification.
        Supports:
          - 'module:ClassName' (e.g. 'controller_bridge:NcI2cBridge')
          - 'module.submodule.ClassName'
        """
        import importlib
        import os
        import sys

        target = target.strip()
        if ":" in target:
            mod_name, cls_name = target.split(":", 1)
        elif "." in target:
            mod_name, cls_name = target.rsplit(".", 1)
        else:
            raise InvalidLocatorError(
                f"Invalid class specification '{target}'. Expected 'module:ClassName' or 'module.submodule.ClassName'."
            )
        mod_name = mod_name.strip()
        cls_name = cls_name.strip()

        # 确保当前工作目录在 sys.path 中以支持加载本地模块 (如 controller_bridge.py)
        cwd = os.getcwd()
        if cwd not in sys.path:
            sys.path.insert(0, cwd)

        try:
            mod = importlib.import_module(mod_name)
        except Exception as err:
            raise InvalidLocatorError(
                f"Failed to import module '{mod_name}' for bridge '{target}': {err}"
            ) from err

        if not hasattr(mod, cls_name):
            raise InvalidLocatorError(f"Module '{mod_name}' has no attribute or class named '{cls_name}'.")

        cls = getattr(mod, cls_name)
        if not isinstance(cls, type):
            raise InvalidLocatorError(f"Resolved object '{target}' is not a class, got {type(cls).__name__}.")
        return cls

    def _try_load_bridge_from_env(self, bus: str, name: str) -> Type[Any] | None:
        """
        Attempt to dynamically discover and register a bridge from:
        1. Environment variables:
           - CIO_BRIDGE_{BUS}_{NAME} (e.g. CIO_BRIDGE_I2C_NC="controller_bridge:NcI2cBridge")
           - CIO_BRIDGE_{NAME} (e.g. CIO_BRIDGE_NC="controller_bridge:NcI2cBridge")
        2. Multi-bridge definition in CIO_BRIDGES:
           - CIO_BRIDGES="i2c[nc]=controller_bridge:NcI2cBridge,spi[custom]=pkg.mod:MySpi"
        3. Inline module specification in bridge name:
           - name contains ':' (e.g. "controller_bridge:NcI2cBridge")
        4. Plugin modules declared in CIO_PLUGINS:
           - CIO_PLUGINS="controller_bridge,my_plugin"
        """
        try:
            from cio.env import ensure_dotenv_loaded
            ensure_dotenv_loaded()
        except Exception:
            pass

        import os
        bus_key = bus.lower()
        name_key = name.lower()

        # 1. 检查内联模块指定 (如 i2c[controller_bridge:NcI2cBridge]:0)
        if ":" in name:
            try:
                cls = self._resolve_class_from_string(name)
                self.register_bridge(bus_key, name_key, cls)
                return cls
            except Exception:
                pass

        # 2. 检查环境变量 CIO_BRIDGE_{BUS}_{NAME} 与 CIO_BRIDGE_{NAME}
        env_keys = [
            f"CIO_BRIDGE_{bus_key.upper()}_{name_key.upper()}",
            f"CIO_BRIDGE_{name_key.upper()}",
        ]
        for ek in env_keys:
            val = os.environ.get(ek)
            if val and val.strip():
                try:
                    cls = self._resolve_class_from_string(val.strip())
                    self.register_bridge(bus_key, name_key, cls)
                    return cls
                except Exception as err:
                    raise InvalidLocatorError(
                        f"Failed to load bridge class for '{name}' configured via env var '{ek}={val}': {err}"
                    ) from err

        # 3. 检查 CIO_BRIDGES (列表格式)
        cio_bridges_env = os.environ.get("CIO_BRIDGES")
        if cio_bridges_env and cio_bridges_env.strip():
            tokens = [t.strip() for t in cio_bridges_env.split(",") if t.strip()]
            for tok in tokens:
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    k = k.strip().lower()
                    v = v.strip()
                    matched = False
                    if k == f"{bus_key}[{name_key}]" or k == name_key or k == f"[{name_key}]":
                        matched = True
                    if matched:
                        try:
                            cls = self._resolve_class_from_string(v)
                            self.register_bridge(bus_key, name_key, cls)
                            return cls
                        except Exception as err:
                            raise InvalidLocatorError(
                                f"Failed to load bridge class for '{name}' configured in CIO_BRIDGES='{tok}': {err}"
                            ) from err

        # 4. 检查 CIO_PLUGINS 自动导入外挂模块
        plugins_env = os.environ.get("CIO_PLUGINS")
        if plugins_env and plugins_env.strip():
            import importlib
            import sys
            cwd = os.getcwd()
            if cwd not in sys.path:
                sys.path.insert(0, cwd)
            for mod_name in [p.strip() for p in plugins_env.split(",") if p.strip()]:
                try:
                    importlib.import_module(mod_name)
                    if bus_key in self._bridges and name_key in self._bridges[bus_key]:
                        return self._bridges[bus_key][name_key]
                except Exception:
                    pass

        return None

    def get_bridge_cls(self, bus: str, name: str | None = None) -> Type[Any]:
        """
        Get bridge class for a given bus and optional bridge name.
        If bridge name is omitted, returns the default bridge for this bus.
        """
        bus_key = bus.lower()
        if bus_key not in self._bridges or not self._bridges[bus_key]:
            raise InvalidLocatorError(f"No protocol bridge registered for bus '{bus}'.")

        if name is None or not str(name).strip():
            default_name = self._default_bridges.get(bus_key)
            if not default_name:
                # 尝试从环境变量 CIO_DEFAULT_BRIDGE_{BUS} 或 CIO_DEFAULT_BRIDGE 加载
                try:
                    from cio.env import ensure_dotenv_loaded
                    ensure_dotenv_loaded()
                except Exception:
                    pass
                import os
                env_default = (
                    os.environ.get(f"CIO_DEFAULT_BRIDGE_{bus_key.upper()}")
                    or os.environ.get("CIO_DEFAULT_BRIDGE")
                )
                if env_default and env_default.strip():
                    env_default_key = env_default.strip().lower()
                    if env_default_key in self._bridges.get(bus_key, {}):
                        self._default_bridges[bus_key] = env_default_key
                        default_name = env_default_key
                    else:
                        loaded_cls = self._try_load_bridge_from_env(bus_key, env_default_key)
                        if loaded_cls is not None:
                            self._default_bridges[bus_key] = env_default_key
                            default_name = env_default_key

            if not default_name or default_name not in self._bridges[bus_key]:
                available = list(self._bridges.get(bus_key, {}).keys())
                raise InvalidLocatorError(
                    f"No default bridge configured for bus '{bus}'. "
                    f"Available bridges: {available}. "
                    f"Please specify a bridge explicitly in brackets, e.g. '{bus}[cb]:channel @ transport' "
                    f"or '{bus}[nc]:channel @ transport', or set CIO_DEFAULT_BRIDGE_{bus.upper()} in your environment/.env."
                )
            return self._bridges[bus_key][default_name]

        name_key = name.lower()
        if name_key not in self._bridges[bus_key]:
            # 尝试通过环境变量或动态外挂加载
            loaded_cls = self._try_load_bridge_from_env(bus_key, name)
            if loaded_cls is not None:
                return loaded_cls

            available = list(self._bridges[bus_key].keys())
            raise InvalidLocatorError(
                f"Unsupported bridge '{name}' for bus '{bus}'. Available: {available}. "
                f"You can register it via cio.register_bridge('{bus}', '{name}', BridgeClass) "
                f"or set CIO_BRIDGE_{name.upper()} in your environment/.env."
            )
        return self._bridges[bus_key][name_key]

    def has_bus(self, bus: str) -> bool:
        """Check whether a bus protocol is registered."""
        return bus.lower() in self._bridges

    def has_bridge(self, bus: str, name: str) -> bool:
        """Check whether a specific bridge is registered under a bus protocol."""
        bus_key = bus.lower()
        name_key = name.lower()
        if bus_key in self._bridges and name_key in self._bridges[bus_key]:
            return True
        return self._try_load_bridge_from_env(bus_key, name) is not None

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
