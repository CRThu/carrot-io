"""
Environment variable & local .env device injection with lazy singleton management.
"""
from __future__ import annotations

import atexit
import os
import threading
from typing import Any

from cio.core.exceptions import DeviceConfigError
from cio.core.factory import connect

_ACTIVE_DEVICES: dict[str, Any] = {}
_DEVICE_LOCK = threading.Lock()
_CLEANUP_REGISTERED = False
_DOTENV_LOADED = False


def load_local_dotenv(dotenv_path: str | None = None, override: bool = False) -> dict[str, str]:
    """
    轻量级解析当前工作目录下的 .env 文件并注入 os.environ。
    仅依赖标准库，零第三方外部依赖。
    """
    global _DOTENV_LOADED
    path = dotenv_path or os.path.join(os.getcwd(), ".env")
    loaded: dict[str, str] = {}

    if not os.path.isfile(path):
        _DOTENV_LOADED = True
        return loaded

    try:
        with open(path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                # 忽略空行与注释
                if not line or line.startswith("#"):
                    continue
                # 支持 export KEY=VAL 语法
                if line.startswith("export "):
                    line = line[7:].strip()
                if "=" not in line:
                    continue

                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()

                # 去除外层配对的单双引号
                if len(val) >= 2 and (
                    (val.startswith('"') and val.endswith('"'))
                    or (val.startswith("'") and val.endswith("'"))
                ):
                    val = val[1:-1]

                loaded[key] = val
                if override or key not in os.environ:
                    os.environ[key] = val
    except Exception:
        # 防御性读取，不阻断主流程
        pass

    _DOTENV_LOADED = True
    return loaded


def resolve_device_url(name: str = "default") -> str:
    """
    根据设备名称解析对应的环境变量 URL。
    默认设备: CIO_DEVICE -> CIO_DEVICE_DEFAULT -> CIO_URL
    具名设备 (如 'power'): CIO_DEVICE_POWER
    """
    # 确保本级目录的 .env 已加载
    if not _DOTENV_LOADED:
        load_local_dotenv()

    norm_name = (name or "default").strip()
    if norm_name.lower() in ("default", ""):
        url = (
            os.environ.get("CIO_DEVICE")
            or os.environ.get("CIO_DEVICE_DEFAULT")
            or os.environ.get("CIO_URL")
        )
        if url:
            return url.strip()
        raise DeviceConfigError(
            "Default device is not configured. "
            "Please set 'CIO_DEVICE' in your environment or local .env file "
            '(e.g. CIO_DEVICE="i2c+serial://COM3?baud=2000000&reg_len=2").'
        )

    # 具名多设备检索
    env_key = f"CIO_DEVICE_{norm_name.upper()}"
    url = os.environ.get(env_key)
    if url:
        return url.strip()

    raise DeviceConfigError(
        f"Device '{norm_name}' is not configured. "
        f"Please set '{env_key}' in your environment or local .env file "
        f'(e.g. {env_key}="serial://COM4?baud=9600").'
    )


def _cleanup_all_devices() -> None:
    """进程退出时的 atexit 安全清理钩子，批量安全关闭所有已打开的硬件连接。"""
    with _DEVICE_LOCK:
        for dev_inst in list(_ACTIVE_DEVICES.values()):
            try:
                if hasattr(dev_inst, "close"):
                    dev_inst.close()
            except Exception:
                pass
        _ACTIVE_DEVICES.clear()


def close_all_devices() -> None:
    """显式关闭并清空所有当前已初始化的单例设备。"""
    _cleanup_all_devices()


def reset_devices() -> None:
    """重置单例设备池与环境变量加载状态（供测试或重新配置使用）。"""
    global _DOTENV_LOADED
    _cleanup_all_devices()
    _DOTENV_LOADED = False


def get_device(name: str = "default") -> Any:
    """
    获取或惰性初始化具名设备单例。
    对于同步使用场景，默认返回 .sync 包装器以支持直调总线方法。
    """
    global _CLEANUP_REGISTERED
    norm_key = (name or "default").strip().lower()

    with _DEVICE_LOCK:
        if not _CLEANUP_REGISTERED:
            atexit.register(_cleanup_all_devices)
            _CLEANUP_REGISTERED = True

        if norm_key in _ACTIVE_DEVICES:
            return _ACTIVE_DEVICES[norm_key]

        url = resolve_device_url(norm_key)
        transport = connect(url)
        # 默认提供同步视图包装，以实现无 with 直调的总线体验
        sync_dev = transport.sync if hasattr(transport, "sync") else transport
        _ACTIVE_DEVICES[norm_key] = sync_dev
        return sync_dev


class _LazyDeviceProxy:
    """
    全能惰性设备代理门面：
    - dev.read(...) / dev.write_reg(...) -> 自动转发给默认设备 (CIO_DEVICE)
    - dev["power"].write(...) -> 自动转发给具名设备 (CIO_DEVICE_POWER)
    - with dev: -> 兼容标准上下文管理器
    """

    def __getattr__(self, name: str) -> Any:
        target = get_device("default")
        return getattr(target, name)

    def __getitem__(self, name: str) -> Any:
        return get_device(name)

    def __enter__(self) -> Any:
        target = get_device("default")
        if hasattr(target, "__enter__"):
            return target.__enter__()
        return target

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        target = get_device("default")
        if hasattr(target, "__exit__"):
            return target.__exit__(exc_type, exc_val, exc_tb)
        return None

    def __repr__(self) -> str:
        with _DEVICE_LOCK:
            if "default" in _ACTIVE_DEVICES:
                return repr(_ACTIVE_DEVICES["default"])
        return "<LazyDevice: 'default' (not yet connected)>"


# 顶层唯一单例入口
dev = _LazyDeviceProxy()
