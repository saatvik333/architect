"""Shared pytest fixtures for security-immune tests."""

from __future__ import annotations

import os

# Ensure required env vars are set for tests that import ArchitectConfig.
os.environ.setdefault("ARCHITECT_PG_PASSWORD", "test_password")

from unittest.mock import AsyncMock

import pytest

from security_immune.config import SecurityImmuneConfig
from security_immune.scanners.code_scanner import CodeScanner
from security_immune.scanners.dependency_auditor import DependencyAuditor
from security_immune.scanners.policy_enforcer import PolicyEnforcer
from security_immune.scanners.prompt_validator import PromptValidator
from security_immune.scanners.runtime_monitor import RuntimeMonitor


@pytest.fixture
def config() -> SecurityImmuneConfig:
    """Return the default service configuration."""
    return SecurityImmuneConfig()


@pytest.fixture
def code_scanner(config: SecurityImmuneConfig) -> CodeScanner:
    """Return a fresh CodeScanner."""
    return CodeScanner(config)


@pytest.fixture
def dependency_auditor(config: SecurityImmuneConfig) -> DependencyAuditor:
    """Return a fresh DependencyAuditor."""
    return DependencyAuditor(config)


@pytest.fixture
def prompt_validator() -> PromptValidator:
    """Return a fresh PromptValidator."""
    return PromptValidator()


@pytest.fixture
def runtime_monitor() -> RuntimeMonitor:
    """Return a fresh RuntimeMonitor."""
    return RuntimeMonitor()


@pytest.fixture
def policy_enforcer(config: SecurityImmuneConfig) -> PolicyEnforcer:
    """Return a fresh PolicyEnforcer."""
    return PolicyEnforcer(config)


@pytest.fixture
def mock_publisher() -> AsyncMock:
    """Return a mock EventPublisher."""
    publisher = AsyncMock()
    publisher.publish = AsyncMock()
    publisher.connect = AsyncMock()
    publisher.close = AsyncMock()
    return publisher
