"""Tests for configuration schema."""

from architect_common.config import ArchitectConfig, PostgresConfig, RedisConfig


def test_postgres_dsn() -> None:
    cfg = PostgresConfig(
        host="db.example.com",
        port=5432,
        database="test_db",
        user="test_user",
        password="secret",  # type: ignore[arg-type]
    )
    assert "db.example.com" in cfg.dsn
    assert "test_db" in cfg.dsn
    assert "test_user" in cfg.dsn


def test_redis_url_no_password() -> None:
    cfg = RedisConfig(host="localhost", port=6379, db=0, password="")  # type: ignore[arg-type]
    assert cfg.url == "redis://localhost:6379/0"


def test_default_config_loads() -> None:
    cfg = ArchitectConfig()
    assert cfg.environment == "dev"
    assert cfg.log_level == "INFO"
    assert cfg.postgres.host == "localhost"
    assert cfg.redis.port == 6379
    assert cfg.temporal.namespace == "architect"
