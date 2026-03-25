"""Shared pytest fixtures for human-interface tests."""

from __future__ import annotations

import os

# Ensure required env vars are set for tests that import ArchitectConfig.
os.environ.setdefault("ARCHITECT_PG_PASSWORD", "test_password")

import pytest

from human_interface.config import HumanInterfaceConfig
from human_interface.ws_manager import WebSocketManager


@pytest.fixture
def config() -> HumanInterfaceConfig:
    """Return the default service configuration."""
    return HumanInterfaceConfig()


@pytest.fixture
def ws_manager() -> WebSocketManager:
    """Return a fresh WebSocketManager."""
    return WebSocketManager()
