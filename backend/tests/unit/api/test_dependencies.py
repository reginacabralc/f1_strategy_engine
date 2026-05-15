"""Tests for FastAPI dependency provider selection."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from pitwall.api import dependencies
from pitwall.repositories.degradation import InMemoryDegradationRepository
from pitwall.repositories.events import InMemorySessionEventLoader
from pitwall.repositories.sessions import InMemorySessionRepository
from pitwall.repositories.sql import (
    SqlDegradationRepository,
    SqlSessionEventLoader,
    SqlSessionRepository,
)


class _FakeEngine:
    pass


def _fake_create_db_engine(database_url: str | None = None) -> _FakeEngine:
    return _FakeEngine()


@pytest.fixture(autouse=True)
def clear_dependency_caches() -> Iterator[None]:
    dependencies._sql_engine_if_configured.cache_clear()
    dependencies.get_session_repository.cache_clear()
    dependencies.get_degradation_repository.cache_clear()
    dependencies.get_event_loader.cache_clear()
    yield
    dependencies._sql_engine_if_configured.cache_clear()
    dependencies.get_session_repository.cache_clear()
    dependencies.get_degradation_repository.cache_clear()
    dependencies.get_event_loader.cache_clear()


def test_default_providers_fall_back_to_memory_when_database_url_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(dependencies, "database_url_from_env", lambda: None)

    assert isinstance(dependencies.get_session_repository(), InMemorySessionRepository)
    assert isinstance(dependencies.get_degradation_repository(), InMemoryDegradationRepository)
    assert isinstance(dependencies.get_event_loader(), InMemorySessionEventLoader)


def test_providers_use_sql_when_database_url_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://pitwall:pitwall@db:5432/pitwall")
    monkeypatch.setattr(dependencies, "create_db_engine", _fake_create_db_engine)

    assert isinstance(dependencies.get_session_repository(), SqlSessionRepository)
    assert isinstance(dependencies.get_degradation_repository(), SqlDegradationRepository)
    assert isinstance(dependencies.get_event_loader(), SqlSessionEventLoader)


def test_sql_providers_share_one_engine_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[Any] = []

    def fake_create_db_engine(database_url: str | None = None) -> _FakeEngine:
        engine = _FakeEngine()
        calls.append(engine)
        return engine

    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://pitwall:pitwall@db:5432/pitwall")
    monkeypatch.setattr(dependencies, "create_db_engine", fake_create_db_engine)

    dependencies.get_session_repository()
    dependencies.get_degradation_repository()
    dependencies.get_event_loader()

    assert len(calls) == 1
