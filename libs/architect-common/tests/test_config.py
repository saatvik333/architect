"""Tests for configuration schema."""

from urllib.parse import urlparse

from architect_common.config import ArchitectConfig, PostgresConfig, RedisConfig


def test_postgres_dsn() -> None:
    cfg = PostgresConfig(
        host="db.example.com",
        port=5432,
        database="test_db",
        user="test_user",
        password="secret",
    )
    parsed = urlparse(cfg.dsn)
    assert parsed.hostname == "db.example.com"
    assert parsed.path == "/test_db"
    assert parsed.username == "test_user"


def test_redis_url_no_password() -> None:
    cfg = RedisConfig(host="localhost", port=6379, db=0, password="")
    assert cfg.url == "redis://localhost:6379/0"


def test_default_config_loads() -> None:
    cfg = ArchitectConfig()
    assert cfg.environment == "dev"
    assert cfg.log_level == "INFO"
    assert cfg.postgres.host == "localhost"
    assert cfg.redis.port == 6379
    assert cfg.temporal.namespace == "architect"
