"""Tests for database engine configuration."""

from __future__ import annotations

import pytest

from pitwall.db.engine import database_url_from_env


def test_database_url_from_env_loads_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://pitwall:pitwall@localhost/pitwall")

    assert database_url_from_env() == "postgresql+psycopg://pitwall:pitwall@localhost/pitwall"


def test_database_url_from_env_has_helpful_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        database_url_from_env(load_dotenv_file=False)
