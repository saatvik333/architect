"""Tests for error hierarchy."""

from architect_common.errors import (
    ArchitectError,
    LedgerVersionNotFoundError,
    OptimisticConcurrencyError,
    SandboxError,
    SandboxSecurityError,
    SandboxTimeoutError,
)


class TestErrorHierarchy:
    def test_base_error(self) -> None:
        err = ArchitectError("test", details={"key": "val"})
        assert str(err) == "test"
        assert err.details == {"key": "val"}

    def test_ledger_error_is_architect_error(self) -> None:
        err = LedgerVersionNotFoundError("missing")
        assert isinstance(err, ArchitectError)

    def test_occ_error_is_architect_error(self) -> None:
        err = OptimisticConcurrencyError("conflict")
        assert isinstance(err, ArchitectError)

    def test_sandbox_error_hierarchy(self) -> None:
        err = SandboxSecurityError("blocked")
        assert isinstance(err, SandboxError)
        assert isinstance(err, ArchitectError)

    def test_sandbox_timeout(self) -> None:
        err = SandboxTimeoutError("too slow", details={"timeout": 60})
        assert err.details["timeout"] == 60
