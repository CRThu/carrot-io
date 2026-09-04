"""
Unit tests for environment variable injection, local .env loading, and dev lazy singleton.
"""
import os
import tempfile
import pytest

import cio
from cio import dev, DeviceConfigError
from cio.core.env import (
    load_local_dotenv,
    resolve_device_url,
    get_device,
    reset_devices,
    close_all_devices,
    _cleanup_all_devices,
)


@pytest.fixture(autouse=True)
def clean_env():
    """Reset device singletons and clean up test environment variables."""
    reset_devices()
    old_env = os.environ.copy()
    for key in list(os.environ.keys()):
        if key.startswith("CIO_DEVICE") or key == "CIO_URL":
            del os.environ[key]
    yield
    reset_devices()
    os.environ.clear()
    os.environ.update(old_env)


def test_missing_config_raises_device_config_error():
    with pytest.raises(DeviceConfigError) as exc_info:
        resolve_device_url("default")
    assert "Default device is not configured" in str(exc_info.value)
    assert "CIO_DEVICE" in str(exc_info.value)

    with pytest.raises(DeviceConfigError) as exc_info2:
        resolve_device_url("power")
    assert "Device 'power' is not configured" in str(exc_info2.value)
    assert "CIO_DEVICE_POWER" in str(exc_info2.value)

    # Subscript access on dev with unconfigured name
    with pytest.raises(DeviceConfigError) as exc_info3:
        _ = dev["unconfigured_relay"]
    assert "CIO_DEVICE_UNCONFIGURED_RELAY" in str(exc_info3.value)


def test_env_resolution_single_and_multi_devices():
    os.environ["CIO_DEVICE"] = "tcp://127.0.0.1:5001"
    os.environ["CIO_DEVICE_POWER"] = "tcp://127.0.0.1:5002"
    os.environ["CIO_DEVICE_SCOPE"] = "tcp://127.0.0.1:5003"

    assert resolve_device_url("default") == "tcp://127.0.0.1:5001"
    assert resolve_device_url("") == "tcp://127.0.0.1:5001"
    assert resolve_device_url("power") == "tcp://127.0.0.1:5002"
    assert resolve_device_url("POWER") == "tcp://127.0.0.1:5002"
    assert resolve_device_url("Scope") == "tcp://127.0.0.1:5003"


def test_local_dotenv_parsing():
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as tmp:
        tmp.write("# Test .env configuration\n")
        tmp.write("CIO_DEVICE=\"tcp://127.0.0.1:9001\"\n")
        tmp.write("export CIO_DEVICE_POWER='tcp://127.0.0.1:9002'\n")
        tmp.write("   CIO_DEVICE_RELAY = tcp://127.0.0.1:9003  \n")
        tmp_name = tmp.name

    try:
        loaded = load_local_dotenv(dotenv_path=tmp_name, override=True)
        assert loaded["CIO_DEVICE"] == "tcp://127.0.0.1:9001"
        assert loaded["CIO_DEVICE_POWER"] == "tcp://127.0.0.1:9002"
        assert loaded["CIO_DEVICE_RELAY"] == "tcp://127.0.0.1:9003"

        assert os.environ["CIO_DEVICE"] == "tcp://127.0.0.1:9001"
        assert resolve_device_url("power") == "tcp://127.0.0.1:9002"
        assert resolve_device_url("relay") == "tcp://127.0.0.1:9003"
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def test_dev_lazy_proxy_and_getitem():
    os.environ["CIO_DEVICE"] = "mock://dut"
    os.environ["CIO_DEVICE_POWER"] = "mock://power"

    # Direct top-level import `from cio import dev`
    # Default device write/read
    dev.write(b"HELLO_DUT")
    default_inst = get_device("default")
    assert default_inst.tx_history == [b"HELLO_DUT"]

    # Properties pass-through
    assert dev.is_open is True
    dev.trace = False
    assert dev.trace is False
    assert repr(dev).startswith("<")

    # dev["power"] dictionary subscript access for multi-device setup
    pwr = dev["power"]
    assert pwr is not None
    assert pwr is get_device("power")
    assert pwr is not default_inst
    dev["power"].write(b"SET_V 3.3")
    assert pwr.tx_history == [b"SET_V 3.3"]

    # with dev context manager support
    with dev as context_dev:
        assert context_dev is not None
        context_dev.write(b"IN_CONTEXT")
        assert default_inst.tx_history == [b"HELLO_DUT", b"IN_CONTEXT"]


def test_safe_cleanup_and_atexit():
    os.environ["CIO_DEVICE"] = "mock://dut"
    os.environ["CIO_DEVICE_POWER"] = "mock://power"

    dut_inst = dev["default"]
    pwr_inst = dev["power"]
    dut_inst.open()
    pwr_inst.open()
    assert dut_inst.is_open
    assert pwr_inst.is_open

    # Trigger atexit handler
    _cleanup_all_devices()
    assert not dut_inst.is_open
    assert not pwr_inst.is_open

    # Double cleanup is completely safe
    close_all_devices()


@pytest.mark.asyncio
async def test_dev_async_context_and_raw_access():
    os.environ["CIO_DEVICE"] = "mock://async_dut"

    raw_inst = dev.raw
    assert not raw_inst.is_open

    async with dev as async_d:
        assert async_d.is_open
        await async_d.write(b"ASYNC_MSG")

    assert not raw_inst.is_open
    assert raw_inst.tx_history == [b"ASYNC_MSG"]


def test_lazy_device_proxy_setattr_passthrough(monkeypatch):
    """Verify that setting attributes on cio.dev updates the underlying default device."""
    monkeypatch.setenv("CIO_DEVICE", "mock://dut_setattr")
    dev.trace = True
    assert dev.raw.trace is True
    dev.timeout = 4.2
    assert dev.raw.timeout == 4.2


def test_device_pool_close_device_and_clear_history(monkeypatch):
    """Verify close_device() / dev.close() and clear_history() manage singleton pool cleanly."""
    monkeypatch.setenv("CIO_DEVICE", "mock://dut_lifecycle")
    from cio.core.env import _ACTIVE_DEVICES, close_device, clear_history

    reset_devices()

    # Access device to create in pool
    dev.write(b"INIT_CMD")
    assert "default" in _ACTIVE_DEVICES
    assert len(dev.history()) >= 1

    # Clear history via facade
    dev.clear_history()
    assert len(dev.history()) == 0

    # Explicit close_device unregisters it
    dev.close()
    assert "default" not in _ACTIVE_DEVICES

    # Re-accessing recreates clean instance
    dev.write(b"NEW_SESSION")
    assert "default" in _ACTIVE_DEVICES
    close_all_devices()
    assert "default" not in _ACTIVE_DEVICES


