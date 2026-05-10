"""Tests for ``/health`` and ``/ready``."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pitwall import __version__
from pitwall.api.main import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def test_health_returns_200_with_version(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body == {"status": "ok", "version": __version__}


def test_ready_returns_200(client: TestClient) -> None:
    # V1: process-up is enough. Day 3+ will return 503 when the DB or
    # the model is not ready; that test will live next to this one.
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_unknown_route_returns_404(client: TestClient) -> None:
    r = client.get("/api/v1/this-does-not-exist")
    assert r.status_code == 404
