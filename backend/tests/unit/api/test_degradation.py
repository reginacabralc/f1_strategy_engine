"""Tests for GET /api/v1/degradation."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from pitwall.api.dependencies import get_degradation_repository
from pitwall.api.main import create_app
from pitwall.repositories.degradation import CoefficientRow, InMemoryDegradationRepository


def _make_client(rows: dict[tuple[str, str], CoefficientRow] | None = None) -> TestClient:
    app = create_app()
    repo = InMemoryDegradationRepository(rows or {})
    app.dependency_overrides[get_degradation_repository] = lambda: repo
    return TestClient(app)


_MONACO_MEDIUM = CoefficientRow(
    circuit_id="monaco",
    compound="MEDIUM",
    a=74_500.0,
    b=120.0,
    c=5.0,
    r_squared=0.82,
    n_laps=412,
)


# ---------------------------------------------------------------------------
# 404 cases
# ---------------------------------------------------------------------------


def test_degradation_404_when_no_coefficient_in_db() -> None:
    client = _make_client()
    r = client.get("/api/v1/degradation", params={"circuit": "monaco", "compound": "MEDIUM"})
    assert r.status_code == 404


def test_degradation_404_for_unknown_circuit() -> None:
    client = _make_client({("monaco", "MEDIUM"): _MONACO_MEDIUM})
    r = client.get("/api/v1/degradation", params={"circuit": "spa", "compound": "MEDIUM"})
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# 422 — invalid compound
# ---------------------------------------------------------------------------


def test_degradation_400_for_invalid_compound() -> None:
    client = _make_client()
    r = client.get("/api/v1/degradation", params={"circuit": "monaco", "compound": "SUPER_SOFT"})
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# 200 — shape and values
# ---------------------------------------------------------------------------


def test_degradation_200_returns_curve_shape() -> None:
    client = _make_client({("monaco", "MEDIUM"): _MONACO_MEDIUM})
    r = client.get("/api/v1/degradation", params={"circuit": "monaco", "compound": "MEDIUM"})
    assert r.status_code == 200

    body = r.json()
    assert body["circuit_id"] == "monaco"
    assert body["compound"] == "MEDIUM"
    assert "coefficients" in body
    assert "a" in body["coefficients"]
    assert "b" in body["coefficients"]
    assert "c" in body["coefficients"]
    assert "r_squared" in body
    assert "n_samples" in body
    assert "sample_points" in body


def test_degradation_coefficient_values_correct() -> None:
    client = _make_client({("monaco", "MEDIUM"): _MONACO_MEDIUM})
    body = client.get(
        "/api/v1/degradation", params={"circuit": "monaco", "compound": "MEDIUM"}
    ).json()

    assert body["coefficients"]["a"] == pytest.approx(74_500.0)
    assert body["coefficients"]["b"] == pytest.approx(120.0)
    assert body["coefficients"]["c"] == pytest.approx(5.0)
    assert body["r_squared"] == pytest.approx(0.82)
    assert body["n_samples"] == 412


def test_degradation_compound_is_case_insensitive() -> None:
    client = _make_client({("monaco", "MEDIUM"): _MONACO_MEDIUM})
    r = client.get("/api/v1/degradation", params={"circuit": "monaco", "compound": "medium"})
    assert r.status_code == 200
    assert r.json()["compound"] == "MEDIUM"


def test_degradation_circuit_is_case_insensitive() -> None:
    client = _make_client({("monaco", "MEDIUM"): _MONACO_MEDIUM})
    r = client.get("/api/v1/degradation", params={"circuit": "MONACO", "compound": "MEDIUM"})
    assert r.status_code == 200


@pytest.mark.parametrize("compound", ["SOFT", "MEDIUM", "HARD", "INTER", "WET"])
def test_degradation_accepts_all_valid_compounds(compound: str) -> None:
    row = CoefficientRow(
        circuit_id="monaco",
        compound=compound,
        a=74_000.0,
        b=100.0,
        c=4.0,
        r_squared=0.75,
        n_laps=200,
    )
    client = _make_client({("monaco", compound): row})
    r = client.get("/api/v1/degradation", params={"circuit": "monaco", "compound": compound})
    assert r.status_code == 200
