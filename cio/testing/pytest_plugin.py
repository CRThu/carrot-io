"""
Pytest marks plugin for hardware and loopback testing.
"""
from __future__ import annotations

import pytest


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "hardware: mark test to require real physical hardware device")
    config.addinivalue_line("markers", "loopback: mark test to require hardware loopback cable")
