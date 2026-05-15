"""Tests for ``/health`` and ``/ready``."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pitwall import __version__
from pitwall.api import main as api_main
from pitwall.api.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_health_returns_200_with_version(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body == {"status": "ok", "version": __version__}


def test_ready_returns_200_when_database_check_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_main, "_database_is_ready", lambda: True)

    r = TestClient(create_app()).get("/ready")

    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready_returns_503_when_database_check_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api_main, "_database_is_ready", lambda: False)

    r = TestClient(create_app()).get("/ready")

    assert r.status_code == 503
    assert "Database is not ready" in r.json()["detail"]


def test_unknown_route_returns_404(client: TestClient) -> None:
    r = client.get("/api/v1/this-does-not-exist")
    assert r.status_code == 404


def test_unhandled_exception_returns_json_500() -> None:
    app = create_app()

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("boom")

    with TestClient(app, raise_server_exceptions=False) as client:
        r = client.get("/boom")

    assert r.status_code == 500
    assert r.json() == {"detail": "Internal server error."}
